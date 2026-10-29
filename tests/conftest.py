"""Keep existing Turkish UI regression expectations independent of user preferences."""

import gc
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
    # Process deleteLater events while Python wrappers and the application are alive.
    # Leaving these objects to interpreter shutdown can abort inside Qt on Windows.
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import delete, isValid

    gc.collect()
    for widget in app.topLevelWidgets():
        if isValid(widget):
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()
    delete(app)
