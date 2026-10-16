"""Prepare a small approved I2 trial inside a project; never installs or starts it."""

import argparse
import json
from pathlib import Path

from unitytranslator.filesystem import ProjectPaths
from unitytranslator.i2_trial import prepare_i2_trial, validate_i2_trial
from unitytranslator.json_boundary import strict_json
from unitytranslator.repository import ProjectRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "project", "plugin", "plugin-evidence", "winhttp"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in (
        "runtime-relative",
        "source-set",
        "unity-version",
        "assembly-relative",
        "target-name",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--unit-id", action="append", required=True)
    args = parser.parse_args()
    catalog = strict_json(
        (
            Path(__file__).resolve().parents[1] / "adapters/i2mono/loader-components.json"
        ).read_bytes()
    )
    digest = next(
        item["sha256"] for item in catalog["components"] if Path(item["path"]).name == "winhttp.dll"
    )
    with ProjectRepository(ProjectPaths(args.game, args.project)) as repo:
        result = prepare_i2_trial(
            repo,
            runtime_relative=args.runtime_relative,
            plugin=args.plugin,
            plugin_evidence=args.plugin_evidence,
            winhttp=args.winhttp,
            winhttp_sha256=digest,
            source_set=args.source_set,
            unity_version=args.unity_version,
            assembly_relative=args.assembly_relative,
            target_name=args.target_name,
            selected_unit_ids=set(args.unit_id),
        )
        relative = Path(result["manifest"]).relative_to(repo.paths.project).as_posix()
        result["verification"] = validate_i2_trial(repo, relative)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
