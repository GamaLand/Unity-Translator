import asyncio
import os
import threading
import time
from pathlib import Path

import pytest
from test_repository import draft

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtGui import QFontMetrics, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from unitytranslator.domain import GenerationProfile  # noqa: E402
from unitytranslator.filesystem import ProjectPaths  # noqa: E402
from unitytranslator.game_process import GameProcessStatus  # noqa: E402
from unitytranslator.jobs import JobStore  # noqa: E402
from unitytranslator.portable import PortableService  # noqa: E402
from unitytranslator.repository import ProjectRepository  # noqa: E402
from unitytranslator.ui.text_editor import DataTextEdit  # noqa: E402
from unitytranslator.ui.window import (  # noqa: E402
    CandidateHistoryDialog,
    MainWindow,
    PluralEditorDialog,
    ReviewModel,
)
from unitytranslator.validation import format_issues  # noqa: E402

PLURAL_SOURCE = "{[COUNT]} turns[i2p_Zero]No turns[i2p_One]{[COUNT]} turn"
PLURAL_TARGET = "{[COUNT]} tur[i2p_Zero]Tur yok[i2p_One]{[COUNT]} tur"


def test_resume_and_new_job_send_current_model_selection(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window.provider.setCurrentIndex(window.provider.findData("llama-cpp"))
        window.model.setCurrentText("synthetic-llama-model")
        window.current_job = "saved-lm-studio-job"
        window.tabs.setTabEnabled(4, True)
        submitted = []
        with monkeypatch.context() as patch:
            patch.setattr(window.bridge, "submit", lambda *args: submitted.append(args))
            window.resume_button.setEnabled(True)
            window.resume_button.click()
            assert submitted[-1] == ("run_job", {
                "job_id": "saved-lm-studio-job",
                "parallel_requests": 1,
                "model_selection": window.model_data(),
            })
            window.completed("create_job", {"job_id": "new-job", "count": 1})
            assert submitted[-1][0] == "run_job"
            selection = submitted[-1][1]["model_selection"]
            assert selection["provider"] == "llama-cpp"
            assert selection["address"] == "http://127.0.0.1:8080"
            assert selection["model"] == "synthetic-llama-model"
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)


def test_translation_continues_minimized_without_gui_event_processing(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    paths = ProjectPaths(game, project)
    with ProjectRepository(paths) as repo:
        repo.ingest([draft(key=f"UI/{index}") for index in range(8)], {})
        job = JobStore(repo).create(
            [row["unit_id"] for row in repo.page()],
            GenerationProfile("lm-studio", "http://localhost:1234", "synthetic", 8192),
        )
    started = threading.Event()
    release = threading.Event()

    async def translate(self, *args, **kwargs):
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return {"translation": "Başla", "issues": []}

    monkeypatch.setattr("unitytranslator.providers.LocalProvider.translate_record", translate)
    window = MainWindow()
    results = {}
    window.bridge.completed.connect(lambda command, result: results.update({command: result}))
    window.show()
    window.game_path.setText(str(game))
    window.project_path.setText(str(project))
    window.open_project()
    try:
        wait_for(app, lambda: window.project_open)
        future = window.bridge.submit("run_job", {"job_id": job, "parallel_requests": 4})
        wait_for(app, started.is_set)
        window.showMinimized()
        app.processEvents()
        assert window.isMinimized()
        release.set()
        # Deliberately do not pump Qt: persistence must not depend on window paints/timers.
        future.result(timeout=5)
        window.showNormal()
        wait_for(app, lambda: window.job_progress.value() == 8)
        assert "8/8" in window.job_status.text()
        window.on_progress({**results["run_job"], "status": "paused", "pause_reason": "timeout"})
        assert "Otomatik duraklatıldı" in window.job_status.text()
    finally:
        release.set()
        window.close()
        wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(paths) as repo:
        assert JobStore(repo).progress(job)["counts"] == {"completed": 8}


@pytest.mark.parametrize(
    "status,phrase",
    [
        ("closed", "kapalı olarak gözlendi"),
        ("running", "Oyun çalışıyor"),
        ("unknown", "kapalı olduğu doğrulanamadı"),
    ],
)
def test_ui_game_process_check_is_local_and_ignores_old_request_results(
    tmp_path, monkeypatch, status, phrase
):
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    inspected = []

    def inspect(path):
        inspected.append(path)
        return GameProcessStatus(status)

    monkeypatch.setattr("unitytranslator.application.inspect_game_processes", inspect)
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.game_path.setText(str(game))
    window.project_path.setText(str(project))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: window.project_open)
        window.check_game_process()
        wait_for(app, lambda: phrase in window.game_process_status.text())
        assert inspected == [game.resolve()]
        assert "kurulum/onay değildir" in window.game_process_status.text()
        if status == "closed":
            window.tabs.setCurrentIndex(1)
            app.processEvents()
            output = Path(".cache/ui-game-process.png")
            output.parent.mkdir(exist_ok=True)
            assert window.grab().save(str(output))
        current = window.game_process_status.text()
        stale = {
            "status": "running",
            "reason": "",
            "observed_at": "old",
            "project_id": window.current_project_id,
            "request_token": "previous-request",
        }
        window.completed("game_process", stale)
        assert window.game_process_status.text() == current
        stale.update(project_id="previous-project", request_token=window.game_process_token)
        window.completed("game_process", stale)
        assert window.game_process_status.text() == current
        assert errors == []
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)


