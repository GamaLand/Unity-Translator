"""Durable claim/retry queue; HTTP requests never hold a SQLite transaction open."""

import asyncio
import json
from collections.abc import Callable, Sequence
from hashlib import sha256
from time import perf_counter
from typing import Any
from uuid import uuid4

from unitytranslator.domain import GenerationProfile
from unitytranslator.policy import PolicyStore
from unitytranslator.providers import LocalProvider, ProviderError, local_endpoint
from unitytranslator.repository import ProjectRepository, canonical, now


class JobStore:
    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    def fingerprint(self) -> str:
        digest = sha256()
        for row in self.repository.db.execute(
            "SELECT unit_id,source_revision FROM text_units WHERE active=1 ORDER BY unit_id"
        ):
            digest.update(canonical(list(row)).encode("utf-8"))
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
            raise ValueError("İş türü/kayıt seçimi geçersiz.")
        if (kind == "prototype" and len(units) > 10) or (kind == "pilot" and len(units) > 200):
            raise ValueError("Prototip/pilot kayıt sınırı aşıldı.")
        if profile.provider not in ("lm-studio", "llama-cpp") or not profile.model.strip():
            raise ValueError("Sağlayıcı/model seçimi gerekli.")
        if profile.reasoning_effort not in ("default", "none") or (
            profile.reasoning_effort == "none" and profile.provider != "lm-studio"
        ):
            raise ValueError("This reasoning option is available only for LM Studio requests.")
        if (
            not 512 <= profile.context_tokens <= 1_048_576
            or not 128 <= profile.output_tokens <= 8192
        ):
            raise ValueError("Bağlam/çıkış token sınırı geçersiz.")
        if not 0 <= profile.temperature <= 2 or profile.prompt_version != "translate-v1":
            raise ValueError("Üretim profili geçersiz.")
        local_endpoint(profile.address)
        policy = PolicyStore(self.repository)
        policy.rules(profile.glossary_version)
        policy.style(profile.style_version, "unknown")
        encoded = canonical(profile.to_dict())
        fingerprint = self.fingerprint()
        if kind == "bulk" and not self.pilot_reviewed(profile, fingerprint):
            raise ValueError(
                "Bu profil/kaynak için pilot raporu kullanıcıya gösterilmeden toplu iş açılamaz."
            )
        identifier = uuid4().hex
        with self.repository.transaction() as db:
            selected = []
            for unit in units:
                row = db.execute(
                    "SELECT u.source_revision,u.active,w.status,w.version,"
                    "w.translation_revision FROM text_units u JOIN work_items w USING(unit_id) "
                    "WHERE u.unit_id=?",
                    (unit,),
                ).fetchone()
                if row is None or not row["active"]:
                    raise ValueError("Seçilen kaynak kayıt artık etkin değil.")
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
                raise ValueError("Seçimde çevrilecek bekleyen kayıt yok; onaylar korunuyor.")
            db.execute(
                "INSERT INTO jobs(id,kind,status,profile_json,source_fingerprint,"
                "created_at,updated_at) "
                "VALUES(?,?,'queued',?,?,?,?)",
                (identifier, kind, encoded, fingerprint, now(), now()),
            )
            db.executemany(
                "INSERT INTO job_items(job_id,unit_id,source_revision,work_version,"
                "candidate_only,status) "
                "VALUES(?,?,?,?,?,'queued')",
                [(identifier, *row) for row in selected],
            )
        return identifier

    def pilot_reviewed(self, profile: GenerationProfile, fingerprint: str | None = None) -> bool:
        return (
            self.repository.db.execute(
                "SELECT 1 FROM jobs WHERE kind='pilot' "
                "AND status IN ('completed','completed_with_errors','cancelled') "
                "AND report_seen=1 AND profile_json=? AND source_fingerprint=?",
                (canonical(profile.to_dict()), fingerprint or self.fingerprint()),
            ).fetchone()
            is not None
        )

    def reviewed_pilot(self) -> dict[str, Any] | None:
        row = self.repository.db.execute(
            "SELECT * FROM jobs WHERE kind='pilot' AND report_seen=1 "
            "AND status IN ('completed','completed_with_errors','cancelled') "
            "AND source_fingerprint=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
            (self.fingerprint(),),
        ).fetchone()
        return dict(row) if row is not None else None

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
                                           if previous.get(key) != current.get(key)),
            }
        seen = self.repository.db.execute(
            "SELECT 1 FROM jobs WHERE kind='pilot' AND report_seen=1 LIMIT 1"
        ).fetchone()
        return {"allowed": False, "reason": "source_changed" if seen else "review_needed",
                "pilot_job_id": None, "different_fields": []}

    def job(self, job_id: str) -> dict[str, Any]:
        row = self.repository.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("İş bulunamadı.")
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
        if job["source_fingerprint"] != self.fingerprint():
            return "source_changed"
        count = self.repository.db.execute(
            "SELECT count(*) FROM job_items WHERE job_id=?", (job_id,)
        ).fetchone()[0]
        required = min(200, self.repository.count())
        if count < required:
            return "sample"
        if job["status"] == "cancelled":
            attempted, completed, active = self.repository.db.execute(
                "SELECT coalesce(sum(attempts>0),0),coalesce(sum(status='completed'),0),"
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
                "unfinished": "Önce tamamlanmış pilot raporunu inceleyin.",
                "source_changed": "Kaynak değişti; yeni bir pilot değerlendirmesi gerekli.",
                "sample": "Pilot örneklemi yetersiz; temsilî pilot oluşturun.",
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
        if job["status"] not in ("queued", "paused") or job["cancel_requested"]:
            raise ValueError("Bu iş başlatılamaz; durumunu kontrol edin.")
        with self.repository.transaction() as db:
            if db.execute(
                "SELECT 1 FROM jobs WHERE id!=? AND status IN ('running','pausing')", (job_id,)
            ).fetchone():
                raise ValueError("Başka bir model işi sürüyor.")
            db.execute(
                "UPDATE jobs SET status='running',pause_requested=0,updated_at=? WHERE id=?",
                (now(), job_id),
            )
            db.execute("DELETE FROM project_settings WHERE key=?", ("pause_reason:" + job_id,))
        return GenerationProfile(**json.loads(job["profile_json"]))

    def pause(self, job_id: str, reason: str = "user") -> None:
        with self.repository.transaction() as db:
            updated = db.execute(
                "UPDATE jobs SET pause_requested=1,status=CASE WHEN status='running' "
                "THEN 'pausing' ELSE 'paused' END,updated_at=? WHERE id=? "
                "AND status IN ('queued','running','pausing','paused')",
                (now(), job_id),
            )
            if updated.rowcount:
                db.execute(
                    "INSERT OR REPLACE INTO project_settings(key,value) VALUES(?,?)",
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

    def claim(self, job_id: str) -> dict[str, Any] | None:
        with self.repository.transaction() as db:
            job = self.job(job_id)
            if job["pause_requested"] or job["cancel_requested"]:
                return None
            while True:
                item = db.execute(
                    "SELECT j.*,u.active,u.source_revision AS current_source,w.version,"
                    "w.status AS work_status,s.source_text,s.category,s.context "
                    "FROM job_items j JOIN text_units u USING(unit_id) "
                    "JOIN work_items w USING(unit_id) "
                    "JOIN source_revisions s ON s.id=j.source_revision "
                    "WHERE j.job_id=? AND j.status='queued' ORDER BY j.rowid LIMIT 1",
                    (job_id,),
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
                    raise ValueError("Kayıt başka bir iş tarafından işleniyor.")
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
                raise ValueError("İş claim'i geçersiz veya deneme bütçesi tükendi.")
            count = db.execute(
                "SELECT attempts FROM job_items WHERE job_id=? AND unit_id=?",
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
                candidate = db.execute(
                    "SELECT id FROM translation_revisions WHERE source_revision=? "
                    "AND metadata_json=? AND text=? AND origin='model'",
                    (item["source_revision"], canonical(metadata), result["translation"]),
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
                    if retry
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

    async def run(
        self,
        job_id: str,
        progress: Callable[[dict[str, Any]], None] | None = None,
        *,
        parallel_requests: int = 1,
    ) -> dict[str, Any]:
        if type(parallel_requests) is not int or not 1 <= parallel_requests <= 16:
            raise ValueError("Paralel istek sayısı 1–16 arasında olmalı.")
        if self.active_job is not None:
            raise ValueError("Bir model işi zaten çalışıyor.")
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
        rules = policy.rules(profile.glossary_version)
        last_event = 0.0

        async def worker() -> None:
            nonlocal last_event
            while item := self.store.claim(job_id):
                relevant = [
                    rule
                    for rule in rules
                    if rule.matches(
                        item["source_text"],
                        item["category"],
                        language=self.repository.source_language,
                    )
                ]
                metadata = {
                    "profile": profile.to_dict(),
                    "parallel_requests": parallel_requests,
                    "glossary_rules": [r.model_dump() for r in relevant],
                }
                run_id = self.store.attempt(item, metadata)
                started = perf_counter()
                try:
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
                        style=policy.style(profile.style_version, item["category"]),
                        glossary=[r.model_dump() for r in relevant],
                        prompt_version=profile.prompt_version,
                        **(
                            {"reasoning_effort": profile.reasoning_effort}
                            if profile.reasoning_effort != "default"
                            else {}
                        ),
                        **(
                            {"format_rules": self.repository.format_rules(item["unit_id"])}
                            if self.repository.format_rules(item["unit_id"]) != "protected-i2-v4"
                            else {}
                        ),
                    )
                    result["glossary_version"] = profile.glossary_version
                    result["style_version"] = profile.style_version
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
                except (ProviderError, ValueError) as exc:
                    code = exc.code if isinstance(exc, ProviderError) else "unsupported_format"
                    failure_metadata = dict(metadata)
                    if isinstance(exc, ProviderError) and exc.diagnostics:
                        failure_metadata["error_diagnostics"] = exc.diagnostics
                    self.store.record_attempt(
                        run_id, code, perf_counter() - started, failure_metadata
                    )
                    retry = (
                        code
                        in (
                            "timeout",
                            "connection",
                            "invalid_response",
                            "validation_error",
                            "response_schema_error",
                            "protected_content_error",
                            "output_truncated",
                            "unexpected_tool_call",
                        )
                        and item["attempts"] + 1 < 3
                    )
                    self.store.fail(item, code, retry)
                    if code in (
                        "out_of_memory",
                        "not_found",
                        "unauthorized",
                        "unsupported_option",
                    ) or (code in ("connection", "timeout") and not retry):
                        self.store.pause(job_id, code)
                    elif retry:
                        await asyncio.sleep(0.5 * (item["attempts"] + 1))
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
        except asyncio.CancelledError:
            self.store.cancel(job_id)
            return self.store.settle(job_id)
        finally:
            self.active_job = None
            self.task = None
