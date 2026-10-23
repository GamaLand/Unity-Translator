import sqlite3

import pytest
from test_repository import draft

from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def repo(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as value:
        value.ingest([draft(text="Start {0}\r\nNext")], {})
        yield value


def put(repo, text="Başla {0}\r\nSonraki"):
    row = repo.page()[0]
    return EditorDraftStore(repo).put(row["unit_id"], row["source_revision"], row["version"], text)


def test_draft_reopen_keeps_exact_unfinished_text_and_does_not_change_work(repo):
    before = repo.page()[0]
    text = "<unfinished {\r\nçğıİöşü\u00a0\u2028"
    saved = put(repo, text)
    assert repo.page()[0] == before
    assert repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == 0
    paths = repo.paths
    repo.close()
    with ProjectRepository(paths) as reopened:
        assert EditorDraftStore(reopened).get("UI/start") == saved
        assert saved["text"] == text


def test_revision_conflict_and_old_base_do_not_overwrite_draft(repo):
    store = EditorDraftStore(repo)
    saved = put(repo)
    with pytest.raises(ValueError, match="Taslak değişti"):
        store.put("UI/start", saved["source_revision"], saved["base_version"], "lost")
    repo.edit("UI/start", 0, "Başlat {0}\r\nSonraki")
    with pytest.raises(ValueError, match="temel sürüm"):
        store.put("UI/start", saved["source_revision"], 1, "lost", saved["revision"])
    assert store.get("UI/start") == saved


@pytest.mark.parametrize("change", ["source", "translation", "approval", "inactive"])
def test_stale_commit_retains_draft_and_current_translation(repo, change):
    saved = put(repo)
    if change == "source":
        repo.ingest([draft(text="New {0}\r\nNext")], {})
    elif change == "inactive":
        repo.ingest([draft("UI/other")], {})
    else:
        repo.edit("UI/start", 0, "Başlat {0}\r\nSonraki")
        if change == "approval":
            repo.approve("UI/start", repo.page()[0]["version"])
    before = list(repo.db.iterdump())
    with pytest.raises(ValueError, match="taslak korundu"):
        EditorDraftStore(repo).commit("UI/start", saved["revision"])
    assert list(repo.db.iterdump()) == before


def test_invalid_half_written_draft_commit_rolls_back_without_deleting(repo):
    saved = put(repo, "Eksik")
    before = list(repo.db.iterdump())
    with pytest.raises(ValueError, match="korumalı biçim"):
        EditorDraftStore(repo).commit("UI/start", saved["revision"])
    assert list(repo.db.iterdump()) == before


def test_commit_is_manual_revision_clears_existing_approval_and_removes_draft(repo):
    repo.edit("UI/start", 0, "Başlat {0}\r\nSonraki")
    repo.approve("UI/start", repo.page()[0]["version"])
    saved = put(repo)
    store = EditorDraftStore(repo)
    assert store.commit("UI/start", saved["revision"])
    assert store.get("UI/start") is None
    row = repo.page()[0]
    assert row["translation"] == saved["text"]
    assert row["status"] == "translated"
    approval = repo.db.execute(
        "SELECT approved_source,approved_translation FROM work_items WHERE unit_id='UI/start'"
    ).fetchone()
    assert tuple(approval) == (None, None)
    assert repo.history("UI/start")["revisions"][0]["origin"] == "manual"


def test_identical_draft_commit_preserves_approval_and_translation_history(repo):
    repo.edit("UI/start", 0, "Başla {0}\r\nSonraki")
    repo.approve("UI/start", repo.page()[0]["version"])
    before = repo.page()[0]
    saved = put(repo)
    assert not EditorDraftStore(repo).commit("UI/start", saved["revision"])
    assert repo.page()[0] == before
    assert EditorDraftStore(repo).get("UI/start") is None


def test_discard_requires_current_revision_and_new_base_can_follow(repo):
    store = EditorDraftStore(repo)
    saved = put(repo)
    updated = store.put("UI/start", saved["source_revision"], 0, "Yarım", 1)
    with pytest.raises(ValueError, match="kaldırma reddedildi"):
        store.discard("UI/start", 1)
    assert store.get("UI/start") == updated
    store.discard("UI/start", updated["revision"])
    assert store.get("UI/start") is None


def test_other_unit_source_and_future_base_version_are_rejected(repo):
    repo.ingest([draft(), draft("UI/other")], {})
    own = next(row for row in repo.page() if row["unit_id"] == "UI/start")
    with pytest.raises(ValueError, match="kimliği"):
        EditorDraftStore(repo).put("UI/start", own["source_revision"], own["version"] + 1, "x")
    other = next(row for row in repo.page() if row["unit_id"] == "UI/other")
    with pytest.raises(ValueError, match="kimliği"):
        EditorDraftStore(repo).put("UI/start", other["source_revision"], 0, "x")


def test_deleted_draft_stamp_cannot_target_a_new_draft_after_reopen(repo):
    first = put(repo)
    EditorDraftStore(repo).discard("UI/start", first["revision"])
    paths = repo.paths
    repo.close()
    with ProjectRepository(paths) as reopened:
        replacement = put(reopened, "Yeni taslak")
        assert replacement["revision"] > first["revision"]
        with pytest.raises(ValueError, match="kaldırma reddedildi"):
            EditorDraftStore(reopened).discard("UI/start", first["revision"])
        assert EditorDraftStore(reopened).get("UI/start") == replacement


def test_identical_autosave_keeps_stamp_and_invalid_stamp_cannot_commit(repo):
    first = put(repo)
    store = EditorDraftStore(repo)
    assert (
        store.put("UI/start", first["source_revision"], 0, first["text"], first["revision"])
        == first
    )
    with pytest.raises(ValueError, match="belirteci"):
        store.commit("UI/start", True)
    with pytest.raises(ValueError, match="belirteci"):
        store.discard("UI/start", True)
    assert store.get("UI/start") == first


def test_commit_transaction_rolls_back_manual_revision_if_draft_delete_fails(repo):
    first = put(repo)
    repo.db.execute(
        "CREATE TRIGGER refuse_draft_delete BEFORE DELETE ON editor_drafts "
        "BEGIN SELECT RAISE(ABORT,'synthetic disk transaction failure'); END"
    )
    before = list(repo.db.iterdump())
    with pytest.raises(sqlite3.IntegrityError):
        EditorDraftStore(repo).commit("UI/start", first["revision"])
    assert list(repo.db.iterdump()) == before


def test_v3_migration_preserves_approved_translation_and_readable_backup(repo):
    repo.edit("UI/start", 0, "Başla {0}\r\nSonraki")
    repo.approve("UI/start", repo.page()[0]["version"])
    before = repo.page()[0]
    identifier, paths = repo.project_id, repo.paths
    repo.db.execute("DROP TABLE snapshot_sources")
    repo.db.execute("DROP INDEX units_logical_source")
    repo.db.execute("ALTER TABLE text_units DROP COLUMN logical_source_id")
    repo.db.execute("DROP TABLE source_descriptors")
    repo.db.execute("DELETE FROM schema_migrations WHERE version=5")
    repo.db.execute("DROP TABLE editor_drafts")
    repo.db.execute("DELETE FROM schema_migrations WHERE version=4")
    repo.db.execute("PRAGMA user_version=3")
    repo.close()
    with ProjectRepository(paths) as reopened:
        assert reopened.project_id == identifier
        assert reopened.page()[0] == before
        assert reopened.db.execute("PRAGMA user_version").fetchone()[0] == 5
        assert EditorDraftStore(reopened).get("UI/start") is None
    backups = list((paths.project / "backups").glob("schema-3-*.sqlite3"))
    preserved = False
    for backup in backups:
        with sqlite3.connect(backup) as stream:
            preserved |= stream.execute("SELECT count(*) FROM text_units").fetchone()[0] == 1
    assert preserved


def test_utf8_size_limits_reject_without_changing_existing_draft(repo, monkeypatch):
    import unitytranslator.editor_drafts as module

    first = put(repo)
    monkeypatch.setattr(module, "MAX_DRAFT_BYTES", 3)
    store = EditorDraftStore(repo)
    with pytest.raises(ValueError, match="boyut sınırı"):
        store.put("UI/start", first["source_revision"], 0, "çç", first["revision"])
    assert store.get("UI/start") == first
    monkeypatch.setattr(module, "MAX_DRAFT_BYTES", 100)
    monkeypatch.setattr(module, "MAX_TOTAL_DRAFT_BYTES", 1)
    with pytest.raises(ValueError, match="toplam"):
        store.put("UI/start", first["source_revision"], 0, "ç", first["revision"])
    assert store.get("UI/start") == first


def test_failed_v4_migration_keeps_v3_data_and_backup(tmp_path, monkeypatch):
    import unitytranslator.repository as module

    game = tmp_path / "game"
    game.mkdir()
    paths = ProjectPaths(game, tmp_path / "project")
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        repo.db.execute("DROP TABLE editor_drafts")
        repo.db.execute("DELETE FROM schema_migrations WHERE version=4")
        repo.db.execute("PRAGMA user_version=3")
    real_files = module.files

    class BadSql:
        def read_text(self):
            return "CREATE TABLE partial(value TEXT); INVALID SQL;"

    class Resources:
        def joinpath(self, name):
            return (
                BadSql()
                if name == "schema-v4.sql"
                else real_files("unitytranslator.resources").joinpath(name)
            )

    monkeypatch.setattr(module, "files", lambda _: Resources())
    with pytest.raises(sqlite3.DatabaseError):
        ProjectRepository(paths)
    with sqlite3.connect(paths.project / "project.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM text_units").fetchone()[0] == 1
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='partial'").fetchone()
    assert list((paths.project / "backups").glob("schema-3-*.sqlite3"))
