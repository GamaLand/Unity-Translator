"""Uygulamayla gelen sabit runtime bileşenleri; ağ veya oyun yazma yoktur."""

import struct
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.json_boundary import strict_json
from unitytranslator.loader_support import confined
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_configuration import prepare_runtime_settings

CORE_NAMES = (
    "BepInEx.dll",
    "0Harmony.dll",
    "Mono.Cecil.dll",
    "Mono.Cecil.Mdb.dll",
    "Mono.Cecil.Pdb.dll",
    "Mono.Cecil.Rocks.dll",
    "MonoMod.Utils.dll",
    "MonoMod.RuntimeDetour.dll",
    "BepInEx.Preloader.dll",
)
RUNTIME_NAMES = {"core/" + name for name in CORE_NAMES} | {
    "plugin/UnityTranslator.I2Mono.dll",
    "winhttp.dll",
}


def bundled_kit_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "runtime-kit"
    return Path(__file__).resolve().parents[2] / "dist/runtime-kit"


def trusted_catalog() -> dict[str, Any]:
    resource = files("unitytranslator.resources").joinpath("runtime-kit-catalog.json")
    if not resource.is_file():
        raise ValueError("Bu pakette oyuna uygulama bileşenleri bulunmuyor.")
    data = resource.read_bytes()
    if len(data) > 1024 * 1024:
        raise ValueError("Runtime kataloğu boyut sınırını aşıyor.")
    value = strict_json(data)
    if not isinstance(value, dict):
        raise ValueError("Runtime kataloğu nesne olmalı.")
    if (
        value.get("format_version") != 1
        or value.get("purpose") != "bundled-i2mono-runtime"
        or set(value["runtime_files"]) != RUNTIME_NAMES
    ):
        raise ValueError("Runtime kataloğu geçersiz.")
    return value


