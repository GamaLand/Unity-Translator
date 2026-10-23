"""Source-set activation and schema-4 compatibility use only synthetic data."""

import sqlite3
from dataclasses import replace

import pytest
from test_repository import draft

from unitytranslator.domain import GenerationProfile
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.jobs import JobStore
from unitytranslator.repository import ProjectRepository
from unitytranslator.source_contracts import ReaderResult, SourceDescriptor, SourceSnapshot


@pytest.fixture
def repo(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repository:
        yield repository


def snapshot(identity="a", object_id=1, text="Start"):
    descriptor = SourceDescriptor(
        identity,
        "synthetic",
        "synthetic",
        "1",
        "shared.assets",
        object_id,
        "en",
    )
    unit = replace(draft(identity, text), source_file="shared.assets", source_object=object_id)
    return SourceSnapshot(descriptor, (unit,))


def test_logical_source_update_does_not_deactivate_sibling_in_same_container(repo):
    first, second = snapshot(), snapshot("b", 2)
    repo.ingest_reader_result(ReaderResult((first, second), True))
    row = next(row for row in repo.page() if row["unit_id"] == "b")
    repo.edit("b", row["version"], "Begin")
    repo.approve("b", next(row for row in repo.page() if row["unit_id"] == "b")["version"])
    before = next(row for row in repo.page() if row["unit_id"] == "b")
    EditorDraftStore(repo).put(
        "b", before["source_revision"], before["version"], "Unfinished draft"
    )
    draft_before = EditorDraftStore(repo).get("b")
    repo.ingest((), {}, source=first.source)
    assert repo.page() == [before]
    assert EditorDraftStore(repo).get("b") == draft_before
    assert repo.db.execute("SELECT count(*) FROM source_revisions").fetchone()[0] == 2


def test_partial_or_failed_complete_read_cannot_publish_any_source(repo):
    first, second = snapshot(), snapshot("b", 2)
    repo.ingest_reader_result(ReaderResult((first, second), True))
    before = list(repo.db.iterdump())
    with pytest.raises(ValueError, match="Incomplete"):
        repo.ingest_reader_result(ReaderResult((first,), False))
    assert list(repo.db.iterdump()) == before
    bad = replace(second, units=(replace(second.units[0], source_hash="bad"),))
    with pytest.raises(ValueError):
        repo.ingest_reader_result(ReaderResult((replace(first, units=()), bad), True))
    assert list(repo.db.iterdump()) == before


def test_complete_set_retires_missing_sources_but_retains_history(repo):
    first, second = snapshot(), snapshot("b", 2)
    repo.ingest_reader_result(ReaderResult((first, second), True))
    repo.ingest_reader_result(ReaderResult((first,), True))
    assert [row["unit_id"] for row in repo.page()] == ["a"]
    assert repo.db.execute("SELECT count(*) FROM source_revisions").fetchone()[0] == 2
    assert repo.db.execute("SELECT active FROM source_descriptors WHERE id='b'").fetchone()[0] == 0
    repo.ingest_reader_result(ReaderResult((first, second), True))
    assert repo.count() == 2


def test_scope_identity_collisions_and_wrong_members_are_atomic(repo):
    first = snapshot()
    repo.ingest_reader_result(ReaderResult((first,), True))
    before = list(repo.db.iterdump())
    conflicts = [
        ReaderResult((first, first), True),
        ReaderResult((replace(first, source=replace(first.source, logical_id="other")),), True),
        ReaderResult((replace(first, source=replace(first.source, source_object=2)),), True),
        ReaderResult((replace(first, source=replace(first.source, profile_id="other")),), True),
    ]
    for conflict in conflicts:
        with pytest.raises(ValueError):
            repo.ingest_reader_result(conflict)
        assert list(repo.db.iterdump()) == before


@pytest.mark.parametrize("path", ["../escape", "C:/game", "\\root", "file:stream", "a/../b"])
def test_descriptors_reject_untrusted_paths(path):
    with pytest.raises(ValueError):
        replace(snapshot().source, source_file=path)


def test_schema4_backup_preserves_approvals_drafts_history_and_receipt(repo):
    repo.ingest([draft(), draft("draft", "Next")], {})
    repo.edit("UI/start", 0, "Begin")
    repo.approve("UI/start", 1)
    row = next(row for row in repo.page() if row["unit_id"] == "draft")
    EditorDraftStore(repo).put("draft", row["source_revision"], row["version"], "Unfinished")
    rows, saved_draft = repo.page(), EditorDraftStore(repo).get("draft")
    job = JobStore(repo).create(
        ["draft"], GenerationProfile("lm-studio", "http://127.0.0.1:1234", "synthetic", 8192)
    )
    repo.db.execute("UPDATE job_items SET attempts=2,status='failed' WHERE job_id=?", (job,))
    job_before = tuple(repo.db.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone())
    item_before = tuple(
        repo.db.execute("SELECT * FROM job_items WHERE job_id=?", (job,)).fetchone()
    )
    receipt = repo.paths.write_json("deployment/receipts/synthetic.json", {"owned": "unchanged"})
    receipt_hash = hash_file(receipt)
    # Reconstruct the exact schema-4 shape with realistic existing state.
    repo.db.execute("DROP TABLE snapshot_sources")
    repo.db.execute("DROP INDEX units_logical_source")
    repo.db.execute("ALTER TABLE text_units DROP COLUMN logical_source_id")
    repo.db.execute("DROP TABLE source_descriptors")
    repo.db.execute("DELETE FROM schema_migrations WHERE version=5")
    repo.db.execute("PRAGMA user_version=4")
    paths = repo.paths
    repo.close()
    with ProjectRepository(paths) as reopened:
        assert reopened.db.execute("PRAGMA user_version").fetchone()[0] == 5
        assert reopened.page() == rows
        assert EditorDraftStore(reopened).get("draft") == saved_draft
        assert hash_file(receipt) == receipt_hash
        assert tuple(reopened.db.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()) == (
            job_before
        )
        assert (
            tuple(reopened.db.execute("SELECT * FROM job_items WHERE job_id=?", (job,)).fetchone())
            == item_before
        )
        # New projects also create an empty schema-4 backup; select the populated one.
        populated = []
        for backup in (paths.project / "backups").glob("schema-4-*.sqlite3"):
            with sqlite3.connect(backup) as db:
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                if db.execute("SELECT count(*) FROM text_units").fetchone()[0]:
                    populated.append(backup)
                    assert db.execute("PRAGMA user_version").fetchone()[0] == 4
                    assert db.execute("SELECT count(*) FROM editor_drafts").fetchone()[0] == 1
        assert len(populated) == 1


def test_schema5_failed_migration_rolls_back(repo, monkeypatch):
    import unitytranslator.repository as module

    repo.ingest([draft()], {})
    repo.db.execute("DROP TABLE snapshot_sources")
    repo.db.execute("DROP INDEX units_logical_source")
    repo.db.execute("ALTER TABLE text_units DROP COLUMN logical_source_id")
    repo.db.execute("DROP TABLE source_descriptors")
    repo.db.execute("DELETE FROM schema_migrations WHERE version=5")
    repo.db.execute("PRAGMA user_version=4")
    paths = repo.paths
    before = list(repo.db.iterdump())
    repo.close()

    class BadResource:
        def joinpath(self, name):
            return self

        def read_text(self):
            return "CREATE TABLE partial(value TEXT); INVALID SQL;"

    monkeypatch.setattr(module, "files", lambda _: BadResource())
    with pytest.raises(sqlite3.DatabaseError):
        ProjectRepository(paths)
    with sqlite3.connect(paths.project / "project.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
        assert list(db.iterdump()) == before
