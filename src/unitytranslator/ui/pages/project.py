"""Project and Texts pages: project, backup, scan and extraction."""

from typing import Any

from unitytranslator.ui.i18n import tr
from unitytranslator.ui.pages.base import STOP, Completion, Page, PageController


class ProjectController(PageController):
    """Complete Project and Texts pages results."""

    COMMANDS = {
        "open": "opened",
        "game_process": "game_process",
        "scan": "scanned",
        "extract": "extracted",
        "backup": "backup_created",
    }

    def opened(self, command: str, result: Any) -> Completion:
        window = self.window
        window.renpy_language.clear()
        window.renpy_available = False
        window.renpy_export_group.setVisible(False)
        window.current_item = None
        window.current_project_id = result["project_id"]
        window.drafts.reset(window.current_project_id)
        window.review_model.set_rows([])
        window.draft_refresh_pending = False
        window.setEnabled(True)
        window.game_process_token = None
        window.runtime_export_token = None
        window.shareable_export_token = None
        window.shareable_available = False
        window.shareable_export_button.setEnabled(False)
        window.pilot_button.setEnabled(False)
        window.deployment_token = None
        window.deployment_status_token = None
        window.deployment = None
        window.installation_kit_available = False
        window.installation_details.clear()
        window.installation_log.clear()
        window.installation_log_reviewed.setChecked(False)
        window.approve_selection_token = None
        window.approve_all_token = None
        window.approve_all_button.setEnabled(True)
        window.bulk_readiness_token = None
        window.matching_review_token = None
        window.translation_memory_token = None
        window.bulk_review_button.setEnabled(True)
        window.game_process_status.setText(tr("Game process state has not been checked."))
        window.project_open = True
        window.current_job = None
        window.job_summaries = {}
        window.job_status.setText(tr("No job selected yet."))
        window.job_progress.setRange(0, 1)
        window.job_progress.setValue(0)
        window.job_progress.setFormat(tr("No jobs yet"))
        window.project_totals = None
        window.next_step.setEnabled(False)
        window.open_project_folder = result.get("project_path", window.project_path.text())
        window.project_path.setText(window.open_project_folder)
        window.game_path.setText(result.get("game_path", window.game_path.text()))
        window.project_folder_button.setEnabled(True)
        for index in range(Page.SOURCES, window.tabs.count()):
            window.tabs.setTabEnabled(index, True)
        window.source_language.setCurrentText(result["source_language"])
        window.target_language.setCurrentText(result["target_language"])
        window.summary.setText(
            tr(
                "Project open · {p1} → {p3} · Game files are read-only",
                p1=f"{result['source_language']}",
                p3=f"{result['target_language']}",
            )
        )
        window.offset = 0
        window.category_filter.blockSignals(True)
        window.category_filter.clear()
        window.category_filter.addItem(tr("All categories"), None)
        window.category_filter.blockSignals(False)
        profile = result.get("last_profile")
        if profile:
            window.apply_profile(profile)
        window.refresh()
        window.bridge.submit("policies")
        window.bridge.submit("jobs")
        window.refresh_installation()
        window.schedule_bulk_readiness()
        return None

    def game_process(self, command: str, result: Any) -> Completion:
        window = self.window
        if (
            result["project_id"] != window.current_project_id
            or result["request_token"] != window.game_process_token
        ):
            return STOP  # A stale session/request result must not replace the current status.
        labels = {
            "closed": tr("The game was observed closed."),
            "running": tr("The game is running. Close it before installing/removing files."),
            "unknown": tr("Could not verify that the game is closed."),
        }
        reasons = {
            "no_executable_identity": tr("Could not identify the game executable."),
            "game_entry_limit": tr("Game file scan limit exceeded."),
            "game_tree_uninspectable": tr(
                "The game folder contains links, reserved names or unreadable folders."
            ),
            "process_or_path_inspection_failed": tr("Process or path query could not finish."),
        }
        window.game_process_status.setText(
            labels.get(result["status"], labels["unknown"])
            + " "
            + reasons.get(result["reason"], "")
            + tr("\nObservation time (UTC): {p1}", p1=f"{result['observed_at']}")
            + tr(
                "\nThis observation is not installation approval. In-game "
                "application is not yet verified."
            )
        )
        return None

    def scanned(self, command: str, result: Any) -> Completion:
        window = self.window
        report = result["result"]
        window.source_file.clear()
        engine = report.get("engine_report", {}).get("engine", "unknown")
        templates = [
            item for item in report.get("renpy_inputs", {}).get("source_candidates", ())
            if item["kind"] == "translation_template_candidate"
        ]
        candidates = list(report["source_candidates"]) if engine != "renpy" else []
        if engine != "unity":
            candidates.extend(templates)
            candidates.extend(
                item for item in report.get("renpy_inputs", {}).get("source_candidates", ())
                if item["kind"] in ("archive", "loose_script", "renpy_python_source")
            )
        window.source_file.addItems(
            [
                item["path"]
                for item in sorted(candidates, key=lambda i: i["size"])
            ]
        )
        if report.get("recommendations") and engine != "renpy":
            window.source_file.setCurrentText(report["recommendations"][0]["source"])
        window.discovery.setPlainText(
            tr(
                (
                    "Runtime indicators: {p1} · {p3} source candidates. Text "
                    "extraction: not yet verified. Game application: not yet "
                    "verified. Report: {p5}"
                ),
                p1=f"{', '.join(report['runtime_indicators']) or tr('Unknown')}",
                p3=f"{len(candidates)}",
                p5=f"{result['report']}",
            )
        )
        window.discovery.append(tr(
            "Engine evidence: {engine}. Ren'Py template candidates: {count}.",
            engine={"unity": "Unity", "renpy": "Ren'Py",
                    "ambiguous": "Unity / Ren'Py"}.get(engine, tr("Unknown")),
            count=str(len(templates)),
        ))
        if report.get("recommendations") and engine != "renpy":
            window.discovery.append(
                tr(
                    "The first source candidate for this game profile was "
                    "selected. The reader will verify its structure."
                )
            )
        window.show_capabilities(report.get("capabilities"))
        return None

    def extracted(self, command: str, result: Any) -> Completion:
        window = self.window
        window.show_capabilities(result.get("capabilities"))
        if result.get("counts", {}).get("sources"):
            window.discovery.append(tr(
                "Verified game-text sources: {sources}. Reviewed exclusions: {excluded}. "
                "Additional text may remain outside this profile.",
                sources=str(result["counts"]["sources"]),
                excluded=str(sum(bool(item.get("excluded_reason"))
                                 for item in result.get("coverage", []))),
            ))
        window.discovery.append(
            tr(
                (
                    "Extraction complete: {p1} records, {p3} characters. Source "
                    "hashes match before/after. {p5}"
                ),
                p1=f"{result['counts']['records']}",
                p3=f"{result['counts']['characters']}",
                p5=f"{result['report']}",
            )
        )
        window.refresh()
        window.schedule_bulk_readiness()
        return None

    def backup_created(self, command: str, result: Any) -> Completion:
        window = self.window
        window.setEnabled(True)
        window.export_status.setPlainText(
            tr("Data backup created and integrity verified:\n")
            + result["folder"]
            + tr(
                "\nIncludes translations, approvals, drafts and job history. "
                "This is not a backup of the game installation or generated "
                "packages. Open this backup folder with Open existing "
                "project."
            )
        )
        return None
