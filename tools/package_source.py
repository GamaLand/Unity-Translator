"""Create a repository-ready source ZIP from the already audited source distribution."""

import argparse
import json
import tarfile
import zipfile
from hashlib import sha256
from pathlib import Path, PurePosixPath

from release_rules import (
    LANGUAGES,
    SOURCE,
    check_release_label,
    private_reason,
    project_version,
    unsafe_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="github-source")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    args = parser.parse_args()
    label = check_release_label(args.label)
    directory = args.dist_dir
    version = project_version(root)
    source = directory / f"unitytranslator-{version}.tar.gz"
    target = directory / f"UnityTranslator-{version}-{label}.zip"
    if target.exists():
        raise ValueError("Source delivery already exists; preserve it and choose a new version.")
    files = {}
    seen = set()
    with tarfile.open(source, "r:gz") as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Source archive must contain regular files only")
            if unsafe_path(member.name):
                raise ValueError("Invalid source entry: " + member.name)
            relative = PurePosixPath(*PurePosixPath(member.name).parts[1:])
            if (
                not relative.parts
                or unsafe_path(str(relative))
                or private_reason(str(relative), SOURCE) is not None
                or str(relative).casefold() in seen
            ):
                raise ValueError("Private or invalid source entry: " + str(relative))
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Missing source member")
            files[str(relative)] = stream.read()
            seen.add(str(relative).casefold())
    assert {"README.md", "LICENSE", ".gitignore", ".gitattributes"} <= files.keys()
    assert "src/unitytranslator/resources/locales/legacy-messages.json" in files
    # Recipient installers are generated from these resources at export time.
    for script in (
        "recipient-core.ps1",
        "patch-installer.ps1",
        "renpy-copy.ps1",
        "renpy-additive.ps1",
    ):
        assert "src/unitytranslator/resources/" + script in files
    for code in LANGUAGES:
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
