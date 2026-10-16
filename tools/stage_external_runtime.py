"""Stage the protected loader in a separate project tree without starting a game."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file
from unitytranslator.json_boundary import strict_json
from unitytranslator.runtime_configuration import prepare_runtime_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "project", "loader", "protected-build"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = ProjectPaths(args.game, args.project)
    loader, build = map(checked_path, (args.loader, args.protected_build))
    preloader = checked_path(build / "BepInEx.Preloader.dll")
    evidence = strict_json((build / "build-evidence.json").read_bytes())
    if (
        evidence["compile_exit_code"] != 0
        or evidence["references_unchanged"] is not True
        or evidence["binary_sha256"] != hash_file(preloader)
    ):
        raise ValueError("Koruma değişiklikli build kanıtı eşleşmiyor.")
    result = subprocess.run(
        [
            sys.executable,
            str(root / "tools/audit_protected_preloader.py"),
            "--assembly",
            str(preloader),
            "--output",
            str(build / "runtime-write-audit.json"),
        ],
        check=False,
    )
    if result.returncode:
        raise ValueError("Preloader statik yazma kontrolünü geçmedi.")
    catalog = strict_json((root / "adapters/i2mono/loader-components.json").read_bytes())
    hashes = {Path(item["path"]).name: item["sha256"] for item in catalog["components"]}
    names = [
        "BepInEx.dll",
        "0Harmony.dll",
        "Mono.Cecil.dll",
        "Mono.Cecil.Mdb.dll",
        "Mono.Cecil.Pdb.dll",
        "Mono.Cecil.Rocks.dll",
        "MonoMod.Utils.dll",
        "MonoMod.RuntimeDetour.dll",
    ]
    for name in names:
        if hash_file(checked_path(loader / "BepInEx/core" / name)) != hashes[name]:
            raise ValueError("Runtime bağımlılığı resmî katalogla eşleşmiyor.")
    relative = "artifacts/external-runtime-" + uuid4().hex + "/BepInEx"
    output = paths.output(relative)
    output.mkdir(parents=True)
    copied = []
    for name in [*names, "BepInEx.Preloader.dll"]:
        incoming = (
            preloader
            if name == "BepInEx.Preloader.dll"
            else checked_path(loader / "BepInEx/core" / name)
        )
        expected = evidence["binary_sha256"] if name == "BepInEx.Preloader.dll" else hashes[name]
        target = paths.output(relative + "/core/" + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with incoming.open("rb") as source, target.open("xb") as destination:
            shutil.copyfileobj(source, destination, 1024 * 1024)
        if hash_file(target) != expected:
            raise ValueError("Runtime kopyası hash kontrolünü geçmedi.")
        copied.append({"file": "core/" + name, "sha256": expected})
    for name in ("plugins", "patchers"):
        paths.output(relative + "/" + name).mkdir()
    settings = prepare_runtime_settings(paths, relative + "/core/BepInEx.Preloader.dll")
    manifest = {
        "format_version": 1,
        "purpose": "experimental-external-runtime-base",
        "status": "prepared",
        "files": copied,
        "settings": settings,
        "application_verified": False,
        "installation_authorized": False,
        "includes_plugin": False,
        "includes_translation": False,
    }
    paths.write_json(relative + "/runtime-base-manifest.json", manifest)
    print(json.dumps({"runtime": str(output), "dlls": len(copied), "settings": settings}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
