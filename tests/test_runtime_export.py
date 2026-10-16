import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_runtime_payload import repo as repo_fixture  # noqa: F401

from unitytranslator.application import ApplicationSession
from unitytranslator.runtime_export import export_selected_runtime


@pytest.fixture
def selected(repo_fixture):  # noqa: F811 — pytest fixture injection
    repo, units = repo_fixture
    repo.ingest(
        units,
        {
            "source": units[0].source_file,
            "unity_versions": ["2017.4.19f1"],
            "i2_candidates": [{"object": units[0].source_object, "source_set": "synthetic"}],
        },
    )
    row = repo.page()[0]
    repo.edit(row["unit_id"], row["version"], "Başla {0}")
    repo.approve(row["unit_id"], repo.page()[0]["version"])
    row = repo.page()[0]
    selection = [
        {key: row[key] for key in ("unit_id", "source_revision", "translation_revision", "version")}
    ]
    return repo, units, selection


def test_selected_export_discovers_source_without_game_specific_defaults(selected):
    repo, _, records = selected
    result = export_selected_runtime(repo, records)
    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert result["records"] == 1 and result["game_written"] is False
    assert result["application"] == "unknown"
    assert payload["entries"][0]["source_set"] == "synthetic"
    assert payload["entries"][0]["text"] == "Başla {0}"
    again = export_selected_runtime(repo, records)
    assert again["path"] != result["path"]
    assert Path(result["path"]).exists()


@pytest.mark.parametrize("change", ["edit", "duplicate", "empty", "limit", "unknown"])
def test_invalid_or_changed_review_selection_is_not_exported(selected, change):
    repo, _, records = selected
    if change == "edit":
        repo.edit(records[0]["unit_id"], records[0]["version"], "Başlat {0}")
        repo.approve(records[0]["unit_id"], repo.page()[0]["version"])
    elif change == "duplicate":
        records = records * 2
    elif change == "empty":
        records = []
    elif change == "limit":
        records = [{**records[0], "unit_id": str(i)} for i in range(11)]
    else:
        records[0]["unit_id"] = "unknown"
    with pytest.raises(ValueError):
        export_selected_runtime(repo, records)
    assert not list(repo.paths.project.glob("artifacts/i2mono/selection-*.json"))


def test_legacy_missing_source_name_requires_reextraction(selected):
    repo, units, records = selected
    repo.ingest(units, {"source": units[0].source_file, "unity_versions": ["2017.4.19f1"]})
    with pytest.raises(ValueError, match="yeniden çıkarın"):
        export_selected_runtime(repo, records)
    assert repo.page()[0]["status"] == "approved"


def test_application_runtime_export_requires_same_project_and_returns_request_identity(selected):
    repo, _, records = selected
    session = ApplicationSession()
    session.repository = repo
    with pytest.raises(ValueError, match="proje kimliği"):
        asyncio.run(session.dispatch("runtime_export", {"project_id": "other", "records": records}))
    result = asyncio.run(
        session.dispatch(
            "runtime_export",
            {
                "project_id": repo.project_id,
                "request_token": "chosen-request",
                "records": records,
            },
        )
    )
    assert result["project_id"] == repo.project_id
    assert result["request_token"] == "chosen-request"


def test_equal_snapshot_times_use_latest_ingest_not_uuid_order(selected, monkeypatch):
    repo, units, records = selected
    metadata = {
        "source": units[0].source_file,
        "unity_versions": ["2017.4.19f1"],
        "i2_candidates": [{"object": units[0].source_object, "source_set": "synthetic"}],
    }
    monkeypatch.setattr("unitytranslator.repository.now", lambda: "2099-01-01T00:00:00+00:00")
    monkeypatch.setattr("unitytranslator.repository.uuid4", lambda: SimpleNamespace(hex="0" * 32))
    repo.ingest(units, {})
    monkeypatch.setattr("unitytranslator.repository.uuid4", lambda: SimpleNamespace(hex="f" * 32))
    repo.ingest(units, metadata)
    assert export_selected_runtime(repo, records)["records"] == 1
