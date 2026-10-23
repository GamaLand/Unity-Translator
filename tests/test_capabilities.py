"""Synthetic evidence gates for independent capability reporting."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

import unitytranslator.discovery as discovery
from unitytranslator.application import ApplicationSession
from unitytranslator.capabilities import Support, discovery_capabilities
from unitytranslator.filesystem import ProjectPaths, hash_file


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        ({}, "no_matching_reader"),
        ({"i2_scripts": [{"namespace": "I2.Loc"}]}, "no_matching_reader"),
        ({"objects": {"TextAsset": 10}}, "no_matching_reader"),
        ({"i2_candidates": [{"object": 1}]}, "no_translatable_records"),
        ({"diagnostics": [{"code": "type_tree_unavailable"}]}, "type_tree_unavailable"),
        ({"errors": [{"code": "i2_schema_error"}]}, "source_read_failed"),
        ({"units": [{"unit_id": "one"}], "errors": [{}]}, "source_read_failed"),
    ],
)
def test_unverified_or_partial_sources_fail_closed(evidence, reason):
    report = discovery_capabilities(evidence, inspected=True)
    assert report.extraction.status == Support.UNKNOWN
    assert report.extraction.reason == reason
    assert report.translation.status == Support.UNKNOWN
    assert report.export.status == report.installation.status == Support.UNKNOWN


def test_extraction_does_not_establish_export_or_installation():
    report = discovery_capabilities(
        {"units": [{"unit_id": "one"}], "i2_candidates": [{"object": 1}]}, inspected=True
    )
    assert report.extraction.status == report.translation.status == Support.SUPPORTED
    assert report.export.status == report.installation.status == Support.UNKNOWN
    assert report.installation.reason == "deployment_not_verified"
    assert report.localization_indicators == ("I2",)
    assert report.runtime_indicators == ()
    assert report.adapter_id == "i2" and report.adapter_version == "1"
    assert json.loads(json.dumps(report.to_dict()))["extraction"]["status"] == "supported"


def test_scan_keeps_hints_separate_and_shared_with_application(tmp_path):
    game = tmp_path / "game"
    data = game / "Example_Data"
    (data / "Managed").mkdir(parents=True)
    assembly = data / "Managed/Assembly-CSharp.dll"
    assembly.write_bytes(b"synthetic")
    source = data / "resources.assets"
    source.write_bytes(b"synthetic")
    before = [hash_file(assembly), hash_file(source)]
    paths = ProjectPaths(game, tmp_path / "project")
    direct = discovery.scan(paths)
    capabilities = direct["capabilities"]
    assert capabilities["runtime_indicators"] == ("Mono",)
    assert capabilities["container_indicators"] == ("serialized_asset_candidate",)
    assert capabilities["localization_indicators"] == ()
    assert all(capabilities[key]["status"] == "unknown" for key in (
        "extraction", "translation", "export", "installation"
    ))
    assert direct["application"] == direct["extraction"] == "unknown"

    async def run():
        session = ApplicationSession()
        try:
            await session.dispatch("open", {"game": str(game), "project": str(paths.project)})
            result = await session.dispatch("scan", {})
            assert result["result"]["capabilities"] == capabilities
            stored = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
            assert stored["capabilities"]["installation"]["status"] == "unknown"
        finally:
            await session.close()

    asyncio.run(run())
    assert before == [hash_file(assembly), hash_file(source)]


def test_probe_exposes_structured_reasons_and_preserves_legacy_result(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    source = game / "source.assets"
    source.write_bytes(b"synthetic")
    paths = ProjectPaths(game, tmp_path / "project")
    before = hash_file(source)

    def run(command, **kwargs):
        evidence = {
            "objects": {"TextAsset": 1}, "units": [], "errors": [],
            "diagnostics": [], "unity_versions": ["synthetic"],
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(evidence).encode(), b"")

    monkeypatch.setattr(discovery.subprocess, "run", run)
    report = discovery.probe_source(paths, "source.assets")
    assert report["extraction"] == report["application"] == "unknown"
    assert report["capabilities"]["extraction"]["reason"] == "no_matching_reader"
    assert before == report["sha256_before"] == report["sha256_after"] == hash_file(source)


def test_cli_summary_includes_independent_capabilities(tmp_path, monkeypatch, capsys):
    from unitytranslator.__main__ import main

    game = tmp_path / "game"
    game.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "unitytranslator", "scan", "--game", str(game),
        "--project", str(tmp_path / "project"),
    ])
    assert main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["capabilities"]["installation"]["status"] == "unknown"
    assert summary["capabilities"]["export"]["reason"] == "approved_selection_required"


def test_ui_shows_independent_capability_states():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from test_ui import wait_for

    from unitytranslator.ui.i18n import tr
    from unitytranslator.ui.window import MainWindow

    window = MainWindow()
    try:
        report = discovery_capabilities({"units": [{"unit_id": "one"}]}, inspected=True).to_dict()
        window.show_capabilities(report)
        text = window.discovery.toPlainText()
        assert text.count(tr("Supported")) == 2
        assert text.count(tr("Unknown")) == 2
        assert text.count("·") == 3
    finally:
        window.close()
        wait_for(QApplication.instance(), lambda: window.backend_closed)
