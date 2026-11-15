"""Per-page controllers that complete backend command results for MainWindow."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from unitytranslator.ui.pages.base import STOP, Completion, Page, PageController
from unitytranslator.ui.pages.export import ExportController
from unitytranslator.ui.pages.installation import InstallationController
from unitytranslator.ui.pages.model import ModelController
from unitytranslator.ui.pages.policies import PoliciesController
from unitytranslator.ui.pages.project import ProjectController
from unitytranslator.ui.pages.review import ReviewController
from unitytranslator.ui.pages.translation import TranslationController

if TYPE_CHECKING:
    from unitytranslator.ui.window import MainWindow

__all__ = [
    "CONTROLLERS", "STOP", "Completion", "CompletionRegistry", "Page", "PageController",
]

type Handler = Callable[[str, Any], Completion]

CONTROLLERS: tuple[type[PageController], ...] = (
    ProjectController,
    ModelController,
    PoliciesController,
    TranslationController,
    ReviewController,
    ExportController,
    InstallationController,
)


class CompletionRegistry:
    """Map each completed command to exactly one page controller handler."""

    def __init__(self, window: "MainWindow") -> None:
        self.controllers = tuple(controller(window) for controller in CONTROLLERS)
        self.commands: dict[str, Handler] = {}
        self.prefixes: list[tuple[str, Handler]] = []
        for controller in self.controllers:
            # CONTROLLERS is fixed source data, so a clash is a programming error.
            for command, name in controller.COMMANDS.items():
                assert command not in self.commands, f"duplicate completion handler: {command}"
                self.commands[command] = getattr(controller, name)
            for prefix, name in controller.PREFIXES.items():
                assert not any(command.startswith(prefix) for command in self.commands), (
                    f"completion prefix overlaps a command: {prefix}"
                )
                self.prefixes.append((prefix, getattr(controller, name)))

    def handler(self, command: str) -> Handler | None:
        handler = self.commands.get(command)
        if handler is not None:
            return handler
        for prefix, prefixed in self.prefixes:
            if command.startswith(prefix):
                return prefixed
        return None
