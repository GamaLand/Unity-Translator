"""Shared recipient vectors: path policy and game-process classification.

The same fixture rows run against Python (filesystem, deployment and game_process) and the
recipient core inlined into a synthetic PowerShell harness. Synthetic only: no installer runs
against a game and no process is started apart from the PowerShell harness.
"""

import json
import os
import shutil
import subprocess
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from unitytranslator.deployment import DeploymentService
from unitytranslator.filesystem import (
    PolicyError,
    ProjectPaths,
    ambiguous_windows_name,
    checked_path,
    checked_relative,
)
from unitytranslator.game_process import (
    ProcessImage,
    classify_game_processes,
    inspect_game_processes,
)
from unitytranslator.recipient_scripts import MARKER, inline_core, recipient_core

FIXTURES = Path(__file__).parent / "fixtures"
LONG = {
    "x255": "x" * 255,
    "x256": "x" * 256,
    "emoji127": "\U0001f600" * 127,
    "emoji128": "\U0001f600" * 128,
}


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="ascii"))


def expand(text: str, tokens: dict[str, str]) -> str:
    for key, value in {**LONG, **tokens}.items():
        text = text.replace("{" + key + "}", value)
    return text


def outcome(call) -> str | None:
    """The accepted absolute path as text, or None when the rule refuses."""
    try:
        return str(call())
    except (ValueError, OSError):
        return None


def same_path(left: str | None, right: str) -> bool:
    return left is not None and left.casefold() == right.casefold()


def run_core(tmp_path: Path, body: str, *args: object) -> Any:
    """Run a body after the generated core in Windows PowerShell; return its JSON output."""
    powershell = shutil.which("powershell.exe")
    if sys.platform != "win32" or powershell is None:
        pytest.skip("Windows PowerShell required for the recipient core")
    host = (
        b"$ErrorActionPreference = 'Stop'\nSet-StrictMode -Version Latest\n"
        + MARKER
        + b"\n"
        + body.encode("ascii")
    )
    harness = tmp_path / "vector-harness.ps1"
    harness.write_bytes(inline_core(host, recipient_core()))
    output = tmp_path / "vector-output.json"
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
            *map(str, args),
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(output.read_text(encoding="utf-8-sig"))


def test_fixture_differences_are_documented():
    for name, rows in (
        ("recipient-paths.json", ("relative", "roots")),
        ("recipient-processes.json", ("cases",)),
    ):
        fixture = load(name)
        differences = fixture["differences"]
        # Core gaps are fixed, not documented: only intentional differences remain.
        for difference in differences.values():
            assert difference["kind"] == "intentional" and difference["reason"]
        for group in rows:
            for row in fixture[group]:
                assert row["expect"] in ("accept", "refuse", "closed", "running", "unknown")
                for key in ("difference", "legacy"):
                    assert row.get(key) is None or row[key] in differences, row
                # A core difference states the exact core result, so a stale entry fails.
                assert ("difference" in row) == ("powershell" in row), row
                if "powershell" in row:
                    assert row["powershell"] != row["expect"], row
                    assert row["powershell"] in (
                        "accept",
                        "refuse",
                        "closed",
                        "running",
                        "unknown",
                    ), row
                if row.get("legacy") or (row["expect"] == "accept" and group == "relative"):
                    assert row["target"]


