import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import unitytranslator.discovery as discovery
from unitytranslator.discovery import probe_source, scan
from unitytranslator.filesystem import PolicyError, ProjectPaths, hash_file


@pytest.fixture
def paths(tmp_path: Path) -> ProjectPaths:
    game = tmp_path / "game"
    game.mkdir()
    return ProjectPaths(game, tmp_path / "project")


@pytest.mark.parametrize("suffix", ["", "child"])
def test_overlapping_roots_rejected(tmp_path: Path, suffix: str) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with pytest.raises(PolicyError):
        ProjectPaths(game, game / suffix)
    with pytest.raises(PolicyError):
        ProjectPaths(game, tmp_path)


@pytest.mark.parametrize(
    "relative",
    [
        "../escape.json",
        "C:\\escape.json",
        "report.json:hidden",
        "CON.json",
        "ambiguous. /file.json",
    ],
)
def test_output_escape_rejected(paths: ProjectPaths, relative: str) -> None:
    with pytest.raises(PolicyError):
        paths.write_json(relative, {"text": "Türkçe"})
    assert not paths.project.exists()


def test_hardlink_does_not_overwrite_original(paths: ProjectPaths) -> None:
    original = paths.game / "original.json"
    original.write_text("original", encoding="utf-8")
    paths.project.mkdir()
    output = paths.project / "report.json"
    os.link(original, output)
    before = hash_file(original)
    with pytest.raises(PolicyError):
        paths.write_json("report.json", {})
    assert hash_file(original) == before


def test_scan_and_export_preserve_game(paths: ProjectPaths) -> None:
    data = paths.game / "Example_Data"
    (data / "Managed").mkdir(parents=True)
    assembly = data / "Managed" / "Assembly-CSharp.dll"
    assembly.write_bytes(b"synthetic-not-an-assembly")
    (data / "level0").write_bytes(b"synthetic-not-a-unity-file")
    before = {p.name: hash_file(p) for p in data.rglob("*") if p.is_file()}
    report = scan(paths)
    assert report["runtime_indicators"] == ["Mono"]
    assert report["extraction"] == report["application"] == "unknown"
    path = paths.write_json("snapshots/example.json", {"report": report, "text": "Iıİi çğöşü"})
    assert json.loads(path.read_text(encoding="utf-8"))["text"] == "Iıİi çğöşü"
    assert before == {p.name: hash_file(p) for p in data.rglob("*") if p.is_file()}


def test_probe_rejects_external_input_before_worker(paths: ProjectPaths) -> None:
    with pytest.raises(ValueError):
        probe_source(paths, "../outside.assets")


def test_symlink_escape_rejected(paths: ProjectPaths) -> None:
    paths.project.mkdir()
    try:
        (paths.project / "link").symlink_to(paths.game, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink yetkisi bulunmuyor; junction testi ayrı çalışır.")
    with pytest.raises(PolicyError):
        paths.write_json("link/report.json", {})


def test_atomic_export_failure_preserves_previous_file(paths: ProjectPaths, monkeypatch) -> None:
    path = paths.write_json("exports/data.json", {"old": "Türkçe"})
    before = path.read_bytes()

    def full_disk(fd):
        raise OSError("synthetic disk full")

    monkeypatch.setattr(os, "fsync", full_disk)
    with pytest.raises(OSError):
        paths.write_json("exports/data.json", {"new": "value"})
    assert path.read_bytes() == before
    assert list(path.parent.glob(".writing-*")) == []


def test_frozen_binary_uses_private_worker_entry(paths: ProjectPaths, monkeypatch) -> None:
    source = paths.game / "synthetic.assets"
    source.write_bytes(b"synthetic")
    commands = []

    def fake_run(command, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL
        commands.append(command)
        result = {"units": [], "errors": [], "diagnostics": [], "unity_versions": []}
        return subprocess.CompletedProcess(command, 0, json.dumps(result).encode(), b"")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(discovery.subprocess, "run", fake_run)
    probe_source(paths, "synthetic.assets")
    assert commands[0][1] == "--unity-worker"
    assert "-m" not in commands[0]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows standard handle regression")
def test_worker_launch_does_not_inherit_invalid_gui_stdin(paths, monkeypatch):
    import _winapi

    source = paths.game / "invalid.assets"
    source.write_bytes(b"not a Unity asset")
    original = _winapi.GetStdHandle
    monkeypatch.setattr(
        _winapi,
        "GetStdHandle",
        lambda handle: 0xDEADBEEF if handle == _winapi.STD_INPUT_HANDLE else original(handle),
    )
    with pytest.raises(OSError) as inherited:
        subprocess.run([sys.executable, "-c", "pass"], capture_output=True, check=False)
    assert inherited.value.winerror == 6
    # The reader may reject the synthetic asset; launching it must no longer fail.
    report = probe_source(paths, "invalid.assets")
    assert report["counts"]["records"] == 0
