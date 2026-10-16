"""Yalnızca insan onaylı çeviriden bağımsız, yerel dağıtım ZIP'i üretir."""

import json
import zipfile
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.deployment import DeploymentService
from unitytranslator.filesystem import hash_file
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_configuration import bepinex_config_text
from unitytranslator.runtime_export import export_selected_runtime
from unitytranslator.runtime_kit import RUNTIME_NAMES, PortableRuntimeKit

PATCH_FOLDER = "UnityTranslatorPatch"


def export_shareable_patch(repo: ProjectRepository) -> dict[str, Any]:
    selected = [dict(row) for row in repo.db.execute(
        "SELECT u.unit_id,u.source_revision,w.translation_revision,w.version FROM text_units u "
        "JOIN work_items w USING(unit_id) WHERE u.active=1 AND w.status='approved' "
        "ORDER BY u.unit_id"
    )]
    context = export_selected_runtime(repo, selected, record_limit=100_000)
    kit = PortableRuntimeKit()
    kit.validate()
    kit.check_game(repo, context["assembly_relative"])
    for relative, expected in context["source_fingerprints"].items():
        if expected is None or hash_file(repo.paths.game / relative) != expected:
            raise ValueError("Oyun kaynağı değişmiş; yeniden çıkarın.")
    identifier = uuid4().hex
    folder = repo.paths.output("exports/shareable-" + identifier)
    folder.mkdir(parents=True)
    inventory = []
    runtime_bytes = 0

    def put(target: str, data: bytes, runtime: bool = False) -> None:
        nonlocal runtime_bytes
        relative = folder.relative_to(repo.paths.project).as_posix() + "/payload/" + target
        path = repo.paths.output(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        inventory.append({"path": target, "sha256": hash_file(path), "bytes": len(data)})
        if runtime:
            runtime_bytes += len(data)

    for name in kit.catalog["files"]:
        if name == "winhttp.dll":
            target = name
        elif name.startswith("core/"):
            target = PATCH_FOLDER + "/BepInEx/" + name
        elif name.startswith("plugin/"):
            target = PATCH_FOLDER + "/BepInEx/plugins/UnityTranslator/" + Path(name).name
        else:
            target = PATCH_FOLDER + "/support/" + name
        put(target, (kit.root / name).read_bytes(), name in RUNTIME_NAMES)
    put(PATCH_FOLDER + "/portable-runtime-v1.marker", b"UnityTranslator portable runtime v1\n")
    put(PATCH_FOLDER + "/BepInEx/config/BepInEx.cfg", bepinex_config_text().encode(), True)
    put(PATCH_FOLDER + "/BepInEx/plugins/UnityTranslator/translation.json",
        Path(context["path"]).read_bytes(), True)
    assembly = Path(context["assembly_relative"])
    executable = assembly.parts[0][:-5] + ".exe"
    game_files = {str(assembly.parent / name).replace("\\", "/"): digest
                  for name, digest in kit.catalog["managed_references"].items()}
    game_files["UnityPlayer.dll"] = kit.catalog["unity_player_sha256"]
    game_files[executable] = hash_file(repo.paths.game / executable)
    game_files.update(context["source_fingerprints"])
    baseline = DeploymentService(repo).read_baseline()
    if baseline is not None:
        game_files.update(baseline["files"])
    manifest = {"format_version": 1, "purpose": "unitytranslator-shareable-patch",
                "package_id": identifier, "patch_folder": PATCH_FOLDER,
                "game_executable": executable, "game_files": game_files,
                "records": len(selected), "experimental": True, "files": inventory}
    (folder / "package.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    resources = files("unitytranslator.resources")
    script = resources.joinpath("patch-installer.ps1").read_bytes()
    (folder / "patch.ps1").write_bytes(b"\xef\xbb\xbf" + script.removeprefix(b"\xef\xbb\xbf"))
    for filename, action in (("Kur.cmd", "Install"), ("Kaldir.cmd", "Remove")):
        (folder / filename).write_bytes((
            '@echo off\r\n"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" '
            '-NoProfile -ExecutionPolicy Bypass -File "%~dp0patch.ps1" -Action ' + action
            + '\r\npause\r\n').encode("ascii"))
    (folder / "README.txt").write_text(
        "UnityTranslator paylaşılabilir çeviri\n\n"
        "ZIP'i ayrı bir klasöre çıkarın. Kur.cmd dosyasını açıp oyun klasörünü seçin.\n"
        "Oyun kapalı olmalı. UnityTranslator, Python, LM Studio veya model gerekmez.\n"
        "Yeni UnityTranslatorPatch klasörü, winhttp.dll ve doorstop_config.ini eklenir.\n"
        "Mevcut dosya/klasör varsa kurulum durur; başka modu veya önceki kurulumu ezmez.\n"
        "Mevcut denemeyi kaldırmak için onu kuran UnityTranslator projesini kullanın.\n"
        "Kaldir.cmd yalnızca bu paketin sahipliği/hash'i eşleşen eklerini kaldırır.\n"
        "Değiştirilmiş dosyalar korunur. Oyun klasörünü taşırsanız kaldırıp yeniden kurun.\n"
        "Yükleyici yolu alıcının bilgisayarında oluşturulur; geliştirici yolu içermez.\n"
        "Uyumluluk deneyseldir; yalnızca hash'leri eşleşen Windows x64 oyun sürümü.\n"
        "Oyun dosyası, model, proje veritabanı veya kaynak İngilizce metin dahil değildir.\n"
        "Bileşen lisans/kaynakları UnityTranslatorPatch/support altındadır.\n",
        encoding="utf-8-sig")
    destination = folder.with_suffix(".zip")
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Dağıtım ZIP kontrolü başarısız.")
    return {"path": str(destination), "records": len(selected), "bytes": destination.stat().st_size,
            "runtime_bytes": runtime_bytes, "sha256": hash_file(destination),
            "requires_unitytranslator": False, "game_written": False, "experimental": True}
