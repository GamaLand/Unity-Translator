"""Review page: record pages, history and approvals."""

from typing import Any

from PySide6.QtWidgets import QMessageBox

from unitytranslator.review_selection import canonical_all_confirmation
from unitytranslator.ui.i18n import tr
from unitytranslator.ui.local_review import progress_text
from unitytranslator.ui.pages.base import STOP, Completion, PageController


class ReviewController(PageController):
    """Complete Review page results."""

    COMMANDS = {
        "matching_review_preview": "matching_review",
        "matching_review_apply": "matching_review",
        "translation_memory_preview": "translation_memory",
        "translation_memory_apply": "translation_memory",
        "local_review_preview": "local_review",
        "local_review_run": "local_review",
        "local_review_cancel": "local_review",
        "approve_all_preview": "approve_all_preview",
        "approve_selection": "approved_many",
        "approve_all": "approved_many",
        "page": "page_loaded",
        "history": "history_loaded",
        "quality_audit": "quality_audited",
        "edit": "record_changed",
        "approve": "record_changed",
        "select_candidate": "record_changed",
    }

    def matching_review(self, command: str, result: Any) -> Completion:
        window = self.window
        if result["project_id"] != window.current_project_id or (
            result["request_token"] != window.matching_review_token
        ):
            return STOP
        if command == "matching_review_preview":
            window.confirm_matching_review(result)
            return STOP
        window.bulk_review_button.setEnabled(True)
        window.matching_review_token = None
        window.refresh()
        window.refresh_installation()
        window.bridge.submit("policies")
        window.review_details.setText(tr("Updated {p0} records.", p0=str(result["changed"])))
        return None

    def translation_memory(self, command: str, result: Any) -> Completion:
        window = self.window
        if result["project_id"] != window.current_project_id or (
            result["request_token"] != window.translation_memory_token
        ):
            return STOP
        if command == "translation_memory_preview":
            window.confirm_translation_memory(result)
            return STOP
        window.bulk_review_button.setEnabled(True)
        window.translation_memory_token = None
        window.refresh()
        window.refresh_installation()
        window.review_details.setText(tr(
            "Added {p0} translation memory candidates. They are not approved; review each "
            "one before approval.", p0=str(result["added"]),
        ))
        return None

    def local_review(self, command: str, result: Any) -> Completion:
        window = self.window
        if command == "local_review_cancel":
            window.statusBar().showMessage(tr("Cancelling the local review…"), 8000)
            return STOP
        if command == "local_review_run":
            # The backend run has ended, even when its project or request is no longer open.
            window.set_local_review_running(False)
        else:
            window.local_review_action.setEnabled(not window.local_review_running)
        if result["project_id"] != window.current_project_id or (
            result["request_token"] != window.local_review_token
        ):
            return STOP
        if command == "local_review_preview":
            window.confirm_local_review(result)
            return STOP
        window.set_local_review_running(False)
        window.local_review_token = None
        # Kept below the record details until the user selects another record, so the
        # page refresh below cannot replace a stop or cancel reason.
        window.local_review_summary = progress_text(result)
        window.refresh()
        window.review_details.setText(window.local_review_summary)
        # The stop or cancel reason when there is one, otherwise the counts.
        window.statusBar().showMessage(window.local_review_summary.split("\n")[-1], 15000)
        return STOP

    def approve_all_preview(self, command: str, result: Any) -> Completion:
        window = self.window
        from unitytranslator.ui.window import AllApprovalDialog

        if (
            result["project_id"] != window.current_project_id
            or result["request_token"] != window.approve_all_token
        ):
            return STOP
        window.approve_all_button.setEnabled(True)
        if not result["count"]:
            QMessageBox.information(
                window,
                tr("All translations"),
                tr("No pending translations are eligible for approval."),
            )
            return STOP
        dialog = AllApprovalDialog(result, window)
        if (
            dialog.exec()
            and dialog.stage == 2
            and dialog.confirmation.text() == dialog.phrase
            and result["project_id"] == window.current_project_id
        ):
            window.approve_all_button.setEnabled(False)
            window.bridge.submit(
                "approve_all",
                {
                    "project_id": window.current_project_id,
                    "request_token": window.approve_all_token,
                    "token": result["token"],
                    "user_action": True,
                    "confirmation": canonical_all_confirmation(result["count"]),
                },
            )
        return None

    def approved_many(self, command: str, result: Any) -> Completion:
        window = self.window
        if result["project_id"] != window.current_project_id or result["request_token"] != (
            window.approve_all_token if command == "approve_all" else window.approve_selection_token
        ):
            return STOP
        if command == "approve_all":
            window.approve_all_button.setEnabled(True)
            window.approve_all_token = None
        window.refresh()
        window.refresh_installation()
        window.bridge.submit("policies")
        window.review_details.setText(
            tr("Approved {p0} selected translations.", p0=f"{result['approved']}")
        )
        return None

    def page_loaded(self, command: str, result: Any) -> Completion:
        window = self.window
        if (
            result.get("project_id") != window.current_project_id
            or result.get("request_token") != window.page_token
        ):
            return STOP
        window.page_pending = False
        window.offset = result["offset"]
        window.review_count = result["count"]
        window.previous_page.setEnabled(window.offset > 0)
        window.next_page.setEnabled(window.offset + len(result["rows"]) < result["count"])
        window.project_totals = result.get("totals")
        adapters = set(result.get("source_adapters", ()))
        window.renpy_available = bool({"renpy-templates", "renpy-scripts"} & set(adapters))
        window.renpy_export_group.setVisible(window.renpy_available)
        window.export_note.setVisible(not window.renpy_available)
        window.update_renpy_actions()
        window.textasset_export_button.setEnabled("krypta-textassets" in adapters)
        window.runtime_export_button.setEnabled(
            adapters in ({"i2"}, {"krypta-textassets"})
        )
        eligible = (window.project_totals or {}).get("pilot_eligible", 0)
        window.pilot_button.setEnabled(eligible > 0 and not window.job_preparing)
        window.pilot_button.setToolTip(
            "" if eligible else tr(
                "No untranslated records remain. Review or export existing translations."
            )
        )
        shareable = result.get("shareable_available", True)
        window.shareable_available = shareable
        window.shareable_note.setVisible(not shareable and not window.renpy_available)
        window.shareable_export_button.setVisible(not window.renpy_available)
        window.shareable_export_button.setEnabled(shareable)
        window.shareable_export_button.setToolTip(
            "" if shareable else tr(
                "Shareable installation ZIPs are unavailable for this source adapter. "
                "Use approved game-text export; it is not an installation package."
            )
        )
        if not eligible and not window.current_job and not window.job_preparing:
            window.job_status.setText(tr(
                "No untranslated records remain. Review or export existing translations."
            ))
        window.update_next_step()
        window.draft_refresh_pending = False
        selected = window.current_item["unit_id"] if window.current_item else None
        # Restoring the selection is not a user choice; the last local review summary stays.
        window.restoring_selection = True
        try:
            window.review_model.set_rows(result["rows"])
            window.retranslate_page_button.setEnabled(
                bool(result["rows"]) and window.job_combo.isEnabled()
            )
            window.selection_changed()
            if selected is not None:
                for index, row in enumerate(result["rows"]):
                    if row["unit_id"] == selected:
                        window.table.selectRow(index)
                        break
        finally:
            window.restoring_selection = False
        window.page_label.setText(
            tr(
                "{p0} records · {p2}–{p4}",
                p0=f"{result['count']}",
                p2=f"{(result['offset'] + 1 if result['rows'] else 0)}",
                p4=f"{result['offset'] + len(result['rows'])}",
            )
        )
        if window.category_filter.count() == 1:
            window.category_filter.blockSignals(True)
            for category in result["categories"]:
                window.category_filter.addItem(category, category)
            window.category_filter.blockSignals(False)
            window.style_category.blockSignals(True)
            for category in result["categories"]:
                if window.style_category.findData(category) < 0:
                    window.style_category.addItem(category, category)
            window.style_category.blockSignals(False)
        return None

    def history_loaded(self, command: str, result: Any) -> Completion:
        window = self.window
        from unitytranslator.ui.window import CandidateHistoryDialog

        dialog = CandidateHistoryDialog(result, window)
        if dialog.exec() and dialog.chosen:
            window.bridge.submit(
                "select_candidate",
                {
                    "unit_id": result["unit_id"],
                    "version": result["current"]["version"],
                    "revision": dialog.chosen,
                    "replace_approved": dialog.replace.isChecked(),
                },
            )
        return None

    def quality_audited(self, command: str, result: Any) -> Completion:
        window = self.window
        window.review_details.setText(
            tr(
                (
                    "Checked {p0} translations; {p2} records have warnings. "
                    "Record states and approvals are preserved.\n"
                ),
                p0=f"{result['audited_current_translations']}",
                p2=f"{result['flagged_records']}",
            )
            + (
                tr(
                    "{p0} records have local reviewer codes (model suggestions, unverified).",
                    p0=f"{result['local_review_records']}",
                ) + "\n"
                if result.get("local_review_records")
                else ""
            )
            + result["html_path"]
        )
        window.export_status.setPlainText(
            tr("Recheck reports:\n") + result["html_path"] + "\n" + result["json_path"]
        )
        return None

    def record_changed(self, command: str, result: Any) -> Completion:
        window = self.window
        window.refresh()
        window.refresh_installation()
        if command == "approve":
            window.bridge.submit("policies")
        return None
