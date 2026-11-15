"""Review > Bulk actions > Run local reviewer: confirmation, codes shown apart, no approval.

The fake OpenAI-compatible server runs on the backend's own event loop on 127.0.0.1.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from test_local_review import FakeServer, verdict
from test_repository import draft
from test_ui import wait_for

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from unitytranslator.filesystem import ProjectPaths  # noqa: E402
from unitytranslator.local_review import STOP_OUT_OF_MEMORY  # noqa: E402
from unitytranslator.repository import ProjectRepository  # noqa: E402
from unitytranslator.ui.i18n import diagnostic, tr  # noqa: E402
from unitytranslator.ui.local_review import review_lines  # noqa: E402
from unitytranslator.ui.window import CandidateHistoryDialog, MainWindow  # noqa: E402


def test_review_action_confirms_runs_and_shows_codes_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    folder = tmp_path / "project"
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        repo.ingest([draft("UI/a", "Start"), draft("UI/b", "Options")], {})
        repo.edit("UI/a", 0, "Başla")
        repo.edit("UI/b", 0, "Seçenekler")
    shown: list[str] = []

    def confirm(self: QMessageBox) -> QMessageBox.StandardButton:
        shown.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", confirm)
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    server = FakeServer()
    asyncio.run_coroutine_threadsafe(server.__aenter__(), window.bridge.loop).result(10)
    window.game_path.setText(str(game))
    window.project_path.setText(str(folder))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: window.project_open and window.review_model.rowCount() == 2)
        window.provider.setCurrentIndex(window.provider.findData("llama-cpp"))
        window.address.setText(f"http://127.0.0.1:{server.port}")
        window.model.setCurrentText("synthetic")
        actions = [a.text() for a in window.bulk_review_menu.actions()]
        assert tr("Run local reviewer…") in actions
        assert not window.local_review_cancel_action.isEnabled()
        window.preview_local_review()
        wait_for(app, lambda: bool(window.review_model.rows[0].get("local_reviews")))
        assert shown and f"http://127.0.0.1:{server.port}/v1" in shown[0]
        assert "synthetic" in shown[0]
        assert tr(
            "The local reviewer only adds issue codes to the current translations. It never "
            "edits text, approves, changes a status or removes a check. Codes stay with the "
            "reviewed revision; editing or replacing the text leaves them behind."
        ) in shown[0]
        wait_for(app, lambda: not window.local_review_running)
        checks = window.review_model.columns.index(
            next(c for c in window.review_model.columns if c[0] == "issues_json")
        )
        cell = window.review_model.data(window.review_model.index(0, checks))
        assert tr("Local reviewer: meaning") in cell and tr("Local reviewer: tone") in cell
        window.table.selectRow(0)
        app.processEvents()
        assert tr(
            "Local reviewer {p0} ({p1}): {p2}", p0="synthetic", p1="review-v1",
            p2="; ".join([tr("Local reviewer: meaning"), tr("Local reviewer: tone")]),
        ) in window.review_details.text()
        assert [row["status"] for row in window.review_model.rows] == ["translated"] * 2
        assert window.local_review_token is None and window.local_review_action.isEnabled()
        assert errors == []
    finally:
        asyncio.run_coroutine_threadsafe(server.__aexit__(), window.bridge.loop).result(10)
        window.close()
        wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        assert [row["status"] for row in repo.page()] == ["translated", "translated"]
        assert repo.db.execute("SELECT count(*) FROM local_reviews").fetchone()[0] == 2


def test_history_dialog_lists_local_reviews_of_each_revision(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft("UI/a", "Start")], {})
        repo.edit("UI/a", 0, "Başla")
        history = repo.history("UI/a")
        history["revisions"][0]["local_reviews"] = [{
            "issues": ["grammar_review"], "note": "Spelling.", "model": "m",
            "prompt_version": "review-v1",
        }]
        dialog = CandidateHistoryDialog(history)
        details = dialog.details.toPlainText()
        for line in review_lines(history["revisions"][0]["local_reviews"]):
            assert line in details
        assert tr("Reviewer note (model output, unverified): {p0}", p0="Spelling.") in details
        dialog.close()


def open_window(
    app: QApplication, game: Path, folder: Path, server: FakeServer,
) -> tuple[MainWindow, list[tuple[str, Any]]]:
    window = MainWindow()
    errors: list[tuple[str, Any]] = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    asyncio.run_coroutine_threadsafe(server.__aenter__(), window.bridge.loop).result(10)
    window.game_path.setText(str(game))
    window.project_path.setText(str(folder))
    window.show()
    window.open_project()
    wait_for(app, lambda: window.project_open and window.review_model.rowCount() > 0)
    window.provider.setCurrentIndex(window.provider.findData("llama-cpp"))
    window.address.setText(f"http://127.0.0.1:{server.port}")
    window.model.setCurrentText("synthetic")
    return window, errors


def test_stop_reason_stays_visible_after_the_page_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    folder = tmp_path / "project"
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        repo.ingest([draft("UI/a", "Start"), draft("UI/b", "Options"), draft("UI/c", "Quit")], {})
        for key, text in (("UI/a", "Başla"), ("UI/b", "Seçenekler"), ("UI/c", "Çık")):
            repo.edit(key, 0, text)
    calls = 0

    async def respond(payload: dict[str, Any], request: dict[str, Any]) -> tuple[int, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return 200, verdict(request, ["grammar_review"])
        return 500, b"out of memory"

    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    server = FakeServer(respond)
    window, errors = open_window(app, game, folder, server)
    try:
        window.parallel_requests.setValue(1)
        window.table.selectRow(0)
        app.processEvents()
        assert window.current_item is not None and window.current_item["unit_id"] == "UI/a"
        window.preview_local_review()
        wait_for(app, lambda: window.local_review_summary is not None)
        # The handler refreshes the page; its selection restore must keep the summary.
        wait_for(app, lambda: not window.page_pending and bool(
            window.review_model.rows[0].get("local_reviews")
        ))
        reason = diagnostic(STOP_OUT_OF_MEMORY)
        details = window.review_details.text()
        assert reason in details and "out_of_memory" not in details
        assert tr(
            "Local reviewer: {p0}/{p1} records reviewed, {p2} with codes, {p3} failed, "
            "{p4} changed since the preview.", p0="1", p1="3", p2="1", p3="0", p4="0",
        ) in details
        # The restored record's own details are still shown above the summary.
        assert window.current_item is not None and window.current_item["unit_id"] == "UI/a"
        assert tr("Automated checks do not guarantee meaning; human review is required.") in (
            details
        )
        assert window.statusBar().currentMessage() == reason
        assert tr("Operation completed.") != window.statusBar().currentMessage()
        assert not window.local_review_running and window.local_review_action.isEnabled()
        # Another refresh keeps it; a selection by the user replaces it.
        window.refresh()
        wait_for(app, lambda: not window.page_pending)
        assert reason in window.review_details.text()
        window.table.selectRow(1)
        app.processEvents()
        assert window.local_review_summary is None
        assert reason not in window.review_details.text()
        # The recheck report mentions records with local reviewer codes.
        window.bridge.submit("quality_audit")
        wait_for(app, lambda: tr(
            "{p0} records have local reviewer codes (model suggestions, unverified).", p0="1",
        ) in window.review_details.text())
        assert errors == []
    finally:
        asyncio.run_coroutine_threadsafe(server.__aexit__(), window.bridge.loop).result(10)
        window.close()
        wait_for(app, lambda: window.backend_closed)


def test_nothing_to_review_informs_without_a_send_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    folder = tmp_path / "project"
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        repo.ingest([draft("UI/a", "Start"), draft("UI/b", "Options")], {})
    shown: list[tuple[str, Any, Any]] = []

    def answer(self: QMessageBox) -> QMessageBox.StandardButton:
        shown.append((self.text(), self.standardButtons(), self.icon()))
        return QMessageBox.StandardButton.Yes  # Even a Yes must not start a run.

    monkeypatch.setattr(QMessageBox, "exec", answer)
    server = FakeServer()
    window, errors = open_window(app, game, folder, server)
    submitted: list[str] = []
    submit = window.bridge.submit

    def record(command: str, *args: Any, **kwargs: Any) -> Any:
        submitted.append(command)
        return submit(command, *args, **kwargs)

    monkeypatch.setattr(window.bridge, "submit", record)
    try:
        window.preview_local_review()
        wait_for(app, lambda: bool(shown))
        app.processEvents()
        ((text, buttons, icon),) = shown
        assert tr("No current translations are left to review.") in text
        address = f"http://127.0.0.1:{server.port}/v1"
        assert tr(
            "Send {p0} records to the model {p1} on the already running server {p2}?",
            p0="0", p1="synthetic", p2=address,
        ) not in text
        assert buttons == QMessageBox.StandardButton.Ok
        assert icon == QMessageBox.Icon.Information
        assert "local_review_run" not in submitted and server.reviews == []
        assert window.local_review_token is None and not window.local_review_running
        assert window.local_review_action.isEnabled()
        # Opening a project drops any pending local review request of the previous one.
        window.local_review_token = "stale"
        window.local_review_summary = "Earlier summary."
        window.submit_open_project({"project": str(folder), "existing_only": True})
        assert window.local_review_token is None and window.local_review_summary is None
        wait_for(app, lambda: window.statusBar().currentMessage() == tr(
            "Project opened. Continue in Texts."
        ))
        assert errors == []
    finally:
        asyncio.run_coroutine_threadsafe(server.__aexit__(), window.bridge.loop).result(10)
        window.close()
        wait_for(app, lambda: window.backend_closed)
