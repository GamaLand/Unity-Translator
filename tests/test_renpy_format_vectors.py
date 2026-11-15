"""Shared Ren'Py text-rule vectors for the Python validator and the recipient tokenizer.

renpy-format-v1.json covers renpy-text-v1 (dialogue and v1 string keys).
renpy-format-v2.json covers string keys under renpy-text-v2 (v1 plus printf conversions).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from unitytranslator.recipient_scripts import installer_bytes
from unitytranslator.renpy_format import RENPY_FORMATS, RENPY_STRING_FORMAT, tokens
from unitytranslator.validation import format_issues, mask

FIXTURES = Path(__file__).parent / "fixtures"


def text(value: Any) -> str:
    return value if isinstance(value, str) else "".join(part * count for part, count in value)


def load() -> list[dict[str, Any]]:
    cases = []
    for name in ("renpy-format-v1.json", "renpy-format-v2.json"):
        data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        assert data["format_rules"] in RENPY_FORMATS
        cases.extend(
            {**case, "rules": data["format_rules"], "source": text(case["source"]),
             "target": text(case["target"])}
            for case in data["cases"]
        )
    return cases


CASES = load()


@pytest.mark.parametrize("case", CASES, ids=range(len(CASES)))
def test_python_validator_matches_shared_vectors(case: dict[str, Any]) -> None:
    rules = case["rules"]
    issues = format_issues(case["source"], case["target"], rules=rules)
    assert (not issues) == case["accepted"], issues
    printf = rules == RENPY_STRING_FORMAT
    if "tokens" in case:
        assert [t.text for t in tokens(case["source"], printf=printf)] == case["tokens"]
    if case["accepted"]:
        masked = mask(case["source"], rules=rules)
        assert masked.restore(masked.text) == case["source"]
        # Every v2 acceptance is also a v1 acceptance, so older recipients stay safe.
        assert not format_issues(case["source"], case["target"], rules="renpy-text-v1")


def test_recipient_tokenizer_matches_shared_vectors(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    if sys.platform != "win32" or powershell is None:
        pytest.skip("Windows PowerShell required for the recipient tokenizer")
    # The shipped script: the shared core's Add-Type block precedes the Ren'Py grammar block.
    script = installer_bytes("renpy-copy.ps1").decode("utf-8").replace("\r\n", "\n")
    opening = "Add-Type -TypeDefinition @'\n"
    assert script.count(opening) == 2
    start = script.index(opening, script.index("# End of shared recipient core.")) + len(opening)
    assert script.index("class RenpyCopyFormat", start) < script.index("\n'@", start)
    end = script.index("\n'@", start)
    (tmp_path / "recipient.cs").write_text(script[start:end], encoding="utf-8")
    payload = [
        {"source": c["source"], "target": c["target"], "printf": c["rules"] == RENPY_STRING_FORMAT}
        for c in CASES
    ]
    (tmp_path / "cases.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    # Compiles only the fixed tokenizer classes; no installer step, game or package runs.
    harness = tmp_path / "harness.ps1"
    harness.write_text(
        "$ErrorActionPreference='Stop'\n"
        "Add-Type -TypeDefinition ([IO.File]::ReadAllText($args[0],[Text.Encoding]::UTF8))\n"
        "$cases=[IO.File]::ReadAllText($args[1],[Text.Encoding]::UTF8) | ConvertFrom-Json\n"
        "$results=@(foreach($case in $cases){\n"
        "  try { [RenpyCopyFormat]::Compare($case.source,$case.target,[bool]$case.printf)\n"
        "    $tokens=@([RenpyCopyFormat]::Tokens($case.source,[bool]$case.printf))\n"
        "    @{accepted=$true; tokens=$tokens} }\n"
        "  catch { @{accepted=$false; tokens=@()} }\n"
        "})\n"
        "[IO.File]::WriteAllText($args[2],(ConvertTo-Json -InputObject $results -Depth 4),"
        "(New-Object Text.UTF8Encoding $false))\n",
        encoding="utf-8",
    )
    output = tmp_path / "results.json"
    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
         str(harness), str(tmp_path / "recipient.cs"), str(tmp_path / "cases.json"), str(output)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    results = json.loads(output.read_text(encoding="utf-8-sig"))
    assert len(results) == len(CASES)
    mismatches = []
    for index, (case, result) in enumerate(zip(CASES, results, strict=True)):
        expected = case.get("recipient", case["accepted"])
        if result["accepted"] != expected:
            mismatches.append((index, case.get("note"), case["source"][:40], expected))
        elif expected and "tokens" in case and list(result["tokens"] or []) != case["tokens"]:
            mismatches.append((index, "tokens", case["source"][:40], result["tokens"]))
    assert not mismatches
