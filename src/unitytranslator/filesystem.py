"""Confined project output paths; no API writes into the original game tree."""

import json
import os
import stat
import tempfile
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from typing import Any

from unitytranslator.diagnostics import Diagnostic


class PolicyError(Diagnostic):
    pass


# One Windows name rule for Python and the recipient installer core. Windows and .NET treat
# these names as devices, drop trailing dots, spaces, NEL or NBSP, or refuse the characters.
_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"{kind}{digit}" for kind in ("COM", "LPT") for digit in "123456789\u00b9\u00b2\u00b3"}
)
_RESERVED_CHARACTERS = frozenset('<>"|?*').union(map(chr, range(32)))
_TRIMMED_ENDINGS = (".", " ", "\x85", "\xa0")
MAX_NAME_UNITS = 255  # NTFS limit for one name, in UTF-16 code units.
# Windows matches device names in ASCII only; str.upper() would also map 'ı' to 'I'.
_ASCII_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def ambiguous_windows_name(part: str) -> bool:
    """True when one path component is not one stable, ordinary Windows file name."""
    return (
        not part
        or part.endswith(_TRIMMED_ENDINGS)
        or not _RESERVED_CHARACTERS.isdisjoint(part)
        or len(part.encode("utf-16-le", "surrogatepass")) > 2 * MAX_NAME_UNITS
        or part.partition(".")[0].rstrip(" ").translate(_ASCII_UPPER) in _DEVICE_NAMES
    )


def _is_network_drive(path: Path) -> bool:
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.GetDriveTypeW.restype = wintypes.UINT
    return int(kernel.GetDriveTypeW(str(path.anchor))) == 4


def checked_path(path: Path) -> Path:
    raw = str(path)
    if raw.startswith(("\\\\", "//")) or ":" in raw[2:]:
        raise PolicyError("Network or device paths and alternate data streams are not accepted.")
    if ".." in path.parts:
        raise PolicyError("Parent directory traversal is not accepted.")
    if path.drive and not path.is_absolute():
        raise PolicyError("Drive-relative paths are not accepted.")
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        if ambiguous_windows_name(part):
            raise PolicyError("Reserved or ambiguous Windows file names are not accepted.")
    absolute = path.absolute()
    for component in [*reversed(absolute.parents), absolute]:
        if component.is_symlink():
            raise PolicyError("Symlinks, junctions and reparse points are not accepted.")
        if component.exists():
            info = component.lstat()
            if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise PolicyError("Symlinks, junctions and reparse points are not accepted.")
    return absolute.resolve()


def checked_relative(root: Path, relative: str) -> Path:
    """Resolve a manifest-relative target with the recipient installer's Confined rule."""
    windows = PureWindowsPath(relative)
    if not relative or windows.drive or windows.root:
        raise PolicyError("The target path must be relative and inside its root.")
    if ":" in relative:
        raise PolicyError("Network or device paths and alternate data streams are not accepted.")
    parts = relative.replace("/", "\\").split("\\")
    if ".." in parts:
        raise PolicyError("Parent directory traversal is not accepted.")
    if any(part == "." or ambiguous_windows_name(part) for part in parts):
        raise PolicyError("Reserved or ambiguous Windows file names are not accepted.")
    root = checked_path(root)
    target = checked_path(root.joinpath(*parts))
    if not target.is_relative_to(root) or target == root:
        raise PolicyError("The target path must be relative and inside its root.")
    return target


class ProjectPaths:
    def __init__(self, game: Path, project: Path):
        self.game = checked_path(game)
        self.project = checked_path(project)
        if _is_network_drive(self.game) or _is_network_drive(self.project):
            raise PolicyError(
                "Select local disk folders for the game and project instead of network drives."
            )
        if not self.game.is_dir():
            raise PolicyError("Game folder not found.")
        if self.project.is_relative_to(self.game) or self.game.is_relative_to(self.project):
            raise PolicyError("The game and project folders must not overlap.")

    def output(self, relative: str) -> Path:
        part = Path(relative)
        if part.is_absolute() or part.drive:
            raise PolicyError("Output path must be relative.")
        target = checked_path(self.project / part)
        if not target.is_relative_to(self.project) or target == self.project:
            raise PolicyError("Output must be inside the project folder.")
        if target.exists() and target.stat().st_nlink > 1:
            raise PolicyError("Hard link output is not accepted.")
        return target

    def write_text(self, relative: str, value: str) -> Path:
        target = self.output(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.output(relative)
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=".writing-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            self.output(relative)
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
        return target

    def write_json(self, relative: str, value: Any) -> Path:
        encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        return self.write_text(relative, encoded)


def hash_file(path: Path) -> str:
    digest = sha256()
    with checked_path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
