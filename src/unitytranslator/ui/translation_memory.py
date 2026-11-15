"""Translation memory options, preview summary and history origin labels."""

import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from unitytranslator.repository import is_memory_metadata
from unitytranslator.ui.i18n import tr


def memory_scope_note() -> str:
    """Reuse covers every active record; review filters never narrow it."""
    return tr("Applies to the whole project; review filters are ignored. Preview before applying.")


class TranslationMemoryOptionsDialog(QDialog):
    """Choose what an explicit translation memory preview may use; nothing is written."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Reuse translation memory"))
        layout = QVBoxLayout(self)
        note = QLabel(
            tr(
                "Records with exactly the same source text, text rules, category, context and "
                "dialogue neighbours can receive the approved translation of another record as "
                "an unapproved candidate. Equal source text can still need a different "
                "translation: review every candidate before approval. Approvals, drafts and "
                "current translations are never replaced."
            )
        )
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        self.scope = QLabel(memory_scope_note())
        self.scope.setTextFormat(Qt.TextFormat.PlainText)
        self.scope.setWordWrap(True)
        layout.addWidget(self.scope)
        self.include_translated = QCheckBox(
            tr(
                "Also offer candidates to records with an unapproved translation "
                "(history only; their current text is kept)"
            )
        )
        layout.addWidget(self.include_translated)
        self.model_donors = QCheckBox(
            tr(
                "Also reuse unapproved model translations made with the current model settings "
                "and glossary/style"
            )
        )
        layout.addWidget(self.model_donors)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def summary_text(result: dict[str, Any]) -> str:
    """Preview counts shown before the explicit confirmation."""
    skipped = result["skipped"]
    return "\n".join(
        [
            tr(
                "New candidates: {p0} ({p1} as the current unapproved translation, {p2} in "
                "history only).",
                p0=str(result["candidates"]),
                p1=str(result["current"]),
                p2=str(result["history"]),
            ),
            tr(
                "Matching keys: {p0}. Donors: {p1} approved, {p2} model.",
                p0=str(result["matches"]),
                p1=str(result["donors"]["approved"]),
                p2=str(result["donors"]["model"]),
            ),
            tr(
                "Conflicts: {p0} keys whose donors disagree; {p1} records receive nothing.",
                p0=str(result["conflicts"]),
                p1=str(result["conflict_records"]),
            ),
            tr(
                "Skipped: {p0} approved, {p1} drafts, {p2} queued in jobs, {p3} already "
                "translated, {p4} same text, {p5} already offered, {p6} format check.",
                p0=str(skipped["approved"]),
                p1=str(skipped["draft"]),
                p2=str(skipped["queued"]),
                p3=str(skipped["translated"]),
                p4=str(skipped["same_text"]),
                p5=str(skipped["already_offered"]),
                p6=str(skipped["format"]),
            ),
        ]
    )


def details_text(result: dict[str, Any]) -> str:
    """Examples of new candidates and of conflicting donors."""
    parts = [
        f"{item['key']}\n{item['source']}\n→ {item['text']}\n"
        + tr("Donor record: {p0}", p0=item["donor_key"])
        for item in result["samples"]
    ]
    parts += [
        tr("Conflict: {p0}", p0=item["source"]) + "\n" + "\n".join(item["texts"])
        for item in result["conflict_samples"]
    ]
    return "\n\n".join(parts)


def revision_origin(row: dict[str, Any]) -> str:
    """History label of one stored translation revision."""
    if is_memory_metadata(json.loads(row["metadata_json"])):
        return tr("Translation memory")
    labels = {"model": tr("Model"), "manual": tr("Manual edit"), "import": tr("Import")}
    return labels[row["origin"]]


def memory_note(donor_key: str, approved: bool) -> str:
    """Origin of a translation memory candidate and whether a reviewer approved it."""
    if approved:
        return tr(
            "Translation memory candidate from record {p0}; approved by a reviewer.",
            p0=donor_key,
        )
    return tr("Translation memory candidate from record {p0}; it is not approved.", p0=donor_key)


def revision_note(row: dict[str, Any], approved_revision: str | None = None) -> str:
    """Donor of a translation memory revision; empty for every other origin."""
    metadata = json.loads(row["metadata_json"])
    if not is_memory_metadata(metadata):
        return ""
    metadata = metadata if "donor_key" in metadata else metadata.get("original_metadata", {})
    approved = approved_revision is not None and row["id"] == approved_revision
    return memory_note(str(metadata.get("donor_key", "")), approved)
