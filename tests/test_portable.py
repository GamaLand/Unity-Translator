import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_repository import draft

from unitytranslator.filesystem import ProjectPaths
from unitytranslator.portable import PortableService
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def repo(tmp_path: Path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repository:
        repository.ingest([draft()], {})
        yield repository


def translated_export(repo: ProjectRepository):
    item = repo.page()[0]
    repo.candidate(
        item["unit_id"],
        item["source_revision"],
        item["version"],
        "Başla",
        "model",
        {"profile": {"address": "http://localhost:1234", "model": "synthetic"}},
        [],
    )
    service = PortableService(repo)
    return service, service.read(service.export())


def test_export_sanitizes_profile_and_import_is_idempotent(repo: ProjectRepository) -> None:
    service, value = translated_export(repo)
    assert "address" not in value.units[0].translation.metadata["profile"]
    assert service.apply(value)["applied"] == 1
    count = repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0]
    version = repo.page()[0]["version"]
    assert service.apply(value)["applied"] == 1
    assert repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == count
    assert repo.page()[0]["version"] == version


def test_approved_translation_and_changed_source_not_overwritten(repo: ProjectRepository) -> None:
    service, value = translated_export(repo)
    row = repo.page()[0]
    repo.approve(row["unit_id"], row["version"])
    value.units[0].translation.text = "Different import"
    preview = service.preview(value)
    assert preview["approved_conflicts"] == [row["unit_id"]]
    assert service.apply(value)["applied"] == 0
    assert repo.page()[0]["translation"] == "Başla"
    value.units[0].source_text = "Forged source"
    with pytest.raises(ValueError, match="arşiviyle"):
        service.preview(value)


def test_imported_metadata_never_creates_provider_or_runs_command(repo: ProjectRepository) -> None:
    service, value = translated_export(repo)
    value.units[0].translation.metadata = {
        "command": "do-not-run",
        "address": "https://example.com",
    }
    value.units[0].translation.approved = True
    assert service.apply(value)["applied"] == 1
    assert repo.page()[0]["status"] == "translated"
    assert repo.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_unknown_fields_and_duplicate_ids_rejected_before_write(
    repo: ProjectRepository, tmp_path: Path
) -> None:
    service, value = translated_export(repo)
    payload = value.model_dump()
    payload["server"] = "https://example.com"
    path = tmp_path / "untrusted.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        service.read(path)
    payload.pop("server")
    payload["units"] *= 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        service.read(path)


def test_duplicate_json_fields_and_nonstandard_numbers_rejected(repo, tmp_path: Path) -> None:
    service, value = translated_export(repo)
    text = value.model_dump_json()
    path = tmp_path / "duplicate.json"
    path.write_text(text[:-1] + ',"format_version":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="Yinelenen"):
        service.read(path)
    value.units[0].translation.metadata = {"untrusted": float("nan")}
    path.write_text(json.dumps(value.model_dump()), encoding="utf-8")
    with pytest.raises(ValueError, match="Standart"):
        service.read(path)


def test_complete_revision_history_restores_to_empty_project_without_local_approval(
    repo: ProjectRepository,
    tmp_path: Path,
) -> None:
    service, _ = translated_export(repo)
    repo.edit("UI/start", repo.page()[0]["version"], "Elle düzenleme")
    repo.approve("UI/start", repo.page()[0]["version"])
    repo.ingest([replace(draft(), context="New scene")], {})
    repo.edit("UI/start", repo.page()[0]["version"], "Yeni sahne")
    repo.approve("UI/start", repo.page()[0]["version"])
    value = service.read(service.export())
    assert len(value.history[0].sources) == 2
    assert len(value.history[0].translations) == 3
    assert value.history[0].approved_translation is not None
    with ProjectRepository(ProjectPaths(repo.paths.game, tmp_path / "restored")) as restored:
        target = PortableService(restored)
        assert target.preview(value)["restore_available"] is True
        assert target.restore(value)["restored_units"] == 1
        assert restored.page()[0]["translation"] == "Yeni sahne"
        assert restored.page()[0]["status"] != "approved"
        assert restored.db.execute("SELECT count(*) FROM source_revisions").fetchone()[0] == 2
        assert restored.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        exported = target.read(target.export())
        assert exported.history[0].imported_reviews[0]["translation_revision"] == (
            value.history[0].approved_translation
        )
        source_time = {s.id: s.created_at for s in value.history[0].sources}
        assert {s.id: s.created_at for s in exported.history[0].sources} == source_time
        count = restored.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0]
        target.apply(value)
        target.apply(value)
        assert (
            restored.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == count
        )
        with pytest.raises(ValueError, match="boş projede"):
            target.restore(value)


def test_archive_collision_rolls_back_all_import_changes(repo: ProjectRepository) -> None:
    service, value = translated_export(repo)
    value.history[0].translations[0].text = "Forged revision with same id"
    version = repo.page()[0]["version"]
    with pytest.raises(ValueError, match="çakışıyor"):
        service.apply(value)
    assert repo.page()[0]["version"] == version
    assert repo.page()[0]["translation"] == "Başla"


def test_v1_json_remains_importable(repo: ProjectRepository, tmp_path: Path) -> None:
    service, value = translated_export(repo)
    payload = value.model_dump()
    payload["format_version"] = 1
    payload.pop("history")
    path = tmp_path / "v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.apply(service.read(path))["applied"] == 1


def test_inactive_units_are_preserved_in_archive_restore(
    repo: ProjectRepository, tmp_path: Path
) -> None:
    repo.ingest([draft(), draft("UI/removed", "Removed")], {})
    repo.ingest([draft()], {})
    service = PortableService(repo)
    value = service.read(service.export())
    assert len(value.units) == 1
    assert len(value.history) == 2
    with ProjectRepository(
        ProjectPaths(repo.paths.game, tmp_path / "inactive-restore")
    ) as restored:
        PortableService(restored).restore(value)
        assert restored.count() == 1
        assert restored.db.execute("SELECT count(*) FROM text_units").fetchone()[0] == 2
