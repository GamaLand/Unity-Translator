"""Stage approved native Ren'Py files; no game writes or deployment authority."""

import base64
import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any
from uuid import uuid4
from weakref import WeakKeyDictionary

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.reader_adapters import BUILTIN_READERS, result_from_report
from unitytranslator.renpy_format import RENPY_FORMAT
from unitytranslator.renpy_say import SYNTAX_VERSION, SayShape
from unitytranslator.renpy_templates import (
    MAX_FILE_BYTES,
    MAX_RECORDS,
    TemplateDocument,
    TemplateRecord,
    language_identifier,
    parse_template,
    quoted_literal,
    say_quoted_literal,
)
from unitytranslator.repository import ProjectRepository, canonical
from unitytranslator.source_contracts import ReaderContext, SourceDescriptor, SourceSnapshot
from unitytranslator.validation import format_issues
from unitytranslator.workers.renpy_probe import template_files

_REVISION_KEYS = ("unit_id", "source_revision", "translation_revision", "version")
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_FILES = 512
SHARD_BYTES = 1024 * 1024
SHARD_RECORDS = 4000
_ContextRows = dict[str, tuple[str, dict[str, Any]]]
_REVIEW_CONTEXTS: WeakKeyDictionary[
    ProjectRepository, dict[str, tuple[str, str, _ContextRows]]
] = WeakKeyDictionary()


def _rows(repo: ProjectRepository) -> list[dict[str, Any]]:
    return [dict(row) for row in repo.db.execute(
        "SELECT u.*,s.source_text,s.source_hash,s.context,s.category,s.source_language,"
        "w.version,w.status,w.translation_revision,w.approved_source,w.approved_translation,"
        "t.text AS translation,"
        "EXISTS(SELECT 1 FROM editor_drafts e WHERE e.unit_id=u.unit_id) AS has_draft "
        "FROM text_units u JOIN source_revisions s ON s.id=u.source_revision "
        "JOIN work_items w USING(unit_id) "
        "LEFT JOIN translation_revisions t ON t.id=w.translation_revision "
        "JOIN source_descriptors d ON d.id=u.logical_source_id "
        "WHERE u.active=1 AND d.active=1 "
        "AND d.adapter_id IN ('renpy-templates','renpy-scripts') ORDER BY u.unit_id"
    )]


def _sources(repo: ProjectRepository) -> list[SourceDescriptor]:
    return [SourceDescriptor(**json.loads(row[0])) for row in repo.db.execute(
        "SELECT descriptor_json FROM source_descriptors "
        "WHERE adapter_id IN ('renpy-templates','renpy-scripts') AND active=1 ORDER BY id"
    )]


def _snapshot_metadata(repo: ProjectRepository, source: SourceDescriptor) -> dict[str, Any]:
    row = repo.db.execute(
        "SELECT ss.metadata_json,s.descriptor_json FROM snapshot_sources s "
        "JOIN source_snapshots ss ON ss.id=s.snapshot_id WHERE s.source_id=? "
        "ORDER BY ss.created_at DESC,ss.rowid DESC LIMIT 1", (source.logical_id,),
    ).fetchone()
    if row is None or row[1] != canonical(asdict(source)):
        raise ValueError("Native source snapshots are missing or stale; extract locally again.")
    metadata: dict[str, Any] = json.loads(row[0])
    if (
        metadata.get("complete_source_set") is not True
        or metadata.get("adapter_id") != source.adapter_id
    ):
        raise ValueError("A complete local native-template snapshot is required.")
    return metadata


def _with_say_defaults(metadata: dict[str, Any]) -> dict[str, Any]:
    """Compare legacy plain snapshots without rewriting history or granting approvals."""
    return {
        "syntax_version": SYNTAX_VERSION, **metadata,
        "records": [
            {"attributes": [], "temporary_attributes": [], "nointeract": False, **record}
            for record in metadata.get("records", ())
        ],
    }


