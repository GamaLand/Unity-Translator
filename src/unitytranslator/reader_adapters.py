"""Explicit bundled adapters; profile data never selects imports or executable code."""

import base64
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from hashlib import sha256
from typing import Any

from unitytranslator.domain import TextUnitDraft
from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file
from unitytranslator.source_contracts import (
    ReaderContext,
    ReaderProbe,
    ReaderResult,
    SourceDescriptor,
    SourceReader,
    SourceSnapshot,
    validate_relative_source,
)


def result_from_report(report: dict[str, Any], *, replace_source_set: bool = False) -> ReaderResult:
    """Validate trusted reader output as data before any repository activation."""
    if report.get("extraction") != "supported" or report.get("errors"):
        raise ValueError("Source reading did not produce a complete supported result.")
    units = tuple(TextUnitDraft(**unit) for unit in report["units"])
    sources = tuple(SourceDescriptor(**value) for value in report.get("source_descriptors", ()))
    if not sources:
        # Legacy I2 probe callers and tests may provide the original report schema.
        if report.get("adapter_id", "i2") != "i2":
            raise ValueError("Source descriptors are required for this adapter.")
        sources = tuple(
            SourceDescriptor.legacy(path, next(u.source_language for u in units))
            for path in sorted({unit.source_file for unit in units})
        )
    assigned: set[str] = set()
    snapshots = []
    for source in sources:
        matching = tuple(
            unit
            for unit in units
            if unit.source_file == source.source_file
            and (source.source_object == -1 or source.source_object == unit.source_object)
        )
        if any(unit.unit_id in assigned for unit in matching):
            raise ValueError("Ambiguous record-to-source mapping.")
        assigned.update(unit.unit_id for unit in matching)
        payloads = [p for p in report.get("payloads", ()) if p["logical_id"] == source.logical_id]
        if len(payloads) > 1:
            raise ValueError("Duplicate source payload snapshots.")
        snapshots.append(SourceSnapshot(source, matching, payloads[0] if payloads else {}))
    if len(assigned) != len(units):
        raise ValueError("Some reader records have no unique logical source.")
    return ReaderResult(
        tuple(snapshots),
        True,
        {k: v for k, v in report.items() if k not in ("units", "payloads")},
        replace_source_set,
    )


class I2Reader:
    id = "i2"
    version = "1"

    def probe(self, context: ReaderContext, relative: str) -> ReaderProbe:
        from unitytranslator.discovery import _probe_i2_source

        report = _probe_i2_source(
            ProjectPaths(context.game, context.project),
            relative,
            timeout=context.timeout,
            source_language=context.source_language,
        )
        source = replace(
            SourceDescriptor.legacy(relative, context.source_language),
            fingerprint=report["sha256_before"],
        )
        report.update(
            {
                "adapter_id": self.id,
                "adapter_version": self.version,
                "source_descriptors": [asdict(source)],
            }
        )
        return ReaderProbe((source,), tuple(report.get("diagnostics", ())), report)

    def extract(
        self, context: ReaderContext, relative: str, cancellation: Callable[[], bool]
    ) -> ReaderResult:
        if cancellation():
            raise ValueError("Source extraction was cancelled.")
        probe = self.probe(context, relative)
        if cancellation():
            raise ValueError("Source extraction was cancelled.")
        return result_from_report(probe.report)


class ReaderRegistry:
    def __init__(self, readers: Sequence[SourceReader]):
        identifiers = [reader.id for reader in readers]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Duplicate built-in reader identifiers.")
        self._readers = tuple(readers)

    def select(self, identifiers: Sequence[str]) -> SourceReader:
        if len(identifiers) != 1:
            raise ValueError("Ambiguous reader selection; select exactly one built-in adapter.")
        for reader in self._readers:
            if reader.id == identifiers[0]:
                return reader
        raise ValueError("No matching built-in source reader.")


