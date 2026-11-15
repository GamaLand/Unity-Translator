"""Rebuild the frozen legacy recipient fixtures from earlier release sources.

Synthetic data only. Each revision's ``src`` and ``tests`` trees are extracted with
``git archive`` into a new work directory, and that revision's own exporter runs on a
synthetic game created under the same directory. No game, installer or model is started.
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parent
REVISIONS = {
    "9ba9495": ("unity_shareable_rc",),
    "0b83e59": ("unity_shareable_rc",),
    "556bf5e": ("renpy_copy", "unity_shareable"),
    "1e1dfc3": ("renpy_additive",),
}

COMMON = '''"""Generated legacy fixture exporter; synthetic data only; never starts a game."""

import os
import zipfile
from pathlib import Path

import unitytranslator

OUT = Path(os.environ["UT_LEGACY_OUT"])
SOURCE = Path(os.environ["UT_LEGACY_SOURCE"]).resolve()
REVISION = os.environ["UT_LEGACY_REVISION"]
STAMP = (1980, 1, 1, 0, 0, 0)


def store_tree(root, name):
    with zipfile.ZipFile(OUT / name, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def store_package(path, name):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
    with (OUT / name).open("xb") as stream:
        stream.write(Path(path).read_bytes())


def test_extracted_revision_is_imported():
    assert Path(unitytranslator.__file__).resolve().is_relative_to(SOURCE)
'''

RENPY_COPY = """

import pytest
from test_renpy_scripts import approve, fixture

from unitytranslator.discovery import extract_to_project
from unitytranslator.renpy_package import export_copy_package
from unitytranslator.repository import ProjectRepository


@pytest.mark.parametrize("sharded", [False, True])
def test_export_renpy_translated_copy(tmp_path, monkeypatch, sharded):
    if sharded:
        paths, _ = fixture(tmp_path, 'label start:\\n    e "One."\\n    e "Two."\\n')
        monkeypatch.setattr("unitytranslator.renpy_export.SHARD_RECORDS", 1)
    else:
        paths, _ = fixture(tmp_path)
    (paths.game / "Synthetic.exe").write_bytes(b"Synthetic EXE stand-in; never executed")
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        if sharded:
            approve(repo, "One.", "Bir.")
            approve(repo, "Two.", "Iki.")
        else:
            approve(repo, "Display", "Ekran")
        result = export_copy_package(repo, "turkish")
    name = "renpy-copy-format" + ("2" if sharded else "1") + "-" + REVISION
    store_package(result["path"], name + ".zip")
    store_tree(paths.game, name + "-game.zip")
"""

UNITY_SHAREABLE = """

from test_shareable import krypta_project  # noqa: F401
from test_textasset_pipeline import repo as synthetic_repo  # noqa: F401

from unitytranslator.shareable import export_shareable_patch, supports_shareable_patch


def test_export_unity_shareable_patch(krypta_project):  # noqa: F811
    repo = krypta_project[0]
    assert supports_shareable_patch(repo)
    result = export_shareable_patch(repo)
    name = "unity-shareable-" + REVISION
    store_package(result["path"], name + ".zip")
    store_tree(repo.paths.game, name + "-game.zip")
"""

# Release candidates 0.1.0-rc.6/rc.7 export through their own ``shareable`` fixture
# (install_project with a synthetic portable runtime kit; asserts nothing in the game changed).
UNITY_SHAREABLE_RC = """

from test_shareable import install_project, shareable  # noqa: F401


def test_export_unity_shareable_patch_release_candidate(shareable):  # noqa: F811
    repo, folder, _ = shareable
    name = "unity-shareable-" + REVISION
    store_package(folder.with_suffix(".zip"), name + ".zip")
    store_tree(repo.paths.game, name + "-game.zip")
"""

RENPY_ADDITIVE = """

from test_renpy_scripts import approve, fixture

from unitytranslator.discovery import extract_to_project
from unitytranslator.renpy_package import export_install_package
from unitytranslator.repository import ProjectRepository


