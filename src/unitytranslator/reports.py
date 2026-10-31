"""Local pilot reports keep measured timings separate from human review."""

import json
import math
from collections import Counter
from html import escape
from pathlib import Path
from statistics import median
from typing import Any
from uuid import uuid4

from unitytranslator.jobs import JobStore
from unitytranslator.repository import ProjectRepository, now
from unitytranslator.validation import (
    REVIEW_CHECKS_VERSION,
    format_issues,
    issue_label,
    review_issues,
)


def save_current_quality_audit(repository: ProjectRepository) -> dict[str, Any]:
    """Recheck current candidates without changing revisions, statuses or approvals."""
    findings = []
    count = 0
    for row in repository.db.execute(
        "SELECT u.unit_id,u.original_key,s.source_text,s.source_language,"
        "t.id AS translation_revision,t.text,t.target_language,t.issues_json,w.status "
        "FROM text_units u JOIN source_revisions s ON s.id=u.source_revision "
        "JOIN work_items w USING(unit_id) JOIN translation_revisions t "
        "ON t.id=w.translation_revision AND t.source_revision=u.source_revision "
        "WHERE u.active=1 ORDER BY u.original_key,u.unit_id"
    ):
        count += 1
        issues = sorted(
            set(
                format_issues(
                    row["source_text"], row["text"], rules=repository.format_rules(row["unit_id"])
                )
                + review_issues(
                    row["source_text"],
                    row["text"],
                    source_language=row["source_language"],
                    target_language=row["target_language"],
                    rules=repository.format_rules(row["unit_id"]),
                )
            )
        )
        if issues:
            findings.append(
                {
                    "unit_id": row["unit_id"],
                    "original_key": row["original_key"],
                    "translation_revision": row["translation_revision"],
                    "source": row["source_text"],
                    "translation": row["text"],
                    "stored_status": row["status"],
                    "audit_issues": issues,
                    "new_issues": sorted(set(issues) - set(json.loads(row["issues_json"]))),
                }
            )
    summary = {
        "review_checks_version": REVIEW_CHECKS_VERSION,
        "created_at": now(),
        "audited_current_translations": count,
        "flagged_records": len(findings),
        "newly_flagged_records": sum(bool(row["new_issues"]) for row in findings),
        "issue_counts": dict(Counter(code for row in findings for code in row["audit_issues"])),
        "note": "Bu ayrı yeniden kontrol raporudur; eski revizyonlar, pilot ölçümleri, "
        "kayıt durumları ve insan onayları değiştirilmedi. Dil ipuçları yalnızca en→tr için "
        "uygulanır; yanlış uyarı veya kaçırılan hata olabilir. İnsan incelemesi gerekir.",
    }
    stem = "reports/quality-audit-" + uuid4().hex
    json_path = repository.paths.write_json(stem + ".json", {**summary, "records": findings})
    table = "".join(
        "<tr>"
        + "".join(
            "<td>" + escape(str(value)) + "</td>"
            for value in (
                row["original_key"],
                row["source"],
                row["translation"],
                row["stored_status"],
                "; ".join(issue_label(code) for code in row["audit_issues"]),
            )
        )
        + "</tr>"
        for row in findings[:200]
    )
    html = (
        '<!doctype html><html lang="tr"><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; '
        'style-src &#39;unsafe-inline&#39;">'
        "<title>Çeviri kalite kontrolleri</title><style>"
        "body{font:16px Segoe UI,sans-serif;margin:24px}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #aaa;padding:8px;white-space:pre-wrap;overflow-wrap:anywhere}"
        "</style><h1>Çeviri kalite kontrolleri</h1><p>"
        + escape(str(summary["note"]))
        + "</p><p>"
        + f"{count} güncel çeviri kontrol edildi; {len(findings)} kayıtta uyarı var. "
        + "HTML ilk 200 uyarılı kaydı gösterir; JSON raporu bütün bulguları içerir.</p>"
        + "<table><thead><tr><th>Kayıt</th><th>Kaynak</th><th>Çeviri</th>"
        + "<th>Kayıt durumu</th><th>Kontroller</th></tr></thead><tbody>"
        + table
        + "</tbody></table></html>"
    )
    html_path = repository.paths.write_text(stem + ".html", html)
    return {**summary, "json_path": str(json_path), "html_path": str(html_path)}