class KryptaTextAssetReader:
    id = "krypta-textassets"
    version = "1"

    def _inspect(self, context: ReaderContext, cancelled: Callable[[], bool]) -> ReaderProbe:
        from unitytranslator.capabilities import discovery_capabilities
        from unitytranslator.krypta_profile import declared_sources, evidence_files, load_profile
        from unitytranslator.textasset_layouts import parse_payload
        from unitytranslator.worker_process import run_json_worker

        worker = (
            [sys.executable, "--textasset-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "unitytranslator.workers.textasset_probe"]
        )
        report = run_json_worker(
            [*worker, str(context.game), context.source_language],
            timeout=context.timeout,
            cancelled=cancelled,
        )
        if report.get("complete_source_set") is not True:
            raise ValueError("Incomplete TextAsset discovery cannot replace active sources.")
        profile = load_profile()
        expected_files = {e["path"] for e in evidence_files(profile)} | {
            source["container"] for source in profile["sources"]
        }
        if set(report.get("fingerprints", ())) != expected_files:
            raise ValueError("Incomplete TextAsset evidence fingerprints.")
        for relative, digest in report["fingerprints"].items():
            validate_relative_source(relative)
            path = checked_path(context.game / relative)
            if not path.is_relative_to(context.game) or hash_file(path) != digest:
                raise ValueError("TextAsset source changed before the result was accepted.")
        result = result_from_report(report, replace_source_set=True)
        expected_sources = {
            (source["container"], source["object"], source["name"], source["schema"])
            for source in declared_sources(profile)
            if not source.get("excluded_reason")
        }
        if {
            (
                s.source.source_file,
                s.source.source_object,
                s.source.asset_name,
                s.source.schema_version,
            )
            for s in result.snapshots
        } != expected_sources:
            raise ValueError("Incomplete or ambiguous TextAsset source selection.")
        for snapshot in result.snapshots:
            if (
                snapshot.source.adapter_id != self.id
                or snapshot.source.profile_id != profile["id"]
                or snapshot.source.source_language != context.source_language
                or snapshot.source.format_rules != "literal-lines-v1"
            ):
                raise ValueError("TextAsset source namespace, locale or format mapping changed.")
            raw = base64.b64decode(snapshot.metadata["raw_base64"], validate=True)
            document = parse_payload(raw, snapshot.source.schema_version)
            if document.drafts(snapshot.source) != snapshot.units:
                raise ValueError("TextAsset records differ from their payload snapshots.")
        report["format_version"] = 1
        report["counts"] = {
            "records": len(report["units"]),
            "unique_texts": len({unit["source_text"] for unit in report["units"]}),
            "characters": sum(len(unit["source_text"]) for unit in report["units"]),
            "errors": 0,
            "sources": len(result.snapshots),
        }
        report["capabilities"] = discovery_capabilities(report, inspected=True).to_dict()
        return ReaderProbe(tuple(s.source for s in result.snapshots), (), report)

    def probe(self, context: ReaderContext, relative: str) -> ReaderProbe:
        return self._inspect(context, context.cancelled)

    def extract(
        self, context: ReaderContext, relative: str, cancellation: Callable[[], bool]
    ) -> ReaderResult:
        return result_from_report(
            self._inspect(context, cancellation).report, replace_source_set=True
        )


class RenpyTemplateReader:
    id = "renpy-templates"
    version = "1"

    def probe(self, context: ReaderContext, relative: str) -> ReaderProbe:
        from unitytranslator.capabilities import discovery_capabilities
        from unitytranslator.renpy_templates import MAX_FILE_BYTES, parse_template
        from unitytranslator.worker_process import run_json_worker
        from unitytranslator.workers.renpy_probe import template_files

        worker = (
            [sys.executable, "--renpy-worker"] if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "unitytranslator.workers.renpy_probe"]
        )
        report = run_json_worker(
            [*worker, str(context.game), relative, context.source_language],
            timeout=context.timeout, cancelled=context.cancelled,
        )
        if report.get("complete_source_set") is not True or report.get("adapter_id") != self.id:
            raise ValueError("Incomplete or incorrect native Ren'Py reader result.")
        language, files, _ = template_files(context.game, relative)
        expected = {path.relative_to(context.game).as_posix() for path in files}
        if set(report.get("fingerprints", ())) != expected:
            raise ValueError("Ren'Py source selection changed before acceptance.")
        result = result_from_report(report, replace_source_set=True)
        if len(result.snapshots) != len(files) or {
            snapshot.source.source_file for snapshot in result.snapshots
        } != expected:
            raise ValueError("Incomplete or duplicate Ren'Py source descriptors.")
        for snapshot in result.snapshots:
            if context.cancelled():
                raise ValueError("Source extraction was cancelled.")
            path = checked_path(context.game / snapshot.source.source_file)
            with path.open("rb") as stream:
                raw = stream.read(MAX_FILE_BYTES + 1)
            if sha256(raw).hexdigest() != report["fingerprints"][snapshot.source.source_file]:
                raise ValueError("Ren'Py source changed before acceptance.")
            verified = parse_template(raw, language).snapshot(
                snapshot.source.source_file, context.source_language
            )
            if verified != snapshot:
                raise ValueError("Ren'Py records differ from their verified source snapshot.")
        report["counts"] = {
            "records": len(report["units"]), "sources": len(files), "errors": 0,
            "unique_texts": len({u["source_text"] for u in report["units"]}),
            "characters": sum(len(u["source_text"]) for u in report["units"]),
        }
        report["capabilities"] = discovery_capabilities(report, inspected=True).to_dict()
        return ReaderProbe(tuple(s.source for s in result.snapshots), (), report)

    def extract(
        self, context: ReaderContext, relative: str, cancellation: Callable[[], bool]
    ) -> ReaderResult:
        return result_from_report(
            self.probe(replace(context, cancelled=cancellation), relative).report,
            replace_source_set=True,
        )


