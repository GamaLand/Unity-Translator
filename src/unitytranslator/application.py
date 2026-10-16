"""Project session shared by the UI and CLI; business rules stay outside widgets."""

import asyncio
import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.discovery import probe_source, save_report, scan
from unitytranslator.domain import GenerationProfile, TextUnitDraft
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.game_process import inspect_game_processes
from unitytranslator.installation import InstallationSession
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.pilot import select_pilot
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.portable import PortableService
from unitytranslator.providers import LocalProvider
from unitytranslator.reports import job_report, save_current_quality_audit, save_job_report
from unitytranslator.repository import ProjectRepository, now
from unitytranslator.review_selection import all_approval_preview, approve_all, approve_selection
from unitytranslator.runtime_export import export_selected_runtime
from unitytranslator.shareable import export_shareable_patch


class ApplicationSession:
    def __init__(self, progress: Callable[[dict[str, Any]], None] | None = None):
        self.repository: ProjectRepository | None = None
        self.jobs: TranslationJobService | None = None
        self.progress = progress
        self.extracting = False
        self.installation: InstallationSession | None = None
        self.all_approval: dict[str, Any] | None = None

    @property
    def repo(self) -> ProjectRepository:
        if self.repository is None:
            raise ValueError("Önce bir proje açın.")
        return self.repository

    async def close(self) -> None:
        if self.jobs is not None and self.jobs.active_job is not None:
            task = self.jobs.task
            self.jobs.cancel()
            if task is not None and task != asyncio.current_task():
                await task
        if self.repository is not None:
            self.repository.close()
            self.repository = None
        self.jobs = None
        self.installation = None
        self.all_approval = None

    async def dispatch(self, command: str, data: dict[str, Any]) -> Any:
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
                deployment_result = self.installation.status()
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

                deployment_result = self.installation.prepare(
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
            rows = self.repo.page(offset, **filters)
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
                        "coalesce(sum(w.status='approved'),0) AS approved "
                        "FROM text_units u JOIN work_items w USING(unit_id) WHERE u.active=1"
                    ).fetchone()
                ),
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
            result = await asyncio.to_thread(scan, self.repo.paths)
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
            try:
                report = await asyncio.to_thread(
                    probe_source,
                    self.repo.paths,
                    data["source"],
                    source_language=self.repo.source_language,
                )
                output = save_report(self.repo.paths, "extract", report)
                if report["extraction"] != "supported":
                    raise ValueError(f"Çıkarma desteklenmedi; tanı raporu: {output}")
                snapshot = self.repo.ingest(
                    [TextUnitDraft(**v) for v in report["units"]],
                    {k: v for k, v in report.items() if k != "units"},
                )
                return {"snapshot": snapshot, "counts": report["counts"], "report": str(output)}
            finally:
                self.extracting = False
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
                "allowed": JobStore(self.repo).pilot_reviewed(profile),
            }
        if command == "history":
            return self.repo.history(data["unit_id"])
        if command == "select_candidate":
            return self.repo.select_candidate(
                data["unit_id"],
                data["version"],
                data["revision"],
                replace_approved=data.get("replace_approved", False),
            )
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
        if command in ("create_job", "create_affected_job"):
            if self.extracting or self.jobs is None or self.jobs.active_job is not None:
                raise ValueError("Çıkarma bitmeden çeviri başlatılamaz.")
            policy = PolicyStore(self.repo)
            profile = GenerationProfile(
                **data["profile"],
                glossary_version=policy.active_version("glossary"),
                style_version=policy.active_version("style"),
            )
            if command == "create_affected_job":
                data = {
                    **data,
                    "kind": "prototype",
                    "retranslate": True,
                    "approved_candidates": True,
                    "units": [row["unit_id"] for row in policy.impacted()][:10],
                }
            units = (
                select_pilot(self.repo)
                if data["kind"] == "pilot"
                else JobStore(self.repo).bulk_units()
                if data["kind"] == "bulk"
                else data["units"]
            )
            identifier = JobStore(self.repo).create(
                units,
                profile,
                data["kind"],
                retranslate=data.get("retranslate", False),
                approved_candidates=data.get("approved_candidates", False),
            )
            return {"job_id": identifier, "count": len(units), "profile": asdict(profile)}
        if command == "run_job":
            if self.jobs is None or self.extracting:
                raise ValueError("Proje/çıkarma durumu çeviriye uygun değil.")
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
