"""Project session shared by the UI and CLI; business rules stay outside widgets."""

import asyncio
import json
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.discovery import probe_source, save_report, scan, validate_source_selection
from unitytranslator.domain import GenerationProfile, OperationCancelled
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.game_process import inspect_game_processes
from unitytranslator.installation import InstallationSession
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.pilot import select_pilot
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.portable import PortableService
from unitytranslator.providers import LocalProvider, local_endpoint
from unitytranslator.reader_adapters import deployment_adapter_for, result_from_report
from unitytranslator.reports import job_report, save_current_quality_audit, save_job_report
from unitytranslator.repository import ProjectRepository, now
from unitytranslator.review_selection import (
    all_approval_preview,
    apply_matching_review,
    approve_all,
    approve_selection,
    matching_review_preview,
)
from unitytranslator.runtime_export import export_selected_runtime
from unitytranslator.shareable import export_shareable_patch, supports_shareable_patch


class ApplicationSession:
    def __init__(self, progress: Callable[[dict[str, Any]], None] | None = None):
        self.repository: ProjectRepository | None = None
        self.jobs: TranslationJobService | None = None
        self.progress = progress
        self.extracting = False
        self.extraction_cancelled = threading.Event()
        self.extraction_task: asyncio.Task[Any] | None = None
        self.preparing = threading.Event()
        self.preparation_cancelled = threading.Event()
        self.shutdown_requested = threading.Event()
        self.installation: InstallationSession | None = None
        self.all_approval: dict[str, Any] | None = None
        self.matching_review: dict[str, Any] | None = None

    @property
    def repo(self) -> ProjectRepository:
        if self.repository is None:
            raise ValueError("Önce bir proje açın.")
        return self.repository

    async def close(self) -> None:
        self.extraction_cancelled.set()
        if self.extraction_task is not None and self.extraction_task != asyncio.current_task():
            await asyncio.gather(self.extraction_task, return_exceptions=True)
        if self.jobs is not None and self.jobs.active_job is not None:
            task = self.jobs.task
            self.jobs.cancel()
            if task is not None and task != asyncio.current_task():
                await asyncio.gather(task, return_exceptions=True)
        if self.repository is not None:
            self.repository.close()
            self.repository = None
        self.jobs = None
        self.installation = None
        self.all_approval = None
        self.matching_review = None

    def operation_cancelled(self) -> bool:
        return self.shutdown_requested.is_set() or self.preparation_cancelled.is_set()

    def request_preparation_cancel(self) -> bool:
        """Called by the UI thread without waiting behind synchronous preparation."""
        if not self.preparing.is_set():
            return False
        self.preparation_cancelled.set()
        return True

    def reserve_preparation(self) -> None:
        """Reserve before queuing so an immediate UI cancellation cannot hit an old job."""
        self.preparation_cancelled.clear()
        self.preparing.set()

    def request_shutdown(self) -> None:
        """Only thread-safe events here; SQLite remains on the backend thread."""
        self.shutdown_requested.set()
        self.preparation_cancelled.set()
        self.extraction_cancelled.set()

    def prepare_job(self, command: str, data: dict[str, Any]) -> dict[str, Any]:
        repo = self.repo
        if not self.preparing.is_set():
            self.reserve_preparation()
        repo.db.set_progress_handler(lambda: int(self.operation_cancelled()), 10000)
        try:
            if self.extracting or self.jobs is None or self.jobs.active_job is not None:
                raise ValueError("Çıkarma bitmeden çeviri başlatılamaz.")
            repo.check_cancelled()
            policy = PolicyStore(repo)
            profile = GenerationProfile(
                **data["profile"],
                glossary_version=policy.active_version("glossary"),
                style_version=policy.active_version("style"),
            )
            if self.progress:
                self.progress({"kind": "preparation", "stage": "sample"})
            if command == "create_page_job":
                if data.get("project_id") != repo.project_id:
                    raise ValueError("The page selection belongs to a different project.")
                identifier = JobStore(repo).create_review_job(data["records"], profile)
                return {"job_id": identifier, "count": len(data["records"]),
                        "profile": profile.to_dict()}
            if command == "create_affected_job":
                data = {
                    **data, "kind": "prototype", "retranslate": True,
                    "approved_candidates": True,
                    "units": [row["unit_id"] for row in policy.impacted()][:10],
                }
            units = (
                select_pilot(repo) if data["kind"] == "pilot"
                else JobStore(repo).bulk_units() if data["kind"] == "bulk"
                else data["units"]
            )
            if not units and data["kind"] in ("prototype", "pilot", "bulk"):
                return {"job_id": None, "count": 0, "reason": "no_eligible_records"}
            if self.progress:
                self.progress({"kind": "preparation", "stage": "context"})
            identifier = JobStore(repo).create(
                units, profile, data["kind"], retranslate=data.get("retranslate", False),
                approved_candidates=data.get("approved_candidates", False),
            )
            return {"job_id": identifier, "count": len(units), "profile": profile.to_dict()}
        except (OperationCancelled, sqlite3.OperationalError):
            if not self.operation_cancelled():
                raise
            return {"job_id": None, "count": 0, "reason": "preparation_cancelled"}
        finally:
            repo.db.set_progress_handler(None, 0)
            self.preparing.clear()
            self.preparation_cancelled.clear()

    async def dispatch(self, command: str, data: dict[str, Any]) -> Any:
        if self.shutdown_requested.is_set():
            raise OperationCancelled("The application is closing.")
        if command == "cancel_preparation":
            return True
        if command == "cancel_extract":
            self.extraction_cancelled.set()
            return {"cancel_requested": True}
        if command == "open":
            if self.extracting:
                raise ValueError("Çıkarma sürüyor; bitmesini bekleyin.")
            paths = (
                ProjectRepository.existing_paths(Path(data["project"]))
                if data.get("existing_only") is True
                else ProjectPaths(Path(data["game"]), Path(data["project"]))
            )
            if self.repository is None or self.repository.paths.project != paths.project:
                # Keep the current session and drafts if opening a replacement project fails.
                replacement = ProjectRepository(
                    paths, data.get("source_language", "en"), data.get("target_language", "tr")
                )
                try:
                    await self.close()
                except BaseException:
                    replacement.close()
                    raise
                self.repository = replacement
                self.preparation_cancelled.clear()
                self.repository.operation_cancelled = self.operation_cancelled
                self.jobs = TranslationJobService(self.repository)
            elif self.repository.paths.game != paths.game:
                raise ValueError("Projenin bağlı olduğu oyun klasörü eşleşmiyor.")
            if self.installation is None:
                self.installation = InstallationSession(self.repo)
            latest = self.repo.db.execute(
                "SELECT profile_json FROM jobs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return {
                **self.repo.manifest(),
                "game_path": str(self.repo.paths.game),
                "project_path": str(self.repo.paths.project),
                "last_profile": json.loads(latest[0]) if latest else None,
            }
        if command.startswith("deployment_"):
            if data.get("project_id") != self.repo.project_id or self.installation is None:
                raise ValueError("Kurulum isteğinin proje kimliği eşleşmiyor.")
            if command != "deployment_status" and (
                self.extracting or (self.jobs and self.jobs.active_job)
            ):
                raise ValueError(
                    "Kurulum/kaldırma için çıkarma veya çeviri işinin bitmesini bekleyin."
                )
            if command == "deployment_status":
                deployment_result = deployment_adapter_for(self.installation).probe()
            elif command == "deployment_prepare":

                def progress(message: str) -> None:
                    if self.progress:
                        self.progress(
                            {
                                "kind": "deployment",
                                "project_id": self.repo.project_id,
                                "message": message,
                            }
                        )

                deployment_result = deployment_adapter_for(self.installation).prepare(
                    log_file=data.get("log_file", ""),
                    log_reviewed=data.get("log_reviewed", False),
                    progress=progress,
                )
            elif command == "deployment_install":
                deployment_result = self.installation.install(
                    data["review_id"],
                    user_action=data.get("user_action", False),
                    experimental_reviewed=data.get("experimental_reviewed", False),
                )
            elif command == "deployment_remove":
                deployment_result = self.installation.remove(
                    data["plan_id"], user_action=data.get("user_action", False)
                )
            else:
                raise ValueError("Bilinmeyen kurulum işlemi.")
            return {
                **deployment_result,
                "project_id": self.repo.project_id,
                "request_token": data.get("request_token"),
            }
        if command == "backup":
            folder = "backups/manual-" + uuid4().hex
            destination = self.repo.paths.output(folder + "/project.sqlite3")
            destination.parent.mkdir(parents=True)
            try:
                with sqlite3.connect(destination) as backup:
                    self.repo.db.backup(backup)
                    if backup.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise ValueError("Yedek doğrulanamadı.")
                self.repo.paths.write_json(folder + "/project.json", self.repo.manifest())
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            return {"folder": str(destination.parent), "database": str(destination)}
        if command.startswith("editor_draft_"):
            if data.get("project_id") != self.repo.project_id:
                raise ValueError("Taslak isteğinin proje kimliği eşleşmiyor.")
            drafts = EditorDraftStore(self.repo)
            unit = data["unit_id"]
            result: Any
            if command == "editor_draft_get":
                result = drafts.get(unit)
            elif command == "editor_draft_put":
                result = drafts.put(
                    unit,
                    data["source_revision"],
                    data["base_version"],
                    data["text"],
                    data.get("expected_revision", 0),
                )
            elif command == "editor_draft_commit":
                result = drafts.commit(unit, data["expected_revision"])
            elif command == "editor_draft_discard":
                drafts.discard(unit, data["expected_revision"])
                result = None
            else:
                raise ValueError("Bilinmeyen taslak işlemi.")
            return {
                "project_id": self.repo.project_id,
                "unit_id": unit,
                "draft": result,
                "request_token": data.get("request_token"),
            }
        if command == "page":
            filters = {
                key: data[key]
                for key in ("search", "status", "category", "affected")
                if key in data
            }
            count = self.repo.count(**filters)
            last_offset = ((max(1, count) - 1) // 200) * 200
            offset = min(max(0, int(data.get("offset", 0))), last_offset)
            rows = self.repo.page(
                offset, **filters, source_order=data.get("dialogue_context") == "source-window-v1",
            )
            if data.get("dialogue_context") == "source-window-v1":
                from unitytranslator.dialogue_context import DialogueContextStore

                DialogueContextStore(self.repo).preview(rows)
            if any(row["format_rules"] == "renpy-text-v1" for row in rows):
                from unitytranslator.renpy_export import add_review_context

                add_review_context(self.repo, rows)
            drafts = EditorDraftStore(self.repo)
            for row in rows:
                row["editor_draft"] = drafts.get(row["unit_id"])
            return {
                "project_id": self.repo.project_id,
                "request_token": data.get("request_token"),
                "totals": dict(
                    self.repo.db.execute(
                        "SELECT count(*) AS total, "
                        "coalesce(sum(w.translation_revision IS NOT NULL),0) AS translated, "
                        "coalesce(sum(w.status='approved'),0) AS approved, "
                        "coalesce(sum(w.status!='approved' AND "
                        "w.translation_revision IS NULL),0) AS pilot_eligible "
                        "FROM text_units u JOIN work_items w USING(unit_id) WHERE u.active=1"
                    ).fetchone()
                ),
                "shareable_available": supports_shareable_patch(self.repo),
                "source_adapters": [row[0] for row in self.repo.db.execute(
                    "SELECT DISTINCT d.adapter_id FROM text_units u "
                    "JOIN source_descriptors d ON d.id=u.logical_source_id "
                    "WHERE u.active=1 AND d.active=1 ORDER BY d.adapter_id"
                )],
                "rows": rows,
                "count": count,
                "offset": offset,
                "categories": [
                    r[0]
                    for r in self.repo.db.execute(
                        "SELECT DISTINCT category FROM source_revisions ORDER BY category"
                    )
                ],
            }
        if command == "scan":
            result = await asyncio.to_thread(
                scan, self.repo.paths, engine=data.get("engine", "auto")
            )
            return {"result": result, "report": str(save_report(self.repo.paths, "scan", result))}
        if command == "game_process":
            # The session may change while awaiting; inspect only the captured game.
            identifier, game = self.repo.project_id, self.repo.paths.game
            status = await asyncio.to_thread(inspect_game_processes, game)
            return {
                **asdict(status),
                "project_id": identifier,
                "request_token": data.get("request_token"),
                "observed_at": now(),
            }
        if command == "extract":
            if self.extracting or (self.jobs and self.jobs.active_job):
                raise ValueError("Başka bir çıkarma/çeviri işlemi sürüyor.")
            self.extracting = True
            self.extraction_cancelled.clear()
            self.extraction_task = asyncio.current_task()
            try:
                report = await asyncio.to_thread(
                    probe_source,
                    self.repo.paths,
                    data["source"],
                    source_language=self.repo.source_language,
                    cancellation=self.extraction_cancelled.is_set,
                    engine=data.get("engine", "auto"),
                )
                output = save_report(self.repo.paths, "extract", report)
                if self.extraction_cancelled.is_set():
                    raise ValueError("Extraction cancelled; existing records were preserved.")
                if report["extraction"] != "supported":
                    raise ValueError(f"Çıkarma desteklenmedi; tanı raporu: {output}")
                validate_source_selection(self.repo, report)
                snapshot = self.repo.ingest_reader_result(
                    result_from_report(
                        report, replace_source_set=report.get("complete_source_set") is True
                    )
                )[0]
                return {
                    "snapshot": snapshot,
                    "counts": report["counts"],
                    "report": str(output),
                    "capabilities": report["capabilities"],
                    "coverage": report.get("coverage", []),
                }
            finally:
                self.extracting = False
                self.extraction_task = None
        if command in ("models", "connection_test"):
            if self.jobs and self.jobs.active_job:
                raise ValueError("Üretim işi sürerken ikinci model isteği açılamaz.")
            provider = LocalProvider(
                data["provider"],
                data["address"],
                structured_output=data.get("structured_output", True),
            )
            if command == "models":
                return await provider.inspect_models()
            return await provider.translate_sample(
                data["model"],
                "<b>Welcome {0}</b>\nYou have 3 points.",
                source_language="en",
                target_language=self.repo.target_language,
                context_tokens=data.get("context_tokens", 8192),
                output_tokens=data.get("output_tokens", 4096),
                temperature=data.get("temperature", 0.2),
                **(
                    {"reasoning_effort": data["reasoning_effort"]}
                    if data.get("reasoning_effort", "default") != "default"
                    else {}
                ),
            )
        if command == "policies":
            policy = PolicyStore(self.repo)
            styles = {}
            version = policy.active_version("style")
            if version is not None:
                styles = json.loads(
                    self.repo.db.execute(
                        "SELECT styles_json FROM style_versions WHERE id=?", (version,)
                    ).fetchone()[0]
                )
            return {
                "glossary": [
                    r.model_dump() for r in policy.rules(policy.active_version("glossary"))
                ],
                "styles": styles,
                "impacted": policy.impacted(),
            }
        if command == "set_policies":
            policy = PolicyStore(self.repo)
            with self.repo.transaction():
                glossary = policy.set_glossary(
                    [GlossaryRule.model_validate(v) for v in data["glossary"]]
                )
                style = policy.set_styles(data["styles"])
            return {"glossary_version": glossary, "style_version": style}
        if command == "edit":
            return self.repo.edit(data["unit_id"], data["version"], data["text"])
        if command == "approve":
            self.repo.approve(data["unit_id"], data["version"])
            return True
        if command in ("matching_review_preview", "matching_review_apply"):
            if data.get("project_id") != self.repo.project_id:
                raise ValueError("Bulk review project identity does not match.")
            if self.extracting or (self.jobs and self.jobs.active_job):
                raise ValueError("Wait for extraction or translation to finish before bulk review.")
            if command == "matching_review_preview":
                preview = matching_review_preview(self.repo, data["action"], data["filters"])
                token = uuid4().hex
                self.matching_review = {
                    "project_id": self.repo.project_id, "token": token, "preview": preview,
                }
                return {key: value for key, value in preview.items()
                        if key not in ("records", "policies")} | {
                    "project_id": self.repo.project_id, "token": token,
                    "request_token": data.get("request_token"),
                }
            pending, self.matching_review = self.matching_review, None
            if pending is None or pending["project_id"] != self.repo.project_id or (
                pending["token"] != data.get("token")
            ):
                raise ValueError("Bulk review preview expired. Open it again.")
            return {
                "project_id": self.repo.project_id, "request_token": data.get("request_token"),
                "action": pending["preview"]["action"],
                "changed": apply_matching_review(
                    self.repo, pending["preview"], user_action=data.get("user_action", False),
                ),
            }
        if command in ("approve_all_preview", "approve_all"):
            if data.get("project_id") != self.repo.project_id:
                raise ValueError("Bütün çeviriler onayının proje kimliği eşleşmiyor.")
            if command == "approve_all_preview":
                preview = all_approval_preview(self.repo)
                token = uuid4().hex
                self.all_approval = {
                    "project_id": self.repo.project_id,
                    "token": token,
                    "preview": preview,
                }
                return {key: value for key, value in preview.items() if key != "records"} | {
                    "project_id": self.repo.project_id,
                    "token": token,
                    "request_token": data.get("request_token"),
                }
            pending, self.all_approval = self.all_approval, None
            if (
                pending is None
                or pending["project_id"] != self.repo.project_id
                or data.get("token") != pending["token"]
            ):
                raise ValueError("Onay önizlemesi geçersiz; yeniden açın.")
            return {
                "project_id": self.repo.project_id,
                "request_token": data.get("request_token"),
                "approved": approve_all(
                    self.repo,
                    pending["preview"],
                    user_action=data.get("user_action", False),
                    confirmation=data.get("confirmation", ""),
                ),
            }
        if command == "approve_selection":
            if data.get("project_id") != self.repo.project_id:
                raise ValueError("Grup incelemesinin proje kimliği eşleşmiyor.")
            return {
                "project_id": self.repo.project_id,
                "request_token": data.get("request_token"),
                "approved": approve_selection(
                    self.repo,
                    data["records"],
                    user_action=data.get("user_action", False),
                    reviewed=data.get("reviewed", False),
                ),
            }
        if command == "bulk_readiness":
            if data.get("project_id") != self.repo.project_id:
                raise ValueError("Pilot sorgusunun proje kimliği eşleşmiyor.")
            policy = PolicyStore(self.repo)
            profile = GenerationProfile(
                **data["profile"],
                glossary_version=policy.active_version("glossary"),
                style_version=policy.active_version("style"),
            )
            return {
                "project_id": self.repo.project_id,
                "request_token": data.get("request_token"),
                **JobStore(self.repo).bulk_readiness(profile),
            }
        if command == "use_pilot_profile":
            if (
                data.get("project_id") != self.repo.project_id
                or data.get("user_action") is not True
            ):
                raise ValueError("Explicitly select pilot settings for the current project.")
            if self.extracting or (self.jobs is not None and self.jobs.active_job is not None):
                raise ValueError("Stop extraction or translation before selecting pilot settings.")
            store = JobStore(self.repo)
            job = store.job(data["job_id"])
            if not job["report_seen"] or store.pilot_review_blocker(job["id"]) is not None:
                raise ValueError("A reviewed representative pilot for current sources is required.")
            profile = GenerationProfile(**json.loads(job["profile_json"]))
            policy = PolicyStore(self.repo)
            profile = replace(
                profile, glossary_version=policy.active_version("glossary"),
                style_version=policy.active_version("style"),
            )
            return {"project_id": self.repo.project_id, "request_token": data.get("request_token"),
                    "profile": profile.to_dict()}
        if command == "history":
            history = self.repo.history(data["unit_id"])
            if self.repo.format_rules(data["unit_id"]) == "renpy-text-v1":
                from unitytranslator.renpy_export import template_candidate

                history["template_candidate"] = template_candidate(self.repo, data["unit_id"])
            return history
        if command == "select_candidate":
            return self.repo.select_candidate(
                data["unit_id"],
                data["version"],
                data["revision"],
                replace_approved=data.get("replace_approved", False),
            )
        if command == "textasset_export":
            from unitytranslator.textasset_export import export_payloads

            if data.get("project_id") != self.repo.project_id or self.extracting:
                raise ValueError("Project changed or extraction is active; retry when it finishes.")
            return {**export_payloads(self.repo), "project_id": self.repo.project_id}
        if command == "renpy_export":
            from unitytranslator.renpy_export import export_native

            if data.get("project_id") != self.repo.project_id or self.extracting:
                raise ValueError("Project changed or extraction is active; retry when it finishes.")
            return {
                **export_native(self.repo, data["language"]), "project_id": self.repo.project_id
            }
        if command == "renpy_package":
            from unitytranslator.renpy_package import export_install_package

            if data.get("project_id") != self.repo.project_id or self.extracting:
                raise ValueError("Project changed or extraction is active; retry when it finishes.")
            return {
                **export_install_package(self.repo, data["language"]),
                "project_id": self.repo.project_id,
            }
        if command == "export":
            return str(PortableService(self.repo).export())
        if command == "runtime_export":
            if data.get("project_id") != self.repo.project_id:
                raise ValueError("Deneme isteğinin proje kimliği eşleşmiyor.")
            return {
                **export_selected_runtime(self.repo, data["records"]),
                "project_id": self.repo.project_id,
                "request_token": data.get("request_token"),
            }
        if command in ("import_preview", "import_apply", "import_restore"):
            if self.extracting or (self.jobs is not None and self.jobs.active_job is not None):
                raise ValueError("İçe aktarma için çalışan çıkarma/çeviri işini durdurun.")
            service = PortableService(self.repo)
            value = service.read(Path(data["path"]))
            if command == "import_restore":
                return service.restore(value)
            return service.preview(value) if command == "import_preview" else service.apply(value)
        if command in ("create_job", "create_affected_job", "create_page_job"):
            return self.prepare_job(command, data)
        if command == "run_job":
            if self.jobs is None or self.extracting:
                raise ValueError("Proje/çıkarma durumu çeviriye uygun değil.")
            if "model_selection" in data:
                selected = data["model_selection"]
                saved = json.loads(JobStore(self.repo).job(data["job_id"])["profile_json"])
                if (
                    selected["provider"] != saved["provider"]
                    or local_endpoint(selected["address"]) != local_endpoint(saved["address"])
                    or selected["model"] != saved["model"]
                ):
                    raise ValueError(
                        "The selected provider, server or model differs from this job's saved "
                        "settings. Restore the job's model settings to resume, or start a new "
                        "pilot with the selected model."
                    )
            return await self.jobs.run(
                data["job_id"], self.progress, parallel_requests=data.get("parallel_requests", 1)
            )
        if command == "pause":
            if self.jobs is not None:
                self.jobs.pause()
            return True
        if command == "cancel":
            selected = data.get("job_id")
            if self.jobs is not None and self.jobs.active_job is not None:
                if selected is not None and selected != self.jobs.active_job:
                    raise ValueError("İptal seçimi çalışan işle eşleşmiyor.")
                self.jobs.cancel()
            elif selected is not None:
                JobStore(self.repo).cancel(selected)
            return True
        if command == "jobs":
            return [
                JobStore(self.repo).progress(row[0])
                for row in self.repo.db.execute(
                    "SELECT id FROM jobs ORDER BY created_at DESC LIMIT 50"
                )
            ]
        if command == "job_report":
            report = job_report(self.repo, data["job_id"])
            path = str(save_job_report(self.repo, data["job_id"]))
            return {"report": {**report, "records": report["records"][:200]}, "path": path}
        if command == "quality_audit":
            return save_current_quality_audit(self.repo)
        if command == "shareable_export":
            if data.get("project_id") != self.repo.project_id:
                raise ValueError("Dağıtım isteğinin proje kimliği eşleşmiyor.")
            return {
                **export_shareable_patch(self.repo),
                "project_id": self.repo.project_id,
                "request_token": data.get("request_token"),
            }
        if command == "pilot_seen":
            JobStore(self.repo).acknowledge_pilot(data["job_id"])
            return True
        raise ValueError("Bilinmeyen uygulama işlemi.")
