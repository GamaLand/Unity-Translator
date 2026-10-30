import asyncio
from dataclasses import replace

import pytest
from test_jobs import profile
from test_repository import draft

from unitytranslator.application import ApplicationSession
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore
from unitytranslator.policy import PolicyStore
from unitytranslator.repository import ProjectRepository
from unitytranslator.review_selection import apply_matching_review, matching_review_preview


@pytest.fixture
def matching_repo(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft(key=f"UI/{i:03}", text=f"Hello {i}") for i in range(210)], {})
        yield repo


def test_identical_approval_spans_pages_and_preserves_other_translations(matching_repo):
    repo = matching_repo
    for offset in (0, 200):
        for row in repo.page(offset):
            repo.edit(row["unit_id"], row["version"], row["source_text"])
    first, second, third = repo.page()[:3]
    repo.edit(first["unit_id"], first["version"], first["source_text"] + " ")
    repo.approve(second["unit_id"], second["version"])
    EditorDraftStore(repo).put(
        third["unit_id"], third["source_revision"], third["version"], "Draft", 0,
    )
    before = repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0]
    preview = matching_review_preview(repo, "approve_identical", {})
    assert preview["count"] == 207 and len(preview["samples"]) == 20
    assert apply_matching_review(repo, preview, user_action=True) == 207
    assert repo.count(status="approved") == 208
    assert repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == before
    assert list(repo.paths.game.iterdir()) == []


def test_empty_reset_preserves_history_approvals_drafts_and_jobs(matching_repo):
    repo = matching_repo
    rows = repo.page()
    for row in rows[:7]:
        repo.db.execute("UPDATE work_items SET status='needs_review' WHERE unit_id=?",
                        (row["unit_id"],))
    # A legacy whitespace revision is retained as history after removing its current pointer.
    row = rows[0]
    repo.edit(row["unit_id"], row["version"], "Synthetic")
    revision = repo.page()[0]["translation_revision"]
    repo.db.execute("UPDATE translation_revisions SET text=? WHERE id=?", (" \n\u2003", revision))
    row = rows[1]
    repo.edit(row["unit_id"], row["version"], "Hello")
    current = repo.page()[1]
    repo.approve(current["unit_id"], current["version"])
    row = rows[2]
    EditorDraftStore(repo).put(row["unit_id"], row["source_revision"], row["version"], "Draft", 0)
    JobStore(repo).create([rows[3]["unit_id"]], profile())
    repo.db.execute("UPDATE work_items SET status='processing' WHERE unit_id=?",
                    (rows[4]["unit_id"],))
    preview = matching_review_preview(repo, "reset_empty", {"status": "needs_review"})
    assert preview["count"] == 3
    assert apply_matching_review(repo, preview, user_action=True) == 3
    assert repo.page()[0]["translation_revision"] is None
    assert repo.page()[0]["status"] == "pending"
    assert repo.db.execute(
        "SELECT text FROM translation_revisions WHERE id=?", (revision,),
    ).fetchone()[0] == " \n\u2003"
    assert repo.page()[1]["status"] == "approved"
    assert repo.page()[2]["status"] == "needs_review"
    assert repo.page()[3]["status"] == "needs_review"
    assert repo.page()[4]["status"] == "processing"
    job = JobStore(repo).create([rows[0]["unit_id"]], profile())
    assert JobStore(repo).job(job)["status"] == "queued"


@pytest.mark.parametrize("change", ["revision", "draft", "membership", "policy", "queue"])
def test_preview_changes_fail_atomically(matching_repo, change):
    repo = matching_repo
    for row in repo.page()[:2]:
        repo.edit(row["unit_id"], row["version"], row["source_text"])
    preview = matching_review_preview(repo, "approve_identical", {})
    row = repo.page()[1]
    if change == "revision":
        repo.edit(row["unit_id"], row["version"], "Different")
    elif change == "draft":
        EditorDraftStore(repo).put(
            row["unit_id"], row["source_revision"], row["version"], "Draft", 0,
        )
    elif change == "membership":
        row = repo.page()[2]
        repo.edit(row["unit_id"], row["version"], row["source_text"])
    elif change == "policy":
        PolicyStore(repo).set_styles({"default": "Formal"})
    else:
        JobStore(repo).create([row["unit_id"]], profile(), retranslate=True)
    with pytest.raises(ValueError, match="changed"):
        apply_matching_review(repo, preview, user_action=True)
    assert repo.count(status="approved") == 0