def template_candidate(repo: ProjectRepository, unit_id: str) -> dict[str, Any] | None:
    """Present snapshot text as untrusted provenance, never as a target revision."""
    row = repo.db.execute(
        "SELECT d.descriptor_json,s.source_text,s.context FROM text_units u "
        "JOIN source_descriptors d ON d.id=u.logical_source_id "
        "JOIN source_revisions s ON s.id=u.source_revision "
        "WHERE u.unit_id=? AND u.active=1 AND d.adapter_id='renpy-templates'", (unit_id,),
    ).fetchone()
    if row is None:
        return None
    source = SourceDescriptor(**json.loads(row[0]))
    try:
        metadata = _snapshot_metadata(repo, source)
    except ValueError:
        return None  # Portable history is not a verified local template snapshot.
    for entry in metadata.get("records", ()):
        if entry["unit_id"] == unit_id and entry["source"] == row[1] and entry["candidate"]:
            return {
                "text": entry["candidate"], "template_language": metadata["template_language"],
                "source_file": source.source_file, "block": entry["block"],
                "speaker": entry["speaker"], "slot": entry["slot"], "line": entry["line"],
                "trusted": False, "target_language_verified": False,
                "issues": format_issues(row[1], entry["candidate"], rules=RENPY_FORMAT),
            }
    return None


def _review_context_index(repo: ProjectRepository, source: SourceDescriptor) -> _ContextRows:
    identity = repo.db.execute(
        "SELECT ss.id,s.descriptor_json FROM snapshot_sources s "
        "JOIN source_snapshots ss ON ss.id=s.snapshot_id WHERE s.source_id=? "
        "ORDER BY ss.created_at DESC,ss.rowid DESC LIMIT 1", (source.logical_id,),
    ).fetchone()
    descriptor = canonical(asdict(source))
    if identity is None or identity[1] != descriptor:
        raise ValueError("A current local native snapshot is required for review context.")
    cache = _REVIEW_CONTEXTS.setdefault(repo, {})
    previous = cache.get(source.logical_id)
    if previous is not None and previous[:2] == (identity[0], descriptor):
        return previous[2]
    metadata = _snapshot_metadata(repo, source)
    # Original byte payloads are not a presentation cache. Drop them before
    # indexing a large snapshot and retain hashes, locations and say structure only.
    metadata.pop("original_members", None)
    metadata.pop("raw_base64", None)
    contexts: _ContextRows = {}
    for entry in metadata.get("records", ()):
        shape = SayShape(entry["speaker"], tuple(entry.get("attributes", ())),
                         tuple(entry.get("temporary_attributes", ())))
        contexts[entry["unit_id"]] = (sha256(entry["source"].encode()).hexdigest(), {
            "file": source.source_file, "line": entry["line"], "block": entry["block"],
            "speaker": shape.prefix().strip() or "—",
        })
    for location in metadata.get("locations", ()):
        entry = metadata["records"][location["record"]]
        context = contexts[entry["unit_id"]][1]
        context.update(
            file=location.get("container", source.source_file) + " / " + location["member"],
            line=location["line"],
        )
    cache[source.logical_id] = (identity[0], descriptor, contexts)
    return contexts


def add_review_context(repo: ProjectRepository, rows: list[dict[str, Any]]) -> None:
    """Cache display context by immutable local snapshot; never cache export authority."""
    native = [row for row in rows if row["format_rules"] == RENPY_FORMAT]
    needed = {row["logical_source_id"] for row in native}
    for row in native:
        row.pop("native_context", None)
    for source in _sources(repo):
        if source.logical_id not in needed:
            continue
        try:
            contexts = _review_context_index(repo, source)
        except ValueError:
            continue
        for row in native:
            found = contexts.get(row["unit_id"])
            if row["logical_source_id"] == source.logical_id and found is not None and (
                found[0] == row["source_hash"]
            ):
                row["native_context"] = dict(found[1])


