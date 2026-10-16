"""Collect audited local runtime components with corresponding sources and licenses."""

import argparse
import json
import shutil
import zipfile
from pathlib import Path

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.json_boundary import strict_json
from unitytranslator.loader_support import confined
from unitytranslator.runtime_kit import CORE_NAMES, RuntimeKit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("loader", "protected-build", "plugin-build", "support", "protected-source"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    for name in ("loader", "protected_build", "plugin_build", "support", "protected_source"):
        setattr(args, name, checked_path(getattr(args, name)))
    root = Path(__file__).resolve().parents[1]
    output = checked_path(root / "dist/runtime-kit")
    if output.exists():
        raise ValueError("Mevcut runtime kit üzerine yazılmaz.")
    catalog = strict_json((root / "adapters/i2mono/loader-components.json").read_bytes())
    stock = {Path(item["path"]).name: item["sha256"] for item in catalog["components"]}
    protected = strict_json(confined(args.protected_build, "build-evidence.json").read_bytes())
    plugin = strict_json(confined(args.plugin_build, "build-evidence.json").read_bytes())
    if (
        protected["compile_exit_code"] != 0
        or protected["references_unchanged"] is not True
        or plugin["status"] != "compiled"
    ):
        raise ValueError("Derleme kanıtları hazır değil.")
    assembly_paths = [
        Path(name)
        for name in plugin["references_sha256"]
        if Path(name).name == "Assembly-CSharp.dll"
    ]
    assemblies = [plugin["references_sha256"][str(path)] for path in assembly_paths]
    if len(assemblies) != 1:
        raise ValueError("Tek oyun assembly referansı gerekli.")
    pending = []
    for name in CORE_NAMES:
        source = (
            confined(args.protected_build, name)
            if name == "BepInEx.Preloader.dll"
            else confined(args.loader, "BepInEx/core/" + name)
        )
        expected = protected["binary_sha256"] if name == "BepInEx.Preloader.dll" else stock[name]
        pending.append((source, "core/" + name, expected))
    pending.extend(
        [
            (confined(args.loader, "winhttp.dll"), "winhttp.dll", stock["winhttp.dll"]),
            (
                confined(args.plugin_build, "UnityTranslator.I2Mono.dll"),
                "plugin/UnityTranslator.I2Mono.dll",
                plugin["output_sha256"],
            ),
        ]
    )
    pending.append(
        (root / "LICENSE", "LICENSES/UnityTranslator-MIT.txt", hash_file(root / "LICENSE"))
    )
    support = strict_json(confined(args.support, "support-manifest.json").read_bytes())
    if support["status"] != "prepared":
        raise ValueError("Lisans/kaynak destek paketi hazır değil.")
    for item in support["files"]:
        if item["kind"] in ("notice", "source"):
            pending.append((confined(args.support, item["path"]), item["path"], item["sha256"]))
    # The source trace contains no personal reference paths or proprietary game DLLs.
    source_trace = strict_json(confined(args.protected_source, "source-manifest.json").read_bytes())
    if source_trace["status"] != "prepared":
        raise ValueError("Koruma kaynak paketi hazır değil.")
    if not any(
        item["path"] == "binary/BepInEx.Preloader.dll"
        and item["sha256"] == protected["binary_sha256"]
        for item in source_trace["files"]
    ):
        raise ValueError("Koruma kaynak paketi kullanılan binary ile eşleşmiyor.")
    for item in source_trace["files"]:
        incoming = confined(args.protected_source, item["path"])
        if hash_file(incoming) != item["sha256"]:
            raise ValueError("Koruma kaynak izi değişti.")
    for source, _, expected in pending:
        if hash_file(source) != expected:
            raise ValueError("Runtime kaynak bileşeni değişmiş.")
    output.mkdir(parents=True)
    for source, name, _ in pending:
        target = confined(output, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    notices = []
    for _, name, digest in pending:
        if not name.startswith(("core/", "plugin/")) and name != "winhttp.dll":
            continue
        if name.startswith("plugin/"):
            item = {
                "source_repository": "UnityTranslator",
                "license_files": ["LICENSES/UnityTranslator-MIT.txt"],
                "source_archive": "SOURCES/UnityTranslator-I2Mono.zip",
                "modified": False,
            }
        else:
            upstream = next(
                item for item in catalog["components"] if Path(item["path"]).name == Path(name).name
            )
            item = {
                "source_repository": upstream["source_repository"],
                "license_files": [
                    "LICENSES/" + Path(path).name for path in upstream["license_files"]
                ],
                "modified": name == "core/BepInEx.Preloader.dll",
            }
            if item["modified"]:
                item["source_archive"] = "SOURCES/protected-preloader.zip"
        notices.append({"path": name, "sha256": digest, **item})
    (output / "RUNTIME-NOTICES.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "components": notices,
                "upstream_sources": catalog["sources"],
                "license_metadata": catalog["licenses"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(
        confined(output, "SOURCES/protected-preloader.zip"), "x", zipfile.ZIP_DEFLATED
    ) as archive:
        for item in source_trace["files"]:
            archive.write(confined(args.protected_source, item["path"]), item["path"])
    with zipfile.ZipFile(
        confined(output, "SOURCES/UnityTranslator-I2Mono.zip"), "x", zipfile.ZIP_DEFLATED
    ) as archive:
        for name in (
            "TranslationCore.cs",
            "PayloadJson.cs",
            "Plugin.cs",
            "MemoryLanguage.cs",
            "README.md",
        ):
            archive.write(root / "adapters/i2mono" / name, name)
        archive.write(root / "LICENSE", "LICENSE")
        archive.write(root / "tools/build_i2mono.py", "tools/build_i2mono.py")
    (output / "README.txt").write_text(
        "UnityTranslator experimental I2 Mono runtime components.\n"
        "Use the application's reviewed file plan; do not copy these files manually into a game.\n"
        "Third-party licenses are in LICENSES; corresponding sources are in SOURCES.\n"
        "The protected preloader differs from upstream; "
        "full source and change evidence are included.\n"
        "General game compatibility is not verified.\n",
        encoding="utf-8",
    )
    inventory = {
        path.relative_to(output).as_posix(): hash_file(path)
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    result = {
        "format_version": 1,
        "purpose": "bundled-i2mono-runtime",
        "assembly_sha256": assemblies[0],
        "files": inventory,
        "managed_references": {
            Path(name).name: digest
            for name, digest in plugin["references_sha256"].items()
            if Path(name).parent == assembly_paths[0].parent
        },
        "unity_player_sha256": hash_file(assembly_paths[0].parents[2] / "UnityPlayer.dll"),
        "runtime_files": {
            name: inventory[name]
            for _, name, _ in pending
            if name.startswith(("core/", "plugin/")) or name == "winhttp.dll"
        },
    }
    (root / "src/unitytranslator/resources/runtime-kit-catalog.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    RuntimeKit(output).validate()
    print(json.dumps({"runtime_kit": str(output), "files": len(inventory)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
