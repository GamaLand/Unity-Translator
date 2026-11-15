"""Frozen synthetic projects from earlier releases migrate through the numbered path.

The databases in tests/fixtures/legacy-projects were written by earlier revisions' own
code (see its README). Each test verifies the pinned bytes, works on a copy in a new
temporary directory and relinks only the copy's game folder before opening it.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

import unitytranslator.repository as module
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore
from unitytranslator.portable import PortableService
from unitytranslator.repository import LATEST_SCHEMA, MIGRATIONS, ProjectRepository

FIXTURES = Path(__file__).parent / "fixtures" / "legacy-projects"
INDEX = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
PROJECTS = {item["name"]: item for item in INDEX["fixtures"]}
NAMES = sorted(PROJECTS)
# Development schemas no release has left as a project's final schema.
UNRELEASED_SCHEMAS = {7}
TableRows = dict[str, tuple[list[str], list[tuple[object, ...]]]]


def pinned(item: dict[str, Any], key: str) -> bytes:
    data = (FIXTURES / item[key]).read_bytes()
    assert sha256(data).hexdigest() == item[key + "_sha256"], item[key]
    return data


def frozen_copy(tmp_path: Path, name: str) -> ProjectPaths:
    """Copy a verified frozen project and relink the copy to a new synthetic game folder."""
    item = PROJECTS[name]
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.sqlite3").write_bytes(pinned(item, "database"))
    (project / "project.json").write_bytes(pinned(item, "manifest"))
    paths = ProjectPaths(game, project)
    with closing(sqlite3.connect(project / "project.sqlite3")) as db:
        assert (
            db.execute("SELECT game_path FROM project").fetchone()[0]
            == (INDEX["game_path_placeholder"])
        )
        db.execute("UPDATE project SET game_path=?", (str(paths.game),))
        db.commit()
    return paths


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(path)) as db:
        yield db


def table_rows(db: sqlite3.Connection) -> TableRows:
    """Every row of every table, in rowid order, by the table's current columns."""
    tables = [
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name<>'schema_migrations' ORDER BY name"
        )
    ]
    result: TableRows = {}
    for table in tables:
        names = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
        result[table] = (
            names,
            [
                tuple(row)
                for row in db.execute(f"SELECT {','.join(names)} FROM {table} ORDER BY rowid")
            ],
        )
    return result


def assert_rows_preserved(db: sqlite3.Connection, before: TableRows) -> None:
    """Migrations only add objects and columns; every earlier value stays byte-equal."""
    for table, (names, rows) in before.items():
        current = [
            tuple(row)
            for row in db.execute(f"SELECT {','.join(names)} FROM {table} ORDER BY rowid")
        ]
        assert current == rows, table


def dump(path: Path) -> list[str]:
    with connect(path) as db:
        return list(db.iterdump())


def user_version(path: Path) -> int:
    with connect(path) as db:
        return int(db.execute("PRAGMA user_version").fetchone()[0])


def failing_step(monkeypatch: pytest.MonkeyPatch, version: int) -> None:
    """Make schema-v<version>.sql fail after its first statement has already run."""
    real_files = module.files

    class Broken:
        def read_text(self) -> str:
            return "CREATE TABLE partial_migration(value TEXT); INVALID SQL;"

    class Resources:
        def joinpath(self, name: str) -> Any:
            if name == f"schema-v{version}.sql":
                return Broken()
            return real_files("unitytranslator.resources").joinpath(name)

    monkeypatch.setattr(module, "files", lambda _: Resources())


def test_frozen_projects_cover_every_earlier_schema() -> None:
    assert INDEX["synthetic_only"] is True
    # Schema 7 has not been released; test_migrations builds schema-7 projects from the
    # frozen schema-6 projects by stopping the numbered steps at 7 and migrates them to 8.
    assert {item["schema"] for item in PROJECTS.values()} == set(range(1, LATEST_SCHEMA)) - (
        UNRELEASED_SCHEMAS
    )
    released = {item["revision"] for item in PROJECTS.values() if item["build"] == "release"}
    assert released >= {
        "9ba9495",
        "0b83e59",
        "e8d768c",
        "556bf5e",
        "41ea1da",
        "9088210",
        "bcfa3e2",
    }
    stepwise = {item["schema"] for item in PROJECTS.values() if item["build"] == "stepwise"}
    assert stepwise == {1, 2, 3}
    assert {path.suffix for path in FIXTURES.iterdir()} == {".sqlite3", ".json", ".md", ".py"}


@pytest.mark.parametrize("name", NAMES)
def test_frozen_bytes_are_pinned_and_keep_their_schema(name: str) -> None:
    item = PROJECTS[name]
    data = pinned(item, "database")
    assert data.startswith(b"SQLite format 3\0")
    assert int.from_bytes(data[60:64], "big") == item["schema"] == item["expect"]["user_version"]
    manifest = json.loads(pinned(item, "manifest"))
    assert manifest["project_id"] == item["expect"]["project_id"]
    assert manifest["database"] == "project.sqlite3"