def test_data_editor_preserves_untouched_and_edited_newlines_and_unicode_spaces():
    QApplication.instance() or QApplication([])
    original = "A\r\nB\rC\nD\u00a0E\u2028F\u2029G"
    editor = DataTextEdit()
    editor.setPlainText(original)
    assert editor.toPlainText() != original  # Gerçek Qt normalleştirmesi.
    assert editor.value() == original
    assert not editor.acceptRichText()
    editor.moveCursor(QTextCursor.MoveOperation.End)
    editor.insertPlainText(" yeni")
    assert editor.value() == original + " yeni"


def test_new_target_uses_source_newlines_and_changed_line_count_still_fails():
    QApplication.instance() or QApplication([])
    editor = DataTextEdit(reference="A\r\nB")
    editor.insertPlainText("Bir\nİki")
    assert editor.value() == "Bir\r\nİki"
    editor.insertPlainText("\nÜç")
    assert format_issues("A\r\nB", editor.value())


def test_plural_dialog_preserves_per_branch_newline_encoding():
    QApplication.instance() or QApplication([])
    source = "{[N]} turns\r\nNext[i2p_One]{[N]} turn\rNext"
    target = "{[N]} tur\r\nSonraki[i2p_One]{[N]} tur\rSonraki"
    dialog = PluralEditorDialog(source, target)
    dialog.edits["One"].moveCursor(QTextCursor.MoveOperation.End)
    dialog.edits["One"].insertPlainText(" metin")
    dialog.transfer.click()
    assert dialog.value == target + " metin"


def test_ui_can_approve_crlf_translation_without_inventing_a_manual_edit(tmp_path):
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    target = "Başla {0}\r\nSonraki\u00a0satır"
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        repo.ingest([draft(text="Start {0}\r\nNext line")], {})
        repo.edit("UI/start", 0, target)
        revisions = repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0]
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.game_path.setText(str(game))
    window.project_path.setText(str(project))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: window.project_open and window.review_model.rowCount() == 1)
        window.table.selectRow(0)
        assert window.translation_editor.value() == target
        window.approve()
        wait_for(app, lambda: window.review_model.rows[0]["status"] == "approved")
        assert errors == []
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        assert repo.page()[0]["translation"] == target
        assert (
            repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == revisions
        )


