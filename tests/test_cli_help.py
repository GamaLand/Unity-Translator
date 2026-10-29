import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "command", [[], ["scan"], ["probe"], ["extract"], ["project"], ["models"], ["sample"],
                ["export-textassets"], ["export-renpy"], ["export-renpy-zip"]]
)
def test_cli_help_is_english_without_game_or_server_input(command):
    result = subprocess.run(
        [sys.executable, "-m", "unitytranslator", *command, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.isascii()
    assert "usage:" in result.stdout and "--help" in result.stdout
