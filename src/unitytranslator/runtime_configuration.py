"""Prepare external runtime settings without installing or starting components."""

from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file


def doorstop_config_bytes(preloader: Path, *, enabled: bool = False) -> bytes:
    if type(enabled) is not bool:
        raise ValueError("Loader etkinlik seçimi bool olmalı.")
    path = str(checked_path(preloader))
    if any(char in path for char in '\r\n\0"'):
        raise ValueError("Loader yolu INI değeri olarak güvenli değil.")
    text = (
        "; UnityTranslator experimental external runtime; preparation is not activation.\r\n"
        "[General]\r\n"
        f"enabled={'true' if enabled else 'false'}\r\n"
        f'target_assembly="{path}"\r\n'
        "redirect_output_log=false\r\nboot_config_override=\r\nignore_disable_switch=false\r\n"
        "[UnityMono]\r\ndll_search_path_override=\r\ndebug_enabled=false\r\n"
        "debug_address=127.0.0.1:10000\r\ndebug_suspend=false\r\n"
    )
    # Doorstop x64 imports GetPrivateProfileStringW; Windows Unicode INI BOM.
    return b"\xff\xfe" + text.encode("utf-16-le")


def bepinex_config_text() -> str:
    return (
        "# UnityTranslator external runtime configuration; generated for review.\n"
        "[Logging.Disk]\nEnabled = false\nWriteUnityLog = false\n"
        "[Logging.Console]\nEnabled = false\n"
        "[Caching]\nEnableAssemblyCache = false\n"
        "[Preloader]\nDumpAssemblies = false\nLoadDumpedAssemblies = false\n"
        "BreakBeforeLoadAssemblies = false\nApplyRuntimePatches = true\n"
    )


def prepare_runtime_settings(paths: ProjectPaths, preloader_relative: str) -> dict[str, Any]:
    preloader = paths.output(preloader_relative)
    if (
        not preloader.is_file()
        or preloader.name != "BepInEx.Preloader.dll"
        or preloader.parent.name.casefold() != "core"
    ):
        raise ValueError("Proje içinde core/BepInEx.Preloader.dll gerekli.")
    runtime = checked_path(preloader.parent.parent)
    config = checked_path(runtime / "config/BepInEx.cfg")
    if config.exists():
        raise ValueError("Mevcut runtime yapılandırmasının üzerine yazılmaz.")
    relative = "artifacts/runtime-settings-" + uuid4().hex
    folder = paths.output(relative)
    if folder.exists():
        raise ValueError("Ayar hedefi yeni olmalı.")
    folder.mkdir(parents=True)
    config.parent.mkdir(parents=True, exist_ok=True)
    with config.open("x", encoding="utf-8", newline="\n") as output:
        output.write(bepinex_config_text())
    ini = paths.output(relative + "/doorstop_config.ini")
    with ini.open("xb") as output_bytes:
        output_bytes.write(doorstop_config_bytes(preloader))
    result = {
        "format_version": 1,
        "purpose": "external-runtime-settings",
        "status": "prepared",
        "doorstop_ini": str(ini),
        "doorstop_ini_sha256": hash_file(ini),
        "runtime_config": str(config),
        "runtime_config_sha256": hash_file(config),
        "runtime_root": str(runtime),
        "preloader_sha256": hash_file(preloader),
        "loader_enabled": False,
        "game_written": False,
        "installation_authorized": False,
        "application_verified": False,
    }
    paths.write_json(relative + "/settings-manifest.json", result)
    return result