def test_plural_dialog_preserves_source_order_and_rejects_broken_variables():
    app = QApplication.instance() or QApplication([])
    dialog = PluralEditorDialog(PLURAL_SOURCE, PLURAL_TARGET)
    assert list(dialog.edits) == ["Plural", "Zero", "One"]
    assert [dialog.tabs.tabText(i) for i in range(3)] == [
        "Varsayılan (çoğul)",
        "Sıfır (0)",
        "Tekil (1)",
    ]
    assert all(field.isReadOnly() for field in dialog.sources.values())
    assert dialog.transfer.isEnabled()
    dialog.edits["One"].setPlainText("Bir tur")
    assert not dialog.transfer.isEnabled()
    dialog.edits["One"].setPlainText("{[COUNT]} tur sürer")
    dialog.show()
    app.processEvents()
    dialog.tabs.setCurrentIndex(2)
    app.processEvents()
    dialog.transfer.click()
    assert dialog.value == "{[COUNT]} tur[i2p_Zero]Tur yok[i2p_One]{[COUNT]} tur sürer"
    dialog.close()


def test_plural_dialog_blank_cancel_and_stale_record_keep_edits():
    app = QApplication.instance() or QApplication([])
    dialog = PluralEditorDialog(PLURAL_SOURCE, "", is_current=lambda: False)
    assert not dialog.transfer.isEnabled()
    assert "Her dal" in dialog.feedback.text()
    for form in dialog.edits:
        dialog.edits[form].setPlainText(dialog.sources[form].toPlainText())
    dialog.show()
    app.processEvents()
    dialog.transfer.click()
    assert dialog.isVisible() and dialog.value is None
    assert "Ana kayıt veya taslak değişti" in dialog.feedback.text()
    assert dialog.edits["One"].toPlainText() == "{[COUNT]} turn"
    dialog.reject()
    assert dialog.value is None


def test_plural_dialog_does_not_silently_replace_malformed_unsaved_text():
    QApplication.instance() or QApplication([])
    with pytest.raises(ValueError):
        PluralEditorDialog(PLURAL_SOURCE, "Taslak[i2p_One]Tekil")


