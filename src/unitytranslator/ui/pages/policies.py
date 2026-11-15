"""Glossary page: translation policies."""

from typing import Any

from unitytranslator.language import DEFAULT_STYLE
from unitytranslator.ui.i18n import tr
from unitytranslator.ui.pages.base import Completion, PageController


class PoliciesController(PageController):
    """Complete Glossary page results."""

    COMMANDS = {
        "policies": "policies_loaded",
        "set_policies": "policies_saved",
    }

    def policies_loaded(self, command: str, result: Any) -> Completion:
        window = self.window
        window.glossary.setRowCount(0)
        for value in result["glossary"]:
            window.add_rule(value)
        window.styles = result["styles"].copy()
        if not window.styles:
            window.styles = {"default": DEFAULT_STYLE}
        window.style_editor.setPlainText(window.styles.get(window.style_key, ""))
        window.impact_note.setText(
            tr(
                (
                    "{p0} records affected by policy changes; regeneration "
                    "requires user action. Approved text is preserved."
                ),
                p0=f"{len(result['impacted'])}",
            )
        )
        window.affected_job_button.setEnabled(bool(result["impacted"]))
        return None

    def policies_saved(self, command: str, result: Any) -> Completion:
        window = self.window
        window.bridge.submit("policies")
        window.schedule_bulk_readiness()
        return None
