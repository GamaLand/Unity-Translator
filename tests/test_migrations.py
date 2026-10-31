import sqlite3
from importlib.resources import files
from pathlib import Path

import pytest

import unitytranslator.repository as module
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.repository import ProjectRepository


def old_project(tmp_path: Path) -> ProjectPaths:
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    paths = ProjectPaths(game, project)
    db = sqlite3.connect(project / "project.sqlite3")
    db.executescript(files("unitytranslator.resources").joinpath("schema-v1.sql").read_text())
    db.execute("PRAGMA user_version=1")
    db.execute("INSERT INTO schema_migrations VALUES(1,'synthetic')")
    db.execute(
        "INSERT INTO project VALUES('original-id','en','tr',?,'synthetic')", (str(paths.game),)
    )
    db.commit()
    db.close()
    return paths


def test_migration_has_consistent_backup_and_preserves_identity(tmp_path: Path) -> None:
    paths = old_project(tmp_path)
    with ProjectRepository(paths) as repo:
        assert repo.project_id == "original-id"
        assert repo.db.execute("PRAGMA user_version").fetchone()[0] == 6
    backups = list((paths.project / "backups").glob("schema-1-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
        assert backup.execute("SELECT id FROM project").fetchone()[0] == "original-id"
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_failed_migration_rolls_back_and_does_not_open_new_schema(
    tmp_path: Path, monkeypatch
) -> None:
    paths = old_project(tmp_path)

    class BrokenResource:
        def joinpath(self, name):
            return self

        def read_text(self):
            return "CREATE TABLE partial(value TEXT); INVALID SQL;"

    monkeypatch.setattr(module, "files", lambda _: BrokenResource())
    with pytest.raises(sqlite3.DatabaseError):
        ProjectRepository(paths)
    with sqlite3.connect(paths.project / "project.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT name FROM sqlite_master WHERE name='partial'").fetchone() is None
    assert list((paths.project / "backups").glob("*.sqlite3"))


def test_newer_schema_is_rejected_without_database_mutation(tmp_path: Path) -> None:
    paths = old_project(tmp_path)
    with sqlite3.connect(paths.project / "project.sqlite3") as db:
        db.execute("PRAGMA user_version=999")
    before = hash_file(paths.project / "project.sqlite3")
    with pytest.raises(ValueError, match="yeni"):
        ProjectRepository(paths)
    assert hash_file(paths.project / "project.sqlite3") == before
