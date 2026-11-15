"""Project session shared by the UI and CLI; business rules stay outside widgets."""

import asyncio
import json
import sqlite3
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from unitytranslator.commands import (
    FAMILY_FALLBACKS,
    ApproveAllPayload,
    ApprovePayload,
    CancelPayload,
    CandidatePayload,
    DeploymentPayload,
    DraftPayload,
    EditPayload,
    EnginePayload,
    ExtractPayload,
    Guard,
    Identified,
    IdleScope,
    ImportPayload,
    JobIdPayload,
    JobPayload,
    LanguagePayload,
    MatchingReviewPayload,
    ModelPayload,
    OpenPayload,
    PagePayload,
    PilotProfilePayload,
    PolicyPayload,
    ReadinessPayload,
    RecordsPayload,
    RunPayload,
    SelectionPayload,
    TranslationMemoryPayload,
    UnitPayload,
    command,
    registry,
)
from unitytranslator.diagnostics import Diagnostic
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
from unitytranslator.repository import REVIEW_PAGE_SIZE, ProjectRepository, now
from unitytranslator.review_selection import (
    all_approval_preview,
    apply_matching_review,
    approve_all,
    approve_selection,
    matching_review_preview,
)
from unitytranslator.runtime_export import export_selected_runtime
from unitytranslator.shareable import export_shareable_patch, supports_shareable_patch
from unitytranslator.translation_memory import apply as apply_translation_memory
from unitytranslator.translation_memory import preview as translation_memory_preview