class RenpyScriptReader:
    id = "renpy-scripts"
    version = "1"

    def probe(self, context: ReaderContext, relative: str) -> ReaderProbe:
        from unitytranslator.capabilities import discovery_capabilities
        from unitytranslator.report_stream import MAX_REPORT_BYTES, report_digest
        from unitytranslator.worker_process import run_json_worker
        from unitytranslator.workers.renpy_script_probe import probe

        anchor = _renpy_source_anchor(context)
        worker = (
            [sys.executable, "--renpy-script-worker"] if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "unitytranslator.workers.renpy_script_probe"]
        )
        received = run_json_worker(
            [*worker, str(context.game), relative, context.source_language,
             *(["--anchor", anchor] if anchor else []), "--stream-report"],
            timeout=context.timeout, cancelled=context.cancelled,
            max_output=MAX_REPORT_BYTES, stream_report=True,
        )
        if context.cancelled():
            raise ValueError("Source extraction was cancelled.")
        # Independently reconstruct the bounded data in the parent. A worker report
        # can never introduce a record, path, source descriptor or source byte.
        expected_digest = report_digest(received)
        del received  # Release the worker's complete object before reconstructing it locally.
        report = probe(
            context.game, relative, context.source_language,
            cancelled=context.cancelled, timeout=context.timeout, anchor=anchor,
        )
        if expected_digest != report_digest(report):
            raise ValueError("Ren'Py original-source report differs from verified local bytes.")
        if context.cancelled():
            raise ValueError("Source extraction was cancelled.")
        result = result_from_report(report, replace_source_set=True)
        report["counts"] = {
            "records": len(report["units"]), "sources": len(result.snapshots), "errors": 0,
            "unique_texts": len({u["source_text"] for u in report["units"]}),
            "characters": sum(len(u["source_text"]) for u in report["units"]),
        }
        report["capabilities"] = discovery_capabilities(report, inspected=True).to_dict()
        return ReaderProbe(tuple(s.source for s in result.snapshots), (), report)

    def extract(
        self, context: ReaderContext, relative: str, cancellation: Callable[[], bool],
    ) -> ReaderResult:
        return result_from_report(
            self.probe(replace(context, cancelled=cancellation), relative).report,
            replace_source_set=True,
        )


def _renpy_source_anchor(context: ReaderContext) -> str | None:
    """Retain the existing logical source when a new filename sorts before it."""
    import sqlite3
    from contextlib import closing

    database = checked_path(context.project / "project.sqlite3")
    if not database.is_file():
        return None
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as reader:
        if reader.execute("PRAGMA user_version").fetchone()[0] < 5:
            return None
        rows = reader.execute(
            "SELECT source_file FROM source_descriptors WHERE active=1 "
            "AND adapter_id='renpy-scripts' ORDER BY id LIMIT 2"
        ).fetchall()
    if len(rows) > 1:
        raise ValueError("The existing Ren'Py original-source scope is ambiguous.")
    if not rows:
        return None
    anchor: str = rows[0][0]
    validate_relative_source(anchor)
    return anchor


BUILTIN_READERS = ReaderRegistry((
    I2Reader(), KryptaTextAssetReader(), RenpyTemplateReader(), RenpyScriptReader(),
))


class I2DeploymentAdapter:
    """Delegate to the existing authoritative plan/approval/fingerprint services."""

    id = "i2-mono"
    version = "1"

    def __init__(self, installation: Any):
        self.installation = installation

    def probe(self) -> dict[str, Any]:
        result: dict[str, Any] = self.installation.status()
        return result

    def prepare(self, **options: Any) -> dict[str, Any]:
        result: dict[str, Any] = self.installation.prepare(**options)
        return result


class KryptaDeploymentAdapter(I2DeploymentAdapter):
    """Same inventory/review pipeline, with a separately pinned built-in runtime."""

    id = "krypta-memory"


class UnsupportedDeploymentAdapter:
    """Report shared ownership state without selecting any Unity runtime or installer."""

    id = "unsupported"
    version = "1"

    def __init__(self, installation: Any):
        self.installation = installation

    def probe(self) -> dict[str, Any]:
        if self.installation.adapter_kind() != "unsupported":
            raise ValueError("Deployment adapter selection changed before inspection.")
        result: dict[str, Any] = self.installation.status()
        return result

    def prepare(self, **options: Any) -> dict[str, Any]:
        raise ValueError(
            "No built-in deployment adapter supports this source and engine selection."
        )


def deployment_adapter_for(
    installation: Any,
) -> I2DeploymentAdapter | UnsupportedDeploymentAdapter:
    kind = installation.adapter_kind()
    if kind == "krypta":
        return KryptaDeploymentAdapter(installation)
    if kind == "i2":
        return I2DeploymentAdapter(installation)
    if kind == "unsupported":
        return UnsupportedDeploymentAdapter(installation)
    raise ValueError("No built-in deployment adapter supports this source and engine selection.")
