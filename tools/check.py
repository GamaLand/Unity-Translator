"""Local and CI synthetic checks with no game, model or server input.

Without a flag, or with --python-only, run Ruff, mypy and pytest. --with-dotnet adds the
synthetic C# test projects for a complete local run; --dotnet-only runs just those projects,
as the separate CI C# job does.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from unitytranslator.filesystem import checked_path

DOTNET_PROJECTS = (
    ("adapters/kryptafm/tests/CoreTests.csproj", None),
    ("adapters/kryptafm/tests/PluginTests.csproj", None),
    ("adapters/i2mono/tests/CoreTests.csproj", None),
    ("adapters/bepinex-protected/tests/DiagnosticsTests.csproj", "protected-diagnostics"),
    ("adapters/bepinex-protected/tests/PortableTests.csproj", "portable-diagnostics"),
)


def python_commands(base: Path) -> list[list[str]]:
    return [
        [sys.executable, "-m", "ruff", "check", "src", "tests", "tools"],
        [sys.executable, "-m", "mypy", "src/unitytranslator"],
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", str(base)],
    ]


def dotnet_commands(base: Path) -> list[list[str]]:
    commands = []
    for project, output in DOTNET_PROJECTS:
        command = ["dotnet", "run", "--project", project]
        if output is not None:
            command += ["--", str(base / output)]
        commands.append(command)
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--python-only", action="store_true", help="run Ruff, mypy and pytest (the default)"
    )
    scope.add_argument(
        "--with-dotnet", action="store_true", help="run the Python checks and the C# projects"
    )
    scope.add_argument("--dotnet-only", action="store_true", help="run only the C# projects")
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
    commands = [] if args.dotnet_only else python_commands(base)
    if args.with_dotnet or args.dotnet_only:
        commands += dotnet_commands(base)
    for command in commands:
        result = subprocess.run(command, cwd=root, env=env, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