DEPLOYMENT_IDENTITY = "Installation request project identity does not match."
DEPLOYMENT_IDLE = FAMILY_FALLBACKS["deployment_"][0].idle
MODEL_IDLE: tuple[IdleScope, str] = (
    "job", "A second model request cannot start while a generation job is running."
)
MATCHING_IDENTITY = "Bulk review project identity does not match."
MATCHING_IDLE: tuple[IdleScope, str] = (
    "work", "Wait for extraction or translation to finish before bulk review."
)
APPROVE_ALL_IDENTITY = "Approve-all request project identity does not match."
MEMORY_IDENTITY = "Translation memory request project identity does not match."
MEMORY_IDLE: tuple[IdleScope, str] = (
    "work", "Wait for extraction or translation to finish before reusing translation memory."
)
EXPORT_STATE = "Project changed or extraction is active; retry when it finishes."
IMPORT_IDLE: tuple[IdleScope, str] = (
    "work", "Stop the running extraction or translation job before importing."
)


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
        self.translation_memory: dict[str, Any] | None = None

    @property
    def repo(self) -> ProjectRepository:
        if self.repository is None:
            raise ValueError("Open a project first.")
        return self.repository

    def current_project_id(self) -> str | None:
        """The open project's identity, recorded with failures; never raises."""
        repository = self.repository
        return None if repository is None else str(repository.project_id)

    async def close(self) -> None:
        self.extraction_cancelled.set()
        if self.extraction_task is not None and self.extraction_task != asyncio.current_task():
            await asyncio.gather(self.extraction_task, return_exceptions=True)
        if self.jobs is not None and self.jobs.active_job is not None:
            task = self.jobs.task
            # Closing or switching projects pauses the job; only the Cancel action cancels.
            self.jobs.suspend()
            if task is not None and task != asyncio.current_task():
                await asyncio.gather(task, return_exceptions=True)
        if self.repository is not None:
            self.repository.close()
            self.repository = None
        self.jobs = None
        self.installation = None
        self.all_approval = None
        self.matching_review = None
        self.translation_memory = None

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
                raise ValueError("Translation cannot start before extraction finishes.")
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
        spec = COMMANDS.get(command)
        if spec is None:
            for prefix, (guard, message) in FAMILY_FALLBACKS.items():
                if command.startswith(prefix):
                    self.check_guard(guard, data)
                    raise ValueError(message)
            raise ValueError("Unknown application action.")
        self.check_guard(spec.guard, data)
        return await spec.handler(self, data)

    def busy(self, scope: IdleScope) -> bool:
        job = self.jobs is not None and self.jobs.active_job is not None
        return {"work": self.extracting or job, "extraction": self.extracting, "job": job}[scope]

    def check_guard(self, guard: Guard, data: Mapping[str, Any]) -> None:
        if guard.project:
            self.repo  # noqa: B018 - raises "Open a project first." without a project
        if guard.identity is not None and (
            data.get("project_id") != self.repo.project_id
            or (guard.installation and self.installation is None)
        ):
            raise ValueError(guard.identity)
        if guard.idle is not None and self.busy(guard.idle[0]):
            raise ValueError(guard.idle[1])

    @command("cancel_preparation", project=False)
    async def command_cancel_preparation(self, data: Mapping[str, Any]) -> bool:
        return True

    @command("cancel_extract", project=False)
    async def command_cancel_extract(self, data: Mapping[str, Any]) -> dict[str, bool]:
        self.extraction_cancelled.set()
        return {"cancel_requested": True}

    @command("open", project=False,
             idle=("extraction", "Extraction is running; wait for it to finish."))
    async def command_open_project(self, data: OpenPayload) -> dict[str, Any]:
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
            raise ValueError("The project's linked game folder does not match.")
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

    def deployment_session(self) -> InstallationSession:
        if self.installation is None:
            raise ValueError(DEPLOYMENT_IDENTITY)
        return self.installation

    def deployment_result(self, result: dict[str, Any], data: DeploymentPayload) -> dict[str, Any]:
        return {
            **result,
            "project_id": self.repo.project_id,
            "request_token": data.get("request_token"),
        }

    @command("deployment_status", identity=DEPLOYMENT_IDENTITY, installation=True)
    async def command_deployment_status(self, data: DeploymentPayload) -> dict[str, Any]:
        installation = self.deployment_session()
        return self.deployment_result(deployment_adapter_for(installation).probe(), data)

    @command("deployment_prepare", identity=DEPLOYMENT_IDENTITY, idle=DEPLOYMENT_IDLE,
             installation=True)
    async def command_deployment_prepare(self, data: DeploymentPayload) -> dict[str, Any]:
        installation = self.deployment_session()

        def progress(message: str) -> None:
            if self.progress:
                self.progress(
                    {
                        "kind": "deployment",
                        "project_id": self.repo.project_id,
                        "message": message,
                    }
                )

        result = deployment_adapter_for(installation).prepare(
            log_file=data.get("log_file", ""),
            log_reviewed=data.get("log_reviewed", False),
            progress=progress,
        )
        return self.deployment_result(result, data)

    @command("deployment_install", identity=DEPLOYMENT_IDENTITY, idle=DEPLOYMENT_IDLE,
             installation=True)
    async def command_deployment_install(self, data: DeploymentPayload) -> dict[str, Any]:
        result = self.deployment_session().install(
            data["review_id"],
            user_action=data.get("user_action", False),
            experimental_reviewed=data.get("experimental_reviewed", False),
        )
        return self.deployment_result(result, data)

    @command("deployment_remove", identity=DEPLOYMENT_IDENTITY, idle=DEPLOYMENT_IDLE,
             installation=True)
    async def command_deployment_remove(self, data: DeploymentPayload) -> dict[str, Any]:
        result = self.deployment_session().remove(
            data["plan_id"], user_action=data.get("user_action", False)
        )
        return self.deployment_result(result, data)

    @command("backup")
    async def command_backup(self, data: Mapping[str, Any]) -> dict[str, str]:
        folder = "backups/manual-" + uuid4().hex
        destination = self.repo.paths.output(folder + "/project.sqlite3")
        destination.parent.mkdir(parents=True)
        try:
            with sqlite3.connect(destination) as backup:
                self.repo.db.backup(backup)
                if backup.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("The backup could not be verified.")
            self.repo.paths.write_json(folder + "/project.json", self.repo.manifest())
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return {"folder": str(destination.parent), "database": str(destination)}

    def draft_result(self, data: DraftPayload, result: Any) -> dict[str, Any]:
        return {
            "project_id": self.repo.project_id,
            "unit_id": data["unit_id"],
            "draft": result,
            "request_token": data.get("request_token"),
        }

    @command("editor_draft_get", identity="Draft request project identity does not match.")
    async def command_editor_draft_get(self, data: DraftPayload) -> dict[str, Any]:
        drafts = EditorDraftStore(self.repo)
        unit = data["unit_id"]
        return self.draft_result(data, drafts.get(unit))

    @command("editor_draft_put", identity="Draft request project identity does not match.")
    async def command_editor_draft_put(self, data: DraftPayload) -> dict[str, Any]:
        drafts = EditorDraftStore(self.repo)
        unit = data["unit_id"]
        result = drafts.put(
            unit,
            data["source_revision"],
            data["base_version"],
            data["text"],
            data.get("expected_revision", 0),
        )
        return self.draft_result(data, result)

    @command("editor_draft_commit", identity="Draft request project identity does not match.")
    async def command_editor_draft_commit(self, data: DraftPayload) -> dict[str, Any]:
        drafts = EditorDraftStore(self.repo)
        unit = data["unit_id"]
        return self.draft_result(data, drafts.commit(unit, data["expected_revision"]))

    @command("editor_draft_discard", identity="Draft request project identity does not match.")
    async def command_editor_draft_discard(self, data: DraftPayload) -> dict[str, Any]:
        drafts = EditorDraftStore(self.repo)
        unit = data["unit_id"]
        drafts.discard(unit, data["expected_revision"])
        return self.draft_result(data, None)

    @command("page")
    async def command_page(self, data: PagePayload) -> dict[str, Any]:
        raw = cast(Mapping[str, Any], data)
        filters = {
            key: raw[key] for key in ("search", "status", "category", "affected") if key in raw
        }
        count = self.repo.count(**filters)
        last_offset = ((max(1, count) - 1) // REVIEW_PAGE_SIZE) * REVIEW_PAGE_SIZE
        offset = min(max(0, int(data.get("offset", 0))), last_offset)
        rows = self.repo.page(
            offset, **filters, source_order=data.get("dialogue_context") == "source-window-v1",
        )
        if data.get("dialogue_context") == "source-window-v1":
            from unitytranslator.dialogue_context import DialogueContextStore

            DialogueContextStore(self.repo).preview(rows)
        if any(row["format_rules"] in ("renpy-text-v1", "renpy-text-v2") for row in rows):
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

    @command("scan")
    async def command_scan(self, data: EnginePayload) -> dict[str, Any]:
        result = await asyncio.to_thread(
            scan, self.repo.paths, engine=data.get("engine", "auto")
        )
        return {"result": result, "report": str(save_report(self.repo.paths, "scan", result))}

    @command("game_process")
    async def command_game_process(self, data: Mapping[str, Any]) -> dict[str, Any]:
        # The session may change while awaiting; inspect only the captured game.
        identifier, game = self.repo.project_id, self.repo.paths.game
        status = await asyncio.to_thread(inspect_game_processes, game)
        return {
            **asdict(status),
            "project_id": identifier,
            "request_token": data.get("request_token"),
            "observed_at": now(),
        }

    @command("extract", idle=("work", "Another extraction or translation is running."))
    async def command_extract(self, data: ExtractPayload) -> dict[str, Any]:
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
                raise Diagnostic(
                    "Extraction is not supported; diagnostic report: {p0}", p0=output
                )
            validate_source_selection(self.repo, report)
            snapshot = self.repo.ingest_reader_result(
                result_from_report(
                    report, replace_source_set=report.get("complete_source_set") is True
                ),
                format_rules=data.get("format_rules"),
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

    @command("models", project=False, idle=MODEL_IDLE)
    async def command_models(self, data: ModelPayload) -> list[dict[str, Any]]:
        provider = LocalProvider(
            data["provider"],
            data["address"],
            structured_output=data.get("structured_output", True),
        )
        return await provider.inspect_models()

    # The address is validated before the project, as before the registry.
    @command("connection_test", project=False, idle=MODEL_IDLE)
    async def command_connection_test(self, data: ModelPayload) -> dict[str, Any]:
        provider = LocalProvider(
            data["provider"],
            data["address"],
            structured_output=data.get("structured_output", True),
        )
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

    @command("policies")
    async def command_policies(self, data: Mapping[str, Any]) -> dict[str, Any]:
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

    @command("set_policies")
    async def command_set_policies(self, data: PolicyPayload) -> dict[str, Any]:
        policy = PolicyStore(self.repo)
        with self.repo.transaction():
            glossary = policy.set_glossary(
                [GlossaryRule.model_validate(v) for v in data["glossary"]]
            )
            style = policy.set_styles(data["styles"])
        return {"glossary_version": glossary, "style_version": style}

    @command("edit")
    async def command_edit(self, data: EditPayload) -> Any:
        return self.repo.edit(data["unit_id"], data["version"], data["text"])

    @command("approve")
    async def command_approve(self, data: ApprovePayload) -> bool:
        self.repo.approve(data["unit_id"], data["version"])
        return True

    @command("matching_review_preview", identity=MATCHING_IDENTITY, idle=MATCHING_IDLE)
    async def command_matching_review_preview(self, data: MatchingReviewPayload) -> dict[str, Any]:
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

    @command("matching_review_apply", identity=MATCHING_IDENTITY, idle=MATCHING_IDLE)
    async def command_matching_review_apply(self, data: MatchingReviewPayload) -> dict[str, Any]:
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

    @command("translation_memory_preview", identity=MEMORY_IDENTITY, idle=MEMORY_IDLE)
    async def command_translation_memory_preview(
        self, data: TranslationMemoryPayload,
    ) -> dict[str, Any]:
        include_translated = data.get("include_translated", False) is True
        profile = data.get("profile")
        preview = translation_memory_preview(
            self.repo, include_translated=include_translated, profile=profile,
        )
        self.translation_memory = {"project_id": self.repo.project_id, "preview": preview}
        return {key: value for key, value in preview.items() if key != "actions"} | {
            "project_id": self.repo.project_id, "request_token": data.get("request_token"),
        }

    @command("translation_memory_apply", identity=MEMORY_IDENTITY, idle=MEMORY_IDLE)
    async def command_translation_memory_apply(
        self, data: TranslationMemoryPayload,
    ) -> dict[str, Any]:
        pending, self.translation_memory = self.translation_memory, None
        if pending is None or pending["project_id"] != self.repo.project_id or (
            pending["preview"]["token"] != data.get("token")
        ):
            raise ValueError("Translation memory preview expired. Open it again.")
        return {
            "project_id": self.repo.project_id, "request_token": data.get("request_token"),
            "added": apply_translation_memory(
                self.repo, pending["preview"], user_action=data.get("user_action", False),
            ),
        }

    @command("approve_all_preview", identity=APPROVE_ALL_IDENTITY)
    async def command_approve_all_preview(self, data: ApproveAllPayload) -> dict[str, Any]:
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

    @command("approve_all", identity=APPROVE_ALL_IDENTITY)
    async def command_approve_all(self, data: ApproveAllPayload) -> dict[str, Any]:
        pending, self.all_approval = self.all_approval, None
        if (
            pending is None
            or pending["project_id"] != self.repo.project_id
            or data.get("token") != pending["token"]
        ):
            raise ValueError("The approval preview is invalid; open it again.")
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

    @command("approve_selection", identity="Group review project identity does not match.")
    async def command_approve_selection(self, data: SelectionPayload) -> dict[str, Any]:
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

    @command("bulk_readiness", identity="Pilot query project identity does not match.")
    async def command_bulk_readiness(self, data: ReadinessPayload) -> dict[str, Any]:
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

    @command("use_pilot_profile",
             identity="Explicitly select pilot settings for the current project.")
    async def command_use_pilot_profile(self, data: PilotProfilePayload) -> dict[str, Any]:
        # The explicit-action check precedes the idle check, as before the registry.
        if data.get("user_action") is not True:
            raise ValueError("Explicitly select pilot settings for the current project.")
        if self.busy("work"):
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

    @command("history")
    async def command_history(self, data: UnitPayload) -> dict[str, Any]:
        history = self.repo.history(data["unit_id"])
        if self.repo.format_rules(data["unit_id"]) in ("renpy-text-v1", "renpy-text-v2"):
            from unitytranslator.renpy_export import template_candidate

            history["template_candidate"] = template_candidate(self.repo, data["unit_id"])
        return history

    @command("select_candidate")
    async def command_select_candidate(self, data: CandidatePayload) -> Any:
        return self.repo.select_candidate(
            data["unit_id"],
            data["version"],
            data["revision"],
            replace_approved=data.get("replace_approved", False),
        )

    @command("textasset_export", identity=EXPORT_STATE, idle=("extraction", EXPORT_STATE))
    async def command_textasset_export(self, data: Identified) -> dict[str, Any]:
        from unitytranslator.textasset_export import export_payloads

        return {**export_payloads(self.repo), "project_id": self.repo.project_id}

    @command("renpy_export", identity=EXPORT_STATE, idle=("extraction", EXPORT_STATE))
    async def command_renpy_export(self, data: LanguagePayload) -> dict[str, Any]:
        from unitytranslator.renpy_export import export_native

        return {
            **export_native(self.repo, data["language"]), "project_id": self.repo.project_id
        }

    @command("renpy_package", identity=EXPORT_STATE, idle=("extraction", EXPORT_STATE))
    async def command_renpy_package(self, data: LanguagePayload) -> dict[str, Any]:
        from unitytranslator.renpy_package import export_install_package

        return {
            **export_install_package(self.repo, data["language"]),
            "project_id": self.repo.project_id,
        }

    @command("export")
    async def command_export(self, data: Mapping[str, Any]) -> str:
        return str(PortableService(self.repo).export())

    @command("runtime_export", identity="Trial request project identity does not match.")
    async def command_runtime_export(self, data: RecordsPayload) -> dict[str, Any]:
        return {
            **export_selected_runtime(self.repo, data["records"]),
            "project_id": self.repo.project_id,
            "request_token": data.get("request_token"),
        }

    def import_archive(self, command: str, data: ImportPayload) -> Any:
        service = PortableService(self.repo)
        value = service.read(Path(data["path"]))
        if command == "import_restore":
            return service.restore(value)
        return service.preview(value) if command == "import_preview" else service.apply(value)

    @command("import_preview", idle=IMPORT_IDLE)
    async def command_import_preview(self, data: ImportPayload) -> Any:
        return self.import_archive("import_preview", data)

    @command("import_apply", idle=IMPORT_IDLE)
    async def command_import_apply(self, data: ImportPayload) -> Any:
        return self.import_archive("import_apply", data)

    @command("import_restore", idle=IMPORT_IDLE)
    async def command_import_restore(self, data: ImportPayload) -> Any:
        return self.import_archive("import_restore", data)

    @command("create_job")
    async def command_create_job(self, data: JobPayload) -> dict[str, Any]:
        return self.prepare_job("create_job", dict(data))

    @command("create_affected_job")
    async def command_create_affected_job(self, data: JobPayload) -> dict[str, Any]:
        return self.prepare_job("create_affected_job", dict(data))

    @command("create_page_job")
    async def command_create_page_job(self, data: JobPayload) -> dict[str, Any]:
        return self.prepare_job("create_page_job", dict(data))

    @command("run_job", project=False)
    async def command_run_job(self, data: RunPayload) -> dict[str, Any]:
        if self.jobs is None or self.extracting:
            raise ValueError("The project or extraction state does not allow translation.")
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

    @command("pause", project=False)
    async def command_pause(self, data: Mapping[str, Any]) -> bool:
        if self.jobs is not None:
            self.jobs.pause()
        return True

    @command("cancel", project=False)
    async def command_cancel(self, data: CancelPayload) -> bool:
        selected = data.get("job_id")
        if self.jobs is not None and self.jobs.active_job is not None:
            if selected is not None and selected != self.jobs.active_job:
                raise ValueError("The cancellation selection does not match the running job.")
            self.jobs.cancel()
        elif selected is not None:
            JobStore(self.repo).cancel(selected)
        return True

    @command("jobs")
    async def command_job_list(self, data: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            JobStore(self.repo).progress(row[0])
            for row in self.repo.db.execute(
                "SELECT id FROM jobs ORDER BY created_at DESC LIMIT 50"
            )
        ]

    @command("job_report")
    async def command_job_report(self, data: JobIdPayload) -> dict[str, Any]:
        report = job_report(self.repo, data["job_id"])
        path = str(save_job_report(self.repo, data["job_id"]))
        return {
            "report": {**report, "records": report["records"][:REVIEW_PAGE_SIZE]}, "path": path,
        }

    @command("quality_audit")
    async def command_quality_audit(self, data: Mapping[str, Any]) -> Any:
        return save_current_quality_audit(self.repo)

    @command("shareable_export", identity="Distribution request project identity does not match.")
    async def command_shareable_export(self, data: Identified) -> dict[str, Any]:
        return {
            **export_shareable_patch(self.repo),
            "project_id": self.repo.project_id,
            "request_token": data.get("request_token"),
        }

    @command("pilot_seen")
    async def command_pilot_seen(self, data: JobIdPayload) -> bool:
        JobStore(self.repo).acknowledge_pilot(data["job_id"])
        return True


COMMANDS = registry(ApplicationSession)