def length_band(length: int) -> str:
    return (
        "short"
        if length <= 80
        else "medium"
        if length <= 300
        else "long"
        if length <= 1200
        else "very_long"
    )


def project_estimate(repository: ProjectRepository, job_id: str) -> dict[str, Any] | None:
    job = JobStore(repository).job(job_id)
    if job["status"] not in ("completed", "completed_with_errors"):
        return None
    samples: dict[tuple[str, str], list[float]] = {}
    for row in repository.db.execute(
        "SELECT s.category,length(s.source_text) AS characters,sum(r.elapsed_seconds) AS seconds "
        "FROM job_items j JOIN source_revisions s ON s.id=j.source_revision "
        "JOIN translation_runs r ON r.job_id=j.job_id AND r.unit_id=j.unit_id "
        "WHERE j.job_id=? AND j.status='completed' AND j.candidate_only=0 "
        "GROUP BY j.unit_id",
        (job_id,),
    ):
        key = (row["category"], length_band(row["characters"]))
        samples.setdefault(key, []).append(float(row["seconds"]))
    if not samples:
        return None
    lower = upper = 0.0
    covered = uncovered = 0
    strata = []
    for row in repository.db.execute(
        "SELECT s.category,CASE WHEN length(s.source_text)<=80 THEN 'short' "
        "WHEN length(s.source_text)<=300 THEN 'medium' WHEN length(s.source_text)<=1200 "
        "THEN 'long' ELSE 'very_long' END AS band,count(*) AS count "
        "FROM text_units u JOIN source_revisions s ON s.id=u.source_revision "
        "WHERE u.active=1 GROUP BY s.category,band"
    ):
        values = samples.get((row["category"], row["band"]), [])
        count = row["count"]
        strata.append(
            {
                "category": row["category"],
                "length_band": row["band"],
                "records": count,
                "samples": len(values),
            }
        )
        if not values:
            uncovered += count
            continue
        covered += count
        lower += min(values) * count
        upper += max(values) * count
    return {
        "method": "observed_category_length_ranges",
        "lower_seconds": round(lower),
        "upper_seconds": round(upper),
        "covered_records": covered,
        "unmeasured_records": uncovered,
        "complete_project_estimate": uncovered == 0,
        "strata": strata,
        "human_review_seconds": None,
        "limitations": "Gözlenen min/max süre aralığıdır; istatistiksel güven aralığı değildir. "
        "Ölçülmeyen kategoriler/uzunluklar ve insan incelemesi dahil değildir. "
        "Pilot sırasında geliştirme/derleme işleri de çalıştı.",
    }


