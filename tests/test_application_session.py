import asyncio
import sqlite3
import threading

import pytest
from test_repository import draft

from unitytranslator.application import ApplicationSession
from unitytranslator.game_process import GameProcessStatus


def test_cancel_selected_paused_job_without_active_task_preserves_existing_work(tmp_path):
    from test_jobs import profile

    from unitytranslator.jobs import JobStore

    game = tmp_path / "game"
    game.mkdir()

    async def run():
        session = ApplicationSession()
        try:
            await session.dispatch(
                "open", {"game": str(game), "project": str(tmp_path / "project")}
            )
            session.repo.ingest([draft()], {})
            store = JobStore(session.repo)
            job = store.create(["UI/start"], profile())
            store.pause(job)
            assert store.job(job)["status"] == "paused" and session.jobs.active_job is None
            await session.dispatch("cancel", {"job_id": job})
            assert store.progress(job)["status"] == "cancelled"
            assert store.progress(job)["counts"] == {"cancelled": 1}
            assert session.repo.page()[0]["source_text"] == "Start"
        finally:
            await session.close()

    asyncio.run(run())


def test_existing_project_opens_without_reentering_game_and_bad_selection_preserves_session(
    tmp_path,
):
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"

    async def run():
        session = ApplicationSession()
        try:
            original = await session.dispatch("open", {"game": str(game), "project": str(project)})
            session.repo.ingest([draft()], {})
            with pytest.raises(ValueError, match="kayıtlı proje bulunamadı"):
                await session.dispatch(
                    "open", {"project": str(tmp_path / "missing"), "existing_only": True}
                )
            assert not (tmp_path / "missing").exists()
            assert session.repo.project_id == original["project_id"]
            assert len(session.repo.page()) == 1
            # Valid paths but invalid existing DB must not close the previous project either.
            invalid = tmp_path / "invalid"
            invalid.mkdir()
            (invalid / "project.sqlite3").write_bytes(b"not a database")
            with pytest.raises(sqlite3.DatabaseError):
                await session.dispatch("open", {"game": str(game), "project": str(invalid)})
            assert len(session.repo.page()) == 1
            await session.close()
            reopened = await session.dispatch(
                "open", {"project": str(project), "existing_only": True}
            )
            assert reopened["project_id"] == original["project_id"]
            assert reopened["game_path"] == str(game.resolve())
            assert len(session.repo.page()) == 1
        finally:
            await session.close()

    asyncio.run(run())


def test_manual_backup_reopens_with_approved_translation_and_unsaved_editor_draft(tmp_path):
    from unitytranslator.editor_drafts import EditorDraftStore

    game = tmp_path / "game"
    game.mkdir()

    async def run():
        session, restored = ApplicationSession(), ApplicationSession()
        try:
            await session.dispatch(
                "open", {"game": str(game), "project": str(tmp_path / "project")}
            )
            session.repo.ingest([draft()], {})
            row = session.repo.page()[0]
            session.repo.edit(row["unit_id"], row["version"], "Başla")
            session.repo.approve(row["unit_id"], session.repo.page()[0]["version"])
            approved = session.repo.page()[0]
            drafts = EditorDraftStore(session.repo)
            drafts.put(
                row["unit_id"],
                approved["source_revision"],
                approved["version"],
                "Başlangıç taslağı",
                0,
            )
            saved_draft = drafts.get(row["unit_id"])
            backup = await session.dispatch("backup", {})
            await restored.dispatch("open", {"project": backup["folder"], "existing_only": True})
            assert restored.repo.page()[0] == approved
            assert restored.repo.page()[0]["status"] == "approved"
            assert EditorDraftStore(restored.repo).get(row["unit_id"]) == saved_draft
            assert session.repo.page()[0] == approved
            assert list(game.iterdir()) == []
        finally:
            await restored.close()
            await session.close()

    asyncio.run(run())


def test_game_process_query_returns_captured_project_when_user_changes_session(
    tmp_path, monkeypatch
):
    game = tmp_path / "game"
    game.mkdir()
    second = tmp_path / "second-game"
    second.mkdir()
    started, release = threading.Event(), threading.Event()
    paths = []

    def inspect(path):
        paths.append(path)
        started.set()
        assert release.wait(5)
        return GameProcessStatus("closed")

    monkeypatch.setattr("unitytranslator.application.inspect_game_processes", inspect)

    async def run():
        session = ApplicationSession()
        try:
            first = await session.dispatch(
                "open", {"game": str(game), "project": str(tmp_path / "project")}
            )
            task = asyncio.create_task(
                session.dispatch("game_process", {"request_token": "first-request"})
            )
            assert await asyncio.to_thread(started.wait, 5)
            later = await session.dispatch(
                "open", {"game": str(second), "project": str(tmp_path / "second-project")}
            )
            release.set()
            result = await task
            assert result["project_id"] == first["project_id"] != later["project_id"]
            assert result["request_token"] == "first-request"
            assert result["status"] == "closed" and result["observed_at"]
            assert paths == [game.resolve()]
        finally:
            release.set()
            await session.close()

    asyncio.run(run())


def test_editor_draft_commands_require_bound_project_and_use_common_commit(tmp_path):
    game = tmp_path / "game"
    game.mkdir()

    async def run():
        session = ApplicationSession()
        try:
            opened = await session.dispatch(
                "open", {"game": str(game), "project": str(tmp_path / "project")}
            )
            session.repo.ingest([draft()], {})
            row = session.repo.page()[0]
            data = {
                "project_id": opened["project_id"],
                "unit_id": row["unit_id"],
                "source_revision": row["source_revision"],
                "base_version": row["version"],
                "text": "Başla",
            }
            with pytest.raises(ValueError, match="proje kimliği"):
                await session.dispatch("editor_draft_put", {**data, "project_id": "other"})
            response = await session.dispatch("editor_draft_put", data)
            saved = response["draft"]
            assert session.repo.page()[0] == row
            assert (await session.dispatch("editor_draft_get", data))["draft"] == saved
            await session.dispatch(
                "editor_draft_commit", {**data, "expected_revision": saved["revision"]}
            )
            assert session.repo.page()[0]["translation"] == "Başla"
            assert session.repo.page()[0]["status"] != "approved"
            assert (await session.dispatch("editor_draft_get", data))["draft"] is None
        finally:
            await session.close()

    asyncio.run(run())
