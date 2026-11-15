"""Review shows translation memory candidates and their origin; nothing is approved."""

import os
from pathlib import Path

import pytest
from test_repository import draft
from test_ui import wait_for

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from unitytranslator.filesystem import ProjectPaths  # noqa: E402
from unitytranslator.repository import ProjectRepository  # noqa: E402
from unitytranslator.translation_memory import apply, preview  # noqa: E402
from unitytranslator.ui import window as window_module  # noqa: E402
from unitytranslator.ui.i18n import tr  # noqa: E402
from unitytranslator.ui.translation_memory import (  # noqa: E402
    TranslationMemoryOptionsDialog,
    summary_text,
)
from unitytranslator.ui.window import CandidateHistoryDialog, MainWindow  # noqa: E402


def project(tmp_path: Path) -> tuple[Path, Path]:
    game = tmp_path / "game"
    game.mkdir()
    folder = tmp_path / "project"
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        repo.ingest([draft("UI/a"), draft("UI/b"), draft("UI/c")], {})
        repo.edit("UI/a", 0, "Başla")
        repo.approve("UI/a", repo.page()[0]["version"])
        repo.edit("UI/c", 0, "Başlat")
    return game, folder


def test_history_dialog_labels_translation_memory_and_its_donor(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    game, folder = project(tmp_path)
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        apply(repo, preview(repo, include_translated=True), user_action=True)
        history = repo.history("UI/c")
        dialog = CandidateHistoryDialog(history)
        labels = [dialog.combo.itemText(i) for i in range(dialog.combo.count())]
        index = next(i for i, label in enumerate(labels) if tr("Translation memory") in label)
        dialog.combo.setCurrentIndex(index)
        assert (
            tr("Translation memory candidate from record {p0}; it is not approved.", p0="UI/a")
            in dialog.details.toPlainText()
        )
        assert dialog.translation.toPlainText() == "Başla"
        assert dialog.use.isEnabled()  # An explicit selection, never an approval.
        assert any(tr("Manual edit") in label for label in labels)
        dialog.close()
        assert repo.page()[2]["translation"] == "Başlat"


def test_review_action_previews_confirms_and_shows_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    game, folder = project(tmp_path)
    shown: list[str] = []

    def confirm(self: QMessageBox) -> QMessageBox.StandardButton:
        shown.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(window_module.TranslationMemoryOptionsDialog, "exec", lambda self: 1)
    monkeypatch.setattr(QMessageBox, "exec", confirm)
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.game_path.setText(str(game))
    window.project_path.setText(str(folder))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: window.project_open and window.review_model.rowCount() == 3)
        actions = [a.text() for a in window.bulk_review_menu.actions()]
        assert tr("Reuse translation memory…") in actions
        window.preview_translation_memory()
        wait_for(app, lambda: window.review_model.rows[1]["translation"] == "Başla")
        assert (
            shown
            and tr(
                "Matching keys: {p0}. Donors: {p1} approved, {p2} model.",
                p0="1",
                p1="1",
                p2="0",
            )
            in shown[0]
        )
        row = window.review_model.rows[1]
        assert row["status"] == "translated" and row["translation_origin"] == "translation_memory"
        assert window.review_model.rows[2]["translation"] == "Başlat"
        window.table.selectRow(1)
        app.processEvents()
        assert (
            tr("Translation memory candidate from record {p0}; it is not approved.", p0="UI/a")
            in window.review_details.text()
        )
        assert window.translation_memory_token is None and window.bulk_review_button.isEnabled()
        assert errors == []
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        assert [row["status"] for row in repo.page()] == ["approved", "translated", "translated"]


def test_summary_lists_every_skip_reason() -> None:
    text = summary_text(
        {
            "candidates": 0,
            "current": 0,
            "history": 0,
            "matches": 2,
            "donors": {"approved": 1, "model": 1},
            "conflicts": 1,
            "conflict_records": 3,
            "skipped": {
                "approved": 11,
                "draft": 12,
                "queued": 13,
                "translated": 14,
                "same_text": 15,
                "already_offered": 16,
                "format": 17,
            },
        }
    )
    # Each reason has its own value, so a swapped or missing field changes the line.
    assert text.splitlines()[-1] == tr(
        "Skipped: {p0} approved, {p1} drafts, {p2} queued in jobs, {p3} already "
        "translated, {p4} same text, {p5} already offered, {p6} format check.",
        p0="11",
        p1="12",
        p2="13",
        p3="14",
        p4="15",
        p5="16",
        p6="17",
    )