def _emit(
    document: TemplateDocument, snapshot: SourceSnapshot, language: str,
    selection: dict[str, dict[str, Any]], global_strings: dict[str, str], emitted: set[str],
) -> tuple[list[bytes], dict[str, int]]:
    blocks: dict[str, list[tuple[TemplateRecord, str]]] = {}
    strings = []
    fallback = 0
    for record, unit in zip(document.records, snapshot.units, strict=True):
        if record.kind == "dialogue":
            blocks.setdefault(record.block, []).append((record, unit.unit_id))
        elif record.source in global_strings and record.source not in emitted:
            strings.append((record.source, global_strings[record.source]))
            emitted.add(record.source)
    heading = ["# Generated by UnityTranslator; reviewed native translations only.", ""]
    lines = heading.copy()
    expected: list[tuple[str, str, SayShape, str, str]] = []
    payloads: list[bytes] = []
    size = sum(len(line.encode()) + 1 for line in lines)
    string_header = False
    dialogue_statements = 0

    def flush() -> None:
        nonlocal lines, expected, size, string_header
        if expected:
            raw = ("\n".join(lines) + "\n").encode("utf-8")
            output = parse_template(raw, language)
            actual = [(r.kind, r.block, r.say_shape(), r.source, r.candidate)
                      for r in output.records]
            if actual != expected or any(format_issues(old, new, rules=RENPY_FORMAT)
                                         for _, _, _, old, new in actual):
                raise ValueError("Generated native file failed its fixed-grammar round trip.")
            payloads.append(raw)
        lines, expected = heading.copy(), []
        size = sum(len(line.encode()) + 1 for line in lines)
        string_header = False

    def append(
        group_lines: list[str], group: list[tuple[str, str, SayShape, str, str]], *,
        string: bool = False,
    ) -> None:
        nonlocal size, string_header
        group_size = sum(len(line.encode()) + 1 for line in group_lines)
        header = f"translate {language} strings:"
        header_size = len(header.encode()) + 1 if string and not string_header else 0
        if expected and (
            size + group_size + header_size > SHARD_BYTES
            or len(expected) + len(group) > SHARD_RECORDS
        ):
            flush()
        header_size = len(header.encode()) + 1 if string and not string_header else 0
        if size + group_size + header_size > MAX_FILE_BYTES or len(group) > MAX_RECORDS:
            raise ValueError("A complete native translation block exceeds the output file bounds.")
        if string and not string_header:
            lines.append(header)
            size += header_size
            string_header = True
        lines.extend(group_lines)
        expected.extend(group)
        size += group_size

    for block, entries in blocks.items():
        if not any(unit_id in selection for _, unit_id in entries):
            continue  # Leave the engine's original block in control.
        group_lines = [f"translate {language} {block}:"]
        group = []
        for record, unit_id in entries:
            row = selection.get(unit_id)
            target = row["translation"] if row else record.source
            fallback += row is None
            shape = record.say_shape()
            group_lines.extend((
                "    # " + shape.statement(say_quoted_literal(record.source)),
                "    " + shape.statement(say_quoted_literal(target)), "",
            ))
            group.append(("dialogue", block, shape, record.source, target))
            dialogue_statements += 1
        append(group_lines, group)
    if strings:
        for old, new in strings:
            append(["    old " + quoted_literal(old), "    new " + quoted_literal(new), ""],
                   [("string", "strings", SayShape(), old, new)], string=True)
    flush()
    counts = {
        "fallback_dialogue": fallback, "string_mappings": len(strings),
        "dialogue_statements": dialogue_statements,
        "omitted_dialogue_statements": sum(r.kind == "dialogue" for r in document.records)
        - dialogue_statements,
        "omitted_string_occurrences": sum(
            r.kind == "string" and r.source not in global_strings for r in document.records
        ),
        "mapped_string_occurrences": sum(
            r.kind == "string" and r.source in global_strings for r in document.records
        ),
    }
    return payloads, counts


