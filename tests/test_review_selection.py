import asyncio
from dataclasses import asdict

import pytest
from test_repository import draft

from unitytranslator.application import ApplicationSession
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.repository import ProjectRepository
from unitytranslator.review_selection import all_approval_preview, approve_all, approve_selection


def test_all_approval_covers_more_than_a_page_and_preserves_existing_approvals(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft(key=f"UI/{i:04}") for i in range(205)], {})
        for offset in (0, 200):
            for row in repo.page(offset):
                repo.edit(row["unit_id"], row["version"], "Başla")
        first = repo.page()[0]
        repo.approve(first["unit_id"], first["version"])
        original = dict(repo.page()[0])
        row = repo.page()[1]
        EditorDraftStore(repo).put(
            row["unit_id"], row["source_revision"], row["version"], "Taslak", 0
        )
        preview = all_approval_preview(repo)
        assert preview["count"] == 203 and preview["excluded"] == 1
        assert (
            approve_all(repo, preview, user_action=True, confirmation="203 çeviriyi onayla") == 203
        )
        assert repo.count(status="approved") == 204
        assert repo.page()[0] == original
        assert list(game.iterdir()) == []


@pytest.mark.parametrize("change", ["text", "new", "draft"])
def test_all_approval_rejects_changed_preview_atomically(review_repo, change):
    repo = review_repo
    preview = all_approval_preview(repo)
    row = repo.page()[-1]
    if change == "text":
        repo.edit(row["unit_id"], row["version"], "Yeni çeviri")
    elif change == "new":
        repo.approve(row["unit_id"], row["version"])
    else:
        EditorDraftStore(repo).put(
            row["unit_id"], row["source_revision"], row["version"], "Taslak", 0
        )
    before = repo.count(status="approved")
    with pytest.raises(ValueError, match="değişti"):
        approve_all(repo, preview, user_action=True, confirmation="3 çeviriyi onayla")
    assert repo.count(status="approved") == before


def test_all_approval_session_requires_preview_token_and_exact_confirmation(review_repo):
    paths = review_repo.paths
    review_repo.close()

    async def run():
        session = ApplicationSession()
        try:
            result = await session.dispatch(
                "open", {"project": str(paths.project), "existing_only": True}
            )
            data = {"project_id": result["project_id"], "request_token": "ui-request"}
            preview = await session.dispatch("approve_all_preview", data)
            assert "records" not in preview and preview["count"] == 3
            with pytest.raises(ValueError):
                await session.dispatch(
                    "approve_all",
                    {
                        **data,
                        "token": preview["token"],
                        "user_action": True,
                        "confirmation": "onayla",
                    },
                )
            assert session.repo.count(status="approved") == 0
            preview = await session.dispatch("approve_all_preview", data)
            confirmed = {
                **data,
                "token": preview["token"],
                "user_action": True,
                "confirmation": "3 çeviriyi onayla",
            }
            assert (await session.dispatch("approve_all", confirmed))["approved"] == 3
            with pytest.raises(ValueError, match="geçersiz"):
                await session.dispatch("approve_all", confirmed)
        finally:
            await session.close()

    asyncio.run(run())


def test_all_approval_dialog_has_two_distinct_steps_and_safe_cancel():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QDialog

    from unitytranslator.ui.window import AllApprovalDialog

    QApplication.instance() or QApplication([])
    dialog = AllApprovalDialog({"count": 6749, "warnings": 7, "excluded": 2})
    assert not dialog.confirm.isEnabled()
    dialog.acknowledge.setChecked(True)
    dialog.confirm.click()
    assert dialog.stage == 2 and not dialog.confirm.isEnabled()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.confirmation.setText("6749")
    assert not dialog.confirm.isEnabled()
    dialog.confirmation.setText("6749 çeviriyi onayla")
    assert dialog.confirm.isEnabled()
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    dialog = AllApprovalDialog({"count": 6749, "warnings": 0, "excluded": 0})
    dialog.acknowledge.setChecked(True)
    dialog.confirm.click()
    dialog.confirmation.setText(dialog.phrase)
    dialog.confirm.click()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_all_approval_ui_cancel_then_confirm_updates_entire_project(tmp_path, monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QDialog
    from test_ui import wait_for

    from unitytranslator.ui.window import AllApprovalDialog, MainWindow

    game = tmp_path / "game"
    game.mkdir()
    paths = ProjectPaths(game, tmp_path / "project")
    with ProjectRepository(paths) as repo:
        repo.ingest([draft(key=f"UI/{i:04}") for i in range(201)], {})
        for offset in (0, 200):
            for row in repo.page(offset):
                repo.edit(row["unit_id"], row["version"], "Başla")
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    results, errors = {}, []
    window.bridge.completed.connect(lambda command, result: results.update({command: result}))
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    dialogs = []

    def interact(dialog):
        dialogs.append(dialog)
        assert dialog.phrase == "201 çeviriyi onayla"
        dialog.acknowledge.setChecked(True)
        dialog.confirm.click()
        if len(dialogs) == 1:
            dialog.reject()
            return QDialog.DialogCode.Rejected
        dialog.confirmation.setText(dialog.phrase)
        dialog.confirm.click()
        return dialog.result()

    monkeypatch.setattr(AllApprovalDialog, "exec", interact)
    try:
        window.submit_open_project({"project": str(paths.project), "existing_only": True})
        wait_for(app, lambda: window.project_open and window.review_model.rowCount() == 200)
        assert not window.approve_all_button.icon().isNull()
        window.approve_all_button.click()
        wait_for(app, lambda: len(dialogs) == 1 and window.approve_all_button.isEnabled())
        assert "approve_all" not in results
        assert window.review_model.rows[0]["status"] == "translated"
        window.approve_all_button.click()
        wait_for(app, lambda: "approve_all" in results or errors)
        assert not errors and results["approve_all"]["approved"] == 201
        wait_for(app, lambda: window.review_model.rows[0]["status"] == "approved")
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(paths) as repo:
        assert repo.count(status="approved") == 201


@pytest.fixture
def review_repo(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft(key="UI/" + str(i)) for i in range(3)], {})
        for row in repo.page():
            repo.edit(row["unit_id"], row["version"], "Başla")
        yield repo


