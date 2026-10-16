"""Audit wheel/sdist contents; standalone runtime DLLs are checked separately."""

import argparse
import tarfile
import zipfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    directory = parser.parse_args().dist_dir
    archives = [*directory.glob("*.whl"), *directory.glob("*.tar.gz")]
    if not archives:
        raise ValueError("Build a wheel and sdist with uv build first.")
    private = {
        ".local",
        ".cache",
        ".python",
        ".venv",
        "deployment",
        "obj",
        "bin",
        ".agents",
        ".codex",
        ".claude",
        ".cursor",
    }
    private_names = {
        "agents.md",
        "claude.md",
        "gemini.md",
        "goal.md",
        "technical_design.md",
        "technical.design.md",
        ".cursorrules",
        ".windsurfrules",
        "copilot-instructions.md",
        ".env",
    }
    extensions = (".gguf", ".assets", ".sqlite3", ".ress", ".dll")
    for archive in archives:
        if archive.suffix == ".whl":
            with zipfile.ZipFile(archive) as stream:
                names = stream.namelist()
        else:
            with tarfile.open(archive, "r:gz") as tar:
                names = tar.getnames()
                if any(item.issym() or item.islnk() for item in tar.getmembers()):
                    raise ValueError("Source archives must not contain symbolic or hard links.")
        forbidden = [
            name
            for name in names
            if (
                any(part.casefold() in private for part in name.replace("\\", "/").split("/"))
                or Path(name).name.casefold() in private_names
                or Path(name).name.casefold().startswith(".env.")
                or name.casefold().endswith(extensions)
            )
        ]
        if forbidden:
            raise ValueError(f"{archive.name} contains private or binary data: {forbidden[:5]}")
        for code in ("en", "tr", "de", "fr", "es", "pt", "ru", "zh"):
            if not any(name.endswith("/locales/" + code + ".json") for name in names):
                raise ValueError("Missing interface language: " + code)
            if archive.suffix != ".whl" and not any(
                name.endswith("/guide/" + code + ".md") for name in names
            ):
                raise ValueError("Missing user guide: " + code)
        print(f"{archive.name}: {len(names)} entries; no private game/model/cache data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
