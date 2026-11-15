"""Project translation memory: explicit exact-match reuse as unapproved candidates."""

import asyncio
import json
from hashlib import sha256

import httpx
import pytest

from unitytranslator.application import ApplicationSession
from unitytranslator.dialogue_context import DialogueContextStore
from unitytranslator.domain import GenerationProfile, TextUnitDraft
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.portable import PortableService
from unitytranslator.providers import LocalProvider
from unitytranslator.repository import ProjectRepository, is_memory_metadata
from unitytranslator.runtime_export import export_selected_runtime
from unitytranslator.source_contracts import SourceDescriptor
from unitytranslator.translation_memory import apply, dialogue_digest, preview


def unit(
    key: str,
    text: str = "Start",
    *,
    category: str = "UI",
    context: str = "",
    source_file: str = "synthetic.assets",
) -> TextUnitDraft:
    return TextUnitDraft(
        key,
        key,
        source_file,
        1,
        "en",
        text,
        sha256(text.encode()).hexdigest(),
        category,
        context,
    )


@pytest.fixture
def repo(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repository:
        yield repository


def approve(repo, unit_id, text):
    version = row(repo, unit_id)["version"]
    repo.edit(unit_id, version, text)
    repo.approve(unit_id, row(repo, unit_id)["version"])


def row(repo, unit_id):
    return next(item for item in repo.page(search="") if item["unit_id"] == unit_id)


def snapshot(repo):
    """Every persisted row that reuse could touch, keyed by table."""
    return {
        table: [tuple(r) for r in repo.db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        for table in (
            "work_items",
            "translation_revisions",
            "editor_drafts",
            "policy_impacts",
            "source_snapshots",
            "text_units",
            "source_revisions",
        )
    }


def work(repo, unit_id):
    return tuple(repo.db.execute("SELECT * FROM work_items WHERE unit_id=?", (unit_id,)).fetchone())


def memory_revisions(repo):
    return [
        dict(r)
        for r in repo.db.execute("SELECT * FROM translation_revisions ORDER BY rowid")
        if is_memory_metadata(json.loads(r["metadata_json"]))
    ]


def test_exact_keys_produce_unapproved_candidates_with_origin(repo):
    repo.ingest(
        [
            unit("UI/donor"),
            unit("UI/target"),
            unit("UI/context", context="menu"),
            unit("UI/category", category="Dialogue"),
            unit("UI/space", "Start "),
            unit("UI/case", "start"),
            unit("UI/lonely", "Quit"),
        ],
        {},
    )
    repo.ingest(
        [unit("Lines/0", source_file="lines.txt")],
        {},
        source=SourceDescriptor(
            "lines-v1:lines.txt",
            "krypta-textassets",
            "synthetic",
            "v1",
            "lines.txt",
            -1,
            "en",
            format_rules="literal-lines-v1",
        ),
    )
    approve(repo, "UI/donor", "Başla")
    before = {
        u: work(repo, u)
        for u in (
            "UI/context",
            "UI/category",
            "UI/space",
            "UI/case",
            "UI/lonely",
            "Lines/0",
            "UI/donor",
        )
    }
    result = preview(repo)
    assert result["candidates"] == result["current"] == 1 and result["history"] == 0
    assert result["matches"] == 1 and result["conflicts"] == 0
    assert result["donors"] == {"approved": 1, "model": 0}
    assert result["samples"] == [
        {"key": "UI/target", "source": "Start", "text": "Başla", "donor_key": "UI/donor"}
    ]
    assert apply(repo, result, user_action=True) == 1
    target = row(repo, "UI/target")
    assert target["translation"] == "Başla" and target["status"] == "translated"
    assert target["translation_origin"] == "translation_memory"
    assert target["memory_donor_key"] == "UI/donor"
    work_row = repo.db.execute("SELECT * FROM work_items WHERE unit_id='UI/target'").fetchone()
    assert work_row["approved_translation"] is None and work_row["approved_source"] is None
    [revision] = memory_revisions(repo)
    metadata = json.loads(revision["metadata_json"])
    assert revision["origin"] == "import"
    assert metadata["origin_detail"] == "translation_memory"
    assert metadata["donor_kind"] == "approved" and metadata["donor_unit"] == "UI/donor"
    assert metadata["donor_revision"] == row(repo, "UI/donor")["translation_revision"]
    assert len(metadata["key_digest"]) == 64 and metadata["human_approved"] is False
    history = repo.history("UI/target")["revisions"]
    assert history[0]["id"] == revision["id"]
    assert {u: work(repo, u) for u in before} == before


def test_dialogue_digest_is_part_of_the_key(repo, monkeypatch):
    repo.ingest([unit("D/donor"), unit("D/same"), unit("D/other"), unit("D/none")], {})
    approve(repo, "D/donor", "Başla")

    def window(speaker, source):
        return {
            "speaker": speaker,
            "references": [
                {"offset": 1, "unit_id": "ignored-" + speaker, "speaker": "b", "source": source},
            ],
            "source_hash": sha256(b"Start").hexdigest(),
        }

    windows = {
        "D/donor": window("a", "Yes."),
        "D/same": window("a", "Yes."),
        "D/other": window("a", "No."),
    }
    monkeypatch.setattr(
        DialogueContextStore,
        "verified_windows",
        lambda self, hashes: {k: v for k, v in windows.items() if k in hashes},
    )
    result = preview(repo)
    assert [a["unit_id"] for a in result["actions"]] == ["D/same"]
    # Record IDs of neighbours are not meaning; their speaker and source are.
    assert dialogue_digest(windows["D/donor"]) == dialogue_digest(
        {
            **windows["D/donor"],
            "references": [{**windows["D/donor"]["references"][0], "unit_id": "elsewhere"}],
        }
    )
    assert dialogue_digest(windows["D/donor"]) != dialogue_digest(windows["D/other"])


def test_disagreeing_donors_report_a_conflict_and_add_nothing(repo):
    repo.ingest(
        [
            unit("C/a"),
            unit("C/b"),
            unit("C/target"),
            unit("C/other", "Quit"),
            unit("C/other-target", "Quit"),
        ],
        {},
    )
    approve(repo, "C/a", "Başla")
    approve(repo, "C/b", "Başlat")
    approve(repo, "C/other", "Çık")
    result = preview(repo)
    assert result["conflicts"] == 1 and result["conflict_records"] == 1
    assert result["conflict_samples"] == [{"source": "Start", "texts": ["Başla", "Başlat"]}]
    assert [a["unit_id"] for a in result["actions"]] == ["C/other-target"]
    apply(repo, result, user_action=True)
    assert row(repo, "C/target")["translation"] is None


def test_approved_records_drafts_and_approvals_are_untouched(repo):
    repo.ingest([unit(f"U/{i}") for i in range(6)], {})
    approve(repo, "U/0", "Başla")
    approve(repo, "U/1", "Başla")
    approve(repo, "U/2", "Başlangıç")  # Approved with other text: kept, never a target.
    PolicyStore(repo).set_glossary(
        [GlossaryRule(source="Start", target="Başla", kind="preferred_translation")]
    )
    # Policy impacts mark every approval for re-review; impacted approvals are not donors.
    assert preview(repo)["matches"] == 0
    for unit_id in ("U/0", "U/1", "U/2"):
        repo.approve(unit_id, row(repo, unit_id)["version"])
    EditorDraftStore(repo).put(
        "U/3", row(repo, "U/3")["source_revision"], row(repo, "U/3")["version"], "Taslak"
    )
    repo.edit("U/4", row(repo, "U/4")["version"], "Başlat")
    untouched = ("U/0", "U/1", "U/2", "U/3", "U/4")
    before = {u: work(repo, u) for u in untouched}
    drafts = [tuple(r) for r in repo.db.execute("SELECT * FROM editor_drafts")]
    revisions = [tuple(r) for r in repo.db.execute("SELECT * FROM translation_revisions")]
    result = preview(repo)
    assert result["conflicts"] == 1  # Approved donors disagree: Başla / Başlangıç.
    assert result["skipped"]["draft"] == 1 and result["skipped"]["translated"] == 1
    assert result["candidates"] == 0
    approve(repo, "U/2", "Başla")
    before["U/2"] = work(repo, "U/2")
    revisions = [tuple(r) for r in repo.db.execute("SELECT * FROM translation_revisions")]
    result = preview(repo)
    assert [a["unit_id"] for a in result["actions"]] == ["U/5"]
    apply(repo, result, user_action=True)
    assert {u: work(repo, u) for u in untouched} == before
    assert [tuple(r) for r in repo.db.execute("SELECT * FROM editor_drafts")] == drafts
    after = [tuple(r) for r in repo.db.execute("SELECT * FROM translation_revisions")]
    assert after[: len(revisions)] == revisions and len(after) == len(revisions) + 1


def test_current_unapproved_translation_keeps_current_and_gains_history(repo):
    repo.ingest([unit("H/donor"), unit("H/target")], {})
    approve(repo, "H/donor", "Başla")
    repo.edit("H/target", 0, "Başlat")
    current = work(repo, "H/target")
    assert preview(repo)["skipped"]["translated"] == 1
    result = preview(repo, include_translated=True)
    assert result["history"] == 1 and result["current"] == 0
    apply(repo, result, user_action=True)
    assert work(repo, "H/target") == current  # Version, status and current text unchanged.
    assert row(repo, "H/target")["translation"] == "Başlat"
    [revision] = memory_revisions(repo)
    repeat = preview(repo, include_translated=True)
    assert repeat["candidates"] == 0 and repeat["skipped"]["already_offered"] == 1
    # Only an explicit selection makes it current, and it stays unapproved.
    assert repo.select_candidate("H/target", current[-1], revision["id"])
    assert row(repo, "H/target")["translation"] == "Başla"
    assert row(repo, "H/target")["status"] == "translated"
    assert row(repo, "H/target")["translation_origin"] == "translation_memory"


def test_memory_candidates_never_chain_as_donors(repo):
    repo.ingest([unit("M/a"), unit("M/b"), unit("M/c")], {})
    approve(repo, "M/a", "Başla")
    apply(repo, preview(repo), user_action=True)
    assert row(repo, "M/b")["translation"] == "Başla"
    # Approving a reused candidate still does not make it a donor.
    repo.approve("M/b", row(repo, "M/b")["version"])
    repo.approve("M/c", row(repo, "M/c")["version"])
    repo.ingest([unit("M/a", "Begin"), unit("M/b"), unit("M/c"), unit("M/d")], {})
    assert preview(repo)["matches"] == 0


def test_apply_requires_user_action_unchanged_state_and_is_idempotent(repo):
    repo.ingest([unit("I/donor"), unit("I/a"), unit("I/b")], {})
    approve(repo, "I/donor", "Başla")
    result = preview(repo)
    with pytest.raises(ValueError, match="explicit user action"):
        apply(repo, result, user_action=False)
    with pytest.raises(ValueError, match="explicit user action"):
        apply(repo, result, user_action="yes")
    state = snapshot(repo)
    repo.edit("I/a", row(repo, "I/a")["version"], "Başlat")  # A relevant change.
    with pytest.raises(ValueError, match="matches changed"):
        apply(repo, result, user_action=True)
    result = preview(repo)
    assert apply(repo, result, user_action=True) == 1
    state = snapshot(repo)
    with pytest.raises(ValueError, match="matches changed"):
        apply(repo, result, user_action=True)
    again = preview(repo, include_translated=True)
    assert again["candidates"] == 1  # I/a: a history candidate beside its own edit.
    apply(repo, again, user_action=True)
    state = snapshot(repo)
    final = preview(repo, include_translated=True)
    assert final["candidates"] == 0
    assert final["skipped"]["already_offered"] == 1 and final["skipped"]["same_text"] == 1
    assert snapshot(repo) == state


def test_stored_candidate_is_reused_only_with_identical_provenance_and_checks(repo, monkeypatch):
    def flip(units):
        # A source change and its reversal leave the record without a current translation.
        repo.ingest([*units, unit("V/t", "Begin")], {})
        repo.ingest([*units, unit("V/t")], {})
        assert row(repo, "V/t")["translation_revision"] is None

    def current_metadata():
        revision = row(repo, "V/t")["translation_revision"]
        found = repo.db.execute(
            "SELECT metadata_json FROM translation_revisions WHERE id=?", (revision,)
        ).fetchone()
        return revision, json.loads(found[0])

    repo.ingest([unit("V/b"), unit("V/t")], {})
    approve(repo, "V/b", "Başla")
    apply(repo, preview(repo), user_action=True)
    [first] = memory_revisions(repo)
    # Unchanged provenance: the stored revision is reused, nothing new is added.
    flip([unit("V/b")])
    result = preview(repo)
    assert result["current"] == 1
    apply(repo, result, user_action=True)
    assert current_metadata()[0] == first["id"] and len(memory_revisions(repo)) == 1
    # Issues stored under older review checks are never reused.
    monkeypatch.setattr("unitytranslator.repository.REVIEW_CHECKS_VERSION", "checks-next")
    flip([unit("V/b")])
    apply(repo, preview(repo), user_action=True)
    revision, metadata = current_metadata()
    assert revision != first["id"] and metadata["review_checks_version"] == "checks-next"
    monkeypatch.undo()
    # A new donor wins (lowest record ID); the old revision names a stale donor.
    repo.ingest([unit("V/a"), unit("V/b"), unit("V/t")], {})
    approve(repo, "V/a", "Başla")
    flip([unit("V/a"), unit("V/b")])
    result = preview(repo)
    assert result["current"] == 1 and result["actions"][0]["metadata"]["donor_unit"] == "V/a"
    apply(repo, result, user_action=True)
    revision, metadata = current_metadata()
    assert revision != first["id"] and metadata["donor_unit"] == "V/a"
    assert metadata["donor_key"] == "V/a"
    assert metadata["donor_revision"] == row(repo, "V/a")["translation_revision"]
    assert (
        metadata["review_checks_version"]
        == json.loads(first["metadata_json"])["review_checks_version"]
    )
    assert row(repo, "V/t")["status"] == "translated"
    stored = [r["id"] for r in memory_revisions(repo)]
    assert len(stored) == 3 and first["id"] in stored  # Earlier candidates stay in history.
    # Idempotent: the same preview cannot be applied twice and a new one adds nothing.
    state = snapshot(repo)
    with pytest.raises(ValueError, match="matches changed"):
        apply(repo, result, user_action=True)
    repeat = preview(repo, include_translated=True)
    assert repeat["candidates"] == 0 and repeat["skipped"]["same_text"] == 1
    assert snapshot(repo) == state


def test_history_candidate_with_stale_donor_is_offered_again(repo):
    repo.ingest([unit("W/b"), unit("W/t")], {})
    approve(repo, "W/b", "Başla")
    repo.edit("W/t", 0, "Başlat")
    apply(repo, preview(repo, include_translated=True), user_action=True)
    assert preview(repo, include_translated=True)["skipped"]["already_offered"] == 1
    repo.ingest([unit("W/a"), unit("W/b"), unit("W/t")], {})
    approve(repo, "W/a", "Başla")
    result = preview(repo, include_translated=True)
    assert result["history"] == 1 and result["actions"][0]["metadata"]["donor_unit"] == "W/a"
    apply(repo, result, user_action=True)
    assert {json.loads(r["metadata_json"])["donor_unit"] for r in memory_revisions(repo)} == {
        "W/a",
        "W/b",
    }
    assert row(repo, "W/t")["translation"] == "Başlat"
    assert preview(repo, include_translated=True)["skipped"]["already_offered"] == 1


@pytest.mark.parametrize("change", ["approve", "draft", "donor", "source", "queue"])
def test_preview_token_changes_with_every_relevant_state(repo, change):
    repo.ingest([unit("T/donor"), unit("T/target"), unit("T/next")], {})
    approve(repo, "T/donor", "Başla")
    result = preview(repo)
    if change == "approve":
        approve(repo, "T/target", "Başlat")
    elif change == "draft":
        EditorDraftStore(repo).put(
            "T/target",
            row(repo, "T/target")["source_revision"],
            row(repo, "T/target")["version"],
            "Taslak",
        )
    elif change == "donor":
        approve(repo, "T/next", "Başlangıç")
    elif change == "source":
        repo.ingest([unit("T/donor"), unit("T/target", "Begin"), unit("T/next")], {})
    else:
        JobStore(repo).create(
            ["T/target"],
            GenerationProfile(
                "lm-studio",
                "http://localhost:1234",
                "synthetic",
                8192,
            ),
        )
    assert preview(repo)["token"] != result["token"]
    state = snapshot(repo)
    with pytest.raises(ValueError, match="matches changed"):
        apply(repo, result, user_action=True)
    assert snapshot(repo) == state


def fake_provider(translations):
    def handler(request):
        payload = json.loads(request.content)
        user = json.loads(payload["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translations": [
                                        {"id": user["id"], "text": translations[user["source"]]}
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    return LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))


PROFILE = GenerationProfile("lm-studio", "http://localhost:1234", "synthetic", 8192)


def run_model(repo, units, translations, profile=PROFILE):
    job = JobStore(repo).create(units, profile)
    asyncio.run(TranslationJobService(repo, lambda _: fake_provider(translations)).run(job))


def test_model_donors_need_the_selected_profile_and_policies(repo):
    repo.ingest(
        [
            unit("P/model"),
            unit("P/target"),
            unit("P/x", "Quit"),
            unit("P/y", "Quit"),
            unit("P/z", "Quit"),
        ],
        {},
    )
    run_model(repo, ["P/model", "P/x"], {"Start": "Başla", "Quit": "Çık"})
    assert row(repo, "P/model")["status"] == "translated"
    selected = PROFILE.to_dict()
    assert preview(repo)["matches"] == 0  # Without a selected profile: approved donors only.
    other = {**selected, "temperature": 0.7}
    assert preview(repo, profile=other)["matches"] == 0
    with pytest.raises(ValueError, match="generation profile is invalid"):
        preview(repo, profile={"unknown": 1})
    result = preview(repo, profile=selected)
    assert {a["unit_id"] for a in result["actions"]} == {"P/target", "P/y", "P/z"}
    assert result["donors"] == {"approved": 0, "model": 2}
    metadata = result["actions"][0]["metadata"]
    assert metadata["donor_kind"] == "model" and metadata["donor_profile_fingerprint"]
    # An approved donor wins over a model donor with other text.
    approve(repo, "P/y", "Çıkış")
    result = preview(repo, profile=selected)
    quit_actions = [a for a in result["actions"] if a["text"] in ("Çık", "Çıkış")]
    assert [(a["unit_id"], a["text"]) for a in quit_actions] == [("P/z", "Çıkış")]
    assert result["conflicts"] == 0
    # A policy change after the model run removes model donors.
    PolicyStore(repo).set_styles({"default": "Short."})
    result = preview(repo, profile=selected)
    assert result["donors"] == {"approved": 0, "model": 0}  # P/y awaits policy re-review.
    repo.approve("P/y", row(repo, "P/y")["version"])
    result = preview(repo, profile=selected)
    assert result["donors"] == {"approved": 1, "model": 0}
    assert [a["unit_id"] for a in result["actions"]] == ["P/z"]
    # Model counts in the job report stay unchanged by reuse.
    apply(repo, result, user_action=True)
    assert (
        repo.db.execute(
            "SELECT count(*) FROM translation_revisions WHERE origin='model'"
        ).fetchone()[0]
        == 2
    )


def test_memory_candidates_are_never_exported_as_approved(repo, tmp_path):
    repo.ingest([unit("E/donor"), unit("E/target")], {"kind": "synthetic"})
    approve(repo, "E/donor", "Başla")
    apply(repo, preview(repo), user_action=True)
    exported = json.loads(PortableService(repo).export().read_text(encoding="utf-8"))
    target = next(u for u in exported["units"] if u["unit_id"] == "E/target")
    assert target["translation"]["approved"] is False
    assert target["translation"]["metadata"]["origin_detail"] == "translation_memory"
    item = row(repo, "E/target")
    with pytest.raises(ValueError, match="lacks current human approval"):
        export_selected_runtime(
            repo,
            [
                {
                    key: item[key]
                    for key in (
                        "unit_id",
                        "source_revision",
                        "translation_revision",
                        "version",
                    )
                }
            ],
        )


def run(session, command, data=None):
    return asyncio.run(session.dispatch(command, data or {}))


def test_session_commands_guard_preview_and_apply(tmp_path):
    session = ApplicationSession()
    with pytest.raises(ValueError, match="Open a project first"):
        run(session, "translation_memory_preview", {"project_id": "other"})
    game = tmp_path / "game"
    game.mkdir()
    opened = run(session, "open", {"game": str(game), "project": str(tmp_path / "project")})
    identity = {"project_id": opened["project_id"]}
    try:
        session.repo.ingest([unit("S/donor"), unit("S/target")], {})
        approve(session.repo, "S/donor", "Başla")
        session.extracting = True
        with pytest.raises(ValueError, match="Translation memory request project identity"):
            run(session, "translation_memory_preview", {"project_id": "other"})
        with pytest.raises(ValueError, match="before reusing translation memory"):
            run(session, "translation_memory_preview", identity)
        with pytest.raises(ValueError, match="before reusing translation memory"):
            run(session, "translation_memory_apply", identity)
        session.extracting = False
        with pytest.raises(ValueError, match="preview expired"):
            run(session, "translation_memory_apply", {**identity, "token": "x"})
        result = run(session, "translation_memory_preview", {**identity, "request_token": 7})
        assert "actions" not in result and result["request_token"] == 7
        assert result["candidates"] == 1 and result["project_id"] == opened["project_id"]
        with pytest.raises(ValueError, match="explicit user action"):
            run(session, "translation_memory_apply", {**identity, "token": result["token"]})
        # The failed attempt consumed the preview; a new preview is required.
        with pytest.raises(ValueError, match="preview expired"):
            run(
                session,
                "translation_memory_apply",
                {**identity, "token": result["token"], "user_action": True},
            )
        result = run(session, "translation_memory_preview", identity)
        applied = run(
            session,
            "translation_memory_apply",
            {**identity, "token": result["token"], "user_action": True},
        )
        assert applied["added"] == 1
        page = run(session, "page", {})
        target = next(r for r in page["rows"] if r["unit_id"] == "S/target")
        assert target["translation_origin"] == "translation_memory"
        assert target["status"] == "translated"
        history = run(session, "history", {"unit_id": "S/target"})
        assert is_memory_metadata(json.loads(history["revisions"][0]["metadata_json"]))
    finally:
        session.extracting = False
        asyncio.run(session.close())


def test_renpy_windows_join_the_key_and_block_contexts_stay_separate(repo):
    from unitytranslator.renpy_scripts import parse_scripts
    from unitytranslator.source_contracts import ReaderResult

    source = (
        'label start:\n    a "Hello."\n    b "Yes."\n    return\n'
        'label two:\n    a "Hello."\n    b "Yes."\n'
    )
    document = parse_scripts([("s.rpy", source.encode())], "a" * 64)
    reader = document.snapshot("game/s.rpy", "en")
    repo.ingest_reader_result(
        ReaderResult(
            (reader,),
            True,
            {
                "complete_source_set": True,
                "adapter_id": "renpy-scripts",
            },
        )
    )
    hashes = {u.unit_id: u.source_hash for u in reader.units}
    windows = DialogueContextStore(repo).verified_windows(hashes)
    assert set(windows) == set(hashes)
    hello = [u.unit_id for u in reader.units if u.source_text == "Hello."]
    assert dialogue_digest(windows[hello[0]]) == dialogue_digest(windows[hello[1]])
    approve(repo, hello[0], "Merhaba.")
    # Ren'Py dialogue context names its block, so equal lines in other blocks never match.
    assert preview(repo)["matches"] == 0


def test_failure_inside_apply_rolls_back_every_candidate(repo, monkeypatch):
    repo.ingest([unit("R/donor"), unit("R/a"), unit("R/b")], {})
    approve(repo, "R/donor", "Başla")
    result = preview(repo)
    state = snapshot(repo)
    calls = []
    original = ProjectRepository.candidate

    def failing(self, *args, **kwargs):
        calls.append(args[0])
        if len(calls) == 2:
            raise RuntimeError("injected")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ProjectRepository, "candidate", failing)
    with pytest.raises(RuntimeError, match="injected"):
        apply(repo, result, user_action=True)
    assert snapshot(repo) == state