def test_export_renpy_additive(tmp_path):
    paths, _ = fixture(tmp_path)
    (paths.game / "Synthetic.exe").write_bytes(b"Synthetic EXE stand-in; never executed")
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        approve(repo, "Display", "Ekran")
        result = export_install_package(repo, "turkish")
    name = "renpy-additive-" + REVISION
    store_package(result["path"], name + ".zip")
    store_tree(paths.game, name + "-game.zip")
"""

SNIPPETS = {
    "renpy_copy": RENPY_COPY,
    "unity_shareable": UNITY_SHAREABLE,
    "unity_shareable_rc": UNITY_SHAREABLE_RC,
    "renpy_additive": RENPY_ADDITIVE,
}


def extract(repository: Path, revision: str, target: Path) -> None:
    archive = subprocess.run(
        ["git", "-C", str(repository), "archive", "--format=tar", revision, "src", "tests"],
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(target, filter="data")


def build(repository: Path, revision: str, work: Path, staging: Path) -> None:
    root = work / revision
    root.mkdir()
    extract(repository, revision, root)
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    module = root / "tests" / "test_zz_legacy_fixture_export.py"
    imports, body = [], []
    for kind in REVISIONS[revision]:
        lines = SNIPPETS[kind].splitlines(keepends=True)
        imports.extend(line for line in lines if line.startswith(("import ", "from ")))
        body.extend(line for line in lines if not line.startswith(("import ", "from ")))
    module.write_text(
        COMMON + "\n" + "".join(dict.fromkeys(imports)) + "".join(body), encoding="utf-8"
    )
    environment = {
        **os.environ,
        "PYTHONPATH": str(root / "src"),
        "UT_LEGACY_OUT": str(staging),
        "UT_LEGACY_SOURCE": str(root / "src"),
        "UT_LEGACY_REVISION": revision,
    }
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            "-c",
            str(root / "pytest.ini"),
            "--rootdir",
            str(root),
            "--basetemp",
            str(root / "basetemp"),
            str(module),
        ],
        cwd=root,
        env=environment,
        check=True,
    )


def index(staging: Path, kept: list[dict[str, object]]) -> dict[str, object]:
    fixtures = list(kept)
    for package in sorted(staging.glob("*.zip")):
        if package.name.endswith("-game.zip"):
            continue
        game = package.with_name(package.stem + "-game.zip")
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            manifest = json.loads(archive.read("package.json"))
        name = package.stem
        fixtures.append(
            {
                "name": name,
                "revision": name.rsplit("-", 1)[1],
                "package": package.name,
                "package_sha256": sha256(package.read_bytes()).hexdigest(),
                "game": game.name,
                "game_sha256": sha256(game.read_bytes()).hexdigest(),
                "format_version": manifest["format_version"],
                "purpose": manifest["purpose"],
                "installer": "patch.ps1" if "patch.ps1" in names else "renpy-copy.ps1",
            }
        )
    fixtures.sort(key=lambda item: str(item["name"]))
    return {"format_version": 1, "synthetic_only": True, "fixtures": fixtures}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work",
        type=Path,
        required=True,
        help="New directory under .cache/tests/ for extracted revisions.",
    )
    parser.add_argument("--output", type=Path, default=HERE)
    parser.add_argument("--repository", type=Path, default=HERE.parents[2])
    parser.add_argument(
        "--revision",
        action="append",
        choices=sorted(REVISIONS),
        help="Build only these revisions; index entries of the other revisions are kept.",
    )
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True)  # Refuses an existing work directory.
    staging = work / "staging"
    staging.mkdir()
    revisions = args.revision or list(REVISIONS)
    for revision in revisions:
        build(args.repository.resolve(), revision, work, staging)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)  # Fixture files are still copied create-new.
    current = output / "index.json"
    kept: list[dict[str, object]] = []
    if args.revision and current.exists():
        kept = [
            item
            for item in json.loads(current.read_bytes())["fixtures"]
            if item["revision"] not in revisions
        ]
    (staging / "index.json").write_text(
        json.dumps(index(staging, kept), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for path in sorted(staging.iterdir()):
        if path.name == "index.json" and kept:
            continue
        with path.open("rb") as source, (output / path.name).open("xb") as target:
            shutil.copyfileobj(source, target)
    if kept:
        # New ZIPs were copied in create-new mode; only the merged index is replaced.
        os.replace(staging / "index.json", current)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
