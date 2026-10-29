"""Bounded, read-only engine hints. Detection never grants reader or install support."""

import os
import re
import stat
import time
from pathlib import Path
from typing import Any

from unitytranslator.filesystem import checked_path
from unitytranslator.renpy_archive import inspect_archive

ENGINES = ("auto", "unity", "renpy")
MAX_ENTRIES = 20000
MAX_DEPTH = 32
MAX_SECONDS = 5.0
MAX_HEADER_BYTES = 8192


def engine_evidence(game: Path, selection: str = "auto") -> dict[str, Any]:
    """Inspect installation layout only; callers must verify actual source contents."""
    if selection not in ENGINES:
        raise ValueError("Unknown engine selection.")
    game = checked_path(game)
    hints: list[dict[str, str]] = []
    with os.scandir(game) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_ENTRIES:
                raise ValueError("Engine discovery entry limit exceeded.")
            if entry.name.endswith("_Data") or entry.name == "renpy":
                path = checked_path(Path(entry.path))
                if path.is_dir():
                    hints.append({
                        "engine": "renpy" if entry.name == "renpy" else "unity",
                        "path": entry.name,
                        "kind": "directory_hint",
                    })
    # A loose template layout is useful even without the bundled engine distribution.
    tl = checked_path(game / "game" / "tl")
    if tl.is_dir():
        hints.append({"engine": "renpy", "path": "game/tl", "kind": "directory_hint"})
    content = checked_path(game / "game")
    if content.is_dir():
        with os.scandir(content) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_ENTRIES:
                    raise ValueError("Engine discovery entry limit exceeded.")
                if Path(entry.name).suffix.lower() in (".rpy", ".rpyc", ".rpa") or (
                    entry.name.lower().endswith("_ren.py")
                ):
                    path = checked_path(Path(entry.path))
                    if path.is_file():
                        hints.append({
                            "engine": "renpy", "path": "game/" + entry.name,
                            "kind": "extension_hint",
                        })
    detected = sorted({hint["engine"] for hint in hints})
    automatic = detected[0] if len(detected) == 1 else "ambiguous" if detected else "unknown"
    return {
        "format_version": 1,
        "engine": automatic if selection == "auto" else selection,
        "detected": detected,
        "selection": selection,
        "evidence": sorted(hints, key=lambda item: item["path"]),
        "uncertainties": ["Filesystem hints do not establish source or runtime compatibility."],
    }


def renpy_inputs(game: Path) -> dict[str, Any]:
    """Classify loose inputs and archive signatures without decoding executable data."""
    game = checked_path(game)
    root = checked_path(game / "game")
    candidates: list[dict[str, Any]] = []
    containers: set[str] = set()
    started = time.monotonic()
    pending = [(root, 0)] if root.is_dir() else []
    seen = 0
    while pending:
        directory, depth = pending.pop()
        with os.scandir(checked_path(directory)) as entries:
            for entry in entries:
                seen += 1
                if seen > MAX_ENTRIES or time.monotonic() - started > MAX_SECONDS:
                    raise ValueError("Ren'Py discovery bounds exceeded; no complete scan produced.")
                info = entry.stat(follow_symlinks=False)
                if entry.is_symlink() or getattr(info, "st_file_attributes", 0) & (
                    stat.FILE_ATTRIBUTE_REPARSE_POINT
                ):
                    raise ValueError("Ren'Py discovery refuses symlink or reparse entries.")
                directory_entry = entry.is_dir(follow_symlinks=False)
                suffix = Path(entry.name).suffix.lower()
                python_dialect = entry.name.lower().endswith("_ren.py")
                if not directory_entry and suffix not in (".rpy", ".rpyc", ".rpa") and not (
                    python_dialect
                ):
                    continue
                # The parent directory and direct entry metadata are checked once.
                # Hints grant no authority: readers recheck full paths before opening
                # source bytes, and archive inspection below does the same.
                path = Path(entry.path)
                if directory_entry:
                    if depth >= MAX_DEPTH:
                        raise ValueError("Ren'Py discovery depth limit exceeded.")
                    pending.append((checked_path(path), depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                relative = path.relative_to(game).as_posix()
                kind = "renpy_python_source" if python_dialect else {
                    ".rpy": "loose_script", ".rpyc": "compiled_script", ".rpa": "archive",
                }[
                    suffix
                ]
                if suffix == ".rpy" and path.is_relative_to(root / "tl"):
                    kind = "translation_template_candidate"
                candidate: dict[str, Any] = {
                    "path": relative, "size": info.st_size, "kind": kind,
                    "status": "unverified_hint",
                }
                if python_dialect:
                    candidate.update(
                        status="unverified_hint", reason="source_contract_verification_required",
                    )
                if suffix == ".rpa":
                    with checked_path(path).open("rb") as stream:
                        header = stream.read(8)
                    candidate["header"] = (
                        "RPA-3.0" if header.startswith(b"RPA-3.0 ") else
                        "RPA-2.0" if header.startswith(b"RPA-2.0 ") else "unknown"
                    )
                    if candidate["header"] == "RPA-3.0":
                        try:
                            candidate["archive_inspection"] = inspect_archive(path)
                        except (ValueError, OSError) as exc:
                            candidate["archive_inspection"] = {
                                "status": "unsupported_or_invalid", "reason": str(exc),
                            }
                containers.add(kind)
                candidates.append(candidate)
    version = checked_path(game / "renpy" / "vc_version.py")
    versions = []
    if version.is_file():
        with version.open("rb") as stream:
            raw = stream.read(MAX_HEADER_BYTES)
        match = re.search(rb"(?m)^version = ['\"]([0-9]+(?:\.[0-9]+){2,3})['\"]\r?$", raw)
        if match:
            versions.append({
                "path": "renpy/vc_version.py", "value": match[1].decode("ascii"),
                "kind": "static_literal_hint",
            })
    return {
        "format_version": 1,
        "source_candidates": sorted(candidates, key=lambda item: item["path"]),
        "container_indicators": sorted(containers),
        "version_evidence": versions,
        "complete": True,
    }