def path_layout(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    if sys.platform != "win32":
        pytest.skip("Windows path semantics and junctions required")
    import _winapi

    root = tmp_path / "Target Root"
    root.mkdir()
    outside = tmp_path / "Outside"
    outside.mkdir()
    _winapi.CreateJunction(str(outside), str(root / "linked"))
    root = checked_path(root)
    tokens = {"root": str(root), "root_posix": root.as_posix(), "drive": root.drive}
    return root, tokens


def test_path_vectors_agree_between_python_and_the_recipient_core(tmp_path):
    fixture = load("recipient-paths.json")
    root, tokens = path_layout(tmp_path)
    game = tmp_path / "Unrelated Game"
    game.mkdir()
    project = ProjectPaths(game, root)
    deployment = SimpleNamespace(paths=SimpleNamespace(game=root))
    relative = [expand(row["path"], tokens) for row in fixture["relative"]]
    roots = [expand(row["path"], tokens) for row in fixture["roots"]]
    (tmp_path / "paths.json").write_text(
        json.dumps({"relative": relative, "roots": roots}), encoding="utf-8"
    )
    body = (
        "$vectors = [IO.File]::ReadAllText($args[1],[Text.Encoding]::UTF8) | ConvertFrom-Json\n"
        "$root = Checked $args[0]\n"
        "function Attempt([scriptblock]$Call) { try { & $Call } catch { 'refused' } }\n"
        "$out = @{\n"
        "    relative = @(foreach ($p in @($vectors.relative)) {\n"
        "        Attempt { Confined $root ([string]$p) } })\n"
        "    roots = @(foreach ($p in @($vectors.roots)) { Attempt { Checked ([string]$p) } })\n"
        "}\n"
        "[IO.File]::WriteAllText($args[2], (ConvertTo-Json -InputObject $out -Compress),\n"
        "    [Text.UTF8Encoding]::new($false))\n"
    )
    core = run_core(tmp_path, body, root, tmp_path / "paths.json")
    assert len(core["relative"]) == len(relative) and len(core["roots"]) == len(roots)
    failures = []
    for row, path, powershell in zip(fixture["relative"], relative, core["relative"], strict=True):
        accepted = row["expect"] == "accept"
        target = str(root.joinpath(expand(row.get("target", ""), tokens)))
        strict = outcome(partial(checked_relative, root, path))
        legacy = {
            "deployment.target": outcome(partial(DeploymentService.target, deployment, path)),
            "ProjectPaths.output": outcome(partial(project.output, path)),
        }
        if accepted != same_path(strict, target) or (not accepted and strict is not None):
            failures.append(("checked_relative", ascii(path), strict))
        legacy_accepts = accepted or row.get("legacy") == "legacy-normalizes"
        for name, result in legacy.items():
            if legacy_accepts != same_path(result, target) or (
                not legacy_accepts and result is not None
            ):
                failures.append((name, ascii(path), result))
        core_accepts = row.get("powershell", row["expect"]) == "accept"
        if core_accepts != same_path(powershell, target) or (
            not core_accepts and powershell != "refused"
        ):
            failures.append(("Confined", ascii(path), powershell))
    for row, path, powershell in zip(fixture["roots"], roots, core["roots"], strict=True):
        accepted = row["expect"] == "accept"
        python = outcome(partial(checked_path, Path(path)))
        if accepted != (python is not None):
            failures.append(("checked_path", ascii(path), python))
        core_accepts = row.get("powershell", row["expect"]) == "accept"
        if core_accepts != same_path(powershell, str(Path(python or path))) or (
            not core_accepts and powershell != "refused"
        ):
            failures.append(("Checked", ascii(path), powershell))
    assert failures == []


def test_checked_relative_keeps_existing_messages_and_one_name_rule(tmp_path):
    root = tmp_path / "Root"
    root.mkdir()
    for path, message in (
        ("", "must be relative and inside its root"),
        ("C:a", "must be relative and inside its root"),
        ("/a", "must be relative and inside its root"),
        ("dir/a:b", "alternate data streams"),
        ("a:b", "must be relative and inside its root"),
        ("a/../b", "Parent directory traversal"),
        ("a/./b", "Reserved or ambiguous"),
        ("nul .txt", "Reserved or ambiguous"),
    ):
        with pytest.raises(PolicyError, match=message):
            checked_relative(root, path)
    assert checked_relative(root, "dir\\a.txt") == checked_path(root / "dir/a.txt")
    for name in ("CONIN$", "com\u00b9.log", "a\x85", "a\u00a0", "a?", "x" * 256):
        assert ambiguous_windows_name(name)
        with pytest.raises(PolicyError, match="Reserved or ambiguous"):
            checked_path(root / name)
    for name in ("COM0", "CONSOLE", "\u00a0a", "x" * 255, "\U0001f600" * 127 + "x"):
        assert not ambiguous_windows_name(name)


def process_layout(tmp_path: Path) -> dict[str, str]:
    game = tmp_path / "Game Root"
    (game / "bin").mkdir(parents=True)
    (game / "Game.exe").write_bytes(b"synthetic EXE; never executed")
    other = tmp_path / "Other Install"
    other.mkdir()
    sibling = tmp_path / "Game Root Two"
    sibling.mkdir()
    root = str(checked_path(game))
    return {
        "root": root,
        "root_upper": root.upper(),
        "root_lower": root.lower(),
        "root_posix": root.replace("\\", "/"),
        "other": str(checked_path(other)),
        "sibling": str(checked_path(sibling)),
        "drive": Path(root).drive,
    }


def test_process_vectors_agree_between_python_and_the_recipient_core(tmp_path):
    fixture = load("recipient-processes.json")
    tokens = process_layout(tmp_path)
    cases = []
    failures = []
    for row in fixture["cases"]:
        rows = [(item["name"], item["image"]) for item in row["snapshot"]]
        rows = [
            (expand(name, tokens), None if image is None else expand(image, tokens))
            for name, image in rows
        ]
        snapshot = tuple(
            ProcessImage(pid, name, None if image is None else Path(image))
            for pid, (name, image) in enumerate(rows, start=10)
        )
        names = set(row["names"] or ())
        python = classify_game_processes(Path(tokens["root"]), names, snapshot).status
        if python != row["expect"]:
            failures.append(("python", row["id"], python))
        cases.append(
            {
                "names": row["names"],
                "snapshot": [{"name": name, "image": image} for name, image in rows],
            }
        )
    (tmp_path / "processes.json").write_text(json.dumps(cases), encoding="utf-8")
    body = (
        "$cases = [IO.File]::ReadAllText($args[1],[Text.Encoding]::UTF8) | ConvertFrom-Json\n"
        "$root = Checked $args[0]\n"
        "$result = @(foreach ($case in @($cases)) {\n"
        "    $names = $null\n"
        "    if ($null -ne $case.names) { $names = [string[]]@($case.names) }\n"
        "    GameProcessStatus $root $names @($case.snapshot)\n"
        "})\n"
        "[IO.File]::WriteAllText($args[2], (ConvertTo-Json -InputObject $result -Compress),\n"
        "    [Text.UTF8Encoding]::new($false))\n"
    )
    core = run_core(tmp_path, body, tokens["root"], tmp_path / "processes.json")
    assert len(core) == len(fixture["cases"])
    for row, status in zip(fixture["cases"], core, strict=True):
        if status != row.get("powershell", row["expect"]):
            failures.append(("powershell", row["id"], status))
    assert failures == []


def test_executable_walk_fails_closed_on_an_unreadable_directory(tmp_path, monkeypatch):
    game = tmp_path / "Walk Game"
    (game / "Locked").mkdir(parents=True)
    (game / "Game.exe").write_bytes(b"synthetic EXE; never executed")
    locked = os.path.normcase(str(checked_path(game / "Locked")))
    real = os.scandir

    def scandir(path):
        if os.path.normcase(os.fspath(path)) == locked:
            raise PermissionError(13, "synthetic access denied", os.fspath(path))
        return real(path)

    def snapshot():
        return ()

    monkeypatch.setattr(os, "scandir", scandir)
    monkeypatch.setattr("unitytranslator.game_process.windows_process_snapshot", snapshot)
    result = inspect_game_processes(game)
    assert result.status == "unknown"
    assert result.reason == "game_tree_uninspectable"
    monkeypatch.setattr(os, "scandir", real)
    assert inspect_game_processes(game).status == "closed"
