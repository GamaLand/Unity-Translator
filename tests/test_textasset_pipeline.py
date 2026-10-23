"""Shared queue/review/export integration with synthetic TextAsset payloads only."""

import asyncio
import base64
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import httpx
import pytest

from unitytranslator.domain import GenerationProfile
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.providers import LocalProvider, ProviderError
from unitytranslator.repository import ProjectRepository
from unitytranslator.review_selection import all_approval_preview
from unitytranslator.source_contracts import ReaderResult, SourceDescriptor, SourceSnapshot
from unitytranslator.textasset_export import export_payloads
from unitytranslator.textasset_layouts import parse_payload
from unitytranslator.validation import format_issues, mask


@pytest.fixture
def repo(tmp_path):
    game = tmp_path / "synthetic-game"
    game.mkdir()
    container = game / "shared.assets"
    container.write_bytes(b"synthetic container; no Unity or game assembly")
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repository:
        snapshots = []
        for index, raw in enumerate((b"< back\nNext", b"Other source\n\nLast\n"), 1):
            descriptor = SourceDescriptor(
                f"synthetic-{index}",
                "krypta-textassets",
                "synthetic",
                "subtitle-lines-v1",
                "shared.assets",
                index,
                "en",
                hash_file(container),
                "literal-lines-v1",
                f"Synthetic {index}",
                sha256(raw).hexdigest(),
            )
            document = parse_payload(raw, descriptor.schema_version)
            snapshots.append(
                SourceSnapshot(
                    descriptor,
                    document.drafts(descriptor),
                    {
                        "raw_base64": base64.b64encode(raw).decode("ascii"),
                    },
                )
            )
        repository.ingest_reader_result(
            ReaderResult(
                tuple(snapshots),
                True,
                {
                    "complete_source_set": True,
                    "fingerprints": {"shared.assets": hash_file(container)},
                    "coverage": [{"sources": 2}],
                    "outside_scope": ["Synthetic excluded area"],
                },
            )
        )
        yield repository


def first(repo):
    return next(row for row in repo.page() if row["source_text"] == "< back")


def approve(repo):
    row = first(repo)
    repo.edit(row["unit_id"], row["version"], "< geri")
    row = first(repo)
    repo.approve(row["unit_id"], row["version"])
    return first(repo)


def synthetic_runtime_profile(repo, monkeypatch):
    import unitytranslator.textasset_export as exporter

    profile = {
        "id": "synthetic",
        "unity_version": "synthetic",
        "assembly": {"sha256": "a" * 64},
        "sources": [
            {
                "container": "shared.assets",
                "object": index,
                "name": f"Synthetic {index}",
                "schema": "subtitle-lines-v1",
            }
            for index in (1, 2)
        ],
    }
    monkeypatch.setattr(exporter, "load_profile", lambda: profile)
    monkeypatch.setattr(exporter, "verify_profile_evidence", lambda game, data: {})
    return profile


def test_runtime_candidate_binds_approved_revisions_and_exact_payload(repo, monkeypatch):
    synthetic_runtime_profile(repo, monkeypatch)
    row = approve(repo)
    result = export_payloads(repo, runtime_candidate=True)
    folder = Path(result["folder"])
    manifest = json.loads((folder / "manifest.json").read_text())
    runtime = json.loads((folder / "translation.json").read_text(encoding="utf-8"))
    assert manifest["selection"][0]["translation_revision"] == row["translation_revision"]
    assert manifest["runtime_candidate"]["application_verified"] is False
    assert manifest["runtime_candidate"]["installation_authorized"] is False
    assert hash_file(folder / "translation.json") == manifest["runtime_candidate"]["sha256"]
    assert len(runtime["entries"]) == 1
    entry = runtime["entries"][0]
    assert entry["text"] == "< geri\nNext"
    assert entry["source_sha256"] == sha256(b"< back\nNext").hexdigest()
    assert entry["target_sha256"] == sha256(b"< geri\nNext").hexdigest()


def test_small_runtime_selection_uses_textasset_contract_and_preserves_unselected(
    repo, monkeypatch
):
    from unitytranslator.application import ApplicationSession

    synthetic_runtime_profile(repo, monkeypatch)
    row = approve(repo)
    selection = [
        {key: row[key] for key in ("unit_id", "source_revision", "translation_revision", "version")}
    ]
    session = ApplicationSession()
    session.repository = repo
    result = asyncio.run(
        session.dispatch(
            "runtime_export",
            {
                "project_id": repo.project_id,
                "request_token": "textasset-selection",
                "records": selection,
            },
        )
    )
    assert result["project_id"] == repo.project_id
    assert result["request_token"] == "textasset-selection"
    assert result["records"] == 1 and result["game_written"] is False
    assert result["installation"] == "unsupported"
    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert payload["profile_id"] == "synthetic"
    assert payload["entries"][0]["text"] == "< geri\nNext"
    assert len(payload["entries"]) == 1
    assert (
        repo.paths.game / "shared.assets"
    ).read_bytes() == b"synthetic container; no Unity or game assembly"
    assert first(repo)["translation_revision"] == row["translation_revision"]