def test_plural_edit_transfers_unsaved_draft_then_explicit_save_clears_approval(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        repo.ingest([draft(text=PLURAL_SOURCE)], {})
        repo.edit("UI/start", 0, PLURAL_TARGET)
        repo.approve("UI/start", repo.page()[0]["version"])
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.game_path.setText(str(game))
    window.project_path.setText(str(project))
    window.show()
    window.open_project()

    def edit_dialog(dialog):
        assert dialog.edits["One"].toPlainText() == "{[COUNT]} tur"
        dialog.edits["One"].setPlainText("{[COUNT]} tur sürer")
        dialog.tabs.setCurrentIndex(2)
        dialog.show()
        app.processEvents()
        output = Path(".cache/ui-plural-editor.png")
        output.parent.mkdir(exist_ok=True)
        assert dialog.grab().save(str(output))
        dialog.transfer.click()
        return dialog.result()

    monkeypatch.setattr(PluralEditorDialog, "exec", edit_dialog)
    try:
        wait_for(app, lambda: window.project_open and window.review_model.rowCount() == 1)
        window.table.selectRow(0)
        assert window.plural_button.isEnabled()
        window.plural_button.click()
        assert window.translation_editor.toPlainText().endswith("{[COUNT]} tur sürer")
        assert window.current_item["status"] == "approved"
        assert window.review_model.rows[0]["translation"] == PLURAL_TARGET
        window.save_edit()
        wait_for(app, lambda: window.review_model.rows[0]["translation"] != PLURAL_TARGET)
        assert window.review_model.rows[0]["status"] == "needs_review"
        assert errors == []
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        row = repo.page()[0]
        assert row["translation"].endswith("{[COUNT]} tur sürer")
        assert repo.db.execute("SELECT approved_translation FROM work_items").fetchone()[0] is None


def test_review_table_explains_quality_warning_in_turkish() -> None:
    app = QApplication.instance() or QApplication([])
    model = ReviewModel()
    model.set_rows([{"issues_json": '["negation_content_review","mechanical_condition_review"]'}])
    text = model.data(model.index(0, 5))
    assert "Olumsuzluk" in text and "Koşul" in text
    assert "negation_content_review" not in text
    app.processEvents()


def wait_for(app, predicate, timeout=10):
    started = time.monotonic()
    while not predicate():
        app.processEvents()
        if time.monotonic() - started > timeout:
            raise AssertionError("UI işlemi zamanında tamamlanmadı")
        time.sleep(0.01)
    app.processEvents()


def test_ui_project_paging_manual_approval_and_export(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        repo.ingest([draft(f"UI/{index:05}") for index in range(601)], {})
    window = MainWindow()
    assert all(QFontMetrics(app.font()).inFontUcs4(ord(character)) for character in "çğıİöşü")
    errors = []
    results = {}
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.bridge.completed.connect(lambda command, result: results.update({command: result}))
    window.show()
    window.game_path.setText(str(game))
    window.project_path.setText(str(project))
    window.open_project()
    try:
        wait_for(app, lambda: window.project_open and window.review_model.rowCount() == 200)
        assert len(window.review_model.rows) == 200
        assert "601 kayıt" in window.page_label.text()
        window.tabs.setCurrentIndex(5)
        window.table.selectRow(0)
        window.translation_editor.setPlainText("Başla · Iıİi çğöşü")
        window.save_edit()
        wait_for(app, lambda: window.review_model.rows[0]["translation"] == "Başla · Iıİi çğöşü")
        window.table.selectRow(0)
        window.approve()
        wait_for(app, lambda: window.review_model.rows[0]["status"] == "approved")
        assert window.current_item["status"] == "approved"
        window.bridge.submit("quality_audit")
        wait_for(app, lambda: "quality_audit" in results)
        assert results["quality_audit"]["audited_current_translations"] == 1
        assert Path(results["quality_audit"]["html_path"]).is_file()
        assert window.review_model.rows[0]["status"] == "approved"
        assert "onaylar korunmuştur" in window.review_details.text()
        window.change_page(200)
        wait_for(app, lambda: window.review_model.rows[0]["original_key"] == "UI/00200")
        assert window.review_model.rowCount() == 200
        assert window.source_editor.isReadOnly()
        window.bridge.submit("export")
        wait_for(app, lambda: "export" in results)
        assert Path(results["export"]).is_file()
        window.change_page(-200)
        wait_for(app, lambda: window.review_model.rows[0]["original_key"] == "UI/00000")
        window.table.selectRow(0)
        output = Path(".cache/ui-review.png")
        output.parent.mkdir(exist_ok=True)
        assert window.grab().save(str(output))
        assert errors == []
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        assert repo.page()[0]["status"] == "approved"
        assert repo.page()[0]["translation"] == "Başla · Iıİi çğöşü"


def test_ui_restore_previews_empty_project_and_preserves_imported_review(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "source")) as repo:
        repo.ingest([draft()], {})
        repo.edit("UI/start", 0, "Başla")
        repo.approve("UI/start", repo.page()[0]["version"])
        exported = PortableService(repo).export()
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.game_path.setText(str(game))
    window.project_path.setText(str(tmp_path / "target"))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: window.project_open)
        window.import_path = str(exported)
        window.bridge.submit("import_preview", {"path": str(exported)})
        wait_for(app, lambda: window.restore_button.isEnabled())
        window.restore_button.click()
        wait_for(app, lambda: window.review_model.rowCount() == 1)
        assert window.review_model.rows[0]["translation"] == "Başla"
        assert window.review_model.rows[0]["status"] != "approved"
        assert not window.restore_button.isEnabled()
        assert errors == []
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)


def test_history_dialog_does_not_select_new_candidate_over_approval_without_choice(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft()], {})
        repo.edit("UI/start", 0, "Elle onay")
        repo.approve("UI/start", repo.page()[0]["version"])
        current = repo.page()[0]
        repo.candidate(
            "UI/start",
            current["source_revision"],
            current["version"],
            "Model adayı",
            "model",
            {"model": "synthetic"},
            [],
        )
        history = repo.history("UI/start")
        dialog = CandidateHistoryDialog(history)
        index = next(i for i, row in enumerate(history["revisions"]) if row["origin"] == "model")
        dialog.combo.setCurrentIndex(index)
        app.processEvents()
        assert dialog.translation.toPlainText() == "Model adayı"
        assert not dialog.use.isEnabled()
        dialog.replace.setChecked(True)
        assert dialog.use.isEnabled()
        dialog.use.click()
        assert dialog.chosen == history["revisions"][index]["id"]
        assert repo.page()[0]["status"] == "approved"
        dialog.close()
