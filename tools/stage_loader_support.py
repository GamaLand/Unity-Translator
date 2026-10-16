"""Doğrulanmış yerel loader/kaynak önbelleğinden çevrimdışı destek paketi."""

import argparse
import json
from pathlib import Path

from unitytranslator.filesystem import ProjectPaths
from unitytranslator.loader_support import stage_loader_support


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("game", "project", "loader", "source-cache"):
        parser.add_argument("--" + argument, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = stage_loader_support(
        ProjectPaths(args.game, args.project),
        loader=args.loader,
        source_cache=args.source_cache,
        catalog_root=root / "adapters/i2mono",
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