def test_small_textasset_selection_rejects_stale_approval_and_draft(repo, monkeypatch):
    from unitytranslator.runtime_export import export_selected_runtime

    synthetic_runtime_profile(repo, monkeypatch)
    row = approve(repo)
    selection = [
        {key: row[key] for key in ("unit_id", "source_revision", "translation_revision", "version")}
    ]
    EditorDraftStore(repo).put(row["unit_id"], row["source_revision"], row["version"], "Draft", 0)
    with pytest.raises(ValueError, match="revision changed"):
        export_selected_runtime(repo, selection)
    assert not list((repo.paths.project / "exports").glob("textasset-*"))


def test_candidate_review_is_explicit_and_does_not_establish_approval(repo, monkeypatch):
    synthetic_runtime_profile(repo, monkeypatch)
    row = first(repo)
    repo.edit(row["unit_id"], row["version"], "< geri")
    row = first(repo)
    frozen = [
        {
            key: row[key]
            for key in (
                "unit_id",
                "source_revision",
                "translation_revision",
                "version",
            )
        }
    ]
    with pytest.raises(ValueError):
        export_payloads(repo, frozen, runtime_candidate=True)
    with pytest.raises(ValueError):
        export_payloads(repo, review_candidates=True)
    result = export_payloads(repo, frozen, runtime_candidate=True, review_candidates=True)
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["selection_state"] == "unapproved-review-candidates"
    assert manifest["installation"] == "unsupported"
    assert result["candidate_translations"] == 1
    assert "approved_translations" not in result
    assert first(repo)["status"] == "translated"
    with pytest.raises(ValueError):
        export_payloads(repo, frozen, runtime_candidate=True)


def test_semantic_review_candidates_can_be_previewed_without_approval(repo, monkeypatch):
    synthetic_runtime_profile(repo, monkeypatch)
    row = first(repo)
    repo.candidate(
        row["unit_id"],
        row["source_revision"],
        row["version"],
        row["source_text"],
        "model",
        {},
        ["unchanged_source"],
    )
    row = first(repo)
    assert row["status"] == "needs_review"
    frozen = [
        {
            key: row[key]
            for key in (
                "unit_id",
                "source_revision",
                "translation_revision",
                "version",
            )
        }
    ]
    result = export_payloads(repo, frozen, runtime_candidate=True, review_candidates=True)
    assert result["candidate_translations"] == 1
    assert first(repo)["status"] == "needs_review"
    with pytest.raises(ValueError):
        export_payloads(repo, frozen, runtime_candidate=True)


@pytest.mark.parametrize("mutation", ["missing", "name", "schema", "excluded"])
def test_runtime_candidate_rejects_unreviewed_source_mapping(repo, monkeypatch, mutation):
    profile = synthetic_runtime_profile(repo, monkeypatch)
    approve(repo)
    if mutation == "missing":
        profile["sources"].pop()
    elif mutation == "excluded":
        profile["sources"][0]["excluded_reason"] = "synthetic exclusion"
    else:
        profile["sources"][0][mutation] = "unreviewed"
    with pytest.raises(ValueError, match="reviewed"):
        export_payloads(repo, runtime_candidate=True)
    assert not list(repo.paths.project.glob("exports/textasset-*"))


def test_literal_rule_is_explicit_and_does_not_relax_i2():
    assert format_issues("< back", "< geri")
    assert not format_issues("< back", "< geri", rules="literal-lines-v1")
    assert format_issues("One", "Two\nInjected", rules="literal-lines-v1")
    assert mask("< back", rules="literal-lines-v1").restore("< geri") == "< geri"
    with pytest.raises(ValueError):
        mask("< back", rules="literal-lines-v1").restore("< geri\nInjected")
    assert format_issues("Text", "Text", rules="profile-selected-code") == ["unsupported_format"]