@pytest.mark.parametrize("name", NAMES)
def test_frozen_project_migrates_with_backups_and_keeps_records(tmp_path: Path, name: str) -> None:
    item = PROJECTS[name]
    expect = item["expect"]
    schema = item["schema"]
    paths = frozen_copy(tmp_path, name)
    database = paths.project / "project.sqlite3"
    before_dump = dump(database)
    with connect(database) as db:
        before = table_rows(db)
    with ProjectRepository(paths) as repo:
        db = repo.db
        assert db.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA
        assert [
            row[0] for row in db.execute("SELECT version FROM schema_migrations ORDER BY version")
        ] == expect["migrations"] + list(range(schema + 1, LATEST_SCHEMA + 1))
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert_rows_preserved(db, before)
        assert (repo.project_id, repo.source_language, repo.target_language) == (
            expect["project_id"],
            expect["source_language"],
            expect["target_language"],
        )
        for table, count in expect["counts"].items():
            if table == "schema_migrations":
                continue  # Checked above: earlier rows plus one row per new step.
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == count, table
        assert {
            row[0]: [row[1], row[2]]
            for row in db.execute("SELECT unit_id,source_revision,active FROM text_units")
        } == expect["text_units"]
        assert {
            row[0]: list(row[1:])
            for row in db.execute(
                "SELECT unit_id,status,version,translation_revision,approved_source,"
                "approved_translation FROM work_items"
            )
        } == expect["work_items"]
        page = {row["unit_id"]: row for row in repo.page()}
        assert set(page) == {row["unit_id"] for row in expect["page"]}
        for row in expect["page"]:
            assert {key: page[row["unit_id"]][key] for key in row} == row
        for unit, revisions in expect["history"].items():
            assert [r["id"] for r in repo.history(unit)["revisions"]] == revisions
        drafts = EditorDraftStore(repo)
        for unit, value in expect["drafts"].items():
            stored = drafts.get(unit)
            assert stored is not None
            assert {key: stored[key] for key in value} == value
        assert db.execute("SELECT count(*) FROM editor_drafts").fetchone()[0] == len(
            expect["drafts"]
        )
        jobs = JobStore(repo)
        for job, value in expect["jobs"].items():
            assert {key: jobs.job(job)[key] for key in value} == value
        assert [
            row[0] for row in db.execute("SELECT id FROM glossary_versions ORDER BY id")
        ] == expect["glossary_versions"]
        assert [
            list(row)
            for row in db.execute(
                "SELECT job_id,source_id FROM job_context_sources ORDER BY job_id,source_id"
            )
        ] == expect["job_context_sources"]
        descriptors = [
            row[0] for row in db.execute("SELECT id FROM source_descriptors ORDER BY id")
        ]
        if schema >= 5:
            assert descriptors == expect["source_descriptors"]
        else:  # Schema 5 derives one legacy descriptor per source file.
            files = sorted({row[0] for row in db.execute("SELECT source_file FROM text_units")})
            assert descriptors == ["legacy-file-v1:" + path for path in files]
        assert (
            db.execute(
                "SELECT count(*) FROM text_units WHERE logical_source_id IS NULL"
            ).fetchone()[0]
            == 0
        )
        exported = {entry["unit_id"]: entry for entry in PortableService(repo).export_history()}
        assert set(exported) == set(expect["history"])
        for unit, revisions in expect["history"].items():
            assert sorted(t["id"] for t in exported[unit]["translations"]) == sorted(revisions)
            assert exported[unit]["approved_translation"] == expect["work_items"][unit][4]
    for version in range(schema, LATEST_SCHEMA):
        (backup,) = (paths.project / "backups").glob(f"schema-{version}-*.sqlite3")
        with connect(backup) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert db.execute("PRAGMA user_version").fetchone()[0] == version
            assert_rows_preserved(db, before)
        if version == schema:
            assert dump(backup) == before_dump


@pytest.mark.parametrize("name", NAMES)
def test_failure_mid_migration_rolls_back_to_the_frozen_schema(
    tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema = PROJECTS[name]["schema"]
    paths = frozen_copy(tmp_path, name)
    database = paths.project / "project.sqlite3"
    before = dump(database)
    failing_step(monkeypatch, schema + 1)
    with pytest.raises(sqlite3.DatabaseError):
        ProjectRepository(paths)
    assert user_version(database) == schema
    assert dump(database) == before  # No partial table, column, row or version survived.
    (backup,) = (paths.project / "backups").glob("*.sqlite3")
    assert backup.name.startswith(f"schema-{schema}-")
    assert dump(backup) == before
    monkeypatch.undo()
    with ProjectRepository(paths) as repo:
        assert repo.db.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA
        assert repo.project_id == PROJECTS[name]["expect"]["project_id"]


@pytest.mark.parametrize("name", [n for n in NAMES if PROJECTS[n]["schema"] < 6])
def test_each_numbered_step_commits_on_its_own(
    tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema = PROJECTS[name]["schema"]
    paths = frozen_copy(tmp_path, name)
    database = paths.project / "project.sqlite3"
    with connect(database) as db:
        before = table_rows(db)
    failing_step(monkeypatch, LATEST_SCHEMA)
    with pytest.raises(sqlite3.DatabaseError):
        ProjectRepository(paths)
    # Completed steps stay; only the failed last step was rolled back.
    assert user_version(database) == LATEST_SCHEMA - 1
    with connect(database) as db:
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='partial_migration'").fetchone()
            is None
        )
        assert_rows_preserved(db, before)
    assert sorted(
        int(path.name.split("-")[1]) for path in (paths.project / "backups").glob("*.sqlite3")
    ) == list(range(schema, LATEST_SCHEMA))
    assert len(MIGRATIONS) == LATEST_SCHEMA - 1
