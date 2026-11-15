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


# Per-test hard timeout without an extra dependency. faulthandler's native watchdog fires even
# while the main thread is blocked in native code or a child process, writes every thread's
# stack to the original stderr and ends the run with exit status 1, so a hung test fails fast
# instead of consuming the CI job limit. The limit covers setup, call and teardown. Override it
# for one test with @pytest.mark.test_timeout(seconds), or for a run with the
# UNITYTRANSLATOR_TEST_TIMEOUT environment variable; 0 disables it. It is also disabled under a
# debugger or tracer. Do not combine it with pytest's faulthandler_timeout option.
DEFAULT_TEST_TIMEOUT_SECONDS = 120.0
_TIMEOUT_STDERR = pytest.StashKey[int]()


def pytest_configure(config: pytest.Config) -> None:
    import contextlib
    import sys

    config.addinivalue_line(
        "markers", "test_timeout(seconds): per-test hard timeout in seconds; 0 disables it."
    )
    if sys.__stderr__ is None:
        return
    # Keep a duplicate of the real stderr; captured output is lost when the watchdog exits.
    capture = config.pluginmanager.getplugin("capturemanager")
    released = capture.global_and_fixture_disabled() if capture else contextlib.nullcontext()
    with released:
        config.stash[_TIMEOUT_STDERR] = os.dup(sys.__stderr__.fileno())


def pytest_unconfigure(config: pytest.Config) -> None:
    descriptor = config.stash.get(_TIMEOUT_STDERR, None)
    if descriptor is not None:
        del config.stash[_TIMEOUT_STDERR]
        os.close(descriptor)


def _test_timeout(item: pytest.Item) -> float:
    marker = item.get_closest_marker("test_timeout")
    if marker is not None:
        if len(marker.args) != 1 or marker.kwargs:
            raise pytest.UsageError(f"{item.nodeid}: use @pytest.mark.test_timeout(seconds).")
        return float(marker.args[0])
    configured = os.environ.get("UNITYTRANSLATOR_TEST_TIMEOUT", "").strip()
    return float(configured) if configured else DEFAULT_TEST_TIMEOUT_SECONDS


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> object:
    import faulthandler
    import sys

    seconds = _test_timeout(item)
    descriptor = item.config.stash.get(_TIMEOUT_STDERR, None)
    armed = seconds > 0 and descriptor is not None and sys.gettrace() is None
    if armed:
        faulthandler.dump_traceback_later(seconds, exit=True, file=descriptor)
    try:
        return (yield)
    finally:
        if armed:
            faulthandler.cancel_dump_traceback_later()
