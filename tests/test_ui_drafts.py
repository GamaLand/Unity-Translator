import asyncio
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from test_repository import draft  # noqa: E402
from test_ui import wait_for  # noqa: E402

from unitytranslator.editor_drafts import EditorDraftStore  # noqa: E402
from unitytranslator.filesystem import ProjectPaths  # noqa: E402
from unitytranslator.repository import ProjectRepository  # noqa: E402
from unitytranslator.ui.drafts import DraftController  # noqa: E402
from unitytranslator.ui.window import MainWindow  # noqa: E402


class FakeBridge(QObject):
    completed = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.requests = []

    def submit(self, command, data):
        self.requests.append((command, data))


def test_autosave_coalesces_inflight_text_and_ignores_wrong_response():
    QApplication.instance() or QApplication([])
    bridge = FakeBridge()
    controller = DraftController(bridge)
    controller.reset("project")
    row = {
        "unit_id": "unit",
        "source_revision": "source",
        "version": 0,
        "source_text": "Start",
        "translation": None,
    }
    controller.update(row, "Bir")
    controller.flush()
    first = bridge.requests[0][1]
    controller.update(row, "İki")
    controller.update(row, "Son çğıİöşü")
    controller.flush()
    assert len(bridge.requests) == 1
    response = {
        "project_id": "project",
        "unit_id": "unit",
        "request_token": first["request_token"],
        "draft": {"revision": 1},
    }
    bridge.completed.emit("editor_draft_put", {**response, "request_token": "old"})
    assert len(bridge.requests) == 1 and controller.pending is not None
    bridge.completed.emit("editor_draft_put", response)
    assert len(bridge.requests) == 2
    last = bridge.requests[1][1]
    assert last["text"] == "Son çğıİöşü" and last["expected_revision"] == 1
    bridge.completed.emit(
        "editor_draft_put",
        {**response, "request_token": last["request_token"], "draft": {"revision": 2}},
    )
    assert controller.settled
    assert controller.entries["unit"]["text"] == "Son çğıİöşü"


@pytest.fixture
def opened(tmp_path):
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        repo.ingest([draft("UI/one", "Start {0}\r\nNext"), draft("UI/two")], {})
    window = MainWindow()
    window.game_path.setText(str(game))
    window.project_path.setText(str(project))
    window.show()
    window.open_project()
    wait_for(app, lambda: window.project_open and window.review_model.rowCount() == 2)
    window.tabs.setCurrentIndex(5)
    window.table.selectRow(0)
    yield app, window, game, project
    if not window.backend_closed:
        window.close()
        wait_for(app, lambda: window.backend_closed)


def test_draft_survives_navigation_refresh_immediate_close_and_reopen(opened):
    app, window, game, project = opened
    text = "Yarım {\r\nçğıİöşü\u00a0"
    window.translation_editor.setPlainText(text)
    window.table.selectRow(1)
    window.table.selectRow(0)
    assert window.translation_editor.value() == text
    pages = []
    window.bridge.completed.connect(
        lambda command, result: pages.append(result["request_token"]) if command == "page" else None
    )
    window.refresh()
    token = window.page_token
    wait_for(app, lambda: window.drafts.settled and window.current_item is not None)
    wait_for(app, lambda: token in pages)
    assert window.translation_editor.value() == text
    window.translation_editor.setPlainText(text + " son")
    window.close()  # Debounce süresi geçmeden kapanış.
    wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        saved = EditorDraftStore(repo).get("UI/one")
        assert saved["text"] == text + " son"
        assert repo.page()[0]["translation"] is None
        assert repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == 0
    reopened = MainWindow()
    reopened.game_path.setText(str(game))
    reopened.project_path.setText(str(project))
    reopened.show()
    reopened.open_project()
    try:
        wait_for(app, lambda: reopened.project_open and reopened.review_model.rowCount() == 2)
        reopened.table.selectRow(0)
        assert reopened.translation_editor.value() == text + " son"
        assert "yerelde saklandı" in reopened.draft_status.text()
    finally:
        reopened.close()
        wait_for(app, lambda: reopened.backend_closed)