NOT_APPROVED = "Translation memory candidate from record {p0}; it is not approved."
APPROVED = "Translation memory candidate from record {p0}; approved by a reviewer."


def stored(folder: Path, game: Path) -> list[list[tuple]]:
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        return [
            [tuple(row) for row in repo.db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in ("work_items", "translation_revisions", "editor_drafts")
        ]


def test_history_notes_name_approval_only_for_the_approved_revision(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    game, folder = project(tmp_path)
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        apply(repo, preview(repo, include_translated=True), user_action=True)
        # UI/b approves its memory candidate; UI/c approves its own edit instead.
        for unit_id in ("UI/b", "UI/c"):
            version = next(r for r in repo.page() if r["unit_id"] == unit_id)["version"]
            repo.approve(unit_id, version)
        for unit_id, template in (("UI/b", APPROVED), ("UI/c", NOT_APPROVED)):
            dialog = CandidateHistoryDialog(repo.history(unit_id))
            labels = [dialog.combo.itemText(i) for i in range(dialog.combo.count())]
            index = next(i for i, label in enumerate(labels) if tr("Translation memory") in label)
            dialog.combo.setCurrentIndex(index)
            other = APPROVED if template == NOT_APPROVED else NOT_APPROVED
            assert tr(template, p0="UI/a") in dialog.details.toPlainText()
            assert tr(other, p0="UI/a") not in dialog.details.toPlainText()
            dialog.close()


def test_review_details_name_a_reviewer_approval_of_a_memory_candidate(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    game, folder = project(tmp_path)
    with ProjectRepository(ProjectPaths(game, folder)) as repo:
        apply(repo, preview(repo), user_action=True)
        repo.approve("UI/b", repo.page()[1]["version"])
    window = MainWindow()
    window.game_path.setText(str(game))
    window.project_path.setText(str(folder))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: window.project_open and window.review_model.rowCount() == 3)
        row = window.review_model.rows[1]
        assert row["status"] == "approved" and row["translation_origin"] == "translation_memory"
        window.table.selectRow(1)
        app.processEvents()
        assert tr(APPROVED, p0="UI/a") in window.review_details.text()
        assert tr(NOT_APPROVED, p0="UI/a") not in window.review_details.text()
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)


def test_options_dialog_states_the_whole_project_scope() -> None:
    QApplication.instance() or QApplication([])
    dialog = TranslationMemoryOptionsDialog()
    assert dialog.scope.text() == tr(
        "Applies to the whole project; review filters are ignored. Preview before applying."
    )
    dialog.close()


def test_declined_reuse_submits_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    game, folder = project(tmp_path)
    before = stored(folder, game)
    accept = {"options": 0}
    shown: list[str] = []

    def answer_no(self: QMessageBox) -> QMessageBox.StandardButton:
        shown.append(self.text())
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(
        window_module.TranslationMemoryOptionsDialog, "exec", lambda self: accept["options"]
    )
    monkeypatch.setattr(QMessageBox, "exec", answer_no)
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    commands: list[str] = []
    submit = window.bridge.submit

    def record(command: str, data: dict | None = None):
        commands.append(command)
        return submit(command, data)

    monkeypatch.setattr(window.bridge, "submit", record)
    window.game_path.setText(str(game))
    window.project_path.setText(str(folder))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: window.project_open and window.review_model.rowCount() == 3)
        # The action names its own scope; the other bulk actions follow the filters.
        tooltips = {a.text(): a.toolTip() for a in window.bulk_review_menu.actions()}
        assert tooltips[tr("Reuse translation memory…")] == tr(
            "Applies to the whole project; review filters are ignored. Preview before applying."
        )
        assert tooltips[tr("Return empty translations to pending…")] == tr(
            "Applies to all pages matching the current filters. Preview before applying."
        )
        # Cancelling the options dialog submits nothing.
        commands.clear()
        window.preview_translation_memory()
        app.processEvents()
        assert not any(c.startswith("translation_memory") for c in commands)
        assert window.translation_memory_token is None and window.bulk_review_button.isEnabled()
        # Answering No in the confirmation previews but never applies.
        accept["options"] = 1
        window.preview_translation_memory()
        assert window.translation_memory_token is not None
        assert not window.bulk_review_button.isEnabled()
        wait_for(app, lambda: bool(shown))
        app.processEvents()
        assert [c for c in commands if c.startswith("translation_memory")] == [
            "translation_memory_preview"
        ]
        assert window.translation_memory_token is None and window.bulk_review_button.isEnabled()
        assert window.review_model.rows[1]["translation"] is None
        assert errors == []
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
    assert stored(folder, game) == before
