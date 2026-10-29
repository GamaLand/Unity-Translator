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
    engine = report.get("engine_report", {}).get("engine")
    if report.get("adapter_id") in ("renpy-templates", "renpy-scripts") and inspected:
        original = report["adapter_id"] == "renpy-scripts"
        complete = (
            report.get("extraction") == "supported" and report.get("complete_source_set") is True
            and bool(report.get("units")) and not report.get("errors")
        )
        source = Capability(
            Support.SUPPORTED if complete else Support.UNKNOWN,
            ("native_scripts_extracted" if original else "native_templates_extracted")
            if complete else "source_read_failed",
            ("The verified original-source subset was read with explicit coverage exclusions."
             if original else
             "The native-template subset was read; original scripts and archives are excluded.")
            if complete else "A complete verified native-template source set is required.",
        )
        return CapabilityReport(
            extraction=source,
            translation=Capability(
                source.status, "translation_pipeline_available" if complete
                else "verified_source_required",
                "Verified native-template records use the shared translation and review pipeline.",
            ),
            export=Capability(
                Support.SUPPORTED if complete else Support.UNKNOWN,
                "staged_native_export" if complete else "verified_source_required",
                "Native staging requires current approvals and an explicit language mapping.",
            ),
            installation=Capability(
                Support.UNKNOWN, "native_copy_plan_required",
                "A translated-copy ZIP requires a matching build, current approvals and a "
                "reviewed recipient plan. Original-folder installation is unsupported.",
            ),
            container_indicators=("original_source_container" if original
                                  else "loose_native_template",),
            localization_indicators=("renpy_native_translation",),
            adapter_id=report["adapter_id"], adapter_version="1",
        )
    if engine in ("renpy", "ambiguous"):
        ambiguous = engine == "ambiguous"
        templates = any(
            item.get("kind") == "translation_template_candidate"
            for item in report.get("renpy_inputs", {}).get("source_candidates", ())
        )
        scripts = any(
            item.get("kind") in ("loose_script", "renpy_python_source") or (
                item.get("archive_inspection", {}).get("status") == "verified_literal_index"
                and item["archive_inspection"].get("extensions", {}).get(".rpy", 0)
            ) for item in report.get("renpy_inputs", {}).get("source_candidates", ())
        )
        unavailable = Capability(
            Support.UNKNOWN if ambiguous or templates or scripts else Support.UNSUPPORTED,
            "ambiguous_engine" if ambiguous else (
                "renpy_sources_not_verified" if scripts else (
                    "renpy_templates_not_verified" if templates else "renpy_templates_required"
                )
            ),
            "Select an explicit engine for inspection; this does not authorize installation."
            if ambiguous else (
                "Select an original source or archive to verify its static source contracts."
                if scripts else
                "Select a template to verify the supported subset across its language folder."
                if templates else
                "Supply native game/tl/<language>/*.rpy templates; archives and compiled "
                "scripts cannot be extracted by the current readers."
            ),
        )
        return CapabilityReport(
            extraction=unavailable,
            translation=Capability(
                Support.UNKNOWN, "verified_source_required",
                "Translation requires a verified source and explicit source language.",
            ),
            export=Capability(
                Support.UNKNOWN, "verified_source_required",
                "Native export requires verified templates, approvals and a language mapping.",
            ),
            installation=Capability(
                Support.UNSUPPORTED, "engine_deployment_not_implemented",
                "No verified deployment route exists for this engine selection.",
            ),
            runtime_indicators=tuple(report.get("runtime_indicators", ())),
            container_indicators=tuple(report.get("container_indicators", ())),
        )
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
            Support.UNKNOWN,
            "reviewed_runtime_required" if textasset else "deployment_not_verified",
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
