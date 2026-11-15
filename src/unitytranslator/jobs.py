"""Durable claim/retry queue; HTTP requests never hold a SQLite transaction open."""

import asyncio
import json
import random
from collections.abc import Callable, Sequence
from dataclasses import replace
from hashlib import sha256
from time import perf_counter
from typing import Any
from uuid import uuid4

from unitytranslator.diagnostics import Diagnostic
from unitytranslator.dialogue_context import DialogueContextStore
from unitytranslator.domain import GenerationProfile, OperationCancelled
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.providers import (
    REASONING_MODES,
    LocalProvider,
    ProviderError,
    local_endpoint,
    reasoning_supported,
)
from unitytranslator.repository import ProjectRepository, canonical, now

MAX_PARALLEL_REQUESTS = 36
MAX_ATTEMPTS = 3
# Server outages are not the record's fault: they keep their attempt history but refund the
# attempt budget. Consecutive outages spanning several records pause the job; a record that
# alone keeps failing this way is failed after a bounded number of consecutive outage runs.
OUTAGE_CODES = frozenset({"connection", "server_unavailable"})
OUTAGE_PAUSE_STREAK = 5
MAX_RECORD_OUTAGES = 5
RETRY_CODES = frozenset({
    "timeout",
    "invalid_response",
    "validation_error",
    "response_schema_error",
    "protected_content_error",
    "output_truncated",
    "unexpected_tool_call",
})
PAUSE_CODES = frozenset({"out_of_memory", "not_found", "unauthorized", "unsupported_option"})


def retry_delay(failures: int, base: float) -> float:
    """Jittered exponential backoff, capped at 30 seconds."""
    return float(min(30.0, base * 2 ** max(0, failures - 1)) * random.uniform(0.5, 1.0))


