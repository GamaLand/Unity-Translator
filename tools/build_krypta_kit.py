"""Collect a separate experimental Krypta kit from verified offline components."""

import argparse
import json
import shutil
import zipfile
from pathlib import Path

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.json_boundary import strict_json
from unitytranslator.krypta_runtime import RUNTIME_SCHEMAS, KryptaRuntimeKit
from unitytranslator.loader_support import confined
from unitytranslator.runtime_kit import RuntimeKit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plugin-build", "protected-source", "preloader-audit", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = checked_path(args.output)
    if not output.is_relative_to(root / "dist") or output.exists():
        raise ValueError("Choose a new kit output directory under workspace dist.")
    base = RuntimeKit()
    base.validate()
    build, protected_source = map(checked_path, (args.plugin_build, args.protected_source))
    plugin = strict_json(confined(build, "build-evidence.json").read_bytes())
    trace = strict_json(confined(protected_source, "source-manifest.json").read_bytes())
    protected = strict_json(confined(protected_source, "BUILD-EVIDENCE.json").read_bytes())
    audit = strict_json(checked_path(args.preloader_audit).read_bytes())
    if (
        plugin["adapter_id"] != "krypta-textassets-runtime"
        or plugin["compile_exit_code"] != 0
        or plugin["references_unchanged"] is not True
        or trace["status"] != "prepared"
        or protected["compile_exit_code"] != 0
        or protected["references_unchanged"] is not True
        or audit["static_checks_passed"] is not True
        or audit["assembly_sha256"] != protected["binary_sha256"]
    ):
        raise ValueError("Runtime compile/source/audit evidence is incomplete.")
    for name, digest in plugin["source_files"].items():
        source = build / name if name == "BuildIdentity.cs" else root / "adapters/kryptafm" / name
        if hash_file(checked_path(source)) != digest:
            raise ValueError("Plugin sources changed after compilation; rebuild first.")
    # Reuse only the pinned upstream components and support, never the I2 plugin/preloader.
    pending = []
    for name, digest in base.catalog["files"].items():
        if name.startswith("plugin/") or name in {
            "core/BepInEx.Preloader.dll",
            "SOURCES/protected-preloader.zip",
            "SOURCES/UnityTranslator-I2Mono.zip",
            "RUNTIME-NOTICES.json",
            "README.txt",
        }:
            continue
        pending.append((confined(base.root, name), name, digest))
    pending.extend(
        [
            (
                confined(build, "UnityTranslator.KryptaFM.dll"),
                "plugin/UnityTranslator.KryptaFM.dll",
                plugin["binary_sha256"],
            ),
            (
                confined(protected_source, "binary/BepInEx.Preloader.dll"),
                "core/BepInEx.Preloader.dll",
                protected["binary_sha256"],
            ),
        ]
    )
    for incoming, _, digest in pending:
        if hash_file(incoming) != digest:
            raise ValueError("Runtime input hash changed.")
    for item in trace["files"]:
        if hash_file(confined(protected_source, item["path"])) != item["sha256"]:
            raise ValueError("Protected source input changed.")
    output.mkdir(parents=True)
    for incoming, name, _ in pending:
        target = confined(output, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(incoming, target)
    with zipfile.ZipFile(
        output / "SOURCES/protected-preloader.zip", "x", zipfile.ZIP_DEFLATED
    ) as z:
        for item in trace["files"]:
            z.write(confined(protected_source, item["path"]), item["path"])
    with zipfile.ZipFile(
        output / "SOURCES/UnityTranslator-KryptaFM.zip", "x", zipfile.ZIP_DEFLATED
    ) as z:
        for name in plugin["source_files"]:
            path = build / name if name == "BuildIdentity.cs" else root / "adapters/kryptafm" / name
            z.write(path, name)
        for name in ("LICENSE", "tools/build_kryptafm.py", "docs/runtime-components.md"):
            z.write(root / name, name)
    upstream_notices = strict_json((base.root / "RUNTIME-NOTICES.json").read_bytes())
    components = [
        item for item in upstream_notices["components"] if not item["path"].startswith("plugin/")
    ]
    for item in components:
        if item["path"] == "core/BepInEx.Preloader.dll":
            item["sha256"] = protected["binary_sha256"]
    components.append(
        {
            "path": "plugin/UnityTranslator.KryptaFM.dll",
            "sha256": plugin["binary_sha256"],
            "source_repository": "UnityTranslator",
            "license_files": ["LICENSES/UnityTranslator-MIT.txt"],
            "source_archive": "SOURCES/UnityTranslator-KryptaFM.zip",
            "modified": False,
        }
    )
    upstream_notices["components"] = components
    (output / "RUNTIME-NOTICES.json").write_text(
        json.dumps(upstream_notices, indent=2), encoding="utf-8"
    )
    (output / "README.txt").write_text(
        "Experimental Krypta FM runtime; in-game coverage is reported separately.\n"
        "No installation is authorized by this component kit alone.\n"
        "Use only a concrete reviewed create-new file plan and current approved translations.\n"
        "Sources and licenses are included. No proprietary game DLL or game text is included.\n",
        encoding="utf-8",
    )
    inventory = {
        path.relative_to(output).as_posix(): hash_file(path)
        for path in output.rglob("*")
        if path.is_file()
    }
    references = plugin["references_sha256"]
    assembly = next(Path(path) for path in references if Path(path).name == "Assembly-CSharp.dll")
    catalog = {
        "format_version": 1,
        "supported_schemas": sorted(RUNTIME_SCHEMAS),
        "ui_trial_enabled": False,
        "purpose": "experimental-krypta-textassets-runtime",
        "application_verified": False,
        "assembly_sha256": references[str(assembly)],
        "unity_player_sha256": plugin["unity_player_sha256"],
        "files": inventory,
        "managed_references": {
            Path(path).name: digest
            for path, digest in references.items()
            if Path(path).parent == assembly.parent
        },
        "runtime_files": {name: inventory[name] for name in KryptaRuntimeKit.runtime_names},
    }
    resource = root / "src/unitytranslator/resources/krypta-runtime-kit-catalog.json"
    resource.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    KryptaRuntimeKit(output).validate()
    print(
        json.dumps(
            {"runtime_kit": str(output), "files": len(inventory), "application_verified": False}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
