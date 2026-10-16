import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from unitytranslator.discovery import extract_to_project, probe_source, save_report, scan
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.providers import LocalProvider
from unitytranslator.repository import ProjectRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="UnityTranslator — salt okunur keşif prototipi")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("gui", help="Open the desktop interface")
    for command, description in (
        ("scan", "Uyumluluk göstergelerini tara"),
        ("probe", "Tek Unity kaynağını ayrı süreçte incele"),
        ("extract", "Yapılandırılmış kaynağı SQLite proje deposuna çıkar"),
        ("project", "Yerel çeviri projesi oluştur/aç"),
    ):
        item = sub.add_parser(command, help=description)
        item.add_argument("--game", required=True, type=Path, help="Oyun klasörü")
        item.add_argument("--project", required=True, type=Path, help="Ayrı yerel çalışma klasörü")
        if command in ("probe", "extract"):
            item.add_argument("--source", required=True, help="Oyun köküne göreli kaynak yolu")
        if command in ("project", "probe"):
            item.add_argument("--source-language", default="en")
            item.add_argument("--target-language", default="tr")
    models = sub.add_parser("models", help="Yerel sunucunun bildirdiği model kimliklerini listele")
    models.add_argument("--provider", choices=("lm-studio", "llama-cpp"), required=True)
    models.add_argument("--address", required=True, help="Yerel sunucu adresi")
    sample = sub.add_parser("sample", help="Tek sentetik metinde üretim ve biçim kontrolü")
    sample.add_argument("--provider", choices=("lm-studio", "llama-cpp"), required=True)
    sample.add_argument("--address", required=True)
    sample.add_argument("--model", required=True, help="Açıkça seçilen model kimliği")
    sample.add_argument(
        "--json-schema", action="store_true", help="Sağlayıcının şemalı çıktısını dene"
    )
    args = parser.parse_args()
    try:
        if args.command == "gui":
            from unitytranslator.ui.window import launch

            return launch()
        if args.command in ("models", "sample"):
            provider = LocalProvider(
                args.provider, args.address, structured_output=getattr(args, "json_schema", False)
            )
            if args.command == "models":
                values = asyncio.run(provider.list_models())
                print(json.dumps({"models": values, "loaded_status": "unknown"}, indent=2))
            else:
                translated = asyncio.run(
                    provider.translate_sample(args.model, "<b>Welcome {0}</b>\nYou have 3 points.")
                )
                print(json.dumps(translated, ensure_ascii=True, indent=2))
            return 0
        paths = ProjectPaths(args.game, args.project)
        if args.command == "project":
            with ProjectRepository(paths, args.source_language, args.target_language) as repository:
                print(json.dumps(repository.manifest(), ensure_ascii=True, indent=2))
            return 0
        if args.command == "extract":
            print(json.dumps(extract_to_project(paths, args.source), ensure_ascii=True, indent=2))
            return 0
        result = (
            scan(paths)
            if args.command == "scan"
            else probe_source(paths, args.source, source_language=args.source_language)
        )
        output = save_report(paths, args.command, result)
        summary = {
            "report": str(output),
            "extraction": result["extraction"],
            "application": result["application"],
        }
        if "counts" in result:
            summary["counts"] = result["counts"]
            summary["unity_versions"] = result["unity_versions"]
        print(json.dumps(summary, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Keşif tamamlanamadı: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
