"""Model page: model list and connection test."""

from typing import Any

from unitytranslator.ui.i18n import tr
from unitytranslator.ui.pages.base import Completion, PageController


class ModelController(PageController):
    """Complete Model page results."""

    COMMANDS = {
        "models": "models_listed",
        "connection_test": "connection_tested",
    }

    def models_listed(self, command: str, result: Any) -> Completion:
        window = self.window
        previous_model = window.model.currentText()
        window.model.clear()
        for model in result:
            window.model.addItem(model["id"], model)
        previous_index = window.model.findText(previous_model)
        if previous_index >= 0:
            window.model.setCurrentIndex(previous_index)
        window.model_status.setText(
            tr("Model list received. Loaded state: ")
            + ", ".join(
                f"{item['id']}: "
                + {True: tr("Loaded"), False: tr("Not loaded")}.get(
                    item["loaded"], "bilinmiyor"
                )
                for item in result
            )
        )
        return None

    def connection_tested(self, command: str, result: Any) -> Completion:
        window = self.window
        window.model_status.setText(
            tr(
                (
                    "Generation and format check passed: {p1}. No human quality "
                    "approval was granted."
                ),
                p1=f"{result['translation']}",
            )
        )
        return None