def test_source_change_keeps_old_source_and_draft_until_explicit_discard(opened, monkeypatch):
    app, window, game, project = opened
    text = "Başla {0}\r\nSonraki"
    window.translation_editor.setPlainText(text)
    window.drafts.flush()
    wait_for(app, lambda: window.drafts.settled)

    # Kuyruktaki işlemi backend IO thread'inde yürüt; UI doğrudan SQL yazmaz.
    async def update_source():
        window.bridge.session.repo.ingest([draft("UI/one", "Changed {1}")], {})

    future = asyncio.run_coroutine_threadsafe(update_source(), window.bridge.loop)
    future.result(timeout=5)
    window.refresh()
    wait_for(app, lambda: window.current_item["source_text"] == "Changed {1}")
    assert window.translation_editor.value() == text
    assert window.source_editor.toPlainText() == "Start {0}\nNext"
    assert "Eski kaynak" in window.draft_status.text()
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[-1]))
    window.save_edit()
    wait_for(app, lambda: bool(messages))
    assert "taslak korundu" in messages[0]
    assert window.translation_editor.value() == text
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.discard_current_draft()
    wait_for(
        app, lambda: not window.draft_refresh_pending and window.translation_editor.value() == ""
    )
    assert window.source_editor.toPlainText() == "Changed {1}"
    window.close()
    wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        assert EditorDraftStore(repo).get("UI/one") is None
        assert repo.page()[0]["translation"] is None


def test_project_switch_flushes_pending_draft_before_changing_session(opened, tmp_path):
    app, window, game, project = opened
    window.translation_editor.setPlainText("Yarım taslak {\r\nİı")
    other_game = tmp_path / "other-game"
    other_game.mkdir()
    other_project = tmp_path / "other-project"
    old_id = window.current_project_id
    window.game_path.setText(str(other_game))
    window.project_path.setText(str(other_project))
    window.open_project()
    wait_for(app, lambda: window.current_project_id != old_id and window.isEnabled())
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        assert EditorDraftStore(repo).get("UI/one")["text"] == "Yarım taslak {\r\nİı"
    assert window.drafts.entries == {}


def test_autosave_error_keeps_text_and_prevents_shutdown_until_retry(opened, monkeypatch):
    app, window, game, project = opened
    original_put = EditorDraftStore.put
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[-1]))

    def fail(*args, **kwargs):
        raise OSError("synthetic draft storage failure")

    monkeypatch.setattr(EditorDraftStore, "put", fail)
    window.translation_editor.setPlainText("Yarım {\r\nİlk")
    window.drafts.flush()
    wait_for(app, lambda: bool(messages))
    assert window.translation_editor.value() == "Yarım {\r\nİlk"
    window.close()
    app.processEvents()
    assert not window.backend_closed and not window.closing and window.isEnabled()
    assert "saklanamadı" in window.draft_status.text()
    monkeypatch.setattr(EditorDraftStore, "put", original_put)
    window.translation_editor.insertPlainText(" son")
    window.close()
    wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        assert EditorDraftStore(repo).get("UI/one") is not None
        assert "son" in EditorDraftStore(repo).get("UI/one")["text"]


def test_autosaving_draft_does_not_clear_manual_approval(opened):
    app, window, game, project = opened

    async def approve():
        repo = window.bridge.session.repo
        repo.edit("UI/one", 0, "Başla {0}\r\nSonraki")
        repo.approve("UI/one", repo.page()[0]["version"])

    asyncio.run_coroutine_threadsafe(approve(), window.bridge.loop).result(timeout=5)
    window.refresh()
    wait_for(app, lambda: window.current_item["status"] == "approved")
    window.translation_editor.setPlainText("Yarım yeni {\r\nçğıİöşü")
    window.drafts.flush()
    wait_for(app, lambda: window.drafts.settled)
    assert window.current_item["status"] == "approved"
    output = project.parent / "ui-drafts.png"
    assert window.grab().save(str(output))
    window.close()
    wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        assert repo.page()[0]["status"] == "approved"
        assert repo.page()[0]["translation"] == "Başla {0}\r\nSonraki"
        assert EditorDraftStore(repo).get("UI/one")["text"] == "Yarım yeni {\r\nçğıİöşü"
