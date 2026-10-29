"""Package the traced portable preloader build and matching sources/licenses."""

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file
from unitytranslator.protected_source import stage_protected_source
from unitytranslator.runtime_kit import RUNTIME_NAMES, RuntimeKit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build = checked_path(args.build)
    evidence = json.loads((build / "build-evidence.json").read_text(encoding="utf-8"))
    binary = build / "BepInEx.Preloader.dll"
    if (
        evidence.get("portable") is not True
        or evidence["compile_exit_code"] != 0
        or not evidence["references_unchanged"]
        or hash_file(binary) != evidence["binary_sha256"]
        or hash_file(build / "source/BepInEx.Preloader/ProtectedRuntimeDiagnostics.cs")
        != evidence["diagnostics_source_sha256"]
    ):
        raise ValueError("Portable derleme kanıtı geçersiz.")
    original = RuntimeKit()
    original.validate()
    target = checked_path(args.output or root / "dist/portable-runtime-kit")
    if not target.is_relative_to(root) or target == root or target.exists():
        raise ValueError("Mevcut portable kit üzerine yazılmaz.")
    trace_game = root / ".cache/portable-source-fixture"
    trace_game.mkdir(exist_ok=True)
    trace_project = root / ".cache" / ("portable-source-" + uuid4().hex)
    upstream = next(path for path in (original.root / "SOURCES").glob("BepInEx-BepInEx-*.zip"))
    traced = stage_protected_source(
        ProjectPaths(trace_game, trace_project),
        build=build,
        archive=upstream,
        catalog_root=root / "adapters/i2mono",
        own_root=root,
    )
    shutil.copytree(original.root, target)
    shutil.copyfile(binary, target / "core/BepInEx.Preloader.dll")
    archive = target / "SOURCES/protected-preloader.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        traced_root = Path(traced["directory"])
        for path in sorted(traced_root.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(traced_root).as_posix())
        for name in (
            "tools/prepare_protected_preloader.py",
            "tools/package_portable_kit.py",
            "adapters/bepinex-protected/PortableRuntimeDiagnostics.cs",
            "LICENSE",
            "docs/installation.md",
        ):
            if name not in zipped.namelist():
                zipped.write(root / name, name)
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None or len(zipped.namelist()) != len(set(zipped.namelist())):
            raise ValueError("Portable kaynak ZIP doğrulanamadı.")
    notices = json.loads((target / "RUNTIME-NOTICES.json").read_text(encoding="utf-8"))
    for component in notices["components"]:
        if component["path"] == "core/BepInEx.Preloader.dll":
            component.update(
                sha256=hash_file(binary),
                modified=True,
                modification="Portable subtree; no persistent shim or diagnostics",
                source_archive="SOURCES/protected-preloader.zip",
            )
    (target / "RUNTIME-NOTICES.json").write_text(
        json.dumps(notices, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    catalog = dict(original.catalog)
    catalog["files"] = {
        path.relative_to(target).as_posix(): hash_file(path)
        for path in sorted(target.rglob("*"))
        if path.is_file()
    }
    catalog["runtime_files"] = {name: catalog["files"][name] for name in sorted(RUNTIME_NAMES)}
    catalog["variant"] = "portable-owned-subtree-v1"
    destination = root / "src/unitytranslator/resources/portable-runtime-kit-catalog.json"
    with destination.open("w", encoding="utf-8") as stream:
        json.dump(catalog, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"files": len(catalog["files"]), "preloader_sha256": hash_file(binary)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
