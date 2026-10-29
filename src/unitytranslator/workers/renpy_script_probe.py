"""Bounded original-source worker; reads bytes and fixed syntax, never game code."""

import json
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, replace
from hashlib import md5, sha256
from pathlib import Path
from typing import Any

from unitytranslator.engines import renpy_inputs
from unitytranslator.filesystem import checked_path
from unitytranslator.renpy_archive import ArchiveIndex, read_index
from unitytranslator.renpy_dialects import inspect_source_dialect
from unitytranslator.renpy_python import source_order
from unitytranslator.renpy_say import SYNTAX_VERSION
from unitytranslator.renpy_scripts import (
    ADAPTER_ID,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    PARSER_VERSION,
    SOURCE_NAMESPACE,
    parse_scripts,
)
from unitytranslator.source_contracts import validate_relative_source


def probe(
    game: Path, relative: str, source_language: str, *,
    cancelled: Callable[[], bool] = lambda: False, timeout: float = 120,
    anchor: str | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout

    def interrupted() -> bool:
        if time.monotonic() > deadline:
            raise ValueError("Ren'Py source reading exceeded its time limit.")
        return cancelled()

    def current_hash(path: Path) -> str:
        digest = sha256()
        with checked_path(path).open("rb") as stream:
            while block := stream.read(1024 * 1024):
                if interrupted():
                    raise ValueError("Source extraction was cancelled.")
                digest.update(block)
        return digest.hexdigest()

    validate_relative_source(relative)
    if anchor is not None:
        validate_relative_source(anchor)
    game = checked_path(game)
    version = checked_path(game / "renpy/vc_version.py")
    version_raw = b""
    if version.is_file():
        with version.open("rb") as stream:
            version_raw = stream.read(8193)
        if len(version_raw) > 8192:
            raise ValueError("Ren'Py version evidence size limit exceeded.")
    try:
        dialect = inspect_source_dialect(game, version_raw, cancelled=interrupted)
    except ValueError as exc:
        raise ValueError(relative + ": " + str(exc)) from exc
    discovered = renpy_inputs(game)
    candidates = discovered["source_candidates"]
    if not dialect["python_source"] and any(
        item["kind"] == "renpy_python_source" for item in candidates
    ):
        raise ValueError(
            "Mixed _ren.py sources require verified dialect and load-order mapping; "
            "the original-source set cannot be activated partially."
        )
    sources = [item for item in candidates
               if item["kind"] in ("archive", "loose_script", "renpy_python_source")]
    selected = next((item for item in sources if item["path"] == relative), None)
    if selected is None:
        raise ValueError("Select an original .rpy/_ren.py source or a bounded RPA-3.0 archive.")
    fingerprints = dict(dialect["fingerprints"])
    if version.is_file():
        fingerprints["renpy/vc_version.py"] = sha256(version_raw).hexdigest()
    inventory: list[tuple[str, int]] = []
    excluded: list[str] = []
    excluded_bytes = 0
    archive_sources: dict[str, ArchiveIndex] = {}
    origins: dict[str, str] = {}
    loose: list[str] = []
    total = 0
    archive_entries = 0
    pairs: list[dict[str, Any]] = []
    current_member = ""

    def exclude(names: Iterable[str]) -> None:
        nonlocal excluded_bytes
        for name in names:
            excluded_bytes += len(name.encode("utf-8"))
            if len(excluded) >= 200000 or excluded_bytes > 16 * 1024 * 1024:
                raise ValueError("Ren'Py exclusion evidence bounds exceeded.")
            excluded.append(name)

    for item in sources:
        path = checked_path(game / item["path"])
        if item["kind"] == "archive":
            index = read_index(path)
            archive_entries += len(index.members)
            if archive_entries > 200000:
                raise ValueError("Ren'Py aggregate archive index entry limit exceeded.")
            if not dialect["python_source"] and any(
                m.name.lower().endswith("_ren.py") for m in index.members
            ):
                raise ValueError(
                    "Archived _ren.py sources require verified dialect and load-order mapping."
                )
            script_members = [m for m in index.members if (
                m.name.endswith(".rpy") or m.name.endswith("_ren.py")
            ) and not m.name.startswith("tl/")]
            if not script_members:
                exclude(item["path"] + ":" + m.name for m in index.members
                        if m.name.endswith(".rpyc"))
                continue
            archive_sources[item["path"]] = index
            if len(archive_sources) > 128:
                raise ValueError("Ren'Py original-source archive count limit exceeded.")
            if path.stat().st_size > 32 * 1024 * 1024 * 1024:
                raise ValueError("Ren'Py source archive size limit exceeded.")
            fingerprints[item["path"]] = current_hash(path)
            for member in sorted(script_members, key=lambda m: m.name):
                total += member.length
                if len(inventory) >= MAX_FILES or total > MAX_TOTAL_BYTES:
                    raise ValueError("Ren'Py source member count or total-size bound exceeded.")
                if member.length > MAX_FILE_BYTES:
                    raise ValueError("Ren'Py source member size limit exceeded.")
                if member.name in origins:
                    raise ValueError(
                        "Overlapping original-source containers need verified precedence."
                    )
                origins[member.name] = item["path"]
                inventory.append((member.name, member.length))
            source_names = {m.name for m in script_members}
            exclude(m.name for m in index.members if m.name not in source_names)
        else:
            loose.append(item["path"])
    if archive_sources and (len(archive_sources) != 1 or loose) and dialect["evidence_kind"] != (
        "audited_source_contracts"
    ):
        raise ValueError("Multiple original-source containers require verified load-order mapping.")
    for name in sorted(loose):
        path = checked_path(game / name)
        size = path.stat().st_size
        total += size
        if len(inventory) >= MAX_FILES or total > MAX_TOTAL_BYTES:
            raise ValueError("Ren'Py loose-source count or total-size bound exceeded.")
        if size > MAX_FILE_BYTES:
            raise ValueError("Ren'Py source member size limit exceeded.")
        member_name = name.removeprefix("game/")
        if member_name in origins:
            raise ValueError("Loose/archive overrides need separately verified source precedence.")
        origins[member_name] = name
        inventory.append((member_name, size))
    containers = sorted([*archive_sources, *loose])
    if anchor is not None and anchor not in containers:
        raise ValueError("Previously active Ren'Py original-source anchor is missing.")
    if relative not in containers:
        raise ValueError("The selected archive has no supported original sources.")
    relative = anchor or containers[0]
    if relative not in fingerprints:
        fingerprints[relative] = current_hash(checked_path(game / relative))
    if not inventory:
        raise ValueError("Select an original .rpy file or a script-bearing RPA-3.0 archive.")
    inventory.sort(key=lambda item: source_order(item[0]))
    bases = [source_order(name) for name, _ in inventory]
    base_set = set(bases)
    if len(base_set) != len(bases):
        raise ValueError("Conflicting .rpy/_ren.py source basenames; no precedence is guessed.")
    exclude(
        item["path"] for item in candidates if item["kind"] == "compiled_script"
        and item["path"].removeprefix("game/").removesuffix(".rpyc") not in base_set
    )

    def members() -> Iterator[tuple[str, bytes]]:
        nonlocal current_member
        compiled_total = 0
        for name, expected_size in inventory:
            current_member = name
            if interrupted():
                raise ValueError("Source extraction was cancelled.")
            origin = origins[name]
            if origin in archive_sources:
                index = archive_sources[origin]
                compiled_name = source_order(name) + ".rpyc"
                raw = index.read_member(name, limit=MAX_FILE_BYTES)
                compiled = index.read_member(compiled_name)
                compiled_total += len(compiled)
                if compiled_total > 128 * 1024 * 1024:
                    raise ValueError("Ren'Py compiled-source evidence size limit exceeded.")
                if (
                    len(compiled) < 62 or not compiled.startswith(b"RENPY RPC2")
                    or compiled[-16:] != md5(raw, usedforsecurity=False).digest()
                ):
                    raise ValueError(
                        "Archived source lacks matching pinned compiled-source evidence."
                    )
                pairs.append({"source": name, "compiled": compiled_name,
                              "compiled_sha256": sha256(compiled).hexdigest(),
                              "source_footer_matches": True})
            else:
                path = checked_path(game / origin)
                with path.open("rb") as stream:
                    raw = stream.read(MAX_FILE_BYTES + 1)
                key = origin
                digest = sha256(raw).hexdigest()
                if key in fingerprints and fingerprints[key] != digest:
                    raise ValueError("Ren'Py source changed during reading.")
                fingerprints[key] = digest
            if len(raw) != expected_size:
                raise ValueError("Ren'Py source size changed during reading.")
            yield name, raw

    try:
        document = parse_scripts(
            members(), fingerprints[relative], cancelled=interrupted,
            reserved_attributes=frozenset(dialect["reserved_attributes"]),
            python_dialect=dialect["python_source"],
        )
    except ValueError as exc:
        raise ValueError("Source member " + current_member + ": " + str(exc)) from exc
    mixed = len(archive_sources) > 1 or bool(archive_sources and loose)
    if mixed:
        document = replace(document, members=tuple(
            {**member, "container": origins[member["name"]]} for member in document.members
        ), locations=tuple(
            {**location, "container": origins[location["member"]]}
            for location in document.locations
        ))
    snapshot = document.snapshot(relative, source_language)
    for name, digest in fingerprints.items():
        if interrupted():
            raise ValueError("Source extraction was cancelled.")
        if current_hash(checked_path(game / name)) != digest:
            raise ValueError("Ren'Py source or version evidence changed during reading.")
    if renpy_inputs(game)["source_candidates"] != candidates:
        raise ValueError("Ren'Py input selection changed during reading.")
    return {
        "format_version": 2, "adapter_id": ADAPTER_ID, "adapter_version": "1",
        "engine_report": {"format_version": 1, "engine": "renpy", "selection": "source"},
        "parser_version": PARSER_VERSION, "template_language": SOURCE_NAMESPACE,
        "syntax_version": SYNTAX_VERSION,
        "dialect_evidence": dialect,
        "version_evidence": discovered["version_evidence"],
        "complete_source_set": True, "extraction": "supported", "application": "unsupported",
        "errors": [], "fingerprints": fingerprints, "source_inventory": candidates,
        "source_descriptors": [asdict(snapshot.source)],
        "units": [asdict(unit) for unit in snapshot.units], "payloads": [snapshot.metadata],
        "coverage": [{"path": name, "kind": (
            "renpy_python_source" if name.endswith("_ren.py") else "original_script"
        ), "sha256": member["sha256"]}
                     for name, member in ((m["name"], m) for m in document.members)],
        "exclusion_counts": document.exclusions,
        "paired_source_evidence": pairs,
        "source_resolution": "disjoint-basename-union-v1" if mixed else "single-source-scope-v1",
        "outside_scope": [
            "Verified symbolic dialogue, attributes, nointeract and literal UI/menu keys.",
            "Multiline/backtick literals, other suffixes and voice/nvl groups are excluded.",
            "Images, compiled-only scripts and arbitrary Python literals are not text inputs.",
        ],
        "excluded_files": sorted(excluded),
    }


def main() -> int:
    try:
        args = sys.argv[1:]
        streaming = args[-1:] == ["--stream-report"]
        args = args[:-1] if streaming else args
        anchor = None
        if len(args) == 5 and args[3] == "--anchor":
            anchor = args[4]
            args = args[:3]
        game, relative, language = args
        report = probe(Path(game), relative, language, anchor=anchor)
        if streaming:
            from unitytranslator.report_stream import write_report

            write_report(report, sys.stdout)
        else:
            print(json.dumps(report, ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({"fatal": type(exc).__name__, "message": str(exc)[:1024]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
