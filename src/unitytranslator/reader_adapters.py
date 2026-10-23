"""Explicit bundled adapters; profile data never selects imports or executable code."""

import base64
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
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


BUILTIN_READERS = ReaderRegistry((I2Reader(), KryptaTextAssetReader()))


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


def deployment_adapter_for(installation: Any) -> I2DeploymentAdapter:
    if installation.adapter_kind() == "krypta":
        return KryptaDeploymentAdapter(installation)
    return I2DeploymentAdapter(installation)
