"""Atomically apply explicit human approval to a page or the whole project."""

from typing import Any

from unitytranslator.repository import ProjectRepository
from unitytranslator.validation import format_issues


def approve_selection(
    repo: ProjectRepository, records: list[dict[str, Any]], *, user_action: bool, reviewed: bool
) -> int:
    if user_action is not True or reviewed is not True:
        raise ValueError("Grup onayı açık kullanıcı seçimi ve insan incelemesi gerektirir.")
    if not 1 <= len(records) <= 200 or len({r["unit_id"] for r in records}) != len(records):
        raise ValueError("Bir sayfadan 1–200 farklı kayıt seçin.")
    return _approve_records(repo, records)


def all_approval_preview(repo: ProjectRepository) -> dict[str, Any]:
    records = []
    excluded = 0
    warnings = 0
    for row in repo.db.execute(
        "SELECT u.unit_id,u.source_revision,w.version,w.translation_revision,w.status,"
        "s.source_text,t.text,EXISTS(SELECT 1 FROM editor_drafts d WHERE d.unit_id=u.unit_id) "
        "AS has_draft FROM text_units u JOIN work_items w USING(unit_id) "
        "JOIN source_revisions s ON s.id=u.source_revision "
        "LEFT JOIN translation_revisions t ON t.id=w.translation_revision "
        "WHERE u.active=1 AND w.status IN ('translated','needs_review') ORDER BY u.unit_id"
    ):
        if not row["text"] or row["has_draft"] or format_issues(
            row["source_text"], row["text"], rules=repo.format_rules(row["unit_id"])
        ):
            excluded += 1
            continue
        warnings += int(row["status"] == "needs_review")
        records.append(
            {
                key: row[key]
                for key in ("unit_id", "source_revision", "translation_revision", "version")
            }
        )
    return {"records": records, "count": len(records), "excluded": excluded, "warnings": warnings}


def approve_all(
    repo: ProjectRepository, preview: dict[str, Any], *, user_action: bool, confirmation: str
) -> int:
    if user_action is not True or confirmation != canonical_all_confirmation(preview["count"]):
        raise ValueError("Bütün çeviriler için iki adımlı açık onay gerekli.")
    with repo.transaction():
        if all_approval_preview(repo) != preview or not preview["records"]:
            raise ValueError("Çeviri listesi değişti; bütün çeviriler onayını yeniden açın.")
        return _approve_records(repo, preview["records"])


def canonical_all_confirmation(count: int) -> str:
    """Internal confirmation protocol, independent of the displayed interface language."""
    return f"{count} çeviriyi onayla"


def _approve_records(repo: ProjectRepository, records: list[dict[str, Any]]) -> int:
    with repo.transaction() as db:
        for frozen in records:
            row = db.execute(
                "SELECT u.source_revision,u.active,w.version,w.translation_revision,w.status,"
                "s.source_text,t.text FROM text_units u JOIN work_items w USING(unit_id) "
                "JOIN source_revisions s ON s.id=u.source_revision "
                "LEFT JOIN translation_revisions t ON t.id=w.translation_revision "
                "WHERE u.unit_id=?",
                (frozen["unit_id"],),
            ).fetchone()
            if (
                row is None
                or not row["active"]
                or row["status"] not in ("translated", "needs_review")
                or any(
                    row[key] != frozen[key]
                    for key in ("source_revision", "translation_revision", "version")
                )
                or row["text"] is None
                or format_issues(
                    row["source_text"], row["text"], rules=repo.format_rules(frozen["unit_id"])
                )
                or db.execute(
                    "SELECT 1 FROM editor_drafts WHERE unit_id=?", (frozen["unit_id"],)
                ).fetchone()
            ):
                raise ValueError(
                    "Seçimde değişmiş, taslaklı veya onaya uygun olmayan kayıt var; "
                    "listeyi yenileyin."
                )
        for frozen in records:
            repo.approve(frozen["unit_id"], frozen["version"])
    return len(records)


def matching_review_preview(
    repo: ProjectRepository, action: str, filters: dict[str, Any],
) -> dict[str, Any]:
    """Freeze an explicit filtered selection across pages; never infer approval."""
    if action not in ("approve_identical", "reset_empty"):
        raise ValueError("Unknown bulk review action.")
    scope: dict[str, Any] = {key: filters.get(key, default) for key, default in (
        ("search", ""), ("status", None), ("category", None), ("affected", False),
    )}
    where, parameters = repo.filters(**scope)
    records = []
    samples: list[dict[str, str]] = []
    excluded = 0
    queued = {row[0] for row in repo.db.execute(
        "SELECT DISTINCT i.unit_id FROM job_items i JOIN jobs j ON j.id=i.job_id "
        "WHERE i.status IN ('queued','processing') "
        "AND j.status IN ('queued','running','pausing','paused')",
    )}
    for row in repo.db.execute(
        "SELECT u.unit_id,u.source_revision,u.original_key,w.version,w.translation_revision,"
        "w.status,w.approved_source,w.approved_translation,s.source_text,t.text,"
        "t.source_revision AS translated_source,"
        "EXISTS(SELECT 1 FROM editor_drafts d WHERE d.unit_id=u.unit_id) AS has_draft "
        "FROM text_units u JOIN work_items w USING(unit_id) "
        "JOIN source_revisions s ON s.id=u.source_revision "
        "LEFT JOIN translation_revisions t ON t.id=w.translation_revision "
        f"WHERE {where} ORDER BY u.unit_id", parameters,
    ):
        text = row["text"]
        identical = text is not None and bool(text.strip()) and text == row["source_text"]
        empty = text is None or not text.strip()
        if not (identical if action == "approve_identical" else empty):
            continue
        eligible = not (row["has_draft"] or row["unit_id"] in queued)
        if action == "approve_identical":
            eligible = eligible and row["status"] in ("translated", "needs_review") and (
                row["translated_source"] == row["source_revision"]
            ) and not format_issues(
                row["source_text"], text, rules=repo.format_rules(row["unit_id"]),
            )
        else:
            eligible = eligible and row["status"] in (
                "needs_review", "validation_error", "translated",
            ) and not (row["approved_source"] or row["approved_translation"])
        if not eligible:
            excluded += 1
            continue
        records.append({key: row[key] for key in (
            "unit_id", "source_revision", "translation_revision", "version",
        )})
        if len(samples) < 20:
            samples.append({"key": row["original_key"][:200], "source": row["source_text"][:200]})
    return {
        "action": action, "filters": scope, "records": records,
        "count": len(records), "excluded": excluded, "samples": samples,
        "policies": list(map(tuple, repo.db.execute(
            "SELECT key,value FROM project_settings ORDER BY key",
        ))),
    }


def apply_matching_review(
    repo: ProjectRepository, preview: dict[str, Any], *, user_action: bool,
) -> int:
    """Revalidate the complete preview and apply atomically without deleting history."""
    if user_action is not True:
        raise ValueError("Explicit confirmation is required for bulk review.")
    with repo.transaction() as db:
        if not preview["records"] or matching_review_preview(
            repo, preview["action"], preview["filters"],
        ) != preview:
            raise ValueError("Bulk review selection changed. Open the preview again.")
        if preview["action"] == "approve_identical":
            return _approve_records(repo, preview["records"])
        for record in preview["records"]:
            db.execute(
                "UPDATE work_items SET status='pending',translation_revision=NULL,"
                "version=version+1 WHERE unit_id=?", (record["unit_id"],),
            )
    return int(preview["count"])
