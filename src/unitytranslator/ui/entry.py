"""Standalone entry: the same binary runs the GUI and isolated Unity reader."""

import json
import sys
from pathlib import Path


def entry() -> int:
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        sys.frozen = True
        sys.executable = str(Path(sys.argv[0]).resolve())
    if len(sys.argv) > 1 and sys.argv[1] == "--unity-worker":
        from unitytranslator.filesystem import checked_path
        from unitytranslator.workers.unity_probe import probe

        try:
            source, logical, game = sys.argv[2:5]
            root = checked_path(Path(game))
            path = checked_path(Path(source))
            if not path.is_relative_to(root):
                raise ValueError("Worker kaynağı oyun kökü dışında.")
            print(
                json.dumps(
                    probe(path, logical, root, sys.argv[5] if len(sys.argv) > 5 else "en"),
                    ensure_ascii=True,
                )
            )
            return 0
        except Exception as exc:
            print(json.dumps({"fatal": type(exc).__name__}))
            return 1
    if len(sys.argv) > 1 and sys.argv[1] == "--verify-ui":
        from unitytranslator.ui.verify import verify_ui

        return verify_ui(sys.argv[2], sys.argv[3])
    from unitytranslator.__main__ import main

    if len(sys.argv) == 1:
        sys.argv.append("gui")
    return main()


if __name__ == "__main__":
    raise SystemExit(entry())
