"""Synthetic multi-engine discovery and deployment isolation; no engine execution."""

import json
import sys

import pytest

from unitytranslator.discovery import probe_source, scan
from unitytranslator.engines import engine_evidence, renpy_inputs
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.installation import InstallationSession
from unitytranslator.reader_adapters import deployment_adapter_for
from unitytranslator.repository import ProjectRepository


def paths_for(tmp_path):
    game = tmp_path / "game-root"
    game.mkdir()
    return ProjectPaths(game, tmp_path / "project")


def template(paths):
    directory = paths.game / "game/tl/sample"
    directory.mkdir(parents=True)
    source = directory / "dialogue.rpy"
    source.write_text('translate sample start_1234:\n    # e "Hello"\n    e ""\n')
    return source


def test_engine_hints_do_not_establish_template_or_installation_support(tmp_path):
    paths = paths_for(tmp_path)
    source = template(paths)
    before = hash_file(source)
    report = scan(paths)
    assert report["format_version"] == 1
    assert report["engine_report"]["engine"] == "renpy"
    assert report["renpy_inputs"]["source_candidates"][0]["status"] == "unverified_hint"
    capabilities = report["capabilities"]
    assert capabilities["extraction"]["reason"] == "renpy_templates_not_verified"
    assert capabilities["installation"]["status"] == "unsupported"
    assert capabilities["localization_indicators"] == ()
    assert hash_file(source) == before
    assert not paths.project.exists()


def test_archive_and_version_inspection_reads_only_literals(tmp_path):
    paths = paths_for(tmp_path)
    (paths.game / "game").mkdir()
    archive = paths.game / "game/archive.rpa"
    archive.write_bytes(b"RPA-3.0 " + b"not an executable pickle" * 20)
    (paths.game / "renpy").mkdir()
    (paths.game / "renpy/vc_version.py").write_text(
        "version = '8.1.2.23090503'\nraise RuntimeError('must never execute')\n"
    )
    before = hash_file(archive)
    report = scan(paths)
    assert report["renpy_inputs"]["version_evidence"][0]["value"] == "8.1.2.23090503"
    assert report["renpy_inputs"]["source_candidates"][0]["header"] == "RPA-3.0"
    assert report["capabilities"]["extraction"]["reason"] == "renpy_templates_required"
    assert hash_file(archive) == before
    # The archive extension alone remains a hint, even for an invalid header.
    archive.write_bytes(b"not an archive")
    assert renpy_inputs(paths.game)["source_candidates"][0]["header"] == "unknown"


def test_mixed_engine_selection_is_explicit_and_cannot_grant_installation(tmp_path):
    paths = paths_for(tmp_path)
    template(paths)
    (paths.game / "Example_Data").mkdir()
    asset = paths.game / "Example_Data/resources.assets"
    asset.write_bytes(b"synthetic")
    report = scan(paths)
    assert report["engine_report"]["engine"] == "ambiguous"
    assert report["capabilities"]["extraction"]["reason"] == "ambiguous_engine"
    with pytest.raises(ValueError, match="Ambiguous"):
        probe_source(paths, "Example_Data/resources.assets")
    assert engine_evidence(paths.game, "unity")["engine"] == "unity"
    with ProjectRepository(paths) as repo:
        installation = InstallationSession(repo)
        assert installation.adapter_kind() == "unsupported"
        with pytest.raises(ValueError, match="No built-in deployment"):
            deployment_adapter_for(installation).prepare()
        with pytest.raises(ValueError, match="not implemented"):
            installation.prepare()


@pytest.mark.parametrize("engine", ["auto", "unity", "renpy"])
@pytest.mark.parametrize("suffix", [".rpy", ".rpyc", ".rpa"])
def test_foreign_sources_never_reach_unity_worker(tmp_path, monkeypatch, engine, suffix):
    paths = paths_for(tmp_path)
    source = paths.game / ("source" + suffix)
    source.write_bytes(b"synthetic")

    def forbidden(*args, **kwargs):
        pytest.fail("Ren'Py data reached a Unity worker")

    monkeypatch.setattr("unitytranslator.discovery._probe_i2_source", forbidden)
    with pytest.raises(ValueError, match="Ren'Py input detected"):
        probe_source(paths, source.name, engine=engine)


