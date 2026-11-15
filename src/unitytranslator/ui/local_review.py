"""Local reviewer texts: confirmation, progress, results and per-revision codes."""

from typing import Any

from unitytranslator.diagnostics import Failure
from unitytranslator.local_review import MAX_RUN_RECORDS, label
from unitytranslator.ui.i18n import diagnostic, localize, tr


def code_labels(reviews: list[dict[str, Any]]) -> list[str]:
    """Distinct local reviewer labels of one revision, apart from automated checks."""
    codes = sorted({code for review in reviews for code in review["issues"]})
    return [diagnostic(label(code)) for code in codes]


def review_lines(reviews: list[dict[str, Any]]) -> list[str]:
    """Each stored review with the model and prompt version that produced it."""
    lines = []
    for review in reviews:
        labels = [diagnostic(label(code)) for code in review["issues"]]
        lines.append(tr(
            "Local reviewer {p0} ({p1}): {p2}",
            p0=str(review.get("model") or ""), p1=str(review.get("prompt_version") or ""),
            p2="; ".join(labels) if labels else tr("no codes"),
        ))
        if review.get("note"):
            lines.append(tr("Reviewer note (model output, unverified): {p0}", p0=review["note"]))
    return lines


def confirmation_text(result: dict[str, Any]) -> str:
    """What the explicit confirmation states before any request is sent."""
    return "\n\n".join([
        tr(
            "Send {p0} records to the model {p1} on the already running server {p2}?",
            p0=str(result["selected"]), p1=result["model"], p2=result["address"],
        ),
        tr(
            "The local reviewer only adds issue codes to the current translations. It never "
            "edits text, approves, changes a status or removes a check. Codes stay with the "
            "reviewed revision; editing or replacing the text leaves them behind."
        ),
        tr(
            "In the current filters: {p0} records; {p1} without a translation, {p2} already "
            "reviewed with these settings, {p3} left for a later run (at most {p4} per run).",
            p0=str(result["in_scope"]), p1=str(result["without_translation"]),
            p2=str(result["already_reviewed"]), p3=str(result["remaining"]),
            p4=str(MAX_RUN_RECORDS),
        ),
    ])


def nothing_to_review_text(result: dict[str, Any]) -> str:
    """The information shown instead of a send question when no record is selected."""
    return "\n\n".join([
        tr("No current translations are left to review."),
        tr(
            "In the current filters: {p0} records; {p1} without a translation, {p2} already "
            "reviewed with these settings, {p3} left for a later run (at most {p4} per run).",
            p0=str(result["in_scope"]), p1=str(result["without_translation"]),
            p2=str(result["already_reviewed"]), p3=str(result["remaining"]),
            p4=str(MAX_RUN_RECORDS),
        ),
    ])


def progress_text(result: dict[str, Any]) -> str:
    text = tr(
        "Local reviewer: {p0}/{p1} records reviewed, {p2} with codes, {p3} failed, "
        "{p4} changed since the preview.",
        p0=str(result["reviewed"]), p1=str(result["total"]), p2=str(result["flagged"]),
        p3=str(result["failed"]), p4=str(result["changed"]),
    )
    if result["status"] == "cancelled":
        text += "\n" + tr("The local review was cancelled; completed reviews were kept.")
    stop = result.get("stop")
    if stop:
        text += "\n" + localize(Failure(stop["message"], code=stop["code"], params=stop["params"]))
    return text