def records(repo):
    return [
        {key: row[key] for key in ("unit_id", "source_revision", "translation_revision", "version")}
        for row in repo.page()
    ]


def test_group_approval_is_explicit_and_does_not_edit_translation_revisions(review_repo):
    repo = review_repo
    frozen = records(repo)
    for consent in (False, 1, "true"):
        with pytest.raises(ValueError, match="açık kullanıcı"):
            approve_selection(repo, frozen, user_action=consent, reviewed=True)
    with pytest.raises(ValueError, match="açık kullanıcı"):
        approve_selection(repo, frozen, user_action=True, reviewed=False)
    assert repo.count(status="approved") == 0
    assert approve_selection(repo, frozen, user_action=True, reviewed=True) == 3
    assert repo.count(status="approved") == 3
    assert [r["translation_revision"] for r in repo.page()] == [
        r["translation_revision"] for r in frozen
    ]
    assert list(repo.paths.game.iterdir()) == []


@pytest.mark.parametrize("change", ["version", "draft", "duplicate", "source"])
def test_group_approval_rejects_changed_selection_without_partial_approval(review_repo, change):
    repo = review_repo
    frozen = records(repo)
    row = repo.page()[-1]
    if change == "version":
        repo.edit(row["unit_id"], row["version"], "Yeni başlangıç")
    elif change == "draft":
        EditorDraftStore(repo).put(
            row["unit_id"], row["source_revision"], row["version"], "Taslak", 0
        )
    elif change == "source":
        repo.ingest([draft(key="UI/0"), draft(key="UI/1"), draft(key="UI/2", text="Continue")], {})
    else:
        frozen.append(dict(frozen[0]))
    with pytest.raises(ValueError):
        approve_selection(repo, frozen, user_action=True, reviewed=True)
    assert repo.count(status="approved") == 0


def test_bulk_readiness_survives_reopen_and_is_bound_to_profile_and_source(tmp_path):
    from test_jobs import FakeProvider, profile

    from unitytranslator.jobs import JobStore, TranslationJobService

    game = tmp_path / "game"
    game.mkdir()
    paths = ProjectPaths(game, tmp_path / "project")
    selected = profile()
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        job = store.create(["UI/start"], selected, "pilot")
        asyncio.run(TranslationJobService(repo, lambda _: FakeProvider()).run(job))
        store.acknowledge_pilot(job)

    async def run():
        session = ApplicationSession()
        try:
            opened = await session.dispatch(
                "open", {"project": str(paths.project), "existing_only": True}
            )
            data = {
                "project_id": opened["project_id"],
                "profile": {
                    key: value
                    for key, value in asdict(selected).items()
                    if key not in ("glossary_version", "style_version")
                },
                "request_token": "readiness",
            }
            assert (await session.dispatch("bulk_readiness", data))["allowed"]
            changed = {**data, "profile": {**data["profile"], "temperature": 0.7}}
            assert not (await session.dispatch("bulk_readiness", changed))["allowed"]
            session.repo.ingest([draft(text="Continue")], {})
            assert not (await session.dispatch("bulk_readiness", data))["allowed"]
        finally:
            await session.close()

    asyncio.run(run())


def test_group_review_dialog_requires_selection_and_reacknowledgement(review_repo):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from unitytranslator.ui.window import BatchReviewDialog

    QApplication.instance() or QApplication([])
    dialog = BatchReviewDialog(review_repo.page())
    assert dialog.records() == [] and not dialog.confirm.isEnabled()
    dialog.select_records(True)
    assert len(dialog.records()) == 3 and not dialog.confirm.isEnabled()
    dialog.reviewed.setChecked(True)
    assert dialog.confirm.isEnabled()
    dialog.table.item(2, 0).setCheckState(Qt.CheckState.Unchecked)
    assert len(dialog.records()) == 2 and not dialog.reviewed.isChecked()
    assert not dialog.confirm.isEnabled()
    assert review_repo.count(status="approved") == 0


def test_qt_bulk_button_restores_saved_pilot_gate_and_rechecks_setting_changes(tmp_path):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from test_jobs import FakeProvider, profile
    from test_ui import wait_for

    from unitytranslator.jobs import JobStore, TranslationJobService
    from unitytranslator.ui.window import MainWindow

    game = tmp_path / "game"
    game.mkdir()
    paths = ProjectPaths(game, tmp_path / "project")
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        job = JobStore(repo).create(["UI/start"], profile(), "pilot")
        asyncio.run(TranslationJobService(repo, lambda _: FakeProvider()).run(job))
        JobStore(repo).acknowledge_pilot(job)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    try:
        window.submit_open_project({"project": str(paths.project), "existing_only": True})
        wait_for(app, lambda: window.bulk_button.isEnabled() or errors)
        assert not errors
        window.temperature.setValue(0.7)
        assert not window.bulk_button.isEnabled()
        wait_for(app, lambda: "Toplu iş kapalı" in window.bulk_note.text())
        window.temperature.setValue(profile().temperature)
        wait_for(app, lambda: window.bulk_button.isEnabled() or errors)
        assert not errors
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
