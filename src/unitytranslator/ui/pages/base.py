"""Shared workflow page identifiers and the base class for page controllers."""

from enum import IntEnum
from typing import TYPE_CHECKING, ClassVar, Final

if TYPE_CHECKING:
    from unitytranslator.ui.window import MainWindow


class Page(IntEnum):
    """Workflow page indexes in sidebar and tab order."""

    PROJECT = 0
    SOURCES = 1
    MODEL = 2
    POLICIES = 3
    TRANSLATION = 4
    REVIEW = 5
    EXPORT = 6
    INSTALLATION = 7


class _Stop:
    def __repr__(self) -> str:
        return "STOP"


# A handler returns STOP where the completion ends early, for example for a stale request
# token; MainWindow.completed then skips the common status-bar message.
STOP: Final = _Stop()

# What a completion handler returns: STOP, or None to show the common status-bar message.
type Completion = _Stop | None


class PageController:
    """Complete backend results for one workflow page.

    ``COMMANDS`` maps exact command names and ``PREFIXES`` maps command-name prefixes to
    handler method names. Handlers take ``(command, result)`` and act on the window.
    """

    COMMANDS: ClassVar[dict[str, str]] = {}
    PREFIXES: ClassVar[dict[str, str]] = {}

    def __init__(self, window: "MainWindow") -> None:
        self.window = window
