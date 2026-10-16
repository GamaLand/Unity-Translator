import json
from dataclasses import replace
from pathlib import Path

import pytest

from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.i2 import extract_i2
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_payload import export_runtime_payload


@pytest.fixture
def repo(tmp_path: Path):
    game = tmp_path / "game"
    managed = game / "Synthetic_Data/Managed"
    managed.mkdir(parents=True)
    (managed / "Assembly-CSharp.dll").write_bytes(b"synthetic metadata fixture")
    units = extract_i2(
        {
            "m_Name": "synthetic",
            "mLanguages": [{"Name": "English", "Code": "en"}],
            "mTerms": [{"Term": "UI/start", "TermType": 0, "Languages": ["Start {0}"]}],
        },
        "Synthetic_Data/resources.assets",
        1,
    )
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repository:
        repository.ingest(units, {})
        yield repository, units


def export(repo):
    return export_runtime_payload(
        repo,
        source_set="synthetic",
        unity_version="2017.4.19f1",
        assembly_relative="Synthetic_Data/Managed/Assembly-CSharp.dll",
        target_name="Türkçe",
    )


def test_only_current_human_approved_i2_terms_are_exported(repo) -> None:
    repository, _ = repo
    row = repository.page()[0]
    with pytest.raises(ValueError, match="onaylı"):
        export(repository)
    repository.edit(row["unit_id"], row["version"], "Başla {0} · Iıİi çğöşü")
    with pytest.raises(ValueError, match="onaylı"):
        export(repository)
    repository.approve(row["unit_id"], repository.page()[0]["version"])
    original = repository.paths.game / "Synthetic_Data/Managed/Assembly-CSharp.dll"
    before = hash_file(original)
    result = export(repository)
    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert payload["entries"][0]["text"] == "Başla {0} · Iıİi çğöşü"
    assert payload["assembly_sha256"] == before == hash_file(original)
    assert result["application"] == "unknown"
    assert result["game_written"] is False


def test_changed_source_drops_approval_and_cannot_be_applied(repo) -> None:
    repository, units = repo
    row = repository.page()[0]
    repository.edit(row["unit_id"], 0, "Başla {0}")
    repository.approve(row["unit_id"], repository.page()[0]["version"])
    repository.ingest([replace(units[0], context="new scene")], {})
    with pytest.raises(ValueError, match="onaylı"):
        export(repository)


def test_wrong_source_set_and_escaping_assembly_are_refused(repo) -> None:
    repository, _ = repo
    with pytest.raises(ValueError, match="Assembly konumu"):
        export_runtime_payload(
            repository,
            source_set="synthetic",
            unity_version="2017.4.19f1",
            assembly_relative="../Assembly-CSharp.dll",
            target_name="Türkçe",
        )
    with pytest.raises(ValueError, match="onaylı"):
        export_runtime_payload(
            repository,
            source_set="other",
            unity_version="2017.4.19f1",
            assembly_relative="Synthetic_Data/Managed/Assembly-CSharp.dll",
            target_name="Türkçe",
        )