def job_report(repository: ProjectRepository, job_id: str) -> dict[str, Any]:
    store = JobStore(repository)
    job = store.job(job_id)
    attempts = [
        dict(row)
        for row in repository.db.execute(
            "SELECT attempt,status,elapsed_seconds,metadata_json FROM translation_runs "
            "WHERE job_id=?",
            (job_id,),
        )
    ]
    measured = sorted(
        row["elapsed_seconds"]
        for row in attempts
        if row["status"]
        not in ("processing", "interrupted", "cancelled", "unsupported_format", "context")
    )
    rows = [
        dict(row)
        for row in repository.db.execute(
            "SELECT j.unit_id,j.status,j.attempts,j.error_code,j.result_revision,j.candidate_only,"
            "s.source_text,s.source_hash,"
            "s.category,s.context,u.original_key,t.text AS translation,t.issues_json,"
            "w.status AS current_status,w.translation_revision AS current_translation,"
            "w.approved_source,w.approved_translation,j.source_revision,"
            "ct.origin AS current_origin,ct.text AS current_text,ct.created_at AS current_created,"
            "b.created_at AS job_created,u.source_revision AS active_source "
            "FROM job_items j JOIN source_revisions s ON s.id=j.source_revision "
            "JOIN text_units u ON u.unit_id=j.unit_id JOIN work_items w ON w.unit_id=j.unit_id "
            "JOIN jobs b ON b.id=j.job_id "
            "LEFT JOIN translation_revisions ct ON ct.id=w.translation_revision "
            "LEFT JOIN translation_revisions t ON t.id=j.result_revision "
            "WHERE j.job_id=? ORDER BY j.rowid",
            (job_id,),
        )
    ]
    categories = Counter(row["category"] for row in rows)
    issue_counts = Counter(
        issue for row in rows for issue in json.loads(row["issues_json"] or "[]")
    )
    failure_counts = Counter(row["error_code"] for row in rows if row["error_code"])
    attempt_statuses = Counter(row["status"] for row in attempts)
    corrections = sum(
        row["result_revision"] is not None
        and row["active_source"] == row["source_revision"]
        and row["current_origin"] == "manual"
        and row["current_created"] >= row["job_created"]
        and row["current_text"] != row["translation"]
        for row in rows
    )
    approved = sum(
        row["approved_source"] == row["source_revision"]
        and row["approved_translation"] == row["result_revision"]
        and row["result_revision"] is not None
        for row in rows
    )
    for row in rows:
        if row["translation"] is None:
            row["review_status"] = "validation_error" if row["status"] == "failed" else "pending"
        elif (
            row["approved_translation"] == row["result_revision"]
            and row["approved_source"] == row["source_revision"]
        ):
            row["review_status"] = "approved"
        elif row["candidate_only"] or json.loads(row["issues_json"] or "[]"):
            row["review_status"] = "needs_review"
        else:
            row["review_status"] = "translated"
    review_blocker = store.pilot_review_blocker(job_id)
    context_attempts = []
    for attempt in attempts:
        metadata = json.loads(attempt["metadata_json"])
        details = metadata.get("result", {}).get("dialogue_context") or metadata.get(
            "error_diagnostics", {},
        ).get("dialogue_context")
        if details is not None:
            context_attempts.append(details)
    return {
        "format_version": 1,
        "job_id": job_id,
        "kind": job["kind"],
        "progress": store.progress(job_id),
        "profile": json.loads(job["profile_json"]),
        "source_fingerprint": job["source_fingerprint"],
        "record_count": len(rows),
        "unique_texts": len({row["source_text"] for row in rows}),
        "source_characters": sum(len(row["source_text"]) for row in rows),
        "categories": dict(categories),
        "failure_codes": dict(failure_counts),
        "issue_counts": dict(issue_counts),
        "retry_count": sum(max(row["attempts"] - 1, 0) for row in rows),
        "measured_attempts": len(measured),
        "attempt_count": len(attempts),
        "validation_metrics": {
            "unit": "attempt",
            "response_schema_errors": attempt_statuses["response_schema_error"],
            "protected_content_errors": attempt_statuses["protected_content_error"],
            "output_truncated_errors": attempt_statuses["output_truncated"],
            "unexpected_tool_call_errors": attempt_statuses["unexpected_tool_call"],
            "legacy_unclassified_validation_errors": attempt_statuses["validation_error"],
            "unsupported_source_formats": attempt_statuses["unsupported_format"],
            "note": "Eski validation_error kayıtları JSON ve korumalı içerik olarak "
            "geriye dönük ayrılamaz; sıfır yeni hata eski sonuçların hatasız olduğu "
            "anlamına gelmez.",
        },
        "dialogue_context_metrics": {
            "mode": json.loads(job["profile_json"]).get("dialogue_context", "none"),
            "reported_attempts": len(context_attempts),
            "with_references": sum(c["reference_count"] > 0 for c in context_attempts),
            "isolated_fallback": sum(c["reference_count"] == 0 for c in context_attempts),
            "budget_reduced": sum(c["omitted_for_budget"] > 0 for c in context_attempts),
        },
        "median_request_seconds": median(measured) if measured else None,
        "p95_request_seconds": measured[math.ceil(len(measured) * 0.95) - 1] if measured else None,
        "human_approved_records": approved,
        "changed_after_generation": corrections,
        "human_review_complete": approved == len(rows) and bool(rows),
        "pilot_review_acknowledged": bool(job["report_seen"]),
        "pilot_review_eligible": review_blocker is None,
        "pilot_review_blocker": review_blocker,
        "quality_note": "Biçim kontrolleri anlam doğruluğunu garanti etmez. "
        "İnsan incelemesi gereklidir.",
        "project_time_estimate": project_estimate(repository, job_id),
        "records": rows,
    }


