"""Confined project output paths; no API writes into the original game tree."""

import json
import os
import stat
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any


class PolicyError(ValueError):
    pass


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
        raise PolicyError("Ağ/aygıt yolu veya alternatif veri akışı kabul edilmiyor.")
    if ".." in path.parts:
        raise PolicyError("Üst dizin geçişi kabul edilmiyor.")
    if path.drive and not path.is_absolute():
        raise PolicyError("Sürücüye göreli yol kabul edilmiyor.")
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        if part.endswith((".", " ")) or Path(part).is_reserved():
            raise PolicyError("Ayrılmış veya belirsiz Windows dosya adı kabul edilmiyor.")
    absolute = path.absolute()
    for component in [*reversed(absolute.parents), absolute]:
        if component.is_symlink():
            raise PolicyError("Symlink/junction/reparse point kabul edilmiyor.")
        if component.exists():
            info = component.lstat()
            if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise PolicyError("Symlink/junction/reparse point kabul edilmiyor.")
    return absolute.resolve()


class ProjectPaths:
    def __init__(self, game: Path, project: Path):
        self.game = checked_path(game)
        self.project = checked_path(project)
        if _is_network_drive(self.game) or _is_network_drive(self.project):
            raise PolicyError("Oyun ve proje için ağ sürücüsü yerine yerel disk klasörleri seçin.")
        if not self.game.is_dir():
            raise PolicyError("Oyun klasörü bulunamadı.")
        if self.project.is_relative_to(self.game) or self.game.is_relative_to(self.project):
            raise PolicyError("Oyun ve proje klasörleri örtüşemez.")

    def output(self, relative: str) -> Path:
        part = Path(relative)
        if part.is_absolute() or part.drive:
            raise PolicyError("Çıktı yolu göreli olmalı.")
        target = checked_path(self.project / part)
        if not target.is_relative_to(self.project) or target == self.project:
            raise PolicyError("Çıktı proje klasörünün içinde olmalı.")
        if target.exists() and target.stat().st_nlink > 1:
            raise PolicyError("Hard link çıktısı kabul edilmiyor.")
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
