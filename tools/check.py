"""Yerel ve CI sentetik doğrulaması; oyun/model/sunucu girdisi yoktur."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from unitytranslator.filesystem import checked_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-dotnet", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = checked_path(root / ".cache" / "tests" / ("verify-" + uuid4().hex))
    if not base.is_relative_to(root) or base.exists():
        raise ValueError("Test hedefi yeni ve çalışma alanında olmalı.")
    base.parent.mkdir(parents=True, exist_ok=True)
    temporary = checked_path(root / ".cache/temp")
    temporary.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        TEMP=str(temporary),
        TMP=str(temporary),
        QT_QPA_PLATFORM="offscreen",
        DOTNET_CLI_TELEMETRY_OPTOUT="1",
        DOTNET_GENERATE_ASPNET_CERTIFICATE="false",
        DOTNET_CLI_HOME=str(root / ".cache/dotnet"),
    )
    commands = [
        [sys.executable, "-m", "ruff", "check", "src", "tests", "tools"],
        [sys.executable, "-m", "mypy", "src/unitytranslator"],
        [sys.executable, "-m", "pytest", "-q", "--basetemp", str(base)],
    ]
    if args.with_dotnet:
        commands.append(["dotnet", "run", "--project", "adapters/i2mono/tests/CoreTests.csproj"])
        commands.append(
            [
                "dotnet",
                "run",
                "--project",
                "adapters/bepinex-protected/tests/DiagnosticsTests.csproj",
                "--",
                str(base / "protected-diagnostics"),
            ]
        )
        commands.append([
            "dotnet", "run", "--project",
            "adapters/bepinex-protected/tests/PortableTests.csproj", "--",
            str(base / "portable-diagnostics"),
        ])
    for command in commands:
        result = subprocess.run(command, cwd=root, env=env, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
