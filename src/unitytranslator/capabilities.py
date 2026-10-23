"""Evidence-based capability reports; reporting never grants deployment authority."""

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Support(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Capability:
    status: Support
    reason: str
    message: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityReport:
    extraction: Capability
    translation: Capability
    export: Capability
    installation: Capability
    runtime_indicators: tuple[str, ...] = ()
    container_indicators: tuple[str, ...] = ()
    localization_indicators: tuple[str, ...] = ()
    adapter_id: str | None = None
    adapter_version: str | None = None
    format_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discovery_capabilities(report: dict[str, Any], *, inspected: bool = False) -> CapabilityReport:
    """Interpret current I2 evidence without inferring support from filenames or scripts.

    Export and installation require separate current revision/build checks. The legacy
    discovery keys remain intact; this versioned report adds independent results.
    """
    extraction = Capability(
        Support.UNKNOWN, "source_not_verified", "Candidate files are not verified text sources."
    )
    localization: tuple[str, ...] = ()
    adapter = None
    textasset = report.get("adapter_id") == "krypta-textassets"
    if inspected:
        candidates = report.get("i2_candidates", [])
        diagnostics = report.get("diagnostics", [])
        if candidates:
            localization = ("I2",)
            adapter = "i2"
        if textasset:
            localization = ("custom_textasset",)
            adapter = "krypta-textassets"
        if report.get("units") and not report.get("errors"):
            extraction = Capability(
                Support.SUPPORTED,
                "source_extracted",
                "The selected built-in reader extracted validated records from this source.",
                ("units", "fingerprints") if textasset
                else ("units", "sha256_before", "sha256_after"),
            )
        elif report.get("errors"):
            extraction = Capability(
                Support.UNKNOWN,
                "source_read_failed",
                "Source errors prevent activation; inspect the structured reader errors.",
                ("errors",),
            )
        elif candidates:
            extraction = Capability(
                Support.UNKNOWN,
                "no_translatable_records",
                "I2 candidates produced no translatable records for the selected language.",
                ("i2_candidates", "diagnostics"),
            )
        elif any(item.get("code") == "type_tree_unavailable" for item in diagnostics):
            extraction = Capability(
                Support.UNKNOWN,
                "type_tree_unavailable",
                "Some type trees are unavailable and no matching text source was verified.",
                ("diagnostics",),
            )
        else:
            extraction = Capability(
                Support.UNKNOWN,
                "no_matching_reader",
                "No localization source matching the current I2 reader was verified.",
                ("objects", "i2_candidates"),
            )
    translation = Capability(
        extraction.status,
        "translation_pipeline_available"
        if extraction.status == Support.SUPPORTED else "verified_source_required",
        "Extracted records can use the shared translation and review pipeline."
        if extraction.status == Support.SUPPORTED
        else "Translation requires a verified source; model availability is checked separately.",
    )
    return CapabilityReport(
        extraction=extraction,
        translation=translation,
        export=Capability(
            Support.SUPPORTED, "staged_payload_export",
            "Staged payload export is available for current approved revisions."
        ) if textasset and extraction.status == Support.SUPPORTED else Capability(
            Support.UNKNOWN, "approved_selection_required",
            "Export requires a supported format and current approved revisions.",
        ),
        installation=Capability(
            Support.UNSUPPORTED if textasset else Support.UNKNOWN,
            "staged_payloads_only" if textasset else "deployment_not_verified",
            "This adapter stages text payloads; normal game installation remains unsupported."
            if textasset else
            "Installation requires separate build evidence and a reviewed additive file plan.",
        ),
        runtime_indicators=tuple(report.get("runtime_indicators", ())),
        container_indicators=tuple(report.get("container_indicators", ())) or (
            ("serialized_asset_candidate",) if report.get("source_candidates") else ()
        ),
        localization_indicators=localization,
        adapter_id=adapter,
        adapter_version="1" if adapter else None,
    )
