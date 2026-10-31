"""Build a standalone package using a generated private pyside6-deploy specification."""

import argparse
import configparser
import os
import subprocess
import sys
from pathlib import Path

from unitytranslator.filesystem import checked_path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=root / "dist/windows")
    output = checked_path(parser.parse_args().output_root)
    if not output.is_relative_to(root / "dist"):
        raise ValueError("Build output must be under the workspace dist folder.")
    target = checked_path(output / "UnityTranslator.dist")
    if not target.is_relative_to(root) or target == root:
        raise ValueError("Derleme hedefi çalışma alanı dışında.")
    if target.exists():
        raise ValueError("Build output already exists; choose a new --output-root.")
    config = configparser.ConfigParser()
    config.read(root / "pysidedeploy.spec", encoding="utf-8")
    for name in ("project_dir", "input_file", "exec_directory"):
        config["app"][name] = str(root / config["app"][name])
    config["app"]["exec_directory"] = str(output)
    output.mkdir(parents=True, exist_ok=True)
    config["app"]["icon"] = ""
    # Builds use reviewed local caches. A missing helper must fail, never download.
    config["nuitka"]["extra_args"] = config["nuitka"]["extra_args"].replace(
        "--assume-yes-for-downloads", "",
    )
    private = root / ".cache" / "pysidedeploy.local.spec"
    private.parent.mkdir(exist_ok=True)
    with private.open("w", encoding="utf-8") as stream:
        config.write(stream)
    environment = os.environ.copy()
    environment["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    )
    environment["NUITKA_CACHE_DIR"] = str(root / ".cache" / "nuitka")
    environment["TEMP"] = environment["TMP"] = str(root / ".cache")
    command = [
        str(Path(sys.executable).parent / "pyside6-deploy.exe"),
        "--config-file",
        str(private),
        "--mode",
        "standalone",
        "--no-install",
        "--force",
        "--keep-deployment-files",
    ]
    result = subprocess.run(
        command, cwd=root, env=environment, check=False, stdin=subprocess.DEVNULL,
    )
    if result.returncode:
        return result.returncode
    # The automatically included Qt PDF image plugin is unused.
    # Remove these files only from the newly generated package.
    for entry in target.rglob("*"):
        if entry.name.casefold() in {"qpdf.dll", "qt6pdf.dll"}:
            path = checked_path(entry)
            if not path.is_relative_to(target) or not path.is_file() or path.stat().st_nlink != 1:
                raise ValueError("Üretilmiş PDF bileşeni güvenle ayrılamadı.")
            path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
