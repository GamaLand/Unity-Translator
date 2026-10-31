"""Bounded, source-only dialogue references. Ordering is evidence, never a key heuristic."""

import base64
import json
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Callable
from hashlib import sha256
from typing import Any
from weakref import WeakKeyDictionary

from unitytranslator.domain import OperationCancelled
from unitytranslator.renpy_python import python_source_view
from unitytranslator.renpy_scripts import ScriptDocument, lex, parse_scripts
from unitytranslator.renpy_templates import TemplateDocument, parse_template
from unitytranslator.repository import ProjectRepository, canonical
from unitytranslator.source_contracts import SourceDescriptor, SourceSnapshot

CONTEXT_VERSION = "source-window-v1"
WINDOW_SIZE = 2
MAX_REFERENCE_BYTES = 8192


def _check(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise OperationCancelled("Local preparation was cancelled.")


def script_runs(
    document: ScriptDocument, *, cancelled: Callable[[], bool] = lambda: False,
) -> list[list[int]]:
    """Group only consecutive accepted says at one indentation in one source member.

    Every other logical statement is a barrier, including excluded says, Python,
    presentation commands and flow control. Indent changes close branch/loop runs.
    Blank lines/comments are harmless; _ren.py conversion markers are barriers too.
    """
    locations: dict[str, dict[int, int]] = defaultdict(dict)
    for location in document.locations:
        if location["kind"] == "dialogue":
            locations[location["member"]][location["line"]] = location["record"]
    runs: list[list[int]] = []
    for member in document.members:
        _check(cancelled)
        original = base64.b64decode(member["raw_base64"], validate=True).decode("utf-8-sig")
        converted = member["name"].endswith("_ren.py")
        text = python_source_view(original).text if converted else original
        physical = text.split("\n")
        markers = [
            i for i, line in enumerate(original.splitlines(), 1)
            if converted and (line.startswith('"""renpy') or line == '"""')
        ]
        statements, _ = lex(text)
        run: list[int] = []
        previous_line, previous_indent = 0, -1
        for statement_index, line in enumerate(statements):
            if statement_index % 256 == 0:
                _check(cancelled)
            index = locations[member["name"]].get(line)
            indent = len(physical[line - 1]) - len(physical[line - 1].lstrip(" "))
            crossed_marker = bisect_right(markers, line) > bisect_right(markers, previous_line)
            if index is None or indent != previous_indent or crossed_marker:
                if run:
                    runs.append(run)
                run = []
            if index is not None:
                run.append(index)
            previous_indent, previous_line = indent, line
        if run:
            runs.append(run)
    return runs


def template_runs(document: TemplateDocument) -> list[list[int]]:
    """Only slots inside the same native block prove template dialogue adjacency."""
    runs: list[list[int]] = []
    for i, record in enumerate(document.records):
        if record.kind != "dialogue":
            continue
        if runs and document.records[runs[-1][-1]].block == record.block:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def windows(
    snapshot: SourceSnapshot, runs: list[list[int]], *,
    cancelled: Callable[[], bool] = lambda: False,
) -> dict[str, dict[str, Any]]:
    """Keep whole utterances, with nearest neighbours first when applying the byte cap."""
    records = snapshot.metadata["records"]
    result: dict[str, dict[str, Any]] = {}
    for run_number, run in enumerate(runs):
        _check(cancelled)
        for position, index in enumerate(run):
            if position % 256 == 0:
                _check(cancelled)
            target = records[index]
            references = []
            size = 0
            for distance in range(1, WINDOW_SIZE + 1):
                for offset in (-distance, distance):
                    neighbour = position + offset
                    if not 0 <= neighbour < len(run):
                        continue
                    entry = records[run[neighbour]]
                    item = {
                        "offset": offset, "unit_id": entry["unit_id"],
                        "speaker": entry["speaker"] or "narrator", "source": entry["source"],
                    }
                    length = len(canonical(item).encode("utf-8"))
                    if size + length > MAX_REFERENCE_BYTES:
                        # Do not skip a near utterance and retain a more distant one.
                        break
                    size += length
                    references.append(item)
                else:
                    continue
                break
            result[target["unit_id"]] = {
                "version": CONTEXT_VERSION, "speaker": target["speaker"] or "narrator",
                "references": sorted(references, key=lambda item: item["offset"]),
                "order": [run_number, position],
                "source_hash": snapshot.units[index].source_hash,
            }
    return result


# Cache only derived, immutable snapshot data. No original bytes or translations.
_INDEX: WeakKeyDictionary[
    ProjectRepository, dict[str, tuple[str, str, dict[str, dict[str, Any]]]],
] = WeakKeyDictionary()
_PROOFS: WeakKeyDictionary[ProjectRepository, dict[str, str]] = WeakKeyDictionary()
_ORDERS: WeakKeyDictionary[ProjectRepository, str] = WeakKeyDictionary()


def evidence_digest(metadata: dict[str, Any]) -> str:
    keys = (
        "complete_source_set", "adapter_id", "original_members", "raw_base64", "records",
        "template_language", "dialect_evidence", "parser_version", "syntax_version",
    )
    return sha256(canonical({key: metadata.get(key) for key in keys}).encode()).hexdigest()


def snapshot_windows(
    source: SourceDescriptor, metadata: dict[str, Any],
    *, cancelled: Callable[[], bool] = lambda: False,
) -> dict[str, dict[str, Any]]:
    """Rebuild accepted records from inert local bytes before trusting any adjacency."""
    _check(cancelled)
    if metadata.get("complete_source_set") is not True or metadata.get("adapter_id") != (
        source.adapter_id
    ):
        return {}
    if source.adapter_id == "renpy-scripts":
        members = metadata["original_members"]
        decoded = [(m["name"], base64.b64decode(m["raw_base64"], validate=True)) for m in members]
        if any(sha256(raw).hexdigest() != member["sha256"]
               for (_, raw), member in zip(decoded, members, strict=True)):
            return {}
        dialect = metadata.get("dialect_evidence", {})
        document = parse_scripts(
            decoded,
            source.fingerprint,
            python_dialect=dialect.get("python_source"),
            reserved_attributes=frozenset(dialect.get("reserved_attributes", ())),
            cancelled=cancelled,
        )
        rebuilt = document.snapshot(source.source_file, source.source_language)
        runs = script_runs(document, cancelled=cancelled)
    elif source.adapter_id == "renpy-templates":
        raw = base64.b64decode(metadata["raw_base64"], validate=True)
        if sha256(raw).hexdigest() != source.fingerprint:
            return {}
        template = parse_template(raw, metadata["template_language"])
        rebuilt = template.snapshot(source.source_file, source.source_language)
        runs = template_runs(template)
    else:
        return {}  # I2/table position is not narrative evidence.
    def mapping(records: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
        return [(
            r["unit_id"], r["kind"], r["source"], r["block"], r["slot"], r["speaker"],
            tuple(r.get("attributes", ())), tuple(r.get("temporary_attributes", ())),
            r.get("nointeract", False), r["line"], r["literal_start"], r["literal_end"],
        ) for r in records]

    expected = mapping(metadata["records"])
    actual = mapping(rebuilt.metadata["records"])
    if actual != expected:
        return {}  # A historical parser mapping must not silently gain guessed neighbours.
    return windows(rebuilt, runs, cancelled=cancelled)


class DialogueContextStore:
    """Bind a job to immutable local snapshots; portable imports grant no evidence."""

    def __init__(self, repository: ProjectRepository):
        self.repo = repository

    def bindings(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.repo.db.execute(
            "SELECT d.id AS source_id,s.snapshot_id,s.descriptor_json "
            "FROM source_descriptors d JOIN snapshot_sources s ON s.source_id=d.id "
            "JOIN source_snapshots ss ON ss.id=s.snapshot_id "
            "WHERE d.active=1 AND d.adapter_id IN ('renpy-scripts','renpy-templates') "
            "AND s.descriptor_json=d.descriptor_json AND ss.id=(SELECT ss2.id "
            "FROM source_snapshots ss2 JOIN snapshot_sources s2 ON ss2.id=s2.snapshot_id "
            "WHERE s2.source_id=d.id ORDER BY ss2.created_at DESC,ss2.rowid DESC LIMIT 1) "
            "ORDER BY d.id"
        )]

    def fingerprint(self) -> str:
        return sha256(canonical([
            [row["source_id"], self._digest(row["snapshot_id"]), row["descriptor_json"]]
            for row in self.bindings()
        ]).encode()).hexdigest()

    def _digest(self, snapshot_id: str) -> str:
        self.repo.check_cancelled()
        cache = _PROOFS.setdefault(self.repo, {})
        if snapshot_id not in cache:
            raw = self.repo.db.execute(
                "SELECT metadata_json FROM source_snapshots WHERE id=?", (snapshot_id,),
            ).fetchone()[0]
            cache[snapshot_id] = evidence_digest(json.loads(raw))
        self.repo.check_cancelled()
        return cache[snapshot_id]

    def bind(self, job_id: str) -> None:
        for row in self.bindings():
            self.repo.db.execute(
                "INSERT INTO job_context_sources VALUES(?,?,?,?,?)",
                (job_id, row["source_id"], row["snapshot_id"], row["descriptor_json"],
                 self._digest(row["snapshot_id"])),
            )

    def _index(self, binding: dict[str, Any]) -> dict[str, dict[str, Any]]:
        snapshot_id = binding["snapshot_id"]
        cache = _INDEX.setdefault(self.repo, {})
        source = SourceDescriptor(**json.loads(binding["descriptor_json"]))
        proof = self._digest(snapshot_id)
        if "metadata_digest" in binding and proof != binding["metadata_digest"]:
            raise ValueError("Frozen dialogue context snapshot changed.")
        previous = cache.get(source.logical_id)
        if previous is None or previous[:2] != (proof, binding["descriptor_json"]):
            raw = self.repo.db.execute(
                "SELECT metadata_json FROM source_snapshots WHERE id=?", (snapshot_id,),
            ).fetchone()[0]
            metadata = json.loads(raw)
            try:
                index = snapshot_windows(
                    source, metadata, cancelled=self.repo.operation_cancelled,
                )
            except OperationCancelled:
                raise
            except (ValueError, KeyError, TypeError, IndexError):
                self.repo.check_cancelled()
                index = {}  # Missing or incompatible evidence means isolated translation.
            self.repo.check_cancelled()
            cache[source.logical_id] = (proof, binding["descriptor_json"], index)
        return cache[source.logical_id][2]

    def window(self, job_id: str, unit_id: str, source_text: str) -> dict[str, Any]:
        row = self.repo.db.execute(
            "SELECT b.* FROM job_context_sources b "
            "JOIN text_units u ON u.logical_source_id=b.source_id "
            "WHERE b.job_id=? AND u.unit_id=?", (job_id, unit_id),
        ).fetchone()
        empty: dict[str, Any] = {
            "version": CONTEXT_VERSION, "references": [], "reason": "order_unavailable",
        }
        if row is None:
            return empty
        binding = dict(row)
        found = self._index(binding).get(unit_id)
        if found is None or found["source_hash"] != sha256(source_text.encode()).hexdigest():
            return empty
        return {
            "version": CONTEXT_VERSION, "speaker": found["speaker"],
            "references": found["references"], "snapshot_id": binding["snapshot_id"],
            "reason": "verified_segment" if found["references"] else "segment_boundary",
        }

    def order(self, units: list[str]) -> list[str]:
        self.repo.check_cancelled()
        positions = {}
        for source_number, row in enumerate(self.bindings()):
            for unit_id, value in self._index(row).items():
                positions[unit_id] = (source_number, *value["order"])
        ordered = sorted(
            units, key=lambda unit: (*positions.get(unit, (len(positions), 0, 0)), unit),
        )
        self.repo.check_cancelled()
        return ordered

    def prepare_review_order(self) -> None:
        bindings = self.bindings()
        identity = canonical(bindings)
        if _ORDERS.get(self.repo) == identity:
            return
        units = [unit for binding in bindings for unit in self._index(binding)]
        ordered = self.order(units)
        self.repo.db.execute(
            "CREATE TEMP TABLE IF NOT EXISTS dialogue_order("
            "unit_id TEXT PRIMARY KEY,position INTEGER)"
        )
        self.repo.db.execute("DELETE FROM temp.dialogue_order")
        self.repo.db.executemany(
            "INSERT INTO temp.dialogue_order VALUES(?,?)",
            [(unit, position) for position, unit in enumerate(ordered)],
        )
        _ORDERS[self.repo] = identity

    def current(self, job_id: str) -> bool:
        job = self.repo.db.execute("SELECT profile_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None or json.loads(job[0]).get("dialogue_context", "none") == "none":
            return True
        old = self.repo.db.execute(
            "SELECT source_id,metadata_digest,descriptor_json FROM job_context_sources "
            "WHERE job_id=? ORDER BY source_id", (job_id,),
        ).fetchall()
        current = [
            (r["source_id"], self._digest(r["snapshot_id"]), r["descriptor_json"])
            for r in self.bindings()
        ]
        return [tuple(row) for row in old] == current

    def preview(self, rows: list[dict[str, Any]]) -> None:
        needed = {r["logical_source_id"] for r in rows}
        for row in rows:
            row["dialogue_context"] = {"references": [], "reason": "order_unavailable"}
        for binding in self.bindings():
            if binding["source_id"] not in needed:
                continue
            index = self._index(binding)
            for row in rows:
                found = index.get(row["unit_id"])
                if found is not None and found["source_hash"] == row["source_hash"]:
                    row["dialogue_context"] = {
                        "references": found["references"], "reason": "verified_segment",
                    }
