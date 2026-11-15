import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from test_frozen_projects import NAMES, PROJECTS, frozen_copy
from test_repository import draft

import unitytranslator.repository as module
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.portable import PortableService
from unitytranslator.repository import LATEST_SCHEMA, ProjectRepository

SCHEMA7_INDEXES = ("source_revisions_unit", "translation_revisions_source", "units_review_order")
# Frozen schema-6 projects written by 0.6.0, 0.6.1 and 0.7.0 replace rebuilding schema 6
# by dropping the schema-7 indexes from a current project.
SCHEMA6 = [name for name in NAMES if PROJECTS[name]["schema"] == 6]


def snapshot_rows(db: sqlite3.Connection) -> dict[str, list[tuple[object, ...]]]:
    tables = [
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name<>'schema_migrations' ORDER BY name"
        )
    ]
    return {
        table: [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        for table in tables
    }


def populated(paths: ProjectPaths) -> ProjectRepository:
    repo = ProjectRepository(paths)
    repo.ingest([draft("UI/a", "Start"), draft("UI/b", "Options"), draft("UI/c", "Quit")], {})
    repo.ingest([draft("UI/a", "Start game"), draft("UI/b", "Options")], {})
    for row in repo.page():
        repo.candidate(
            row["unit_id"],
            row["source_revision"],
            row["version"],
            "Çeviri " + row["unit_id"],
            "model",
            {"run_id": "synthetic"},
            [],
        )
    first = repo.page()[0]
    repo.approve(first["unit_id"], first["version"])
    second = repo.page()[1]
    EditorDraftStore(repo).put(
        second["unit_id"], second["source_revision"], second["version"], "Taslak", 0
    )
    return repo


def test_schema1_migration_has_consistent_backups_and_preserves_identity(tmp_path: Path) -> None:
    (name,) = [name for name in NAMES if PROJECTS[name]["schema"] == 1]
    paths = frozen_copy(tmp_path, name)
    with ProjectRepository(paths) as repo:
        assert repo.project_id == PROJECTS[name]["expect"]["project_id"]
        assert repo.db.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA
    for version in range(1, LATEST_SCHEMA):
        (backup,) = (paths.project / "backups").glob(f"schema-{version}-*.sqlite3")
        with closing(sqlite3.connect(backup)) as db:
            assert db.execute("PRAGMA user_version").fetchone()[0] == version
            assert db.execute("SELECT id FROM project").fetchone()[0] == repo.project_id
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_newer_schema_is_rejected_without_database_mutation(tmp_path: Path) -> None:
    paths = frozen_copy(tmp_path, SCHEMA6[0])
    with closing(sqlite3.connect(paths.project / "project.sqlite3")) as db:
        db.execute("PRAGMA user_version=999")
    before = hash_file(paths.project / "project.sqlite3")
    with pytest.raises(ValueError, match="Unknown or newer project schema; writing was refused"):
        ProjectRepository(paths)
    assert hash_file(paths.project / "project.sqlite3") == before


@pytest.mark.parametrize("name", SCHEMA6)
def test_schema7_adds_indexes_without_changing_frozen_schema6_project(
    tmp_path: Path, name: str
) -> None:
    expect = PROJECTS[name]["expect"]
    paths = frozen_copy(tmp_path, name)
    with closing(sqlite3.connect(paths.project / "project.sqlite3")) as db:
        rows = snapshot_rows(db)
        objects = set(db.execute("SELECT type,name FROM sqlite_master"))
    with ProjectRepository(paths) as reopened:
        assert reopened.db.execute("PRAGMA user_version").fetchone()[0] == 7
        current = reopened.db.execute("SELECT type,name FROM sqlite_master")
        added = {tuple(row) for row in current} - objects
        assert added == {("index", index) for index in SCHEMA7_INDEXES}
        assert snapshot_rows(reopened.db) == rows
        page = {row["unit_id"]: row for row in reopened.page()}
        for row in expect["page"]:
            assert {key: page[row["unit_id"]][key] for key in row} == row
        for unit, revisions in expect["history"].items():
            assert [r["id"] for r in reopened.history(unit)["revisions"]] == revisions
        drafts = EditorDraftStore(reopened)
        for unit, value in expect["drafts"].items():
            stored = drafts.get(unit)
            assert stored is not None and {key: stored[key] for key in value} == value
        exported = PortableService(reopened).export_history()
        assert {item["unit_id"] for item in exported} == set(expect["history"])
    (backup,) = (paths.project / "backups").glob("schema-6-*.sqlite3")
    with closing(sqlite3.connect(backup)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA user_version").fetchone()[0] == 6
        assert snapshot_rows(db) == rows


@pytest.mark.parametrize("name", SCHEMA6)
def test_failed_schema7_migration_keeps_frozen_schema6_project(
    tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = frozen_copy(tmp_path, name)
    with closing(sqlite3.connect(paths.project / "project.sqlite3")) as db:
        before = list(db.iterdump())
    real_files = module.files

    class BadSql:
        def read_text(self) -> str:
            return "CREATE INDEX partial ON text_units(unit_id); INVALID SQL;"

    class Resources:
        def joinpath(self, name: str) -> Any:
            return (
                BadSql()
                if name == "schema-v7.sql"
                else real_files("unitytranslator.resources").joinpath(name)
            )

    monkeypatch.setattr(module, "files", lambda _: Resources())
    with pytest.raises(sqlite3.DatabaseError):
        ProjectRepository(paths)
    with closing(sqlite3.connect(paths.project / "project.sqlite3")) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 6
        assert list(db.iterdump()) == before
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    (backup,) = (paths.project / "backups").glob("schema-6-*.sqlite3")
    with closing(sqlite3.connect(backup)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert list(db.iterdump()) == before


def test_history_lookups_use_schema7_indexes(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with populated(ProjectPaths(game, tmp_path / "project")) as repo:

        def plan(sql: str, *parameters: object) -> str:
            return " ".join(
                str(row[3]) for row in repo.db.execute("EXPLAIN QUERY PLAN " + sql, parameters)
            )

        history = plan(
            "SELECT t.*,s.source_text,s.context FROM translation_revisions t "
            "JOIN source_revisions s ON s.id=t.source_revision WHERE s.unit_id=? "
            "ORDER BY t.created_at DESC,t.rowid DESC LIMIT 200",
            "UI/a",
        )
        assert "source_revisions_unit" in history
        assert "translation_revisions_source" in history

        def page_plan(**filters: Any) -> str:
            statements: list[str] = []
            repo.db.set_trace_callback(statements.append)
            try:
                repo.page(0, **filters)
            finally:
                repo.db.set_trace_callback(None)
            (statement,) = [item for item in statements if "LIMIT" in item]
            return plan(statement)

        unfiltered = page_plan()
        assert "units_review_order" in unfiltered and "TEMP B-TREE" not in unfiltered
        # Selective filters keep the schema-6 scan-and-sort plan instead of an index walk.
        for selective in (page_plan(search="Opt"), page_plan(affected=True)):
            assert "units_review_order" not in selective and "TEMP B-TREE" in selective


def test_set_based_history_export_matches_per_unit_reference(tmp_path: Path) -> None:
    from unitytranslator.portable import portable_metadata

    game = tmp_path / "game"
    game.mkdir()
    with populated(ProjectPaths(game, tmp_path / "project")) as repo:
        db = repo.db
        expected = []
        for unit in db.execute(
            "SELECT u.*,w.translation_revision,w.approved_source,w.approved_translation "
            "FROM text_units u JOIN work_items w USING(unit_id) ORDER BY u.unit_id"
        ).fetchall():
            sources = [
                {
                    key: row[key]
                    for key in (
                        "id",
                        "source_text",
                        "source_hash",
                        "category",
                        "context",
                        "created_at",
                    )
                }
                for row in db.execute(
                    "SELECT * FROM source_revisions WHERE unit_id=? ORDER BY created_at,id",
                    (unit["unit_id"],),
                )
            ]
            translations = [
                {
                    **{
                        key: row[key]
                        for key in ("id", "source_revision", "text", "origin", "created_at")
                    },
                    "metadata": portable_metadata(json.loads(row["metadata_json"])),
                    "issues": json.loads(row["issues_json"]),
                }
                for row in db.execute(
                    "SELECT t.* FROM translation_revisions t JOIN source_revisions s "
                    "ON s.id=t.source_revision WHERE s.unit_id=? ORDER BY t.created_at,t.id",
                    (unit["unit_id"],),
                )
            ]
            expected.append(
                {
                    **{
                        key: unit[key]
                        for key in (
                            "unit_id",
                            "original_key",
                            "source_file",
                            "source_object",
                            "approved_source",
                            "approved_translation",
                        )
                    },
                    "active": bool(unit["active"]),
                    "current_source": unit["source_revision"],
                    "current_translation": unit["translation_revision"],
                    "sources": sources,
                    "translations": translations,
                    "imported_reviews": [],
                }
            )
        exported = PortableService(repo).export_history()
        assert exported == expected
        assert [len(item["sources"]) for item in exported] == [2, 1, 1]
        assert not exported[2]["active"]


def test_candidate_identity_matches_stored_revision(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with populated(ProjectPaths(game, tmp_path / "project")) as repo:
        row = repo.page()[1]
        identity, metadata = repo.candidate_identity(
            row["unit_id"], row["source_revision"], "Yeni", "model", {"run_id": "x"}
        )
        assert repo.candidate(
            row["unit_id"],
            row["source_revision"],
            row["version"],
            "Yeni",
            "model",
            {"run_id": "x"},
            [],
        )
        stored = repo.db.execute(
            "SELECT metadata_json FROM translation_revisions WHERE id=?", (identity,)
        ).fetchone()
        assert stored is not None and json.loads(stored[0]) == metadata
