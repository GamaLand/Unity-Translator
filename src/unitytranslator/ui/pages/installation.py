"""Apply to game page: deployment commands."""

from typing import Any

from unitytranslator.ui.i18n import diagnostic, tr
from unitytranslator.ui.pages.base import STOP, Completion, PageController


class InstallationController(PageController):
    """Complete Apply to game page results."""

    PREFIXES = {"deployment_": "deployment"}

    def deployment(self, command: str, result: Any) -> Completion:
        window = self.window
        from unitytranslator.ui.window import InstallationReviewDialog

        expected_token = (
            window.deployment_status_token
            if command == "deployment_status"
            else window.deployment_token
        )
        if (
            result["project_id"] != window.current_project_id
            or result["request_token"] != expected_token
            or window.closing
        ):
            return STOP
        if command != "deployment_status":
            window.setEnabled(True)
        if command == "deployment_status":
            window.deployment = result["deployment"]
            window.installation_kit_available = result["kit_available"]
            window.update_next_step()
            active = bool(window.deployment and window.deployment["status"] != "removed")
            window.prepare_installation.setEnabled(
                result["kit_available"] and result["approved"] > 0 and not active
            )
            window.remove_installation.setEnabled(active)
            window.installation_log.setEnabled(not result["baseline_exists"])
            window.installation_log_reviewed.setEnabled(not result["baseline_exists"])
            window.installation_state.setText(
                (tr("Installation recorded. ") if active else tr("No active installation. "))
                + tr("{p0} current approved translations. ", p0=f"{result['approved']}")
                + (
                    tr(
                        "Experimental Krypta FM installation is available. "
                        "Remaining screens and text layout require in-game review."
                    ) if result.get("adapter_kind") == "krypta" and result["kit_available"]
                    else diagnostic(result["kit_reason"])
                )
            )
            if result["exclusions"]:
                window.installation_log.setText(
                    ", ".join(item["path"] for item in result["exclusions"])
                )
            if window.deployment and not window.installation_details.toPlainText():
                window.installation_details.setPlainText(
                    tr("Status: ")
                    + {
                        "installed": tr("Active (experimental)"),
                        "removed": tr("Removed"),
                        "installing": tr("Partial installation"),
                        "recovery_required": tr("Recovery required"),
                    }.get(window.deployment["status"], window.deployment["status"])
                    + "\n"
                    + "\n".join(item["target"] for item in window.deployment["files"])
                )
        elif command == "deployment_prepare":
            dialog = InstallationReviewDialog(result, window)
            if dialog.exec() and dialog.reviewed.isChecked():
                window.setEnabled(False)
                window.installation_state.setText(
                    tr("Checking installation and original file hashes…")
                )
                window.bridge.submit(
                    "deployment_install",
                    {
                        "project_id": window.current_project_id,
                        "request_token": window.deployment_token,
                        "review_id": result["review_id"],
                        "user_action": True,
                        "experimental_reviewed": True,
                    },
                )
            else:
                window.refresh_installation()
        else:
            if command == "deployment_install":
                window.installation_details.setPlainText(
                    tr(
                        "Installation completed; original files are unchanged. Start "
                        "the game with your usual launcher. Runtime files remain in "
                        "the project folder; do not move the project while installed."
                    )
                )
            else:
                window.installation_details.setPlainText(
                    tr(
                        (
                            "Removed additions: {p1}; preserved additions: {p3}. Changed "
                            "original files: {p5}. Translations remain in the project "
                            "folder.\n"
                        ),
                        p1=f"{len(result['removed'])}",
                        p3=f"{len(result['preserved'])}",
                        p5=f"{len(result['original_changes'])}",
                    )
                    + "\n".join(result["preserved"])
                )
            window.refresh_installation()
        return None
