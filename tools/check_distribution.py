"""Audit wheel/sdist contents; standalone runtime DLLs are checked separately."""

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from release_rules import (
    LANGUAGES,
    SOURCE,
    WHEEL,
    private_entries,
    project_version,
    strip_archive_root,
    unsafe_path,
)


def audit(archive: Path) -> list[str]:
    """Return the archive entry names after checking privacy, links and layout."""
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as stream:
            names = stream.namelist()
        relative = names
        profile = WHEEL
    else:
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            if any(item.issym() or item.islnk() for item in tar.getmembers()):
                raise ValueError("Source archives must not contain symbolic or hard links.")
        # Every sdist entry must sit inside one root folder; a top-level file outside it
        # would otherwise strip to an empty path and escape the privacy rules.
        if len({PurePosixPath(name).parts[0] for name in names if name}) != 1:
            raise ValueError(f"{archive.name} must contain exactly one top-level folder.")
        relative = [strip_archive_root(name) for name in names]
        profile = SOURCE
    forbidden = [
        name
        for name, path in zip(names, relative, strict=True)
        if path and (unsafe_path(path) or private_entries([path], profile))
    ]
    if forbidden:
        raise ValueError(f"{archive.name} contains private or binary data: {forbidden[:5]}")
    if not any(name.endswith("/resources/renpy-source-NOTICE.txt") for name in names):
        raise ValueError("Missing Ren'Py source-behavior notice.")
    if not any(name.endswith("/resources/renpy-additive.ps1") for name in names):
        raise ValueError("Missing bundled Ren'Py additive installer.")
    if not any(name.endswith("/resources/recipient-core.ps1") for name in names):
        raise ValueError("Missing bundled recipient installer core.")
    if not any(name.endswith("/locales/legacy-messages.json") for name in names):
        raise ValueError("Missing legacy diagnostic message table.")
    for code in LANGUAGES:
        if not any(name.endswith("/locales/" + code + ".json") for name in names):
            raise ValueError("Missing interface language: " + code)
        if archive.suffix != ".whl" and not any(
            name.endswith("/guide/" + code + ".md") for name in names
        ):
            raise ValueError("Missing user guide: " + code)
    return names


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    directory = parser.parse_args().dist_dir
    version = project_version(root)
    archives = [*directory.glob("*.whl"), *directory.glob("*.tar.gz")]
    current = {archive.name for archive in archives}
    if f"unitytranslator-{version}.tar.gz" not in current or not any(
        name.startswith(f"unitytranslator-{version}-") and name.endswith(".whl") for name in current
    ):
        raise ValueError(f"Build a wheel and sdist for {version} with uv build first.")
    for archive in archives:
        names = audit(archive)
        print(f"{archive.name}: {len(names)} entries; no private game/model/cache data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
