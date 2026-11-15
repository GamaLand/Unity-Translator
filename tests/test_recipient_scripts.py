"""Shared recipient core: build-time inlining and the PowerShell process classifier.

Synthetic only. No installer runs against a game and no process is started.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from unitytranslator.game_process import ProcessImage, classify_game_processes
from unitytranslator.recipient_scripts import (
    DEPENDENT,
    INLINED,
    MARKER,
    inline_core,
    installer_bytes,
    recipient_core,
)

RESOURCES = Path(__file__).parents[1] / "src/unitytranslator/resources"


def carries_core(script: bytes) -> bool:
    """True when a shipped script holds the whole core once and no marker line."""
    text = b"\n".join(script.removeprefix(b"\xef\xbb\xbf").splitlines())
    core = b"\n".join(recipient_core().splitlines())
    return text.count(core) == 1 and MARKER not in script


def test_generator_inlines_the_core_exactly_once_and_deterministically():
    for name in INLINED:
        script = installer_bytes(name)
        assert script == installer_bytes(name)
        assert carries_core(script)
        assert script.count(b"public static class RecipientIdentity") == 1
        assert script.count(b"function GameClosed(") == 1
    for name in DEPENDENT:
        script = installer_bytes(name)
        assert script == (RESOURCES / name).read_bytes() and not carries_core(script)
    host = b"param()\r\n" + MARKER + b"\r\nWrite-Output 1\r\n"
    built = inline_core(host, b"# a\n# b\n")
    assert built == b"param()\r\n# a\r\n# b\r\nWrite-Output 1\r\n"
    assert inline_core(b"x\n" + MARKER + b"\n", b"# a\r\n") == b"x\n# a\n"
    for broken in (
        b"param()\n",
        MARKER + b"\n" + MARKER + b"\n",
        b"  " + MARKER + b"\n",
        MARKER + b" extra\n",
        MARKER + b"\n# " + MARKER + b"\n",
    ):
        with pytest.raises(ValueError, match="exactly once"):
            inline_core(broken, b"# core\n")
    with pytest.raises(ValueError, match="bundled installer"):
        inline_core(MARKER + b"\n", MARKER + b"\n")
    with pytest.raises(ValueError, match="bundled installer"):
        installer_bytes("recipient-core.ps1")


def test_core_is_ascii_and_installers_no_longer_duplicate_identity_code():
    # Windows PowerShell 5.1 reads BOM-less scripts with the ANSI code page.
    recipient_core().decode("ascii")
    for name in (*INLINED, *DEPENDENT):
        raw = (RESOURCES / name).read_bytes()
        assert b"PatchFileIdentity" not in raw and b"RenpyCopyIdentity" not in raw
        assert b"class RecipientIdentity" not in raw and b"function Checked(" not in raw
        assert b"function Digest(" not in raw and b"function GameClosed(" not in raw
    assert b"Add-Type -TypeDefinition" not in (RESOURCES / "patch-installer.ps1").read_bytes()
    copy = (RESOURCES / "renpy-copy.ps1").read_bytes()
    assert copy.count(b"public static class") == 1 and b"class RenpyCopyFormat" in copy


def run_core(tmp_path: Path, body: str, *args: object) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("powershell.exe")
    if sys.platform != "win32" or powershell is None:
        pytest.skip("Windows PowerShell required for the recipient core")
    host = (
        b"$ErrorActionPreference = 'Stop'\nSet-StrictMode -Version Latest\n"
        + MARKER
        + b"\n"
        + body.encode("ascii")
    )
    harness = tmp_path / "core-harness.ps1"
    harness.write_bytes(inline_core(host, recipient_core()))
    return subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
            *map(str, args),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=120,
        check=False,
    )


def test_process_classifier_matches_python_vectors(tmp_path):
    game = tmp_path / "Game Root"
    (game / "bin").mkdir(parents=True)
    (game / "Game.exe").write_bytes(b"synthetic EXE; never executed")
    other = tmp_path / "Other Install"
    other.mkdir()
    root = str(game)
    names = {"Game.exe", "Crash.exe"}
    cases = [
        ("closed", names, []),
        ("running", names, [("Game.exe", game / "Game.exe")]),
        ("running", names, [("Helper.exe", game / "bin/Helper.exe")]),
        ("closed", names, [("Game.exe", other / "Game.exe")]),
        ("unknown", names, [("game.EXE", None)]),
        ("closed", names, [("Unrelated.exe", None)]),
        ("unknown", names, [("Crash.exe", Path("Crash.exe"))]),
        ("closed", names, [("Tool.exe", Path("Tool.exe"))]),
        ("unknown", names, [("Tool.exe", Path(root + "\\bin\\..\\Tool.exe"))]),
        ("unknown", names, [("Game.exe", Path(str(other) + "\\NUL.exe"))]),
        ("closed", names, [("Tool.exe", Path(str(other) + "\\NUL.exe"))]),
        ("unknown", names, [("Game.exe", Path("\\\\server\\share\\Game.exe"))]),
        ("running", names, [("Game.exe", None), ("Helper.exe", game / "bin/Helper.exe")]),
        ("unknown", set(), [("Game.exe", game / "Game.exe")]),
    ]
    vectors = []
    for expected, executable_names, rows in cases:
        snapshot = tuple(
            ProcessImage(pid, name, image) for pid, (name, image) in enumerate(rows, start=10)
        )
        assert classify_game_processes(game, executable_names, snapshot).status == expected
        vectors.append(
            {
                "names": sorted(executable_names),
                "snapshot": [
                    {"name": name, "image": None if image is None else str(image)}
                    for name, image in rows
                ],
            }
        )
    vectors.append({"names": None, "snapshot": []})
    (tmp_path / "vectors.json").write_text(json.dumps(vectors), encoding="utf-8")
    body = (
        "$cases = [IO.File]::ReadAllText($args[1],[Text.Encoding]::UTF8) | ConvertFrom-Json\n"
        "$root = Checked $args[0]\n"
        "$result = @(foreach ($case in $cases) {\n"
        "    $names = $null\n"
        "    if ($null -ne $case.names) { $names = [string[]]@($case.names) }\n"
        "    GameProcessStatus $root $names @($case.snapshot)\n"
        "})\n"
        "Write-Output (ConvertTo-Json -InputObject $result -Compress)\n"
    )
    completed = run_core(tmp_path, body, game, tmp_path / "vectors.json")
    assert completed.returncode == 0, completed.stderr
    expected = [case[0] for case in cases] + ["unknown"]
    assert json.loads(completed.stdout) == expected


def test_executable_walk_and_live_check_fail_closed(tmp_path):
    game = tmp_path / "Walk Game"
    (game / "Data/Plugins").mkdir(parents=True)
    (game / "Game.exe").write_bytes(b"synthetic EXE; never executed")
    (game / "Data/Plugins/crash.EXE").write_bytes(b"synthetic EXE; never executed")
    (game / "Data/readme.txt").write_bytes(b"text")
    (game / ".exe").write_bytes(b"not an executable name")
    empty = tmp_path / "No Executable"
    empty.mkdir()
    (empty / "data.bin").write_bytes(b"data")
    linked = tmp_path / "Linked Game"
    linked.mkdir()
    (linked / "Game.exe").write_bytes(b"synthetic EXE; never executed")
    outside = tmp_path / "Outside"
    outside.mkdir()
    if sys.platform != "win32":
        pytest.skip("Windows junctions required")
    import _winapi

    _winapi.CreateJunction(str(outside), str(linked / "junction"))
    body = (
        "function Names($Root,$Limit) {\n"
        "    $names = [RecipientProcess]::ExecutableNames((Checked $Root),$Limit)\n"
        "    if ($null -eq $names) { return 'unknown' }\n"
        "    return (@($names | Sort-Object) -join '|')\n"
        "}\n"
        "function Live($Root) {\n"
        "    try { GameClosed $Root; return 'closed' } catch { return $_.Exception.Message }\n"
        "}\n"
        "$result = @((Names $args[0] 100000), (Names $args[0] 5), (Names $args[0] 6),\n"
        "    (Names $args[1] 100000), (Names $args[2] 100000), (Live $args[0]), (Live $args[1]),\n"
        "    (Live $args[2]))\n"
        "Write-Output (ConvertTo-Json -InputObject $result -Compress)\n"
    )
    completed = run_core(tmp_path, body, game, empty, linked)
    assert completed.returncode == 0, completed.stderr
    no_executable = (
        "No game executable was found in the selected folder; select the game folder. "
        "Nothing was changed."
    )
    uninspectable = (
        "Game folder cannot be inspected for running programs (links, reserved names, "
        "unreadable folders or too many entries); nothing was changed."
    )
    assert json.loads(completed.stdout) == [
        "crash.EXE|Game.exe",
        "unknown",
        "crash.EXE|Game.exe",
        "",
        "unknown",
        "closed",
        no_executable,
        uninspectable,
    ]


def test_live_check_reuses_only_a_recent_closed_snapshot(tmp_path):
    game = tmp_path / "Throttle Game"
    game.mkdir()
    (game / "Game.exe").write_bytes(b"synthetic EXE; never executed")
    other = tmp_path / "Other Game"
    other.mkdir()
    (other / "Other.exe").write_bytes(b"synthetic EXE; never executed")
    # The harness replaces the live snapshot; the later definition wins in PowerShell.
    body = "\n".join(
        (
            "$script:snapshots = 0",
            "$script:rows = @()",
            "function GameProcessSnapshot { $script:snapshots++; $script:rows }",
            "function Live($Root) {",
            "    try { GameClosed $Root; $state = 'closed' } catch { $state = 'refused' }",
            "    return $state+':'+$script:snapshots",
            "}",
            "$image = Join-Path $args[0] 'Game.exe'",
            "$running = @([pscustomobject]@{name='Game.exe';image=$image})",
            "$unknown = @([pscustomobject]@{name='Game.exe';image=$null})",
            "$result = @()",
            "$result += Live $args[0]",
            "$result += Live $args[0]",
            "$result += Live $args[1]",
            "Start-Sleep -Milliseconds 1100",
            "$result += Live $args[0]",
            "Start-Sleep -Milliseconds 1100",
            "$script:rows = $running",
            "$result += Live $args[0]",
            "$result += Live $args[0]",
            "$script:rows = $unknown",
            "$result += Live $args[0]",
            "$result += Live $args[0]",
            "$script:rows = @()",
            "$result += Live $args[0]",
            "$result += Live $args[0]",
            "Write-Output (ConvertTo-Json -InputObject $result -Compress)",
            "",
        )
    )
    completed = run_core(tmp_path, body, game, other)
    assert completed.returncode == 0, completed.stderr
    # The first call per root is fresh, a 'closed' result is reused for at most one second,
    # and 'running' or 'unknown' is never reused.
    assert json.loads(completed.stdout) == [
        "closed:1",
        "closed:1",
        "closed:2",
        "closed:3",
        "refused:4",
        "refused:5",
        "refused:6",
        "refused:7",
        "closed:8",
        "closed:8",
    ]


def test_checked_refuses_names_that_full_path_normalisation_would_hide(tmp_path):
    root = str(tmp_path / "Checked Root")
    Path(root).mkdir()
    drive = Path(root).drive
    refused = "Reserved or ambiguous path name refused."
    traversal = "Path traversal refused."
    rows = [
        (root, "accept"),
        (root + "\\", "accept"),
        (root.replace("\\", "/") + "/", "accept"),
        (drive + "\\", "accept"),
        # Like pathlib, '.' and empty components are collapsed, as in Python checked_path.
        (root + "\\\\", "accept"),
        (root + "\\a\\\\b", "accept"),
        (root + "\\.", "accept"),
        (root + "\\.\\a", "accept"),
        (root + "\\a\\..", traversal),
        (root + "\\CON\u0131N$", "accept"),
        (drive, "Drive-relative path refused."),
        (drive + "a", "Drive-relative path refused."),
        (root + "\\a\u0085", refused),
        (root + "\\CONOUT$", refused),
        (root + "\\" + "x" * 256, refused),
        ("", "Invalid path."),
        ("\\\\server\\share", "Local disk required."),
    ]
    (tmp_path / "rows.json").write_text(json.dumps([path for path, _ in rows]), encoding="utf-8")
    body = "\n".join(
        (
            "$rows = [IO.File]::ReadAllText($args[0],[Text.Encoding]::UTF8) | ConvertFrom-Json",
            "$result = @(foreach ($row in @($rows)) {",
            "    try { $null = Checked ([string]$row); 'accept' } catch { $_.Exception.Message }",
            "})",
            "Write-Output (ConvertTo-Json -InputObject $result -Compress)",
            "",
        )
    )
    completed = run_core(tmp_path, body, tmp_path / "rows.json")
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == [expected for _, expected in rows]


def test_patch_game_check_names_a_hard_linked_original(tmp_path):
    game = tmp_path / "Linked Original"
    game.mkdir()
    (game / "Game.exe").write_bytes(b"synthetic EXE; never executed")
    (game / "data.bin").write_bytes(b"synthetic data")
    os.link(game / "data.bin", tmp_path / "alias.bin")
    script = (RESOURCES / "patch-installer.ps1").read_text(encoding="ascii")
    check = script[script.index("function CheckGame {") : script.index("function SaveReceipt")]
    digests = {"Game.exe": hashlib.sha256((game / "Game.exe").read_bytes()).hexdigest()}
    digests["data.bin"] = hashlib.sha256((game / "data.bin").read_bytes()).hexdigest()
    (tmp_path / "files.json").write_text(json.dumps(digests), encoding="utf-8")
    body = "\n".join(
        (
            "function GameProcessSnapshot { @() }",
            check,
            "$game = Checked $args[0]",
            "$files = [IO.File]::ReadAllText($args[1],[Text.Encoding]::UTF8) | ConvertFrom-Json",
            "$package = [pscustomobject]@{game_files=$files}",
            "try { CheckGame; 'verified' } catch { $_.Exception.Message }",
            "",
        )
    )
    completed = run_core(tmp_path, body, game, tmp_path / "files.json")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == (
        "A game file is a hard link or link/reparse point; the patch cannot verify it: data.bin"
    )
    (tmp_path / "alias.bin").unlink()
    completed = run_core(tmp_path, body, game, tmp_path / "files.json")
    assert completed.stdout.strip() == "verified", completed.stderr
