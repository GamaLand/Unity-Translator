"""Collect standalone runtime/compiler support licenses and corresponding-source notices."""

import argparse
import importlib.metadata as metadata
import json
import shutil
import sys
from hashlib import sha256
from pathlib import Path

from packaging.requirements import Requirement

from unitytranslator.runtime_kit import PortableRuntimeKit, RuntimeKit


def runtime_dependencies() -> list[str]:
    pending = ["UnityPy", "httpx", "pydantic", "dnfile", "PySide6"]
    visited: set[str] = set()
    result = []
    while pending:
        name = pending.pop()
        key = name.casefold().replace("_", "-")
        if key in visited:
            continue
        visited.add(key)
        distribution = metadata.distribution(name)
        result.append(distribution.metadata["Name"])
        for item in distribution.requires or []:
            requirement = Requirement(item)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return sorted(result, key=str.casefold)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=root / "dist/windows")
    output = parser.parse_args().output_root.resolve()
    if not output.is_relative_to(root / "dist"):
        raise ValueError("Package output must be under the workspace dist folder.")
    package = output / "UnityTranslator.dist"
    if not (package / "UnityTranslator.exe").is_file():
        raise ValueError("Önce standalone paketi üretin.")
    kit = root / "dist/runtime-kit"
    if kit.is_dir():
        RuntimeKit(kit).validate()
        destination = package / "runtime-kit"
        if destination.exists():
            RuntimeKit(destination).validate()
        else:
            shutil.copytree(kit, destination)
            RuntimeKit(destination).validate()
    notices = package / "LICENSES"
    portable_kit = PortableRuntimeKit()
    portable_kit.validate()
    portable_destination = package / "portable-runtime-kit"
    if not portable_destination.exists():
        shutil.copytree(portable_kit.root, portable_destination)
    PortableRuntimeKit(portable_destination).validate()
    notices.mkdir(exist_ok=True)
    native_notices = root / "adapters/native_licenses"
    native_catalog = json.loads((native_notices / "catalog.json").read_text(encoding="utf-8"))
    destination = notices / "NativeRuntime"
    destination.mkdir(exist_ok=True)
    for item in native_catalog["licenses"]:
        if Path(item["file"]).name != item["file"]:
            raise ValueError("Native lisans dosyası adı geçersiz.")
        data = (native_notices / item["file"]).read_bytes()
        if sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Native lisans metni değişmiş.")
        (destination / item["file"]).write_bytes(data)
    shutil.copyfile(native_notices / "catalog.json", destination / "catalog.json")
    shutil.copyfile(root / "LICENSE", package / "LICENSE")
    for name in (
        "README-WINDOWS.md",
        "SOURCE-ACCESS.md",
        "NATIVE-NOTICES.md",
        "dependencies.md",
        "release-audit.md",
        "compatibility.md",
        "installation.md",
        "quality.md",
        "runtime-components.md",
        "shareable-patch.md",
        "development.md",
        "roadmap.md",
        "windows-package.md",
        "loader-component-audit.md",
        "protected-source-trace.md",
    ):
        shutil.copyfile(root / "docs" / name, package / name)
    guides = package / "guide"
    guides.mkdir(exist_ok=True)
    for code in ("en", "tr", "de", "fr", "es", "pt", "ru", "zh"):
        shutil.copyfile(root / "guide" / (code + ".md"), guides / (code + ".md"))
    shutil.copyfile(root / "tools/standalone_smoke.ps1", package / "standalone_smoke.ps1")
    inventory = []
    for name in [*runtime_dependencies(), "Nuitka"]:
        distribution = metadata.distribution(name)
        destination = notices / name
        destination.mkdir(exist_ok=True)
        texts = []
        for item in distribution.files or []:
            parts = [part.casefold() for part in item.parts]
            if "licenses" in parts or item.name.casefold().startswith(
                ("license", "copying", "notice")
            ):
                source = Path(distribution.locate_file(item))
                if source.is_file() and source.suffix.casefold() not in (".dll", ".pyd", ".exe"):
                    filename = "_".join(item.parts[-3:])
                    shutil.copyfile(source, destination / filename)
                    texts.append(filename)
        license_text = distribution.metadata.get("License") or distribution.metadata.get(
            "License-Expression"
        )
        if license_text:
            (destination / "METADATA-LICENSE.txt").write_text(license_text, encoding="utf-8")
            texts.append("METADATA-LICENSE.txt")
        inventory.append(
            {
                "name": name,
                "version": distribution.version,
                "license_expression": distribution.metadata.get("License-Expression"),
                "license_files": texts,
            }
        )
    interpreter_license = Path(sys.base_prefix) / "LICENSE.txt"
    if interpreter_license.is_file():
        shutil.copyfile(interpreter_license, notices / "CPython-LICENSE.txt")
    (package / "THIRD_PARTY_NOTICES.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = []
    for path in sorted(package.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(package)
        if any(
            part in (".local", ".cache", ".python", "deployment") for part in relative.parts
        ) or path.suffix.casefold() in (".gguf", ".assets", ".sqlite3", ".resS"):
            raise ValueError("Dağıtımda yerel veri veya oyun/model dosyası bulundu.")
        digest = sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        manifest.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        f"{len(inventory)} runtime dependency license entries; {len(manifest)} distribution files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