def save_job_report(repository: ProjectRepository, job_id: str) -> Path:
    return repository.paths.write_json(
        f"reports/pilot-{job_id}.json", job_report(repository, job_id)
    )


def save_review_html(repository: ProjectRepository, job_id: str) -> Path:
    report = job_report(repository, job_id)
    if report["record_count"] > 200:
        raise ValueError("HTML inceleme raporu yalnızca sınırlı pilot içindir.")
    rows = []
    for item in report["records"]:
        rows.append(
            "<tr>"
            + "".join(
                "<td>" + escape(str(value or "")) + "</td>"
                for value in (
                    item["original_key"],
                    item["source_text"],
                    item["translation"],
                    item["review_status"],
                    issue_label(item["error_code"])
                    if item["error_code"]
                    else "; ".join(
                        issue_label(code) for code in json.loads(item["issues_json"] or "[]")
                    ),
                )
            )
            + "</tr>"
        )
    summary = (
        f"{report['record_count']} kayıt · {report['progress']['counts'].get('completed', 0)} "
        f"biçim kontrolünü geçti · {report['progress']['counts'].get('failed', 0)} ayrıldı · "
        f"{report['progress']['generation_seconds']:.1f} saniye üretim isteği"
    )
    review_note = (
        "Pilot inceleme kapısı kullanıcı tarafından onaylandı. "
        if report["pilot_review_acknowledged"]
        else "Pilot inceleme kapısı henüz onaylanmadı. "
    )
    review_note += (
        f"{report['human_approved_records']} kayıt tek tek onaylandı. "
        "Model sonucu onay değildir. Bu dosya çevrimdışı çalışır; veri veya telemetri göndermez."
    )
    document = (
        "<!doctype html><html lang='tr'><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' "
        "content=\"default-src 'none'; style-src 'unsafe-inline';\">"
        "<title>UnityTranslator pilot incelemesi</title><style>"
        "body{font:16px Segoe UI,sans-serif;margin:28px;color:#17212b}"
        "table{width:100%;border-collapse:collapse;table-layout:fixed}"
        "th,td{border:1px solid #ccd2d8;padding:10px;text-align:left;vertical-align:top;"
        "overflow-wrap:anywhere;white-space:pre-wrap}th{background:#edf3f7}"
        "tr:nth-child(even){background:#f7f9fb}td:first-child{width:15%}</style>"
        f"<h1>{report['record_count']} kayıtlık yerel pilot</h1><p>" + escape(summary) + "</p>"
        "<p>" + escape(review_note) + "</p>"
        "<table><thead><tr><th>Kayıt</th><th>Kaynak</th><th>Çeviri</th><th>Durum</th>"
        "<th>Kontroller</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></html>"
    )
    return repository.paths.write_text(f"reports/pilot-{job_id}.html", document)