def export_native(
    repo: ProjectRepository, language: str, records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Freeze current approvals and an explicit project-language/native-language mapping."""
    language_identifier(language)
    sources = _sources(repo)
    if not sources or len({source.profile_id for source in sources}) != 1:
        raise ValueError("Extract one complete native Ren'Py template language set first.")
    first = sources[0]
    original = first.adapter_id == "renpy-scripts"
    if original:
        from unitytranslator.renpy_scripts import SOURCE_NAMESPACE

        input_language = SOURCE_NAMESPACE
    else:
        input_language, _, _ = template_files(repo.paths.game, first.source_file)
    if language.casefold() == input_language.casefold():
        raise ValueError("Export requires a different language namespace from the input templates.")
    # No database transaction is held while the isolated reader runs.
    report = BUILTIN_READERS.select((first.adapter_id,)).probe(
        ReaderContext(repo.paths.game, repo.paths.project, repo.source_language), first.source_file,
    ).report
    fresh = result_from_report(report, replace_source_set=True)
    verified = {s.source.logical_id: s for s in fresh.snapshots}
    if {source.logical_id: source for source in sources} != {
        key: snapshot.source for key, snapshot in verified.items()
    }:
        raise ValueError("Native source set changed; extract and review again before exporting.")
    with repo.transaction():
        if _sources(repo) != sources:
            raise ValueError("Active native source descriptors changed during inspection.")
        rows = _rows(repo)
        current = {row["unit_id"]: row for row in rows}
        units = {u.unit_id: u for s in fresh.snapshots for u in s.units}
        owners = {u.unit_id: s.source.logical_id for s in fresh.snapshots for u in s.units}
        if current.keys() != units.keys():
            raise ValueError("Current records differ from the complete verified native source set.")
        if any(row["has_draft"] for row in rows):
            raise ValueError("Finish or discard native source editor drafts before exporting.")
        for unit_id, unit in units.items():
            row = current[unit_id]
            if row["logical_source_id"] != owners[unit_id] or any(
                row[key] != value for key, value in asdict(unit).items()
            ):
                raise ValueError("Native source records or context changed; extract again.")
            meaning = {key: value for key, value in asdict(unit).items()
                       if key not in ("source_file", "source_object", "original_key")}
            if sha256(canonical(meaning).encode()).hexdigest() != row["source_revision"]:
                raise ValueError("Native source revision does not match its verified record.")
        if records is None:
            records = [{key: row[key] for key in _REVISION_KEYS}
                       for row in rows if row["status"] == "approved"]
        if not records or any(
            set(record) != set(_REVISION_KEYS)
            or any(not isinstance(record[key], str) or not record[key]
                   for key in _REVISION_KEYS[:-1])
            or type(record["version"]) is not int or record["version"] < 0
            for record in records
        ) or len({record["unit_id"] for record in records}) != len(records):
            raise ValueError("Select current approved native translations without duplicates.")
        selection = {}
        for frozen in records:
            selected = current.get(frozen["unit_id"])
            if (
                selected is None or any(selected[key] != frozen[key] for key in _REVISION_KEYS)
                or selected["status"] != "approved"
                or selected["approved_source"] != selected["source_revision"]
                or selected["approved_translation"] != selected["translation_revision"]
                or not selected["translation"] or format_issues(
                    selected["source_text"], selected["translation"], rules=RENPY_FORMAT
                )
            ):
                raise ValueError("Native export approval, revision or protected format changed.")
            selection[selected["unit_id"]] = selected
        documents = []
        global_strings: dict[str, str] = {}
        approved_strings: dict[str, str] = {}
        occurrences: dict[str, list[str]] = {}
        for source in sources:
            snapshot = verified[source.logical_id]
            metadata = _with_say_defaults(_snapshot_metadata(repo, source))
            fingerprints = report["fingerprints"]
            legacy_fingerprints = {
                key: value for key, value in fingerprints.items()
                if key not in report.get("dialect_evidence", {}).get("fingerprints", {})
            }
            if metadata.get("fingerprints") not in (fingerprints, legacy_fingerprints) or any(
                metadata.get(key) != value for key, value in snapshot.metadata.items()
            ):
                raise ValueError("Native source snapshot content is stale; extract locally again.")
            raw = base64.b64decode(snapshot.metadata["raw_base64"], validate=True)
            document = (
                TemplateDocument(raw, input_language, tuple(
                    TemplateRecord(**{
                        key: entry[key]
                        for key in TemplateRecord.__dataclass_fields__ if key in entry
                    })
                    for entry in snapshot.metadata["records"]
                )) if original else parse_template(raw, input_language)
            )
            documents.append((source, snapshot, document))
            for record, unit in zip(document.records, snapshot.units, strict=True):
                if record.kind != "string":
                    continue
                occurrences.setdefault(record.source, []).append(unit.unit_id)
                current_row = current[unit.unit_id]
                if current_row["status"] == "approved":
                    previous = approved_strings.get(record.source)
                    if previous is not None and previous != current_row["translation"]:
                        raise ValueError("Conflicting approved global Ren'Py string mappings.")
                    approved_strings[record.source] = current_row["translation"]
                if unit.unit_id in selection:
                    target = selection[unit.unit_id]["translation"]
                    if record.source in global_strings and global_strings[record.source] != target:
                        raise ValueError("Conflicting approved global Ren'Py string mappings.")
                    global_strings[record.source] = target
        staged: list[tuple[str, bytes]] = []
        emitted: set[str] = set()
        coverage = []
        total = 0
        for source, snapshot, document in documents:
            payloads, counts = _emit(
                document, snapshot, language, selection, global_strings, emitted
            )
            item = {"source": asdict(source), **counts,
                    "approved_records": sum(u.unit_id in selection for u in snapshot.units),
                    "total_records": len(snapshot.units)}
            outputs = []
            for part, payload in enumerate(payloads, 1):
                total += len(payload)
                if total > MAX_TOTAL_BYTES or len(staged) >= MAX_OUTPUT_FILES:
                    raise ValueError("Native output total-size limit exceeded.")
                suffix = "" if len(payloads) == 1 else f"_{part:04d}"
                name = (
                    f"game/tl/{language}/ut_{sha256(source.logical_id.encode()).hexdigest()}"
                    + suffix + ".rpy"
                )
                outputs.append({"file": name, "sha256": sha256(payload).hexdigest()})
                staged.append((name, payload))
            if len(outputs) == 1:
                item.update(outputs[0])
            elif outputs:
                item["files"] = outputs
            coverage.append(item)

        def verify_sources() -> None:
            if original:
                from unitytranslator.engines import renpy_inputs

                if renpy_inputs(repo.paths.game)["source_candidates"] != report["source_inventory"]:
                    raise ValueError("Original Ren'Py source selection changed during export.")
                for relative, digest in report["fingerprints"].items():
                    if hash_file(checked_path(repo.paths.game / relative)) != digest:
                        raise ValueError("Original Ren'Py source changed during export.")
                return
            _, files, _ = template_files(repo.paths.game, first.source_file)
            discovered = {p.relative_to(repo.paths.game).as_posix() for p in files}
            if discovered != set(report["fingerprints"]):
                raise ValueError("Native template file selection changed during export.")
            for path in files:
                with path.open("rb") as stream:
                    raw = stream.read(MAX_FILE_BYTES + 1)
                if sha256(raw).hexdigest() != report["fingerprints"][path.relative_to(
                    repo.paths.game
                ).as_posix()]:
                    raise ValueError("Native template bytes changed during export.")

        verify_sources()
        identity = uuid4().hex
        pending_name = "exports/.pending-renpy-" + identity
        pending = repo.paths.output(pending_name)
        pending.mkdir(parents=True, exist_ok=False)
        for name, payload in staged:
            target = repo.paths.output(pending_name + "/" + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with repo.paths.output(pending_name + "/" + name).open("xb") as stream:
                stream.write(payload)
        manifest = {
            "format_version": 2 if any("files" in item for item in coverage) else 1,
            "kind": "staged-renpy-native-files",
            "project_id": repo.project_id, "adapter_id": first.adapter_id,
            "parser_version": first.schema_version, "format_rules": RENPY_FORMAT,
            "syntax_version": SYNTAX_VERSION,
            "source_language": repo.source_language, "target_language": repo.target_language,
            "language_mapping": {repo.target_language: language},
            "input_template_language": input_language,
            "selection": records, "fingerprints": report["fingerprints"], "coverage": coverage,
            "global_string_occurrences": [
                {"source": key, "unit_ids": value, "exported": key in global_strings}
                for key, value in sorted(occurrences.items())
            ],
            "outside_scope": report["outside_scope"],
            "excluded_files": report["excluded_files"],
            "installation": "unsupported", "language_activation": "unverified",
            "source_files_modified": False,
        }
        if original:
            manifest["exclusion_counts"] = report["exclusion_counts"]
            manifest["input_kind"] = "original_source"
            manifest["dialect_evidence"] = report["dialect_evidence"]
            manifest["version_evidence"] = report["version_evidence"]
            manifest["source_resolution"] = report["source_resolution"]
        repo.paths.write_json(pending_name + "/manifest.json", manifest)
        for name, payload in staged:
            with repo.paths.output(pending_name + "/" + name).open("rb") as reader:
                if reader.read(len(payload) + 1) != payload:
                    raise ValueError("Staged native-file integrity check failed.")
        expected_manifest = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
        with repo.paths.output(pending_name + "/manifest.json").open("rb") as reader:
            if reader.read(len(expected_manifest) + 1) != expected_manifest:
                raise ValueError("Staged native manifest changed before publication.")
        verify_sources()
        if _rows(repo) != rows or _sources(repo) != sources:
            raise ValueError("Native source, draft or approval changed while staging.")
        destination = repo.paths.output("exports/renpy-" + identity)
        if destination.exists():
            raise ValueError("Native export destination exists; no files were replaced.")
        repo.paths.output(pending_name).rename(destination)
    return {
        "folder": str(destination), "manifest": str(destination / "manifest.json"),
        "sources": len(sources), "files": len(staged), "approved_translations": len(selection),
        "language_mapping": {repo.target_language: language}, "installation": "unsupported",
    }
