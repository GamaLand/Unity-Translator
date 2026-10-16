import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from unitytranslator.domain import TextUnitDraft
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.repository import ProjectRepository


def draft(key: str = "UI/start", text: str = "Start", context: str = "") -> TextUnitDraft:
    return TextUnitDraft(
        key,
        key,
        "synthetic.assets",
        1,
        "en",
        text,
        sha256(text.encode()).hexdigest(),
        "UI",
        context,
    )


@pytest.fixture
def paths(tmp_path: Path) -> ProjectPaths:
    game = tmp_path / "game"
    game.mkdir()
    return ProjectPaths(game, tmp_path / "project")


def test_close_reopen_retains_source_and_translation(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {"kind": "synthetic"})
        item = repo.page()[0]
        assert repo.candidate(
            item["unit_id"],
            item["source_revision"],
            item["version"],
            "Başla",
            "model",
            {"model": "synthetic-model"},
            [],
        )
        identifier = repo.project_id
    with ProjectRepository(paths) as repo:
        assert repo.project_id == identifier
        assert repo.page()[0]["translation"] == "Başla"
        assert repo.db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert repo.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_quality_warning_is_persisted_without_approval_or_text_changes(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft(text="Cannot move before attacking")], {})
        current = repo.page()[0]
        metadata = {"model": "synthetic"}
        repo.candidate(
            current["unit_id"],
            current["source_revision"],
            current["version"],
            "Saldırdıktan sonra hareket eder",
            "model",
            metadata,
            [],
        )
        row = repo.page()[0]
        assert row["status"] == "needs_review"
        assert row["translation"] == "Saldırdıktan sonra hareket eder"
        assert "negation_content_review" in json.loads(row["issues_json"])
        assert "mechanical_condition_review" in json.loads(row["issues_json"])
        stored = repo.history(current["unit_id"])["revisions"][0]
        assert (
            json.loads(stored["metadata_json"])["review_checks_version"] == "review-multilingual-v5"
        )
        assert metadata == {"model": "synthetic"}
        # İnsanın açık onayı mümkündür; uyarı kendi başına onay sayılmaz.
        repo.approve(row["unit_id"], row["version"])
        approved = repo.page()[0]
        assert approved["status"] == "approved"
        assert not repo.candidate(
            row["unit_id"],
            row["source_revision"],
            approved["version"],
            "Saldırmadan önce hareket edemez",
            "import",
            {},
            [],
        )
        assert repo.page()[0]["translation"] == row["translation"]


def test_second_writer_refused(paths: ProjectPaths) -> None:
    with ProjectRepository(paths):
        with pytest.raises(ValueError, match="başka"):
            ProjectRepository(paths)
    with ProjectRepository(paths):
        pass


def test_late_model_and_import_do_not_replace_approval(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        item = repo.page()[0]
        repo.candidate(
            item["unit_id"], item["source_revision"], item["version"], "Başla", "manual", {}, []
        )
        ready = repo.page()[0]
        repo.approve(ready["unit_id"], ready["version"])
        approved = repo.page()[0]
        for origin in ("model", "import"):
            assert not repo.candidate(
                item["unit_id"],
                item["source_revision"],
                approved["version"],
                "Devam",
                origin,
                {},
                [],
            )
            assert repo.page()[0]["translation"] == "Başla"
            assert repo.page()[0]["status"] == "approved"


def test_changed_context_invalidates_approval_but_preserves_history(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        unit = draft()
        repo.ingest([unit], {})
        item = repo.page()[0]
        repo.candidate(
            item["unit_id"], item["source_revision"], item["version"], "Başla", "manual", {}, []
        )
        repo.approve(item["unit_id"], repo.page()[0]["version"])
        repo.ingest([replace(unit, context="Different speaker")], {})
        assert repo.page()[0]["status"] == "needs_review"
        assert repo.page()[0]["translation"] is None
        assert repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == 1
        assert not repo.candidate(
            item["unit_id"], item["source_revision"], item["version"], "Geç cevap", "model", {}, []
        )


def test_failed_snapshot_does_not_deactivate_existing_source(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        unit = draft()
        repo.ingest([unit], {})
        with pytest.raises(ValueError):
            repo.ingest([replace(unit, source_hash="wrong")], {})
        assert len(repo.page()) == 1
        with pytest.raises(ValueError):
            repo.ingest([unit, unit], {})
        assert len(repo.page()) == 1


def test_reingest_does_not_reset_finished_work(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        unit = draft()
        repo.ingest([unit], {})
        item = repo.page()[0]
        repo.candidate(
            item["unit_id"], item["source_revision"], item["version"], "Başla", "model", {}, []
        )
        repo.ingest([unit], {})
        assert repo.page()[0]["status"] == "translated"
        assert repo.page()[0]["version"] == 1


def test_invalid_placeholders_cannot_become_active_or_approved(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft(text="Start {0}")], {})
        item = repo.page()[0]
        assert not repo.candidate(
            item["unit_id"], item["source_revision"], item["version"], "Başla", "model", {}, []
        )
        assert repo.page()[0]["translation"] is None
        with pytest.raises(ValueError):
            repo.approve(item["unit_id"], item["version"])


def test_manual_edit_invalidates_old_approval_and_search_is_turkish(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        item = repo.page()[0]
        assert repo.edit(item["unit_id"], item["version"], "Işık")
        repo.approve(item["unit_id"], repo.page()[0]["version"])
        assert repo.count(search="ışık") == 1
        assert repo.count(search="işik") == 0
        assert repo.page(search="ışık")[0]["translation"] == "Işık"
        version = repo.page()[0]["version"]
        assert repo.edit(item["unit_id"], version, "İleri")
        assert repo.page()[0]["status"] == "translated"
        assert repo.count(search="ileri", status="translated") == 1
        with pytest.raises(ValueError):
            repo.edit(item["unit_id"], version, "stale")


def test_ambiguous_source_set_does_not_replace_original_snapshot(paths: ProjectPaths) -> None:
    (paths.game / "synthetic.assets").write_bytes(b"synthetic original")
    (paths.game / "other.assets").write_bytes(b"synthetic other")
    with ProjectRepository(paths) as repo:
        original = draft()
        repo.ingest([original], {})
        with pytest.raises(ValueError, match="belirsiz"):
            repo.ingest([replace(original, source_file="other.assets")], {})
        assert repo.page()[0]["source_file"] == "synthetic.assets"
