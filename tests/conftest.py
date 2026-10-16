"""Keep existing Turkish UI regression expectations independent of user preferences."""

import os

import pytest

os.environ.setdefault("UNITYTRANSLATOR_UI_LANGUAGE", "tr")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def retain_qt_application():
    """Keep one QApplication alive until all UI objects and threads finish teardown."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        yield
        return
    app = QApplication.instance() or QApplication([])
    yield
    app.closeAllWindows()
    app.processEvents()
