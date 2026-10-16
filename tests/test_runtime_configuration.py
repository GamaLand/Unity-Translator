import configparser
import ctypes
import os
from ctypes import wintypes
from pathlib import Path

import pytest

from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.runtime_configuration import (
    bepinex_config_text,
    doorstop_config_bytes,
    prepare_runtime_settings,
)


def test_settings_are_disabled_external_and_preserve_game_and_existing_files(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    original = game / "existing.log"
    original.write_bytes(b"preserve")
    paths = ProjectPaths(game, tmp_path / "project")
    preloader = paths.output("artifacts/runtime/BepInEx/core/BepInEx.Preloader.dll")
    preloader.parent.mkdir(parents=True)
    preloader.write_bytes(b"synthetic, never execute")
    before = hash_file(original)
    result = prepare_runtime_settings(paths, preloader.relative_to(paths.project).as_posix())
    assert not result["loader_enabled"] and not result["installation_authorized"]
    ini = Path(result["doorstop_ini"]).read_bytes()
    assert ini.startswith(b"\xff\xfe")
    parser = configparser.ConfigParser()
    parser.read_string(ini.decode("utf-16"))
    assert parser["General"]["enabled"] == "false"
    assert parser["General"]["target_assembly"].strip('"') == str(preloader)
    assert parser["UnityMono"]["debug_enabled"] == "false"
    assert Path(result["runtime_config"]).is_relative_to(paths.project)
    assert hash_file(original) == before and list(game.iterdir()) == [original]
    saved = Path(result["runtime_config"]).read_bytes()
    with pytest.raises(ValueError, match="üzerine yazılmaz"):
        prepare_runtime_settings(paths, preloader.relative_to(paths.project).as_posix())
    assert Path(result["runtime_config"]).read_bytes() == saved


def test_disk_cache_and_dump_settings_disable_unnecessary_output():
    parser = configparser.ConfigParser()
    parser.read_string(bepinex_config_text())
    for section, key in [
        ("Logging.Disk", "Enabled"),
        ("Logging.Disk", "WriteUnityLog"),
        ("Logging.Console", "Enabled"),
        ("Caching", "EnableAssemblyCache"),
        ("Preloader", "DumpAssemblies"),
        ("Preloader", "LoadDumpedAssemblies"),
        ("Preloader", "BreakBeforeLoadAssemblies"),
    ]:
        assert not parser.getboolean(section, key)


@pytest.mark.skipif(os.name != "nt", reason="Doorstop Windows INI API")
def test_windows_ini_reader_preserves_turkish_space_and_semicolon_path(tmp_path):
    preloader = tmp_path / "Türkçe ıİ; klasör" / "core" / "BepInEx.Preloader.dll"
    ini = tmp_path / "synthetic-doorstop.ini"
    ini.write_bytes(doorstop_config_bytes(preloader))
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    read = kernel.GetPrivateProfileStringW
    read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.LPCWSTR,
    ]
    read.restype = wintypes.DWORD
    result = ctypes.create_unicode_buffer(4096)
    read("General", "target_assembly", "missing", result, len(result), str(ini))
    assert result.value == str(preloader)
    read("General", "enabled", "missing", result, len(result), str(ini))
    assert result.value == "false"
    read("General", "redirect_output_log", "missing", result, len(result), str(ini))
    assert result.value == "false"


def test_truthy_text_cannot_enable_loader_config(tmp_path):
    with pytest.raises(ValueError, match="bool"):
        doorstop_config_bytes(tmp_path / "preloader.dll", enabled="false")
