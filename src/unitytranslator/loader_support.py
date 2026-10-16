"""Çevrimdışı yükleyici destek paketi; kurulum veya çalıştırma yetkisi yoktur."""

import re
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file
from unitytranslator.json_boundary import strict_json

_PRELOADER_STOCK_HASH = "55d3895351a9d16b63b6f35f1c01b44ac650979e853d0bd3a442b92a082af64f"
_SHIM_STOCK_HASH = "7ce1342d3afa0334b59a3e38c0aed15e162b9abe9d46f95f34be44af47f3b493"
STOCK_SHIM_HASHES = {
    "BepInEx/core/BepInEx.Preloader.dll": _PRELOADER_STOCK_HASH,
    "BepInEx/core/HarmonyXInterop.dll": _SHIM_STOCK_HASH,
}


def classify_loader_write_safety(hashes: dict[str, str]) -> dict[str, Any]:
    stock = all(hashes.get(name) == digest for name, digest in STOCK_SHIM_HASHES.items())
    return {
        "status": "unsupported" if stock else "unknown",
        "reason": "persistent_assembly_shim" if stock else "loader_write_paths_unverified",
        "scope": "original-file-preservation",
        "game_executed": False,
    }


def assess_loader_write_safety(loader: Path) -> dict[str, Any]:
    root = checked_path(loader)
    hashes = {}
    for name in STOCK_SHIM_HASHES:
        path = confined(root, name)
        if path.is_file():
            hashes[name] = hash_file(path)
    return classify_loader_write_safety(hashes)


def confined(root: Path, name: str) -> Path:
    part = Path(name)
    if not name or part.is_absolute() or part.drive or ".." in part.parts:
        raise ValueError("Destek paketi yolu güvenli ve göreli olmalı.")
    path = checked_path(root / part)
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Destek paketi yolu kök dışında.")
    return path


def stage_loader_support(
    paths: ProjectPaths,
    *,
    loader: Path,
    source_cache: Path,
    catalog_root: Path,
) -> dict[str, Any]:
    """Yerel geliştirici kataloğunu doğrular; manifest etkinleştirme izni değildir."""
    loader, source_cache, catalog_root = map(checked_path, (loader, source_cache, catalog_root))
    catalog_path = confined(catalog_root, "loader-components.json")
    if catalog_path.stat().st_size > 1024 * 1024:
        raise ValueError("Yükleyici katalog sınırı aşıldı.")
    catalog_bytes = catalog_path.read_bytes()
    catalog = strict_json(catalog_bytes)
    if catalog["format_version"] != 1:
        raise ValueError("Yükleyici katalog sürümü desteklenmiyor.")
    pending: list[tuple[Path, str, str, str]] = []
    license_names = {item["file"] for item in catalog["licenses"]}
    for item in catalog["components"]:
        if not item["license_files"] or not set(item["license_files"]) <= license_names:
            raise ValueError("Bileşenin lisans bildirimi eksik.")
        pending.append(
            (confined(loader, item["path"]), "loader/" + item["path"], item["sha256"], "binary")
        )
    for item in catalog["licenses"]:
        pending.append(
            (
                confined(catalog_root, item["file"]),
                "LICENSES/" + Path(item["file"]).name,
                item["sha256"],
                "notice",
            )
        )
    for item in catalog["sources"]:
        repo, commit = item["repository"], item["commit"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not re.fullmatch(
            r"[a-f0-9]{40}", commit
        ):
            raise ValueError("Kaynak arşiv kimliği geçersiz.")
        filename = repo.replace("/", "-") + "-" + commit + ".zip"
        pending.append(
            (
                confined(source_cache, filename),
                "SOURCES/" + filename,
                item["source_archive_sha256"],
                "source",
            )
        )
    if not 1 <= len(pending) <= 1000:
        raise ValueError("Destek paketi dosya sınırı aşıldı.")
    names = set()
    for source, name, digest, _ in pending:
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Katalog hash'i geçersiz.")
        if name.casefold() in names:
            raise ValueError("Destek paketi hedefi yineleniyor.")
        names.add(name.casefold())
        if (
            not source.is_file()
            or source.stat().st_size > 64 * 1024 * 1024
            or hash_file(source) != digest
        ):
            raise ValueError("Destek dosyası eksik, büyük veya katalogdan sonra değişmiş.")
    relative = "artifacts/loader-support-" + uuid4().hex
    output = paths.output(relative)
    if output.exists() or any(
        output.is_relative_to(root) or root.is_relative_to(output)
        for root in (loader, source_cache, catalog_root)
    ):
        raise ValueError("Destek hedefi kaynaklarla örtüşüyor veya mevcut.")
    output.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "format_version": 1,
        "purpose": "offline-loader-support",
        "status": "staging",
        "catalog_sha256": sha256(catalog_bytes).hexdigest(),
        "files": [],
        "includes_plugin": False,
        "includes_translation": False,
        "application_verified": False,
        "installation_authorized": False,
        "redistribution_package_verified": False,
        "loader_write_safety": assess_loader_write_safety(loader),
    }
    manifest_name = relative + "/support-manifest.json"
    paths.write_json(manifest_name, manifest)
    try:
        for source, name, expected, kind in pending:
            target = confined(output, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as incoming, target.open("xb") as outgoing:
                written = 0
                for block in iter(lambda: incoming.read(1024 * 1024), b""):
                    written += len(block)
                    if written > 64 * 1024 * 1024:
                        raise ValueError("Destek dosyası kopyalama sırasında boyut sınırını aştı.")
                    outgoing.write(block)
            if hash_file(target) != expected:
                raise ValueError("Destek kopyası hash kontrolünü geçmedi.")
            manifest["files"].append(
                {"path": name, "sha256": expected, "bytes": target.stat().st_size, "kind": kind}
            )
            paths.write_json(manifest_name, manifest)
        with confined(output, "component-catalog.json").open("xb") as stream:
            stream.write(catalog_bytes)
        paths.write_text(
            relative + "/README.txt",
            "Offline loader support files.\n"
            "No plugin, translation or activation plan. Do not install into the game folder.\n"
            "Source archives and license notices are retained separately.\n"
            "Final mod-package scope, source access and in-game testing are not yet verified.\n",
        )
        for name, kind in (("component-catalog.json", "metadata"), ("README.txt", "instructions")):
            target = confined(output, name)
            manifest["files"].append(
                {
                    "path": name,
                    "sha256": hash_file(target),
                    "bytes": target.stat().st_size,
                    "kind": kind,
                }
            )
        manifest["status"] = "prepared"
        paths.write_json(manifest_name, manifest)
    except Exception:
        manifest["status"] = "failed"
        paths.write_json(manifest_name, manifest)
        raise
    return {
        "directory": str(output),
        "manifest": str(paths.output(manifest_name)),
        "files": len(manifest["files"]),
        "status": "prepared",
    }
