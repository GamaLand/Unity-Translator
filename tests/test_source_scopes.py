"""Source-set activation and schema-4 compatibility use only synthetic data."""

import sqlite3
from dataclasses import replace

import pytest
from test_frozen_projects import (
    NAMES,
    PROJECTS,
    assert_rows_preserved,
    connect,
    frozen_copy,
    table_rows,
)
from test_repository import draft

from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.repository import LATEST_SCHEMA, ProjectRepository
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


# Frozen schema-4 projects written by 0.1.0 releases (tests/fixtures/legacy-projects) replace
# reconstructing schema 4 by dropping schema-5 to schema-7 objects from a current project.
SCHEMA4 = [name for name in NAMES if PROJECTS[name]["schema"] == 4]
PRESERVED = ("work_items", "translation_revisions", "editor_drafts", "jobs", "job_items")


@pytest.mark.parametrize("name", SCHEMA4)
def test_schema4_backup_preserves_approvals_drafts_history_and_receipt(tmp_path, name):
    expect = PROJECTS[name]["expect"]
    paths = frozen_copy(tmp_path, name)
    with connect(paths.project / "project.sqlite3") as db:
        before = table_rows(db)
        # Recorded state: an approval, an editor draft and a paused job with a failed attempt.
        assert db.execute("SELECT count(*) FROM work_items WHERE status='approved'").fetchone()[0]
        assert db.execute("SELECT count(*) FROM editor_drafts").fetchone()[0] == 1
        assert db.execute(
            "SELECT count(*) FROM job_items WHERE attempts>0 AND error_code IS NOT NULL"
        ).fetchone()[0]
    # Receipts are files under the project, not rows; the frozen projects have none.
    receipt = paths.write_json("deployment/receipts/synthetic.json", {"owned": "unchanged"})
    receipt_hash = hash_file(receipt)
    with ProjectRepository(paths) as reopened:
        assert reopened.db.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA
        assert_rows_preserved(reopened.db, {table: before[table] for table in PRESERVED})
        page = {row["unit_id"]: row for row in reopened.page()}
        for row in expect["page"]:
            assert {key: page[row["unit_id"]][key] for key in row} == row
        for unit, revisions in expect["history"].items():
            assert [r["id"] for r in reopened.history(unit)["revisions"]] == revisions
        for unit, value in expect["drafts"].items():
            saved_draft = EditorDraftStore(reopened).get(unit)
            assert {key: saved_draft[key] for key in value} == value
        assert hash_file(receipt) == receipt_hash
    (backup,) = (paths.project / "backups").glob("schema-4-*.sqlite3")
    with connect(backup) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
        assert (
            db.execute("SELECT count(*) FROM text_units").fetchone()[0]
            == (expect["counts"]["text_units"])
        )
        assert db.execute("SELECT count(*) FROM editor_drafts").fetchone()[0] == 1


@pytest.mark.parametrize("name", SCHEMA4)
def test_schema5_failed_migration_rolls_back(tmp_path, name, monkeypatch):
    import unitytranslator.repository as module

    paths = frozen_copy(tmp_path, name)
    with connect(paths.project / "project.sqlite3") as db:
        before = list(db.iterdump())

    class BadResource:
        def joinpath(self, resource):
            return self

        def read_text(self):
            return "CREATE TABLE partial(value TEXT); INVALID SQL;"

    monkeypatch.setattr(module, "files", lambda _: BadResource())
    with pytest.raises(sqlite3.DatabaseError):
        ProjectRepository(paths)
    with connect(paths.project / "project.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
        assert list(db.iterdump()) == before
