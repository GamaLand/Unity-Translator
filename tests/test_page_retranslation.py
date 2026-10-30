import asyncio
from dataclasses import replace

import pytest
from test_jobs import FakeProvider, profile
from test_pilot_review import interrupted

from unitytranslator.application import ApplicationSession
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import TranslationJobService
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def prepared(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        store, pilot, _ = interrupted(repo, successful=1)
        store.acknowledge_pilot(pilot)
        yield repo, store, pilot


def selection(rows):
    return [{key: row[key] for key in (
        "unit_id", "source_revision", "version", "translation_revision",
    )} for row in rows]


def test_99_validation_errors_requeue_only_the_exact_page(prepared):
    repo, store, pilot = prepared
    rows = repo.page(status="validation_error")[:99]
    assert len(rows) == 99
    outside = [row for row in repo.page(limit=200) if row["unit_id"] not in {
        r["unit_id"] for r in rows
    }]
    original_attempts = [tuple(row) for row in repo.db.execute(
        "SELECT * FROM translation_runs WHERE job_id=?", (pilot,),
    )]
    session = ApplicationSession()
    session.repository = repo
    fake = FakeProvider()
    session.jobs = TranslationJobService(repo, lambda _: fake)
    settings = {k: v for k, v in profile().to_dict().items()
                if k not in ("glossary_version", "style_version")}

    async def run():
        created = await session.dispatch("create_page_job", {
            "project_id": repo.project_id, "records": selection(rows), "profile": settings,
        })
        assert created["count"] == 99
        assert repo.page(status="validation_error")[:99] == rows
        result = await session.dispatch("run_job", {
            "job_id": created["job_id"], "parallel_requests": 8,
        })
        assert result["counts"] == {"completed": 99}
        assert len(fake.requests) == 99
        selected = {row[0] for row in repo.db.execute(
            "SELECT unit_id FROM job_items WHERE job_id=?", (created["job_id"],),
        )}
        assert selected == {row["unit_id"] for row in rows}

    asyncio.run(run())
    assert [row for row in repo.page(limit=200) if row["unit_id"] in {
        r["unit_id"] for r in outside
    }] == outside
    assert [tuple(row) for row in repo.db.execute(
        "SELECT * FROM translation_runs WHERE job_id=?", (pilot,),
    )] == original_attempts


@pytest.mark.parametrize("change", ["version", "source", "draft", "processing", "inactive"])
def test_page_revalidation_is_atomic(prepared, change):
    repo, store, _ = prepared
    rows = repo.page(status="validation_error")[:2]
    frozen = selection(rows)
    row = rows[-1]
    if change == "version":
        repo.edit(row["unit_id"], row["version"], "Manual edit")
    elif change == "draft":
        EditorDraftStore(repo).put(row["unit_id"], row["source_revision"], row["version"], "Draft")
    elif change == "source":
        frozen[-1]["source_revision"] = "stale-source"
    elif change == "processing":
        with repo.transaction() as db:
            db.execute("UPDATE work_items SET status='processing' WHERE unit_id=?",
                       (row["unit_id"],))
    else:
        with repo.transaction() as db:
            db.execute("UPDATE text_units SET active=0 WHERE unit_id=?", (row["unit_id"],))
    before = list(repo.db.iterdump())
    with pytest.raises(ValueError, match="Page records changed"):
        store.create_review_job(frozen, profile())
    assert list(repo.db.iterdump()) == before


@pytest.mark.parametrize("size", [0, 201])
def test_page_size_is_bounded(prepared, size):
    repo, store, _ = prepared
    records = selection(repo.page())
    records = [] if size == 0 else records + [{**records[0], "unit_id": "extra"}]
    with pytest.raises(ValueError, match="1–200"):
        store.create_review_job(records, profile())


def test_duplicates_and_changed_model_cannot_bypass_page_gates(prepared):
    repo, store, _ = prepared
    records = selection(repo.page(status="validation_error")[:1])
    before = list(repo.db.iterdump())
    with pytest.raises(ValueError, match="distinct"):
        store.create_review_job(records * 2, profile())
    with pytest.raises(ValueError, match="pilot"):
        store.create_review_job(records, replace(profile(), model="different-model"))
    assert list(repo.db.iterdump()) == before


def test_full_200_record_page_is_accepted(prepared):
    repo, store, _ = prepared
    records = selection(repo.page())
    assert len(records) == 200
    job = store.create_review_job(records, profile())
    assert store.progress(job)["counts"] == {"queued": 200}


@pytest.mark.parametrize("blocker", ["project", "extracting", "running"])
def test_page_command_rejects_wrong_project_or_busy_session(prepared, blocker):
    repo, _, _ = prepared
    session = ApplicationSession()
    session.repository = repo
    session.jobs = TranslationJobService(repo)
    if blocker == "extracting":
        session.extracting = True
    elif blocker == "running":
        session.jobs.active_job = "other-job"
    settings = {k: v for k, v in profile().to_dict().items()
                if k not in ("glossary_version", "style_version")}
    before = list(repo.db.iterdump())
    with pytest.raises(ValueError):
        asyncio.run(session.dispatch("create_page_job", {
            "project_id": "wrong-project" if blocker == "project" else repo.project_id,
            "records": selection(repo.page()[:1]), "profile": settings,
        }))
    assert list(repo.db.iterdump()) == before


def test_page_regeneration_preserves_approved_text_and_stores_candidate(prepared):
    repo, store, _ = prepared
    row = repo.page()[0]
    repo.approve(row["unit_id"], row["version"])
    approved = repo.page()[0]
    job = store.create_review_job(selection([approved]), profile())
    fake = FakeProvider()
    result = asyncio.run(TranslationJobService(repo, lambda _: fake).run(job))
    assert result["counts"] == {"completed": 1}
    assert repo.page()[0] == approved
    assert repo.db.execute("SELECT count(*) FROM translation_revisions WHERE source_revision=?",
                           (approved["source_revision"],)).fetchone()[0] == 2


@pytest.mark.parametrize("exclude", [False, True])
def test_desktop_sends_only_visible_page_and_starts_shared_queue(prepared, monkeypatch, exclude):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from test_ui import wait_for

    from unitytranslator.ui.window import MainWindow

    repo, _, _ = prepared
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window.apply_profile(profile().to_dict())
        window.project_open = True
        window.current_project_id = repo.project_id
        window.draft_refresh_pending = False
        window.parallel_requests.setValue(8)
        rows = repo.page(status="validation_error")[:99]
        if exclude:
            rows[0]["editor_draft"] = {"text": "Saved draft"}
            rows[1]["status"] = "processing"
        window.review_model.set_rows(rows)
        submitted = []
        with monkeypatch.context() as patch:
            patch.setattr(window.bridge, "submit", lambda *args: submitted.append(args))
            window.retranslate_page()
            assert submitted[-1][0] == "create_page_job"
            records = submitted[-1][1]["records"]
            assert records == selection(rows[2:] if exclude else rows)
            assert len(records) == (97 if exclude else 99)
            assert not window.retranslate_page_button.isEnabled()
            window.completed("create_page_job", {"job_id": "page-job", "count": len(records)})
            assert submitted[-1] == ("run_job", {
                "job_id": "page-job", "parallel_requests": 8,
                "model_selection": window.model_data(),
            })
    finally:
        window.project_open = False
        window.bulk_timer.stop()
        window.close()
        wait_for(app, lambda: window.backend_closed)
