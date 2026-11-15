"""Translate page: jobs, pilots and bulk readiness."""

from typing import Any

from PySide6.QtWidgets import QDialog

from unitytranslator.ui.i18n import tr
from unitytranslator.ui.pages.base import STOP, Completion, Page, PageController


class TranslationController(PageController):
    """Complete Translate page results."""

    COMMANDS = {
        "bulk_readiness": "bulk_readiness",
        "use_pilot_profile": "pilot_profile_used",
        "create_job": "job_created",
        "create_affected_job": "job_created",
        "create_page_job": "job_created",
        "run_job": "job_ran",
        "pause": "job_stopped",
        "cancel": "job_stopped",
        "job_report": "job_report",
        "pilot_seen": "pilot_seen",
        "jobs": "jobs_listed",
    }

    def bulk_readiness(self, command: str, result: Any) -> Completion:
        window = self.window
        if (
            result["project_id"] != window.current_project_id
            or result["request_token"] != window.bulk_readiness_token
        ):
            return STOP
        window.bulk_button.setEnabled(result["allowed"] and not window.job_preparing)
        window.reviewed_pilot_id = result.get("pilot_job_id")
        window.pilot_profile_button.setVisible(bool(window.reviewed_pilot_id))
        window.pilot_profile_button.setEnabled(bool(window.reviewed_pilot_id))
        window.bulk_note.setText(
            tr("Bulk job ready: the pilot was reviewed for this profile and sources.")
            if result["allowed"]
            else tr("Bulk job unavailable: review the pilot for this profile/sources.")
        )
        if result.get("reason") == "profile_changed":
            fields = set(result.get("different_fields", ()))
            settings = []
            if fields & {"glossary_version", "style_version"}:
                settings.append(tr("Glossary / style"))
            if fields - {"glossary_version", "style_version"}:
                settings.append(tr("Model / generation"))
            window.bulk_note.setText(tr(
                "Bulk job unavailable: settings changed after pilot review ({settings}).",
                settings=", ".join(settings),
            ))
        elif result.get("reason") == "source_changed":
            window.bulk_note.setText(tr(
                "Bulk job unavailable: source records changed after pilot review."
            ))
        return None

    def pilot_profile_used(self, command: str, result: Any) -> Completion:
        window = self.window
        if result["project_id"] != window.current_project_id or result.get("request_token") != (
            window.pilot_profile_token
        ):
            return STOP
        window.pilot_profile_token = None
        window.apply_profile(result["profile"])
        window.bridge.submit("policies")
        window.schedule_bulk_readiness()
        return None

    def job_created(self, command: str, result: Any) -> Completion:
        window = self.window
        window.set_job_preparing(False)
        # A job prepared while closing (drafts still flushing) must never start.
        if window.closing:
            return STOP
        if window.draft_deferred and window.draft_deferred[0] == "close":
            # Never start it; refresh the list in case the close is aborted.
            window.bridge.submit("jobs")
            return STOP
        if result.get("reason") == "preparation_cancelled":
            window.job_status.setText(tr(
                "Preparation cancelled. Existing translations are kept."
            ))
            window.job_progress.setRange(0, 1)
            window.job_progress.setValue(0)
            window.bridge.submit("jobs")
            window.schedule_bulk_readiness()
            return STOP
        if result.get("reason") == "no_eligible_records":
            window.job_status.setText(tr(
                "No untranslated records remain. Review or export existing translations."
            ))
            return STOP
        window.current_job = result["job_id"]
        if command == "create_page_job":
            window.tabs.setCurrentIndex(Page.TRANSLATION)
        window.job_status.setText(tr("Job prepared for {p0} records.", p0=f"{result['count']}"))
        window.job_progress.setRange(0, 0)
        window.job_progress.setFormat(tr("Waiting for the first response…"))
        window.job_combo.setEnabled(False)
        window.parallel_requests.setEnabled(False)
        window.pause_button.setEnabled(True)
        window.resume_button.setEnabled(False)
        window.cancel_button.setEnabled(True)
        window.bridge.submit(
            "run_job",
            {
                "job_id": window.current_job,
                "parallel_requests": window.parallel_requests.value(),
                "model_selection": window.model_data(),
            },
        )
        return None

    def job_ran(self, command: str, result: Any) -> Completion:
        window = self.window
        window.on_progress(result)
        window.bridge.submit("jobs")
        window.refresh()
        window.schedule_bulk_readiness()
        return None

    def job_stopped(self, command: str, result: Any) -> Completion:
        window = self.window
        window.bridge.submit("jobs")
        window.refresh()
        return None

    def job_report(self, command: str, result: Any) -> Completion:
        window = self.window
        from unitytranslator.ui.window import PilotReportDialog

        dialog = PilotReportDialog(result["report"], result["path"], window)
        outcome = dialog.exec()
        if outcome == QDialog.DialogCode.Accepted and dialog.acknowledged:
            window.bridge.submit("pilot_seen", {"job_id": result["report"]["job_id"]})
        elif outcome == 2:
            window.bridge.submit("job_report", {"job_id": result["report"]["job_id"]})
        return None

    def pilot_seen(self, command: str, result: Any) -> Completion:
        window = self.window
        window.bulk_note.setText(
            tr("Pilot review saved. Bulk jobs are available for the same profile and sources.")
        )
        window.schedule_bulk_readiness()
        return None

    def jobs_listed(self, command: str, result: Any) -> Completion:
        window = self.window
        from unitytranslator.ui.window import JOB_STATUS

        window.job_summaries = {job["job_id"]: job for job in result}
        selected = window.current_job
        window.job_combo.blockSignals(True)
        window.job_combo.clear()
        for job in result:
            window.job_combo.addItem(
                f"{job['job_id'][:8]} · {JOB_STATUS.get(job['status'], job['status'])}",
                job["job_id"],
            )
        index = window.job_combo.findData(selected)
        window.job_combo.setCurrentIndex(max(0, index))
        window.job_combo.blockSignals(False)
        window.current_job = window.job_combo.currentData()
        if window.current_job in window.job_summaries:
            window.on_progress(window.job_summaries[window.current_job])
        return None
