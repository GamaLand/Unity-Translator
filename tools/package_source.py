"""Create a repository-ready source ZIP from the already audited source distribution."""

import argparse
import json
import re
import tarfile
import tomllib
import zipfile
from hashlib import sha256
from pathlib import Path, PurePosixPath


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="github-source")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    args = parser.parse_args()
    label = args.label
    directory = args.dist_dir
    if not re.fullmatch(r"[a-z][a-z0-9.-]{0,39}", label):
        raise ValueError("Invalid source delivery label")
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    source = directory / f"unitytranslator-{version}.tar.gz"
    target = directory / f"UnityTranslator-{version}-{label}.zip"
    if target.exists():
        raise ValueError("Source delivery already exists; preserve it and choose a new version.")
    files = {}
    seen = set()
    private = {
        ".local",
        ".cache",
        ".venv",
        ".python",
        "deployment",
        "obj",
        "bin",
        ".agents",
        ".codex",
        ".claude",
        ".cursor",
    }
    names = {
        "agents.md",
        "goal.md",
        "technical_design.md",
        "technical.design.md",
        "claude.md",
        "gemini.md",
        ".env",
    }
    with tarfile.open(source, "r:gz") as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Source archive must contain regular files only")
            relative = PurePosixPath(*PurePosixPath(member.name).parts[1:])
            if (
                not relative.parts
                or relative.is_absolute()
                or ".." in relative.parts
                or any(part.casefold() in private for part in relative.parts)
                or relative.name.casefold() in names
                or relative.name.casefold().endswith("_ren.py")
                or ":" in str(relative)
                or relative.suffix.lower() in {
                    ".dll", ".exe", ".gguf", ".assets", ".sqlite3", ".rpa", ".rpyc", ".rpy"
                }
                or str(relative).casefold() in seen
            ):
                raise ValueError("Private or invalid source entry: " + str(relative))
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Missing source member")
            files[str(relative)] = stream.read()
            seen.add(str(relative).casefold())
    assert {"README.md", "LICENSE", ".gitignore", ".gitattributes"} <= files.keys()
    for code in ("en", "tr", "de", "fr", "es", "pt", "ru", "zh"):
        assert "guide/" + code + ".md" in files
        assert "src/unitytranslator/resources/locales/" + code + ".json" in files
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr("UnityTranslator/" + name, data)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files)
        for name, data in files.items():
            assert archive.read("UnityTranslator/" + name) == data
    digest = sha256(target.read_bytes()).hexdigest()
    with Path(str(target) + ".sha256").open("x", encoding="ascii") as stream:
        stream.write(digest + "  " + target.name + "\n")
    print(
        json.dumps(
            {
                "file": target.name,
                "files": len(files),
                "sha256": digest,
                "bytes": target.stat().st_size,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