def test_export_requires_approvals_and_preserves_all_untouched_bytes(repo):
    original_hash = hash_file(repo.paths.game / "shared.assets")
    with pytest.raises(ValueError, match="approved"):
        export_payloads(repo)
    row = approve(repo)
    result = export_payloads(repo)
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert result["sources"] == 2 and result["approved_translations"] == 1
    assert manifest["installation"] == "unsupported" and not manifest["source_files_modified"]
    assert manifest["outside_scope"] == ["Synthetic excluded area"]
    for payload in manifest["payloads"]:
        raw = (Path(result["folder"]) / payload["file"]).read_bytes()
        assert sha256(raw).hexdigest() == payload["sha256"]
        expected = (
            b"< geri\nNext"
            if payload["source"]["source_object"] == 1
            else (b"Other source\n\nLast\n")
        )
        assert raw == expected
    assert manifest["selection"][0]["unit_id"] == row["unit_id"]
    assert hash_file(repo.paths.game / "shared.assets") == original_hash


def test_stale_revision_and_unfinished_draft_block_export(repo):
    row = approve(repo)
    frozen = [
        {
            key: row[key]
            for key in (
                "unit_id",
                "source_revision",
                "translation_revision",
                "version",
            )
        }
    ]
    saved = EditorDraftStore(repo).put(
        row["unit_id"],
        row["source_revision"],
        row["version"],
        "Unfinished",
    )
    with pytest.raises(ValueError):
        export_payloads(repo, frozen)
    EditorDraftStore(repo).discard(row["unit_id"], saved["revision"])
    repo.edit(row["unit_id"], row["version"], "< önceki")
    row = first(repo)
    repo.approve(row["unit_id"], row["version"])
    with pytest.raises(ValueError, match="revision"):
        export_payloads(repo, frozen)


def test_source_changes_block_export_without_publishing(repo):
    approve(repo)
    (repo.paths.game / "shared.assets").write_bytes(b"changed synthetic source")
    with pytest.raises(ValueError, match="source changed"):
        export_payloads(repo)
    assert not list(repo.paths.project.glob("exports/textasset-*"))


def test_changed_positional_source_does_not_transfer_approvals_or_drafts(repo):
    row = approve(repo)
    saved = EditorDraftStore(repo).put(
        row["unit_id"],
        row["source_revision"],
        row["version"],
        "Unfinished",
    )
    source = SourceDescriptor(
        **json.loads(
            repo.db.execute(
                "SELECT descriptor_json FROM source_descriptors WHERE id='synthetic-1'"
            ).fetchone()[0]
        )
    )
    document = parse_payload(b"Inserted\n< back\nNext", source.schema_version)
    source = replace(source, payload_fingerprint=document.fingerprint)
    repo.ingest(document.drafts(source), {}, source=source)
    assert all(record["status"] != "approved" for record in repo.page())
    assert EditorDraftStore(repo).get(row["unit_id"]) == saved
    assert (
        repo.db.execute(
            "SELECT approved_translation FROM work_items WHERE unit_id=?", (row["unit_id"],)
        ).fetchone()[0]
        == row["translation_revision"]
    )


def test_literal_record_uses_shared_queue_and_current_approval_selection(repo):
    row = first(repo)
    captured = []

    def handler(request):
        payload = json.loads(request.content)
        captured.append(payload)
        data = json.loads(payload["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translations": [{"id": data["id"], "text": "< geri"}],
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = LocalProvider("lm-studio", "http://127.0.0.1:1234", httpx.MockTransport(handler))
    profile = GenerationProfile("lm-studio", "http://127.0.0.1:1234", "synthetic", 8192)
    job = JobStore(repo).create([row["unit_id"]], profile)
    asyncio.run(TranslationJobService(repo, lambda _: provider).run(job))
    assert JobStore(repo).progress(job)["status"] == "completed"
    translated = first(repo)
    assert translated["translation"] == "< geri" and translated["status"] == "translated"
    assert captured and all_approval_preview(repo)["count"] == 1
    repo.approve(translated["unit_id"], translated["version"])
    assert export_payloads(repo)["approved_translations"] == 1


def test_textasset_installation_is_blocked_before_inventory_or_plan_creation(repo):
    from unitytranslator.installation import InstallationSession

    approve(repo)
    installation = InstallationSession(repo)
    before = list(repo.paths.project.rglob("*"))
    with pytest.raises(ValueError, match="staged text exports only"):
        installation.prepare()
    assert installation.pending is None
    assert list(repo.paths.project.rglob("*")) == before
    status = installation.status()
    assert not status["kit_available"]


def test_model_cannot_insert_a_line_break_into_literal_payload():
    def handler(request):
        data = json.loads(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translations": [{"id": data["id"], "text": "injected\nline"}],
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = LocalProvider("lm-studio", "http://127.0.0.1:1234", httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="değişken|etiket"):
        asyncio.run(
            provider.translate_record(
                "synthetic",
                "< back",
                "id",
                "en",
                "tr",
                context_tokens=8192,
                format_rules="literal-lines-v1",
            )
        )