class RuntimeKit:
    def __init__(self, root: Path | None = None):
        self.root = checked_path(root or bundled_kit_root())
        self.catalog = trusted_catalog()

    def validate(self) -> None:
        inventory = self.catalog["files"]
        if not 1 <= len(inventory) <= 2000 or not RUNTIME_NAMES <= set(inventory):
            raise ValueError("Runtime dosya envanteri eksik.")
        if any(inventory[name] != digest for name, digest in self.catalog["runtime_files"].items()):
            raise ValueError("Runtime bileşen envanteri eşleşmiyor.")
        actual = set()
        total = 0
        for path in self.root.rglob("*"):
            path = checked_path(path)
            if path.is_file():
                actual.add(path.relative_to(self.root).as_posix())
        if actual != set(inventory):
            raise ValueError("Runtime paketi eksik veya beklenmeyen dosya içeriyor.")
        for name, digest in inventory.items():
            path = confined(self.root, name)
            size = path.stat().st_size
            total += size
            if size > 64 * 1024 * 1024 or total > 256 * 1024 * 1024 or hash_file(path) != digest:
                raise ValueError("Runtime dosyası değişmiş veya boyut sınırını aşıyor.")

    def check_game(self, repo: ProjectRepository, assembly_relative: str) -> None:
        assembly = checked_path(repo.paths.game / assembly_relative)
        if (
            not assembly.is_relative_to(repo.paths.game)
            or assembly.name != "Assembly-CSharp.dll"
            or hash_file(assembly) != self.catalog["assembly_sha256"]
        ):
            raise ValueError("Bu oyun sürümüyle eşleşen uygulama adaptörü bulunmuyor.")
        for name, expected in self.catalog["managed_references"].items():
            if Path(name).name != name or hash_file(confined(assembly.parent, name)) != expected:
                raise ValueError("Oyunun çalışma altyapısı adaptör sürümüyle eşleşmiyor.")
        if (
            hash_file(confined(repo.paths.game, "UnityPlayer.dll"))
            != self.catalog["unity_player_sha256"]
        ):
            raise ValueError("Unity motoru adaptör sürümüyle eşleşmiyor.")
        data_name = assembly.parent.parent.name
        if not data_name.endswith("_Data"):
            raise ValueError("Oyun veri klasörü belirsiz.")
        executable = confined(repo.paths.game, data_name[:-5] + ".exe")
        with executable.open("rb") as stream:
            header = stream.read(64)
            if len(header) != 64 or header[:2] != b"MZ":
                raise ValueError("Oyun yürütülebilir dosyası doğrulanamadı.")
            offset = struct.unpack_from("<I", header, 60)[0]
            if not 64 <= offset <= 1024 * 1024:
                raise ValueError("Oyun PE başlığı geçersiz.")
            stream.seek(offset)
            if stream.read(6) != b"PE\0\0\x64\x86":
                raise ValueError("Bu adaptör yalnızca Windows x64 oyunları içindir.")

    def stage(self, repo: ProjectRepository, assembly_relative: str) -> dict[str, Any]:
        self.validate()
        self.check_game(repo, assembly_relative)
        assembly = checked_path(repo.paths.game / assembly_relative)
        relative = "artifacts/external-runtime-" + uuid4().hex + "/BepInEx"
        copied = []
        for name in CORE_NAMES:
            source = confined(self.root, "core/" + name)
            target = repo.paths.output(relative + "/core/" + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(source.read_bytes())
            expected = self.catalog["runtime_files"]["core/" + name]
            if hash_file(target) != expected:
                raise ValueError("Runtime kopyası eşleşmiyor.")
            copied.append({"file": "core/" + name, "sha256": expected})
        for folder in ("plugins", "patchers"):
            repo.paths.output(relative + "/" + folder).mkdir()
        support = Path(relative).parent.as_posix() + "/support/"
        for name, expected in self.catalog["files"].items():
            if name in RUNTIME_NAMES:
                continue
            target = repo.paths.output(support + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(confined(self.root, name).read_bytes())
            if hash_file(target) != expected:
                raise ValueError("Lisans/kaynak kopyası eşleşmiyor.")
        settings = prepare_runtime_settings(repo.paths, relative + "/core/BepInEx.Preloader.dll")
        repo.paths.write_json(
            relative + "/runtime-base-manifest.json",
            {
                "format_version": 1,
                "purpose": "experimental-external-runtime-base",
                "status": "prepared",
                "files": copied,
                "settings": settings,
                "application_verified": False,
                "installation_authorized": False,
                "includes_plugin": False,
                "includes_translation": False,
            },
        )
        evidence = str(Path(relative).parent.as_posix()) + "/plugin-evidence.json"
        repo.paths.write_json(
            evidence,
            {
                "status": "compiled",
                "origin": "bundled-runtime-kit",
                "output_sha256": self.catalog["runtime_files"]["plugin/UnityTranslator.I2Mono.dll"],
                "references_sha256": {str(assembly): self.catalog["assembly_sha256"]},
            },
        )
        return {
            "runtime_relative": relative,
            "plugin": confined(self.root, "plugin/UnityTranslator.I2Mono.dll"),
            "plugin_evidence": repo.paths.output(evidence),
            "winhttp": confined(self.root, "winhttp.dll"),
            "winhttp_sha256": self.catalog["runtime_files"]["winhttp.dll"],
        }


class PortableRuntimeKit(RuntimeKit):
    def __init__(self, root: Path | None = None):
        self.root = checked_path(root or bundled_kit_root().parent / "portable-runtime-kit")
        resource = files("unitytranslator.resources").joinpath("portable-runtime-kit-catalog.json")
        self.catalog = strict_json(resource.read_bytes())
        if (
            self.catalog.get("format_version") != 1
            or self.catalog.get("variant") != "portable-owned-subtree-v1"
            or set(self.catalog["runtime_files"]) != RUNTIME_NAMES
        ):
            raise ValueError("Taşınabilir runtime kataloğu geçersiz.")
