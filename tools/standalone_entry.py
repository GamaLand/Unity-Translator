"""Packaging entry kept separate from the application package."""

import sys
from pathlib import Path

from unitytranslator.ui.entry import entry

if "__compiled__" in globals():
    sys.frozen = True
    sys.executable = str(Path(sys.argv[0]).resolve())

if __name__ == "__main__":
    raise SystemExit(entry())
