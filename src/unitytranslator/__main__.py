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
    parser = argparse.ArgumentParser(
        description="UnityTranslator - local game translation and review"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("gui", help="Open the desktop interface")
    for command, description in (
        ("scan", "Scan read-only compatibility indicators"),
        ("probe", "Inspect a supported source in an isolated process"),
        ("extract", "Extract a supported source into the SQLite project"),
        ("project", "Create or open a translation project"),
        ("export-textassets", "Export current approved game-text payloads to the project only"),
        ("export-renpy", "Stage approved native Ren'Py files in a new project export directory"),
        ("export-renpy-zip", "Package approved Ren'Py text for additive installation "
         "without a game copy"),
    ):
        item = sub.add_parser(command, help=description)
        item.add_argument("--game", required=True, type=Path, help="Game installation directory")
        item.add_argument(
            "--project",
            required=True,
            type=Path,
            help="Separate local translation project directory",
        )
        if command in ("probe", "extract"):
            item.add_argument(
                "--source", required=True, help="Source path relative to the game directory"
            )
        if command in ("scan", "probe", "extract"):
            item.add_argument(
                "--engine", choices=("auto", "unity", "renpy"), default="auto",
                help="Inspection engine override; does not grant installation support",
            )
        if command in ("export-renpy", "export-renpy-zip"):
            item.add_argument(
                "--language", required=True,
                help="Explicit Ren'Py language identifier for the project's target language",
            )
        if command in ("project", "probe"):
            item.add_argument("--source-language", default="en")
            item.add_argument("--target-language", default="tr")
    models = sub.add_parser("models", help="List model identifiers reported by the local server")
    models.add_argument("--provider", choices=("lm-studio", "llama-cpp"), required=True)
    models.add_argument("--address", required=True, help="Local server address")
    sample = sub.add_parser(
        "sample", help="Generate one synthetic translation and check its format"
    )
    sample.add_argument("--provider", choices=("lm-studio", "llama-cpp"), required=True)
    sample.add_argument("--address", required=True)
    sample.add_argument("--model", required=True, help="Explicitly selected model identifier")
    sample.add_argument(
        "--json-schema", action="store_true", help="Request structured output from the provider"
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
        if args.command in ("export-textassets", "export-renpy", "export-renpy-zip"):
            existing = ProjectRepository.existing_paths(args.project)
            if existing.game != paths.game:
                raise ValueError("Project is bound to another game directory.")
            with ProjectRepository(existing) as repository:
                if args.command == "export-renpy-zip":
                    from unitytranslator.renpy_package import export_install_package

                    exported = export_install_package(repository, args.language)
                elif args.command == "export-renpy":
                    from unitytranslator.renpy_export import export_native

                    exported = export_native(repository, args.language)
                else:
                    from unitytranslator.textasset_export import export_payloads

                    exported = export_payloads(repository)
                print(json.dumps(exported, ensure_ascii=True, indent=2))
            return 0
        if args.command == "project":
            with ProjectRepository(paths, args.source_language, args.target_language) as repository:
                print(json.dumps(repository.manifest(), ensure_ascii=True, indent=2))
            return 0
        if args.command == "extract":
            print(json.dumps(
                extract_to_project(paths, args.source, engine=args.engine),
                ensure_ascii=True, indent=2,
            ))
            return 0
        result = (
            scan(paths, engine=args.engine)
            if args.command == "scan"
            else probe_source(
                paths, args.source, source_language=args.source_language, engine=args.engine
            )
        )
        output = save_report(paths, args.command, result)
        summary = {
            "report": str(output),
            "extraction": result["extraction"],
            "application": result["application"],
            "capabilities": result["capabilities"],
        }
        if "engine_report" in result:
            summary["engine_report"] = result["engine_report"]
        if "counts" in result:
            summary["counts"] = result["counts"]
            if "unity_versions" in result:
                summary["unity_versions"] = result["unity_versions"]
        print(json.dumps(summary, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
