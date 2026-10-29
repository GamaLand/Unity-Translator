"""Bounded native-template inspection worker. Game scripts are parsed strictly as data."""

import json
import os
import sys
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from unitytranslator.filesystem import checked_path
from unitytranslator.renpy_say import SYNTAX_VERSION
from unitytranslator.renpy_templates import (
    ADAPTER_ID,
    MAX_FILE_BYTES,
    PARSER_VERSION,
    language_identifier,
    parse_template,
)
from unitytranslator.source_contracts import validate_relative_source

MAX_FILES = 128
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_DEPTH = 16


def template_files(game: Path, relative: str) -> tuple[str, tuple[Path, ...], list[str]]:
    validate_relative_source(relative)
    part = Path(relative)
    if (
        len(part.parts) < 4 or part.parts[:2] != ("game", "tl")
        or part.suffix.lower() != ".rpy"
    ):
        raise ValueError("Select a loose game/tl/<language>/*.rpy translation template.")
    language = language_identifier(part.parts[2])
    selected = checked_path(game / part)
    if not selected.is_relative_to(game) or not selected.is_file():
        raise ValueError("Selected native Ren'Py template is missing.")
    root = checked_path(game / "game" / "tl" / language)
    pending = [(root, 0)]
    files: list[Path] = []
    excluded: list[str] = []
    count, total = 0, 0
    while pending:
        directory, depth = pending.pop()
        with os.scandir(checked_path(directory)) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError("Ren'Py template discovery entry limit exceeded.")
                path = checked_path(Path(entry.path))
                if not path.is_relative_to(root):
                    raise ValueError("Ren'Py template path escaped its language root.")
                if path.is_dir():
                    if depth >= MAX_DEPTH:
                        raise ValueError("Ren'Py template discovery depth limit exceeded.")
                    pending.append((path, depth + 1))
                elif path.is_file():
                    if path.suffix.lower() != ".rpy":
                        excluded.append(path.relative_to(game).as_posix())
                        continue
                    size = path.stat().st_size
                    total += size
                    if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES or len(files) >= MAX_FILES:
                        raise ValueError("Ren'Py template file or total-size limit exceeded.")
                    files.append(path)
    return language, tuple(sorted(files)), sorted(excluded)


def probe(game: Path, relative: str, source_language: str) -> dict[str, Any]:
    game = checked_path(game)
    language, files, excluded = template_files(game, relative)
    fingerprints: dict[str, str] = {}
    snapshots = []
    native_ids: set[str] = set()
    strings: dict[str, str] = {}
    for path in files:
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        before = sha256(raw).hexdigest()
        document = parse_template(raw, language)
        with path.open("rb") as stream:
            after = stream.read(MAX_FILE_BYTES + 1)
        if after != raw:
            raise ValueError("Ren'Py source changed while reading.")
        name = path.relative_to(game).as_posix()
        snapshot = document.snapshot(name, source_language)
        if snapshot.source.fingerprint != before:
            raise ValueError("Ren'Py source bytes differ from their fingerprint.")
        for record in document.records:
            if record.kind == "dialogue" and record.slot == 0:
                if record.block in native_ids:
                    raise ValueError("Duplicate native Ren'Py identifier across template files.")
                native_ids.add(record.block)
            elif record.kind == "string":
                previous = strings.get(record.source)
                if previous is not None and previous != record.candidate:
                    raise ValueError("Conflicting global Ren'Py string mappings.")
                strings[record.source] = record.candidate
        snapshots.append(snapshot)
        fingerprints[name] = before
    if template_files(game, relative)[1] != files:
        raise ValueError("Ren'Py source file selection changed while reading.")
    return {
        "adapter_id": ADAPTER_ID, "adapter_version": "1", "format_version": 2,
        "engine_report": {"format_version": 1, "engine": "renpy", "selection": "source"},
        "parser_version": PARSER_VERSION,
        "syntax_version": SYNTAX_VERSION,
        "template_language": language,
        "complete_source_set": True,
        "extraction": "supported", "application": "unsupported", "errors": [],
        "fingerprints": fingerprints,
        "source_descriptors": [asdict(s.source) for s in snapshots],
        "units": [asdict(u) for s in snapshots for u in s.units],
        "payloads": [s.metadata for s in snapshots],
        "coverage": [{"path": name, "kind": "native_template"} for name in fingerprints],
        "outside_scope": [
            "Original scripts, archives, compiled scripts, Python, screens and styles.",
            "Native installation and language activation are not verified.",
        ],
        "excluded_files": excluded,
    }


def main() -> int:
    try:
        game, relative, language = sys.argv[1:]
        print(json.dumps(probe(Path(game), relative, language), ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({"fatal": type(exc).__name__, "message": str(exc)[:1024]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