class JobStore:
    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    def fingerprint(self, profile: GenerationProfile | None = None) -> str:
        digest = sha256()
        for index, row in enumerate(self.repository.db.execute(
            "SELECT unit_id,source_revision FROM text_units WHERE active=1 ORDER BY unit_id"
        )):
            if index % 1024 == 0:
                self.repository.check_cancelled()
            digest.update(canonical(list(row)).encode("utf-8"))
        # Newer text rules join the identity, so a rule upgrade needs a new pilot. Legacy
        # rules add nothing and keep existing reviewed pilots valid.
        newer = sorted({
            json.loads(row[0]).get("format_rules") for row in self.repository.db.execute(
                "SELECT descriptor_json FROM source_descriptors WHERE active=1"
            )
        } - {None, "protected-i2-v4", "literal-lines-v1", "renpy-text-v1"})
        if newer:
            digest.update(canonical(newer).encode("utf-8"))
        if profile is not None and profile.dialogue_context != "none":
            digest.update(profile.dialogue_context.encode())
            digest.update(DialogueContextStore(self.repository).fingerprint().encode())
        return digest.hexdigest()

    def create(
        self,
        units: Sequence[str],
        profile: GenerationProfile,
        kind: str = "prototype",
        retranslate: bool = False,
        approved_candidates: bool = False,
    ) -> str:
        if kind not in ("prototype", "pilot", "bulk") or len(units) != len(set(units)) or not units:
            raise ValueError("Invalid job type or record selection.")
        if (kind == "prototype" and len(units) > 10) or (kind == "pilot" and len(units) > 200):
            raise ValueError("The prototype or pilot record limit was exceeded.")
        if profile.provider not in ("lm-studio", "llama-cpp") or not profile.model.strip():
            raise ValueError("A provider and model selection is required.")
        if profile.reasoning_effort not in REASONING_MODES or not reasoning_supported(
            profile.provider, profile.reasoning_effort
        ):
            raise ValueError("This reasoning option is not available for the selected provider.")
        if (
            not 512 <= profile.context_tokens <= 1_048_576
            or not 128 <= profile.output_tokens <= 8192
        ):
            raise ValueError("The context or output token limit is invalid.")
        if not 0 <= profile.temperature <= 2 or profile.prompt_version != "translate-v1":
            raise ValueError("Invalid generation profile.")
        local_endpoint(profile.address)
        if profile.dialogue_context not in ("none", "source-window-v1"):
            raise ValueError("Unknown dialogue context policy.")
        policy = PolicyStore(self.repository)
        policy.rules(profile.glossary_version)
        policy.style(profile.style_version, "unknown")
        encoded = canonical(profile.to_dict())
        fingerprint = self.fingerprint(profile)
        if kind == "bulk" and not self.pilot_reviewed(profile, fingerprint):
            raise ValueError(
                "A bulk job cannot be created until the pilot report for this profile "
                "and source has been shown to the user."
            )
        identifier = uuid4().hex
        # Context reconstruction is read-only and may be expensive on a cold large
        # snapshot. Finish it before opening the short atomic queue transaction.
        if profile.dialogue_context != "none":
            units = DialogueContextStore(self.repository).order(list(units))
        self.repository.check_cancelled()
        with self.repository.transaction() as db:
            selected = []
            for unit in units:
                self.repository.check_cancelled()
                row = db.execute(
                    "SELECT u.source_revision,u.active,w.status,w.version,"
                    "w.translation_revision FROM text_units u JOIN work_items w USING(unit_id) "
                    "WHERE u.unit_id=?",
                    (unit,),
                ).fetchone()
                if row is None or not row["active"]:
                    raise ValueError("The selected source record is no longer active.")
                if row["status"] == "processing" or (
                    row["status"] == "approved" and not approved_candidates
                ):
                    continue
                if row["translation_revision"] is not None and not retranslate:
                    continue
                selected.append(
                    (unit, row["source_revision"], row["version"], int(row["status"] == "approved"))
                )
            if not selected:
                raise ValueError(
                    "The selection has no pending records to translate; approvals are preserved."
                )
            db.execute(
                "INSERT INTO jobs(id,kind,status,profile_json,source_fingerprint,"
                "created_at,updated_at) "
                "VALUES(?,?,'queued',?,?,?,?)",
                (identifier, kind, encoded, fingerprint, now(), now()),
            )
            if profile.dialogue_context != "none":
                contexts = DialogueContextStore(self.repository)
                contexts.bind(identifier)
            db.executemany(
                "INSERT INTO job_items(job_id,unit_id,source_revision,work_version,"
                "candidate_only,status) "
                "VALUES(?,?,?,?,?,'queued')",
                [(identifier, *row) for row in selected],
            )
            self.repository.check_cancelled()
        return identifier

    def pilot_reviewed(self, profile: GenerationProfile, fingerprint: str | None = None) -> bool:
        expected = replace(profile, glossary_version=None, style_version=None)
        return any(
            replace(GenerationProfile(**json.loads(row[0])),
                    glossary_version=None, style_version=None) == expected
            for row in self.repository.db.execute(
                "SELECT profile_json FROM jobs WHERE kind='pilot' "
                "AND status IN ('completed','completed_with_errors','cancelled') "
                "AND report_seen=1 AND source_fingerprint=?",
                (fingerprint or self.fingerprint(profile),),
            )
        )

    def create_review_job(
        self, records: list[dict[str, Any]], profile: GenerationProfile,
    ) -> str:
        """Queue an exact review page without resetting records or their attempt history."""
        if not 1 <= len(records) <= 200 or len({r["unit_id"] for r in records}) != len(records):
            raise ValueError("Select 1–200 distinct records from the current page.")
        with self.repository.transaction() as db:
            for record in records:
                current = db.execute(
                    "SELECT u.source_revision,u.active,w.version,w.translation_revision,w.status "
                    "FROM text_units u JOIN work_items w USING(unit_id) WHERE unit_id=?",
                    (record["unit_id"],),
                ).fetchone()
                if (
                    current is None or not current["active"] or current["status"] == "processing"
                    or type(record["version"]) is not int
                    or any(current[key] != record[key] for key in (
                        "source_revision", "version", "translation_revision",
                    ))
                    or db.execute("SELECT 1 FROM editor_drafts WHERE unit_id=?",
                                  (record["unit_id"],)).fetchone()
                ):
                    raise ValueError(
                        "Page records changed or have drafts. Refresh the page and try again."
                    )
            return self.create(
                [record["unit_id"] for record in records], profile, "bulk",
                retranslate=True, approved_candidates=True,
            )

    def reviewed_pilot(self) -> dict[str, Any] | None:
        fingerprints = {}
        rows = self.repository.db.execute(
            "SELECT * FROM jobs WHERE kind='pilot' AND report_seen=1 "
            "AND status IN ('completed','completed_with_errors','cancelled') "
            "ORDER BY created_at DESC,rowid DESC",
        )
        for row in rows:
            saved = GenerationProfile(**json.loads(row["profile_json"]))
            if saved.dialogue_context not in fingerprints:
                fingerprints[saved.dialogue_context] = self.fingerprint(saved)
            if row["source_fingerprint"] == fingerprints[saved.dialogue_context]:
                return dict(row)
        return None

    def bulk_readiness(self, profile: GenerationProfile) -> dict[str, Any]:
        if self.pilot_reviewed(profile):
            return {"allowed": True, "reason": None, "pilot_job_id": None,
                    "different_fields": []}
        pilot = self.reviewed_pilot()
        if pilot is not None:
            previous = GenerationProfile(**json.loads(pilot["profile_json"])).to_dict()
            current = profile.to_dict()
            return {
                "allowed": False, "reason": "profile_changed", "pilot_job_id": pilot["id"],
                "different_fields": sorted(key for key in previous.keys() | current.keys()
                                           if key not in ("glossary_version", "style_version")
                                           and previous.get(key) != current.get(key)),
            }
        seen = self.repository.db.execute(
            "SELECT 1 FROM jobs WHERE kind='pilot' AND report_seen=1 LIMIT 1"
        ).fetchone()
        return {"allowed": False, "reason": "source_changed" if seen else "review_needed",
                "pilot_job_id": None, "different_fields": []}

    def job(self, job_id: str) -> dict[str, Any]:
        row = self.repository.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Job not found.")
        return dict(row)

    def progress(self, job_id: str) -> dict[str, Any]:
        job = self.job(job_id)
        counts = dict(
            self.repository.db.execute(
                "SELECT status,count(*) FROM job_items WHERE job_id=? GROUP BY status", (job_id,)
            ).fetchall()
        )
        elapsed = self.repository.db.execute(
            "SELECT COALESCE(sum(elapsed_seconds),0) FROM translation_runs WHERE job_id=?",
            (job_id,),
        ).fetchone()[0]
        measured = self.repository.db.execute(
            "SELECT count(*),coalesce(sum(length(s.source_text)),0),coalesce(sum("
            "(SELECT sum(r.elapsed_seconds) FROM translation_runs r "
            "WHERE r.job_id=i.job_id AND r.unit_id=i.unit_id)),0) "
            "FROM job_items i JOIN source_revisions s ON s.id=i.source_revision "
            "WHERE i.job_id=? AND i.status IN ('completed','failed') AND EXISTS "
            "(SELECT 1 FROM translation_runs r WHERE r.job_id=i.job_id "
            "AND r.unit_id=i.unit_id AND r.elapsed_seconds>0)",
            (job_id,),
        ).fetchone()
        remaining = counts.get("queued", 0) + counts.get("processing", 0)
        remaining_chars = self.repository.db.execute(
            "SELECT coalesce(sum(length(s.source_text)),0) FROM job_items i "
            "JOIN source_revisions s ON s.id=i.source_revision WHERE i.job_id=? "
            "AND i.status IN ('queued','processing')",
            (job_id,),
        ).fetchone()[0]
        rate = measured[0] * 60 / measured[2] if measured[2] > 0 else None
        eta = (
            remaining_chars * measured[2] / measured[1]
            if remaining_chars and measured[1] and measured[2] > 0
            else None
        )
        return {
            "job_id": job_id,
            "status": job["status"],
            "pause_reason": self.pause_reason(job_id) if job["pause_requested"] else None,
            "counts": counts,
            "total": sum(counts.values()),
            "generation_seconds": round(elapsed, 3),
            "measured_records": measured[0],
            "records_per_minute": round(rate, 2) if rate is not None else None,
            "active_generation_eta_seconds": 0
            if remaining == 0
            else (round(eta, 1) if eta is not None else None),
            "eta_method": "completed-source-characters; generation time only; approximate",
        }

    def pause_reason(self, job_id: str) -> str | None:
        row = self.repository.db.execute(
            "SELECT value FROM project_settings WHERE key=?", ("pause_reason:" + job_id,)
        ).fetchone()
        return row[0] if row else None

    def pilot_review_blocker(self, job_id: str) -> str | None:
        """Allow reviewed interrupted results only after a full sample was attempted."""
        job = self.job(job_id)
        if job["kind"] != "pilot" or job["status"] not in (
            "completed", "completed_with_errors", "cancelled",
        ):
            return "unfinished"
        if job["source_fingerprint"] != self.fingerprint(
            GenerationProfile(**json.loads(job["profile_json"])),
        ):
            return "source_changed"
        count = self.repository.db.execute(
            "SELECT count(*) FROM job_items WHERE job_id=?", (job_id,)
        ).fetchone()[0]
        required = min(200, self.repository.count())
        if count < required:
            return "sample"
        if job["status"] == "cancelled":
            attempted, completed, active = self.repository.db.execute(
                "SELECT coalesce(sum(attempts>0 OR EXISTS(SELECT 1 FROM translation_runs r "
                "WHERE r.job_id=job_items.job_id AND r.unit_id=job_items.unit_id "
                "AND r.status NOT IN ('processing','cancelled','interrupted'))),0),"
                "coalesce(sum(status='completed'),0),"
                "coalesce(sum(status IN ('queued','processing')),0) "
                "FROM job_items WHERE job_id=?", (job_id,),
            ).fetchone()
            if attempted < required or completed == 0 or active:
                return "sample"
        return None

    def acknowledge_pilot(self, job_id: str) -> None:
        blocker = self.pilot_review_blocker(job_id)
        if blocker is not None:
            raise ValueError({
                "unfinished": "Review a completed pilot report first.",
                "source_changed": "The source changed; a new pilot evaluation is required.",
                "sample": "The pilot sample is insufficient; create a representative pilot.",
            }[blocker])
        with self.repository.transaction() as db:
            db.execute("UPDATE jobs SET report_seen=1,updated_at=? WHERE id=?", (now(), job_id))

    def bulk_units(self) -> list[str]:
        return [
            str(row[0])
            for row in self.repository.db.execute(
                "SELECT u.unit_id FROM text_units u JOIN work_items w USING(unit_id) "
                "WHERE u.active=1 "
                "AND w.status='pending' AND w.translation_revision IS NULL ORDER BY u.unit_id"
            )
        ]

    def start(self, job_id: str) -> GenerationProfile:
        job = self.job(job_id)
        if not DialogueContextStore(self.repository).current(job_id):
            raise ValueError("Dialogue context sources changed; prepare a new job and pilot.")
        if job["status"] not in ("queued", "paused") or job["cancel_requested"]:
            raise ValueError("This job cannot be started; check its status.")
        with self.repository.transaction() as db:
            if db.execute(
                "SELECT 1 FROM jobs WHERE id!=? AND status IN ('running','pausing')", (job_id,)
            ).fetchone():
                raise ValueError("Another model job is running.")
            db.execute(
                "UPDATE jobs SET status='running',pause_requested=0,updated_at=? WHERE id=?",
                (now(), job_id),
            )
            db.execute("DELETE FROM project_settings WHERE key=?", ("pause_reason:" + job_id,))
        return GenerationProfile(**json.loads(job["profile_json"]))

    def pause(self, job_id: str, reason: str = "user") -> None:
        with self.repository.transaction() as db:
            updated = db.execute(
                "UPDATE jobs SET pause_requested=1,status=CASE WHEN status IN "
                "('running','pausing') THEN 'pausing' ELSE 'paused' END,updated_at=? WHERE id=? "
                "AND status IN ('queued','running','pausing','paused')",
                (now(), job_id),
            )
            if updated.rowcount:
                # Keep the first reason of a pending pause; start() clears it on resume.
                db.execute(
                    "INSERT OR IGNORE INTO project_settings(key,value) VALUES(?,?)",
                    ("pause_reason:" + job_id, reason),
                )

    def cancel(self, job_id: str) -> None:
        with self.repository.transaction() as db:
            db.execute(
                "UPDATE jobs SET cancel_requested=1,status='cancelled',updated_at=? "
                "WHERE id=? AND status IN ('queued','running','pausing','paused')",
                (now(), job_id),
            )
            if not self.job(job_id)["cancel_requested"]:
                return
            rows = db.execute(
                "SELECT * FROM job_items WHERE job_id=? AND status='processing'", (job_id,)
            )
            for item in rows:
                db.execute(
                    "UPDATE work_items SET status='pending',version=version+1 "
                    "WHERE unit_id=? AND status='processing' AND version=?",
                    (item["unit_id"], item["work_version"]),
                )
            db.execute(
                "UPDATE job_items SET status='cancelled',claim_id=NULL "
                "WHERE job_id=? AND status IN ('queued','processing')",
                (job_id,),
            )

    def claim(self, job_id: str, avoid: frozenset[str] = frozenset()) -> dict[str, Any] | None:
        """Claim the next queued record; records in ``avoid`` go last, never skipped."""
        with self.repository.transaction() as db:
            if not DialogueContextStore(self.repository).current(job_id):
                self.pause(job_id, "context_sources_changed")
                return None
            job = self.job(job_id)
            if job["pause_requested"] or job["cancel_requested"]:
                return None
            query = (
                "SELECT j.*,u.active,u.source_revision AS current_source,w.version,"
                "w.status AS work_status,s.source_text,s.category,s.context "
                "FROM job_items j JOIN text_units u USING(unit_id) "
                "JOIN work_items w USING(unit_id) "
                "JOIN source_revisions s ON s.id=j.source_revision "
                "WHERE j.job_id=? AND j.status='queued' "
            )
            while True:
                # Both statements keep the job_pending index order (no full sort).
                item = db.execute(
                    query + "AND j.unit_id NOT IN (SELECT value FROM json_each(?)) "
                    "ORDER BY j.rowid LIMIT 1", (job_id, json.dumps(sorted(avoid))),
                ).fetchone() if avoid else None
                if item is None:
                    item = db.execute(
                        query + "ORDER BY j.rowid LIMIT 1", (job_id,)
                    ).fetchone()
                if item is None:
                    return None
                if (
                    not item["active"]
                    or item["current_source"] != item["source_revision"]
                    or (item["work_status"] == "approved" and not item["candidate_only"])
                    or item["attempts"] >= 3
                    or item["version"] != item["work_version"]
                ):
                    status = "failed" if item["attempts"] >= 3 else "skipped"
                    db.execute(
                        "UPDATE job_items SET status=?,error_code='stale_or_exhausted' "
                        "WHERE job_id=? AND unit_id=?",
                        (status, job_id, item["unit_id"]),
                    )
                    continue
                if item["work_status"] == "processing":
                    raise ValueError("The record is being processed by another job.")
                claim = uuid4().hex
                version = item["version"] if item["candidate_only"] else item["version"] + 1
                if not item["candidate_only"]:
                    db.execute(
                        "UPDATE work_items SET status='processing',version=? WHERE unit_id=?",
                        (version, item["unit_id"]),
                    )
                db.execute(
                    "UPDATE job_items SET status='processing',work_version=?,claim_id=? "
                    "WHERE job_id=? AND unit_id=?",
                    (version, claim, job_id, item["unit_id"]),
                )
                return {**dict(item), "claim_id": claim, "work_version": version}

    def attempt(self, item: dict[str, Any], metadata: dict[str, Any]) -> str:
        identifier = uuid4().hex
        with self.repository.transaction() as db:
            updated = db.execute(
                "UPDATE job_items SET attempts=attempts+1 WHERE job_id=? "
                "AND unit_id=? AND claim_id=? AND status='processing' AND attempts<3",
                (item["job_id"], item["unit_id"], item["claim_id"]),
            )
            if updated.rowcount != 1:
                raise ValueError("The job claim is invalid or the attempt budget is exhausted.")
            # Run numbers follow history, not the refundable budget, so they never repeat.
            count = db.execute(
                "SELECT COALESCE(MAX(attempt),0)+1 FROM translation_runs "
                "WHERE job_id=? AND unit_id=?",
                (item["job_id"], item["unit_id"]),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO translation_runs(id,job_id,unit_id,source_revision,attempt,"
                "metadata_json,status,created_at) VALUES(?,?,?,?,?,?,'processing',?)",
                (
                    identifier,
                    item["job_id"],
                    item["unit_id"],
                    item["source_revision"],
                    count,
                    canonical(metadata),
                    now(),
                ),
            )
        return identifier

    def record_attempt(
        self, run_id: str, status: str, elapsed: float, metadata: dict[str, Any]
    ) -> None:
        with self.repository.transaction() as db:
            db.execute(
                "UPDATE translation_runs SET status=?,elapsed_seconds=?,metadata_json=? WHERE id=?",
                (status, elapsed, canonical(metadata), run_id),
            )

    def finish(self, item: dict[str, Any], result: dict[str, Any], run_id: str) -> bool:
        with self.repository.transaction() as db:
            if not DialogueContextStore(self.repository).current(item["job_id"]):
                self.fail(item, "context_sources_changed")
                self.pause(item["job_id"], "context_sources_changed")
                return False
            valid = db.execute(
                "SELECT 1 FROM job_items j JOIN jobs b ON b.id=j.job_id "
                "WHERE j.job_id=? AND j.unit_id=? AND j.claim_id=? "
                "AND j.status='processing' AND b.cancel_requested=0",
                (item["job_id"], item["unit_id"], item["claim_id"]),
            ).fetchone()
            if valid is None:
                return False
            metadata = {
                key: value for key, value in result.items() if key not in ("source", "translation")
            }
            metadata["run_id"] = run_id
            from unitytranslator.validation import REVIEW_CHECKS_VERSION

            metadata["review_checks_version"] = REVIEW_CHECKS_VERSION
            metadata["protected_format_version"] = self.repository.format_rules(item["unit_id"])
            accepted = self.repository.candidate(
                item["unit_id"],
                item["source_revision"],
                item["work_version"],
                result["translation"],
                "model",
                metadata,
                result.get("issues", []),
            )
            candidate_revision = None
            if item["candidate_only"]:
                current = db.execute(
                    "SELECT u.source_revision,u.active,w.version,w.status "
                    "FROM text_units u JOIN work_items w USING(unit_id) WHERE u.unit_id=?",
                    (item["unit_id"],),
                ).fetchone()
                candidate_id, _ = self.repository.candidate_identity(
                    item["unit_id"], item["source_revision"], result["translation"], "model",
                    metadata,
                )
                candidate = db.execute(
                    "SELECT id FROM translation_revisions WHERE id=?", (candidate_id,)
                ).fetchone()
                from unitytranslator.validation import format_issues

                accepted = bool(
                    current
                    and candidate
                    and current["active"]
                    and current["source_revision"] == item["source_revision"]
                    and current["version"] == item["work_version"]
                    and current["status"] == "approved"
                    and not format_issues(
                        item["source_text"],
                        result["translation"],
                        rules=self.repository.format_rules(item["unit_id"]),
                    )
                )
                if accepted:
                    candidate_revision = candidate[0]
            revision = candidate_revision or (
                db.execute(
                    "SELECT translation_revision FROM work_items WHERE unit_id=?",
                    (item["unit_id"],),
                ).fetchone()[0]
                if accepted
                else None
            )
            db.execute(
                "UPDATE job_items SET status=?,claim_id=NULL,error_code=?,result_revision=? "
                "WHERE job_id=? AND unit_id=?",
                (
                    "completed" if accepted else "skipped",
                    None if accepted else "stale_result",
                    revision,
                    item["job_id"],
                    item["unit_id"],
                ),
            )
            return accepted

    def fail(self, item: dict[str, Any], code: str, retry: bool = False) -> None:
        with self.repository.transaction() as db:
            updated = db.execute(
                "UPDATE job_items SET status=?,claim_id=NULL,error_code=? "
                "WHERE job_id=? AND unit_id=? AND claim_id=? AND status='processing'",
                (
                    "queued" if retry else "failed",
                    code,
                    item["job_id"],
                    item["unit_id"],
                    item["claim_id"],
                ),
            )
            if updated.rowcount:
                status = (
                    "pending"
                    if retry or code in OUTAGE_CODES
                    else "needs_review"
                    if code == "context"
                    else "validation_error"
                )
                work = db.execute(
                    "UPDATE work_items SET status=?,version=version+1 WHERE unit_id=? "
                    "AND version=? AND status='processing'",
                    (status, item["unit_id"], item["work_version"]),
                )
                if work.rowcount and retry:
                    db.execute(
                        "UPDATE job_items SET work_version=work_version+1 "
                        "WHERE job_id=? AND unit_id=?",
                        (item["job_id"], item["unit_id"]),
                    )

    def consecutive_outages(self, job_id: str, unit_id: str) -> int:
        """Count this record's latest outage runs, across pause/resume cycles."""
        count = 0
        for (status,) in self.repository.db.execute(
            "SELECT status FROM translation_runs WHERE job_id=? AND unit_id=? "
            "ORDER BY attempt DESC", (job_id, unit_id),
        ):
            if status in ("processing", "cancelled", "interrupted"):
                continue
            if status not in OUTAGE_CODES:
                break
            count += 1
        return count

    def refund_attempt(self, item: dict[str, Any]) -> None:
        """Return an outage attempt to the record's budget; its run history stays."""
        with self.repository.transaction() as db:
            db.execute(
                "UPDATE job_items SET attempts=attempts-1 WHERE job_id=? AND unit_id=? "
                "AND claim_id=? AND status='processing' AND attempts>0",
                (item["job_id"], item["unit_id"], item["claim_id"]),
            )

    def interrupt(self, job_id: str, reason: str = "shutdown") -> None:
        """Pause a job whose run stopped without an explicit cancel; requeue its claims.

        Records whose latest request was cut off get that attempt back. Records waiting
        in backoff keep their already recorded failure. Nothing resumes automatically.
        """
        with self.repository.transaction() as db:
            if not self.job(job_id)["pause_requested"]:
                self.pause(job_id, reason)
            rows = db.execute(
                "SELECT * FROM job_items WHERE job_id=? AND status='processing'", (job_id,)
            ).fetchall()
            for item in rows:
                latest = db.execute(
                    "SELECT status FROM translation_runs WHERE job_id=? AND unit_id=? "
                    "ORDER BY attempt DESC LIMIT 1",
                    (job_id, item["unit_id"]),
                ).fetchone()
                refund = int(latest is not None and latest[0] == "cancelled")
                work = db.execute(
                    "UPDATE work_items SET status='pending',version=version+1 "
                    "WHERE unit_id=? AND status='processing' AND version=?",
                    (item["unit_id"], item["work_version"]),
                )
                db.execute(
                    "UPDATE job_items SET status='queued',claim_id=NULL,"
                    "attempts=MAX(attempts-?,0),work_version=work_version+? "
                    "WHERE job_id=? AND unit_id=?",
                    (refund, int(work.rowcount == 1), job_id, item["unit_id"]),
                )

    def settle(self, job_id: str) -> dict[str, Any]:
        progress = self.progress(job_id)
        job = self.job(job_id)
        if job["cancel_requested"]:
            status = "cancelled"
        elif job["pause_requested"]:
            status = "paused"
        elif progress["counts"].get("queued", 0) or progress["counts"].get("processing", 0):
            status = "running"
        else:
            status = "completed_with_errors" if progress["counts"].get("failed", 0) else "completed"
        with self.repository.transaction() as db:
            db.execute("UPDATE jobs SET status=?,updated_at=? WHERE id=?", (status, now(), job_id))
        return self.progress(job_id)


class TranslationJobService:
    def __init__(
        self,
        repository: ProjectRepository,
        provider_factory: Callable[[GenerationProfile], Any] | None = None,
    ):
        self.repository = repository
        self.store = JobStore(repository)
        self.provider_factory = provider_factory
        self.task: asyncio.Task[Any] | None = None
        self.active_job: str | None = None

    def pause(self) -> None:
        if self.active_job is not None:
            self.store.pause(self.active_job)

    def cancel(self) -> None:
        if self.active_job is not None:
            self.store.cancel(self.active_job)
            if self.task is not None:
                self.task.cancel()

    def suspend(self, reason: str = "shutdown") -> None:
        """Stop the running job for close/project switch; it stays paused, not cancelled."""
        if self.active_job is not None:
            if not self.store.job(self.active_job)["pause_requested"]:
                self.store.pause(self.active_job, reason)
            if self.task is not None:
                self.task.cancel()

    async def run(
        self,
        job_id: str,
        progress: Callable[[dict[str, Any]], None] | None = None,
        *,
        parallel_requests: int = 1,
    ) -> dict[str, Any]:
        if (
            type(parallel_requests) is not int
            or not 1 <= parallel_requests <= MAX_PARALLEL_REQUESTS
        ):
            raise Diagnostic(
                "Parallel requests must be between 1 and {p0}.", p0=MAX_PARALLEL_REQUESTS
            )
        if self.active_job is not None:
            raise ValueError("A translation job is already running.")
        profile = self.store.start(job_id)
        self.active_job = job_id
        self.task = asyncio.current_task()
        provider = (
            self.provider_factory(profile)
            if self.provider_factory
            else LocalProvider(
                profile.provider, profile.address, structured_output=profile.structured_output
            )
        )
        policy = PolicyStore(self.repository)
        cached_rules: tuple[str | None, list[GlossaryRule]] | None = None
        last_event = 0.0
        outage_streak = 0
        outage_units: set[str] = set()

        async def worker() -> None:
            nonlocal last_event, cached_rules, outage_streak
            while True:
                # Capture saved policies once per attempt, before the HTTP await.
                effective = replace(
                    profile,
                    glossary_version=policy.active_version("glossary"),
                    style_version=policy.active_version("style"),
                )
                if cached_rules is None or cached_rules[0] != effective.glossary_version:
                    cached_rules = (
                        effective.glossary_version, policy.rules(effective.glossary_version),
                    )
                # Records in a current outage go last, so a single failing record cannot
                # starve the others or masquerade as a server-wide outage.
                item = self.store.claim(job_id, frozenset(outage_units))
                if item is None:
                    break
                relevant = [
                    rule
                    for rule in cached_rules[1]
                    if rule.matches(
                        item["source_text"],
                        item["category"],
                        language=self.repository.source_language,
                    )
                ]
                metadata = {
                    "profile": effective.to_dict(),
                    "parallel_requests": parallel_requests,
                    "glossary_rules": [r.model_dump() for r in relevant],
                }
                run_id = self.store.attempt(item, metadata)
                started = perf_counter()
                try:
                    dialogue = (
                        DialogueContextStore(self.repository).window(
                            job_id, item["unit_id"], item["source_text"],
                        ) if profile.dialogue_context != "none" else None
                    )
                    if dialogue is not None:
                        metadata["dialogue_context"] = {
                            "digest": sha256(canonical(dialogue).encode()).hexdigest(),
                            **{key: value for key, value in dialogue.items()
                               if key != "references"},
                            "reference_ids": [r["unit_id"] for r in dialogue["references"]],
                        }
                    options: dict[str, Any] = {}
                    if dialogue is not None:
                        options["dialogue_context"] = dialogue
                    if profile.reasoning_effort != "default":
                        options["reasoning_effort"] = profile.reasoning_effort
                    rules = self.repository.format_rules(item["unit_id"])
                    if rules != "protected-i2-v4":
                        options["format_rules"] = rules
                    result = await provider.translate_record(
                        profile.model,
                        item["source_text"],
                        run_id[:12],
                        self.repository.source_language,
                        self.repository.target_language,
                        context_tokens=profile.context_tokens,
                        output_tokens=profile.output_tokens,
                        temperature=profile.temperature,
                        context=item["context"],
                        style=policy.style(effective.style_version, item["category"]),
                        glossary=[r.model_dump() for r in relevant],
                        prompt_version=profile.prompt_version,
                        **options,
                    )
                    result["glossary_version"] = effective.glossary_version
                    result["style_version"] = effective.style_version
                    for rule in relevant:
                        if not rule.matches(
                            result["translation"],
                            item["category"],
                            target=True,
                            language=self.repository.target_language,
                        ):
                            result.setdefault("issues", []).append(
                                "glossary_violation:" + rule.source
                            )
                    accepted = self.store.finish(item, result, run_id)
                    outage_streak = 0
                    outage_units.clear()
                    self.store.record_attempt(
                        run_id,
                        "accepted" if accepted else "stale",
                        perf_counter() - started,
                        {
                            **metadata,
                            "result": {
                                k: v
                                for k, v in result.items()
                                if k not in ("source", "translation")
                            },
                        },
                    )
                except OperationCancelled:
                    self.store.record_attempt(
                        run_id, "cancelled", perf_counter() - started, metadata,
                    )
                    raise asyncio.CancelledError() from None
                except (ProviderError, ValueError) as exc:
                    code = exc.code if isinstance(exc, ProviderError) else "unsupported_format"
                    failure_metadata = dict(metadata)
                    if isinstance(exc, ProviderError) and exc.diagnostics:
                        failure_metadata["error_diagnostics"] = exc.diagnostics
                    self.store.record_attempt(
                        run_id, code, perf_counter() - started, failure_metadata
                    )
                    if code in OUTAGE_CODES:
                        self.store.refund_attempt(item)
                        outage_streak += 1
                        outage_units.add(item["unit_id"])
                        failures = self.store.consecutive_outages(job_id, item["unit_id"])
                        if failures >= MAX_RECORD_OUTAGES:
                            # One record that alone keeps failing is failed (left Pending
                            # for a later job) instead of pausing the job on every resume.
                            outage_units.discard(item["unit_id"])
                            self.store.fail(item, code, False)
                        elif (
                            outage_streak >= OUTAGE_PAUSE_STREAK + parallel_requests - 1
                            and len(outage_units) > 1
                        ):
                            # A server-wide outage spans several records and outlasts
                            # the first concurrent wave of failures.
                            self.store.fail(item, code, True)
                            self.store.pause(job_id, code)
                        else:
                            # Keep the claim while waiting so no other worker retries at once.
                            await asyncio.sleep(retry_delay(failures, 2.0))
                            self.store.fail(item, code, True)
                    else:
                        outage_streak = 0
                        outage_units.clear()
                        retry = code in RETRY_CODES and item["attempts"] + 1 < MAX_ATTEMPTS
                        if retry:
                            await asyncio.sleep(retry_delay(item["attempts"] + 1, 0.5))
                        self.store.fail(item, code, retry)
                        if code in PAUSE_CODES or (code == "timeout" and not retry):
                            self.store.pause(job_id, code)
                except asyncio.CancelledError:
                    self.store.record_attempt(
                        run_id, "cancelled", perf_counter() - started, metadata
                    )
                    raise
                current = perf_counter()
                if progress is not None and current - last_event >= 0.2:
                    progress(self.store.progress(job_id))
                    last_event = current
                await asyncio.sleep(0)

        try:
            workers = [asyncio.create_task(worker()) for _ in range(parallel_requests)]
            try:
                await asyncio.gather(*workers)
            except BaseException:
                for task in workers:
                    task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                raise
            return self.store.settle(job_id)
        except (asyncio.CancelledError, OperationCancelled):
            # Only an explicit cancel cancels; closing, switching projects or a cooperative
            # shutdown leaves the job paused with its queue intact for an explicit resume.
            if self.store.job(job_id)["cancel_requested"]:
                self.store.cancel(job_id)
            else:
                self.store.interrupt(job_id)
            return self.store.settle(job_id)
        finally:
            self.active_job = None
            self.task = None
