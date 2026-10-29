"""Native staging uses synthetic sources and fixed grammar, never an installed game."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from unitytranslator.application import ApplicationSession
from unitytranslator.discovery import extract_to_project
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.portable import PortableService
from unitytranslator.renpy_export import add_review_context, export_native, template_candidate
from unitytranslator.renpy_templates import parse_template
from unitytranslator.repository import ProjectRepository

SOURCE = '''# Synthetic fixture only.
# game/../../untrusted-location-comment.rpy:12
translate sample start_first:
    # e "Hello [name!q]."
    e "Old candidate [name!q]."
    # "Fallback [name!q]."
    "Unreviewed [name!q]."

translate sample untouched:
    # "Never approved."
    "Existing translated."

translate sample strings:
    old "Start{#menu}"
    new "Existing{#menu}"
    old "Omitted"
    new "Not reviewed"
'''


def fixture_paths(tmp_path):
    game = tmp_path / "game-root"
    folder = game / "game/tl/sample"
    folder.mkdir(parents=True)
    (folder / "script.rpy").write_bytes(b"\xef\xbb\xbf" + SOURCE.replace("\n", "\r\n").encode())
    paths = ProjectPaths(game, tmp_path / "project")
    extract_to_project(paths, "game/tl/sample/script.rpy")
    return paths


def approve(repo, source, target):
    row = next(row for row in repo.page() if row["source_text"] == source)
    repo.edit(row["unit_id"], row["version"], target)
    row = next(item for item in repo.page() if item["unit_id"] == row["unit_id"])
    repo.approve(row["unit_id"], row["version"])
    return next(item for item in repo.page() if item["unit_id"] == row["unit_id"])


def decoded(result, language="turkish"):
    records = []
    files = list(Path(result["folder"]).glob(f"game/tl/{language}/*.rpy"))
    for path in files:
        records.extend(parse_template(path.read_bytes(), language).records)
    return records


def test_legacy_plain_snapshots_export_without_rewriting_history(tmp_path):
    paths = fixture_paths(tmp_path)
    with ProjectRepository(paths) as repo:
        approved = approve(repo, "Hello [name!q].", "Merhaba [name!q].")
        # Shape metadata was absent before symbolic-say-v2. Keep that history verbatim.
        for row in repo.db.execute("SELECT id,metadata_json FROM source_snapshots").fetchall():
            metadata = json.loads(row["metadata_json"])
            metadata.pop("syntax_version", None)
            for record in metadata.get("records", ()):
                for key in ("attributes", "temporary_attributes", "nointeract"):
                    record.pop(key, None)
            repo.db.execute("UPDATE source_snapshots SET metadata_json=? WHERE id=?",
                            (json.dumps(metadata), row["id"]))
        repo.db.commit()
        before = list(repo.db.iterdump())
        result = export_native(repo, "turkish")
        assert list(repo.db.iterdump()) == before
        current = next(r for r in repo.page() if r["unit_id"] == approved["unit_id"])
        assert current == approved
        assert decoded(result)[0].candidate == "Merhaba [name!q]."


def test_review_context_cache_tracks_snapshot_and_source_hash(tmp_path, monkeypatch):
    import unitytranslator.renpy_export as exporter
    from unitytranslator.discovery import probe_source
    from unitytranslator.reader_adapters import result_from_report

    paths = fixture_paths(tmp_path)
    original = exporter._snapshot_metadata
    loads = []

    def tracked(repo, source):
        loads.append(source.logical_id)
        return original(repo, source)

    monkeypatch.setattr(exporter, "_snapshot_metadata", tracked)
    with ProjectRepository(paths) as repo:
        before = list(repo.db.iterdump())
        rows = repo.page(limit=1)
        add_review_context(repo, rows)
        line = rows[0]["native_context"]["line"]
        add_review_context(repo, repo.page(offset=1, limit=1))
        assert len(loads) == 1  # No repeated decoding of original byte payloads per page.
        assert list(repo.db.iterdump()) == before
        rows[0]["source_hash"] = "0" * 64
        add_review_context(repo, rows)
        assert "native_context" not in rows[0]
        source = paths.game / "game/tl/sample/script.rpy"
        source.write_bytes(b"\n\n" + source.read_bytes().removeprefix(b"\xef\xbb\xbf"))
        report = probe_source(paths, "game/tl/sample/script.rpy")
        repo.ingest_reader_result(result_from_report(report, replace_source_set=True))
        rows = repo.page(limit=1)
        add_review_context(repo, rows)
        assert len(loads) == 2
        assert rows[0]["native_context"]["line"] == line + 2


def test_review_context_presents_attributes_without_changing_source_revisions(tmp_path):
    from test_renpy_scripts import fixture

    paths, _ = fixture(tmp_path, 'label start:\n    e happy @ -sad "Hello."\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        rows = repo.page()
        original = rows[0]["source_revision"]
        before = list(repo.db.iterdump())
        add_review_context(repo, rows)
        assert rows[0]["native_context"]["speaker"] == "e happy @ -sad"
        assert rows[0]["source_revision"] == original
        assert list(repo.db.iterdump()) == before


def test_template_attribute_change_invalidates_only_its_approved_block(tmp_path):
    paths = fixture_paths(tmp_path)
    with ProjectRepository(paths) as repo:
        old = approve(repo, "Hello [name!q].", "Merhaba [name!q].")
        other = approve(repo, "Start{#menu}", "Başla{#menu}")
    source = paths.game / "game/tl/sample/script.rpy"
    source.write_text(SOURCE.replace('# e "Hello', '# e happy "Hello').replace(
        'e "Old candidate', 'e happy "Old candidate'
    ), encoding="utf-8")
    extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        current = next(r for r in repo.page() if r["unit_id"] == old["unit_id"])
        assert current["status"] != "approved"
        assert current["source_revision"] != old["source_revision"]
        unchanged = next(r for r in repo.page() if r["unit_id"] == other["unit_id"])
        assert unchanged == other


def test_native_export_preserves_sources_and_only_emits_approved_replacements(tmp_path):
    paths = fixture_paths(tmp_path)
    originals = {p: hash_file(p) for p in paths.game.rglob("*") if p.is_file()}
    with ProjectRepository(paths) as repo:
        dialogue = approve(repo, "Hello [name!q].", "Merhaba [name!q].")
        string = approve(repo, "Start{#menu}", "Başla{#menu}")
        before = list(repo.db.iterdump())
        result = export_native(repo, "turkish")
        assert list(repo.db.iterdump()) == before
        again = export_native(repo, "turkish")
        assert again["folder"] != result["folder"]
    assert originals == {p: hash_file(p) for p in paths.game.rglob("*") if p.is_file()}
    output = decoded(result)
    assert [(r.source, r.candidate) for r in output] == [
        ("Hello [name!q].", "Merhaba [name!q]."),
        ("Fallback [name!q].", "Fallback [name!q]."),
        ("Start{#menu}", "Başla{#menu}"),
    ]
    assert result["installation"] == "unsupported"
    manifest = json.loads(Path(result["manifest"]).read_bytes())
    assert manifest["language_mapping"] == {"tr": "turkish"}
    assert manifest["input_template_language"] == "sample"
    assert {s["translation_revision"] for s in manifest["selection"]} == {
        dialogue["translation_revision"], string["translation_revision"]
    }
    assert manifest["coverage"][0]["fallback_dialogue"] == 1
    assert manifest["language_activation"] == "unverified"
    extensions = {p.suffix for p in Path(result["folder"]).rglob("*") if p.is_file()}
    assert extensions == {".json", ".rpy"}


@pytest.mark.parametrize("language", ["", "sample", "Sample", "None", "../bad", "tr-TR", "python"])
def test_language_mapping_is_explicit_and_separate_from_template_namespace(tmp_path, language):
    paths = fixture_paths(tmp_path)
    with ProjectRepository(paths) as repo:
        approve(repo, "Start{#menu}", "Başla{#menu}")
        with pytest.raises(ValueError):
            export_native(repo, language)
    assert not list(paths.project.glob("exports/renpy-*"))


def test_unapproved_candidates_and_unfinished_drafts_cannot_be_exported(tmp_path):
    paths = fixture_paths(tmp_path)
    with ProjectRepository(paths) as repo:
        with pytest.raises(ValueError, match="approved"):
            export_native(repo, "turkish")
        row = approve(repo, "Start{#menu}", "Başla{#menu}")
        EditorDraftStore(repo).put(
            row["unit_id"], row["source_revision"], row["version"], "Unfinished{#menu}"
        )
        with pytest.raises(ValueError, match="drafts"):
            export_native(repo, "turkish")
    assert not list(paths.project.glob("exports/renpy-*"))


@pytest.mark.parametrize("change", ["approval", "version", "translation", "source", "new_file"])
def test_stale_sources_revisions_and_approvals_block_publication(tmp_path, change):
    paths = fixture_paths(tmp_path)
    with ProjectRepository(paths) as repo:
        row = approve(repo, "Start{#menu}", "Başla{#menu}")
        frozen = [{key: row[key] for key in (
            "unit_id", "source_revision", "translation_revision", "version"
        )}]
        if change == "approval":
            repo.db.execute(
                "UPDATE work_items SET approved_source=NULL WHERE unit_id=?", (row["unit_id"],)
            )
        elif change == "version":
            frozen[0]["version"] -= 1
        elif change == "translation":
            repo.db.execute("UPDATE translation_revisions SET text='[injected()]' WHERE id=?",
                            (row["translation_revision"],))
        elif change == "source":
            (paths.game / "game/tl/sample/script.rpy").write_text(SOURCE.replace("Start", "Begin"))
        else:
            (paths.game / "game/tl/sample/added.rpy").write_text(
                'translate sample new_id:\n    # "New"\n    ""\n'
            )
        with pytest.raises(ValueError):
            export_native(repo, "turkish", frozen)
    assert not list(paths.project.glob("exports/renpy-*"))


def test_repeated_global_string_keys_are_deduplicated_and_conflicts_rejected(tmp_path):
    paths = fixture_paths(tmp_path)
    sibling = paths.game / "game/tl/sample/other.rpy"
    sibling.write_text(
        'translate sample strings:\n    old "Start{#menu}"\n    new "Existing{#menu}"\n'
    )
    extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        rows = [row for row in repo.page() if row["source_text"] == "Start{#menu}"]
        for index, row in enumerate(rows):
            repo.edit(row["unit_id"], row["version"], ("Başla" if index else "Başlat") + "{#menu}")
            current = next(item for item in repo.page() if item["unit_id"] == row["unit_id"])
            repo.approve(current["unit_id"], current["version"])
        with pytest.raises(ValueError, match="Conflicting approved global"):
            export_native(repo, "turkish")
        # A single explicit reviewed mapping can cover all recorded native occurrences.
        row = next(item for item in repo.page() if item["unit_id"] == rows[0]["unit_id"])
        frozen = [{key: row[key] for key in (
            "unit_id", "source_revision", "translation_revision", "version"
        )}]
        with pytest.raises(ValueError, match="Conflicting approved global"):
            export_native(repo, "turkish", frozen)
        other = next(item for item in repo.page() if item["unit_id"] == rows[1]["unit_id"])
        repo.edit(other["unit_id"], other["version"], row["translation"])
        other = next(item for item in repo.page() if item["unit_id"] == other["unit_id"])
        repo.approve(other["unit_id"], other["version"])
        result = export_native(repo, "turkish", frozen)
        assert len(decoded(result)) == 1
        manifest = json.loads(Path(result["manifest"]).read_bytes())
        entry = next(item for item in manifest["global_string_occurrences"]
                     if item["source"] == "Start{#menu}")
        assert len(entry["unit_ids"]) == 2 and entry["exported"] is True


@pytest.mark.parametrize("change", ["source", "draft", "approval", "output"])
def test_changes_during_staging_leave_only_pending_files(tmp_path, monkeypatch, change):
    paths = fixture_paths(tmp_path)
    with ProjectRepository(paths) as repo:
        row = approve(repo, "Start{#menu}", "Başla{#menu}")
        original = repo.paths.write_json

        def write(relative, value):
            result = original(relative, value)
            if relative.endswith("/manifest.json"):
                if change == "source":
                    (paths.game / "game/tl/sample/script.rpy").write_text(SOURCE + "# changed\n")
                elif change == "draft":
                    EditorDraftStore(repo).put(
                        row["unit_id"], row["source_revision"], row["version"], "Draft{#menu}"
                    )
                elif change == "approval":
                    repo.db.execute("UPDATE work_items SET approved_source=NULL")
                else:
                    next(result.parent.glob("game/tl/turkish/*.rpy")).write_text("init python:\n")
            return result

        monkeypatch.setattr(repo.paths, "write_json", write)
        with pytest.raises(ValueError):
            export_native(repo, "turkish")
    assert not list(paths.project.glob("exports/renpy-*"))
    assert list(paths.project.glob("exports/.pending-renpy-*"))


def test_literal_statement_injection_remains_quoted_data(tmp_path):
    paths = fixture_paths(tmp_path)
    source = paths.game / "game/tl/sample/script.rpy"
    source.write_text('translate sample safe_id:\n    # "One\\nTwo\\nThree"\n    ""\n')
    # New synthetic project because this intentionally replaces the fixture's source set.
    paths = ProjectPaths(paths.game, tmp_path / "injection-project")
    extract_to_project(paths, "game/tl/sample/script.rpy")
    target = '\"\ninit python:\n    dangerous()'
    with ProjectRepository(paths) as repo:
        approve(repo, "One\nTwo\nThree", target)
        result = export_native(repo, "turkish")
    assert decoded(result)[0].candidate == target
    output = next(Path(result["folder"]).rglob("*.rpy")).read_text()
    assert not any(line.startswith("init ") for line in output.splitlines())


def test_restored_ownership_does_not_grant_local_native_export_authority(tmp_path):
    paths = fixture_paths(tmp_path)
    with ProjectRepository(paths) as repo:
        approve(repo, "Start{#menu}", "Başla{#menu}")
        value = PortableService(repo).read(PortableService(repo).export())
    with ProjectRepository(ProjectPaths(paths.game, tmp_path / "restored")) as repo:
        PortableService(repo).restore(value)
        row = next(row for row in repo.page() if row["translation"])
        repo.approve(row["unit_id"], row["version"])
        with pytest.raises(ValueError, match="snapshots are missing"):
            export_native(repo, "turkish")


def test_corrected_say_normalization_requires_review_and_retains_prior_history(tmp_path):
    from dataclasses import replace

    from unitytranslator.renpy_templates import TemplateDocument
    from unitytranslator.source_contracts import ReaderResult

    game = tmp_path / "game"
    source = game / "game/tl/sample/script.rpy"
    source.parent.mkdir(parents=True)
    raw = b'translate sample start_demo:\n    # e "Two  spaces."\n    e ""\n'
    source.write_bytes(raw)
    paths = ProjectPaths(game, tmp_path / "project")
    parsed = parse_template(raw, "sample")
    legacy = TemplateDocument(raw, "sample", (
        replace(parsed.records[0], source="Two  spaces."),
    )).snapshot("game/tl/sample/script.rpy", "en")
    with ProjectRepository(paths) as repo:
        repo.ingest_reader_result(ReaderResult((legacy,), True, {
            "adapter_id": "renpy-templates", "complete_source_set": True,
            "fingerprints": {"game/tl/sample/script.rpy": hash_file(source)},
        }))
        old = approve(repo, "Two  spaces.", "İki boşluk.")
        with pytest.raises(ValueError, match="records or context changed"):
            export_native(repo, "turkish")
    extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        current = repo.page()[0]
        assert current["source_text"] == "Two spaces."
        assert current["status"] != "approved"
        assert repo.db.execute(
            "SELECT count(*) FROM source_revisions WHERE unit_id=?", (old["unit_id"],),
        ).fetchone()[0] == 2
        assert repo.db.execute(
            "SELECT text FROM translation_revisions WHERE id=?", (old["translation_revision"],),
        ).fetchone()[0] == "İki boşluk."


def test_template_provenance_and_cli_shared_export(tmp_path, monkeypatch, capsys):
    from unitytranslator.__main__ import main

    paths = fixture_paths(tmp_path)
    with ProjectRepository(paths) as repo:
        row = next(row for row in repo.page() if row["source_text"] == "Hello [name!q].")
        before = list(repo.db.iterdump())
        candidate = template_candidate(repo, row["unit_id"])
        assert candidate["text"] == "Old candidate [name!q]."
        assert candidate["trusted"] is candidate["target_language_verified"] is False
        assert candidate["template_language"] == "sample"
        assert list(repo.db.iterdump()) == before
        approve(repo, "Start{#menu}", "Başla{#menu}")
    monkeypatch.setattr(sys, "argv", [
        "unitytranslator", "export-renpy", "--game", str(paths.game),
        "--project", str(paths.project), "--language", "turkish",
    ])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["language_mapping"] == {"tr": "turkish"}


def test_shared_session_rejects_old_project_export_request(tmp_path):
    paths = fixture_paths(tmp_path)

    async def run():
        session = ApplicationSession()
        try:
            await session.dispatch("open", {"project": str(paths.project), "existing_only": True})
            with pytest.raises(ValueError, match="Project changed"):
                await session.dispatch("renpy_export", {"project_id": "old", "language": "turkish"})
        finally:
            await session.close()

    asyncio.run(run())


@pytest.mark.parametrize("unsaved_draft", [False, True])
def test_desktop_native_export_mapping_history_and_draft_flush(
    tmp_path, monkeypatch, unsaved_draft
):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QDialog
    from test_ui import wait_for

    from unitytranslator.ui.window import CandidateHistoryDialog, MainWindow

    paths = fixture_paths(tmp_path)
    with ProjectRepository(paths) as repo:
        approve(repo, "Start{#menu}", "Başla{#menu}")
    app = QApplication.instance()
    window = MainWindow()
    results, errors, history = {}, [], []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.bridge.completed.connect(lambda command, result: results.update({command: result}))
    window.game_path.setText(str(paths.game))
    window.project_path.setText(str(paths.project))
    window.open_project()
    window.show()

    def inspect(dialog):
        history.append(dialog.history)
        assert dialog.template_text.toPlainText() == "Old candidate [name!q]."
        assert dialog.template_text.isReadOnly()
        assert not dialog.use.isEnabled()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(CandidateHistoryDialog, "exec", inspect)
    try:
        wait_for(app, lambda: window.review_model.rowCount() == 5)
        dialogue = next(index for index, row in enumerate(window.review_model.rows)
                        if row["source_text"] == "Hello [name!q].")
        window.table.selectRow(dialogue)
        assert "script.rpy:" in window.review_details.text()
        assert "start_first" in window.review_details.text()
        window.bridge.submit("history", {"unit_id": window.current_item["unit_id"]})
        wait_for(app, lambda: bool(history))
        assert history[0]["template_candidate"]["target_language_verified"] is False
        assert window.renpy_available
        assert not window.textasset_export_button.isEnabled()
        assert not window.runtime_export_button.isEnabled()
        assert not window.shareable_export_button.isEnabled()
        assert not window.renpy_export_button.isEnabled()
        window.renpy_language.setText("turkish")
        if unsaved_draft:
            window.translation_editor.setPlainText("Merhaba [name!q].")
        window.renpy_export_button.click()
        if unsaved_draft:
            wait_for(app, lambda: bool(errors))
            assert errors[-1][0] == "renpy_export" and "drafts" in errors[-1][1]
            assert "renpy_export" not in results
        else:
            wait_for(app, lambda: "renpy_export" in results)
            assert results["renpy_export"]["language_mapping"] == {"tr": "turkish"}
            assert len(decoded(results["renpy_export"])) == 1
            assert not errors
        window.tabs.setCurrentIndex(6)
        assert window.grab().save(str(tmp_path / "native-export.png"))
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(paths) as repo:
        if unsaved_draft:
            assert repo.db.execute("SELECT count(*) FROM editor_drafts").fetchone()[0] == 1
        assert sum(row["status"] == "approved" for row in repo.page()) == 1
