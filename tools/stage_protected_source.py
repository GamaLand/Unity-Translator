"""Yerel koruma derlemesinin kaynak/lisans/hash paketini hazırlar; kurmaz."""

import argparse
import json
from pathlib import Path

from unitytranslator.filesystem import ProjectPaths
from unitytranslator.protected_source import stage_protected_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "project", "build", "archive"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = stage_protected_source(
        ProjectPaths(args.game, args.project),
        build=args.build,
        archive=args.archive,
        catalog_root=root / "adapters/i2mono",
        own_root=root,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