def test_filters_are_preserved_and_comparisons_are_exact(matching_repo):
    repo = matching_repo
    repo.ingest([
        draft("UI/other", "Hello"),
        replace(draft("Other/key", "Hello"), category="dialogue"),
    ], {})
    for row in repo.page():
        repo.edit(row["unit_id"], row["version"], row["source_text"])
    PolicyStore(repo).set_styles({"dialogue": "Formal"})
    preview = matching_review_preview(repo, "approve_identical", {
        "search": "HELLO", "category": "dialogue", "status": "needs_review", "affected": True,
    })
    assert preview["count"] == 1
    with pytest.raises(ValueError, match="confirmation"):
        apply_matching_review(repo, preview, user_action=False)
    assert apply_matching_review(repo, preview, user_action=True) == 1
    assert not PolicyStore(repo).impacted()


def test_session_preview_identity_single_use_and_no_model_requests(tmp_path):
    game = tmp_path / "game"
    game.mkdir()

    async def run():
        session = ApplicationSession()
        try:
            await session.dispatch(
                "open", {"game": str(game), "project": str(tmp_path / "project")}
            )
            session.repo.ingest([draft()], {})
            session.repo.db.execute("UPDATE work_items SET status='needs_review'")
            data = {"project_id": session.repo.project_id, "request_token": "ui"}
            with pytest.raises(ValueError, match="identity"):
                await session.dispatch("matching_review_preview", {
                    **data, "project_id": "other", "action": "reset_empty", "filters": {},
                })
            preview = await session.dispatch("matching_review_preview", {
                **data, "action": "reset_empty", "filters": {},
            })
            assert "records" not in preview and preview["count"] == 1
            confirmed = {**data, "token": preview["token"], "user_action": True}
            assert (await session.dispatch("matching_review_apply", confirmed))["changed"] == 1
            with pytest.raises(ValueError, match="expired"):
                await session.dispatch("matching_review_apply", confirmed)
            assert session.repo.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        finally:
            await session.close()

    asyncio.run(run())


def test_compact_menu_previews_current_filters_and_requires_confirmation(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from test_ui import wait_for

    from unitytranslator.ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        submitted = []
        with monkeypatch.context() as patch:
            patch.setattr(window.bridge, "submit", lambda *args: submitted.append(args))
            window.project_open = True
            window.current_project_id = "synthetic-project"
            window.status_filter.setCurrentIndex(window.status_filter.findData("needs_review"))
            window.search.setText("Hello")
            window.affected_filter.setChecked(True)
            assert len(window.bulk_review_menu.actions()) == 2
            window.bulk_review_menu.actions()[0].trigger()
            command, data = submitted[-1]
            assert command == "matching_review_preview" and data["action"] == "approve_identical"
            assert data["filters"] == {
                "search": "Hello", "status": "needs_review", "category": None, "affected": True,
            }
            result = {**data, "token": "server", "count": 205, "excluded": 2, "samples": []}
            patch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.No)
            submitted.clear()
            window.completed("matching_review_preview", result)
            assert submitted == [] and window.matching_review_token is None
            window.bulk_review_menu.actions()[1].trigger()
            command, data = submitted[-1]
            assert data["action"] == "reset_empty"
            patch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
            window.completed("matching_review_preview", {**result, **data})
            assert submitted[-1] == ("matching_review_apply", {
                "project_id": "synthetic-project", "request_token": data["request_token"],
                "token": "server", "user_action": True,
            })
    finally:
        window.search_timer.stop()
        window.bulk_timer.stop()
        window.close()
        wait_for(app, lambda: window.backend_closed)