def test_unknown_selection_and_unknown_sources_fail_closed(tmp_path):
    paths = paths_for(tmp_path)
    assert engine_evidence(paths.game)["engine"] == "unknown"
    with pytest.raises(ValueError, match="Unknown engine"):
        scan(paths, engine="os.system")
    (paths.game / "source.json").write_text("{}")
    with pytest.raises(ValueError, match="No engine"):
        probe_source(paths, "source.json")


def test_renpy_python_dialect_is_distinct_and_never_reaches_unity(tmp_path, monkeypatch):
    paths = paths_for(tmp_path)
    (paths.game / "game").mkdir()
    source = paths.game / "game/example_ren.py"
    source.write_text('raise RuntimeError("NEVER EXECUTE")')
    (source.parent / "ordinary.py").write_text('_("Not a translation input")')
    assert engine_evidence(paths.game)["engine"] == "renpy"
    candidates = renpy_inputs(paths.game)["source_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["kind"] == "renpy_python_source"
    assert candidates[0]["status"] == "unverified_hint"

    def forbidden(*args, **kwargs):
        pytest.fail("Ren'Py Python dialect reached a Unity worker")

    monkeypatch.setattr("unitytranslator.discovery._probe_i2_source", forbidden)
    for engine in ("auto", "unity", "renpy"):
        with pytest.raises(ValueError, match="_ren.py"):
            probe_source(paths, "game/example_ren.py", engine=engine)


@pytest.mark.parametrize("kind", ["unsupported", "renpy", "unknown", ""])
def test_unknown_deployment_does_not_call_unity_service(kind):
    class Installation:
        def adapter_kind(self):
            return kind

        def status(self):
            pytest.fail("Unsupported source reached Unity installation status")

        def prepare(self, **options):
            pytest.fail("Unsupported source reached Unity installation preparation")

    with pytest.raises(ValueError, match="No built-in deployment"):
        deployment_adapter_for(Installation()).prepare()


def test_renpy_scan_bounds_fail_without_partial_success(tmp_path, monkeypatch):
    paths = paths_for(tmp_path)
    template(paths)
    monkeypatch.setattr("unitytranslator.engines.MAX_ENTRIES", 1)
    with pytest.raises(ValueError, match="bounds exceeded"):
        renpy_inputs(paths.game)


def test_irrelevant_asset_reparse_entries_are_still_rejected(tmp_path, monkeypatch):
    import os
    import stat
    from contextlib import contextmanager
    from types import SimpleNamespace

    paths = paths_for(tmp_path)
    (paths.game / "game").mkdir()
    (paths.game / "game/unrelated.png").write_bytes(b"Opaque asset")
    original = os.scandir

    class ReparseEntry:
        def is_symlink(self):
            return False

        def stat(self, **kwargs):
            return SimpleNamespace(st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)

    @contextmanager
    def scan(directory):
        with original(directory) as entries:
            yield (ReparseEntry() if entry.name == "unrelated.png" else entry for entry in entries)

    monkeypatch.setattr("unitytranslator.engines.os.scandir", scan)
    with pytest.raises(ValueError, match="reparse"):
        renpy_inputs(paths.game)


def test_cli_reports_engine_and_accepts_override(tmp_path, monkeypatch, capsys):
    from unitytranslator.__main__ import main

    paths = paths_for(tmp_path)
    template(paths)
    monkeypatch.setattr(sys, "argv", [
        "unitytranslator", "scan", "--game", str(paths.game),
        "--project", str(paths.project), "--engine", "renpy",
    ])
    assert main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["engine_report"]["engine"] == "renpy"
    assert summary["capabilities"]["installation"]["status"] == "unsupported"
