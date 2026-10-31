"""Preparation cancellation must reach a busy backend without queued event-loop work."""

import asyncio
import sqlite3
import threading
import time

import pytest
from test_repository import draft

from unitytranslator.domain import GenerationProfile, OperationCancelled
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore
from unitytranslator.repository import ProjectRepository
from unitytranslator.ui.bridge import BackendBridge


def profile():
    return GenerationProfile("llama-cpp", "http://localhost:8080", "synthetic", 8192)


def profile_data():
    return {key: value for key, value in profile().to_dict().items()
            if key not in ("glossary_version", "style_version")}


def open_bridge(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    paths = ProjectPaths(game, tmp_path / "project")
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
    bridge = BackendBridge()
    asyncio.run_coroutine_threadsafe(bridge.session.dispatch("open", {
        "game": str(game), "project": str(paths.project),
    }), bridge.loop).result(timeout=5)
    return bridge


def blocked_selection(entered):
    def select(repo):
        entered.set()
        while not repo.operation_cancelled():
            time.sleep(0.005)
        repo.check_cancelled()
    return select


@pytest.mark.parametrize("sql", [False, True])
def test_shutdown_interrupts_busy_preparation_before_backend_can_process_close(
    tmp_path, monkeypatch, sql,
):
    import unitytranslator.application as module

    entered = threading.Event()
    def slow_sql(repo):
        entered.set()
        repo.db.execute(
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n "
            "WHERE x<10000000) SELECT sum(x) FROM n"
        ).fetchone()
        return []

    monkeypatch.setattr(module, "select_pilot", slow_sql if sql else blocked_selection(entered))
    bridge = open_bridge(tmp_path)
    try:
        prepared = bridge.submit("create_job", {"kind": "pilot", "profile": profile_data()})
        assert entered.wait(timeout=5)
        bridge.shutdown()
        bridge.thread.join(timeout=3)
        assert not bridge.thread.is_alive()
        assert prepared.done()
        assert bridge.session.repository is None
    finally:
        if bridge.thread.is_alive():
            bridge.shutdown()
            bridge.thread.join(timeout=3)


@pytest.mark.parametrize("before_start", [False, True])
def test_cancelling_preparation_does_not_cancel_previously_selected_job(
    tmp_path, monkeypatch, before_start,
):
    import unitytranslator.application as module

    bridge = open_bridge(tmp_path)
    try:
        original = asyncio.run_coroutine_threadsafe(bridge.session.dispatch("create_job", {
            "kind": "prototype", "profile": profile_data(), "units": ["UI/start"],
        }), bridge.loop).result(timeout=5)
        entered = threading.Event()
        release = threading.Event()
        monkeypatch.setattr(module, "select_pilot", blocked_selection(entered))
        if before_start:
            def hold_backend():
                entered.set()
                release.wait(timeout=3)

            bridge.loop.call_soon_threadsafe(hold_backend)
            assert entered.wait(timeout=5)
        preparing = bridge.submit("create_job", {"kind": "pilot", "profile": profile_data()})
        assert entered.wait(timeout=5)
        cancelled = bridge.submit("cancel", {"job_id": original["job_id"]})
        release.set()
        cancelled.result(timeout=3)
        preparing.result(timeout=3)
        jobs = asyncio.run_coroutine_threadsafe(
            bridge.session.dispatch("jobs", {}), bridge.loop,
        ).result(timeout=3)
        assert len(jobs) == 1 and jobs[0]["status"] == "queued"
    finally:
        bridge.shutdown()
        bridge.thread.join(timeout=3)
        assert not bridge.thread.is_alive()


def test_cancelled_queue_transaction_leaves_no_job_or_changed_work(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft()], {})
        before = repo.page()
        stop = threading.Event()
        repo.operation_cancelled = stop.is_set
        repo.db.set_trace_callback(
            lambda sql: stop.set() if sql.startswith("INSERT INTO jobs(") else None,
        )
        with pytest.raises(OperationCancelled):
            JobStore(repo).create(["UI/start"], profile())
        repo.db.set_trace_callback(None)
        assert repo.page() == before
        assert repo.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_shutdown_during_resumed_cold_context_settles_job_without_model_requests(
    tmp_path, monkeypatch,
):
    from test_dialogue_context import ingest
    from test_dialogue_context import profile as context_profile

    import unitytranslator.dialogue_context as module

    game = tmp_path / "game"
    game.mkdir()
    paths = ProjectPaths(game, tmp_path / "project")
    with ProjectRepository(paths) as repo:
        snapshot = ingest(repo)
        job = JobStore(repo).create([u.unit_id for u in snapshot.units], context_profile())
    entered = threading.Event()

    def context(source, metadata, *, cancelled):
        entered.set()
        while not cancelled():
            time.sleep(0.005)
        raise OperationCancelled("Synthetic cooperative cancellation")

    monkeypatch.setattr(module, "snapshot_windows", context)
    bridge = BackendBridge()
    try:
        asyncio.run_coroutine_threadsafe(bridge.session.dispatch("open", {
            "project": str(paths.project), "existing_only": True,
        }), bridge.loop).result(timeout=5)
        future = bridge.submit("run_job", {"job_id": job})
        assert entered.wait(timeout=5)
        bridge.shutdown()
        bridge.thread.join(timeout=3)
        assert not bridge.thread.is_alive() and future.done()
    finally:
        if bridge.thread.is_alive():
            bridge.shutdown()
            bridge.thread.join(timeout=3)
    with sqlite3.connect(paths.project / "project.sqlite3") as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (job,)).fetchone()[0] == "cancelled"
        assert db.execute("SELECT status FROM translation_runs").fetchall() == [("cancelled",)]
        assert db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == 0
