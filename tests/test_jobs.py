import asyncio
import json
from pathlib import Path

import httpx
import pytest
from test_repository import draft

from unitytranslator.domain import GenerationProfile
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.providers import LocalProvider, ProviderError
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def paths(tmp_path: Path) -> ProjectPaths:
    game = tmp_path / "game"
    game.mkdir()
    return ProjectPaths(game, tmp_path / "project")


def profile() -> GenerationProfile:
    return GenerationProfile("lm-studio", "http://127.0.0.1:1234", "synthetic", 8192)


def test_automatic_pause_reason_survives_reopen_and_clears_on_resume(paths):
    class MissingModel:
        async def translate_record(self, *args, **kwargs):
            raise ProviderError("not_found", "Synthetic missing model")

    with ProjectRepository(paths) as repo:
        repo.ingest([draft(), draft(key="UI/other")], {})
        store = JobStore(repo)
        job = store.create([row["unit_id"] for row in repo.page()], profile())
        result = asyncio.run(TranslationJobService(repo, lambda _: MissingModel()).run(job))
        assert result["status"] == "paused"
        assert result["pause_reason"] == "not_found"
    with ProjectRepository(paths) as repo:
        store = JobStore(repo)
        assert store.progress(job)["pause_reason"] == "not_found"
        store.start(job)
        assert store.progress(job)["pause_reason"] is None
        store.pause(job)
        assert store.progress(job)["pause_reason"] == "user"


def test_progress_rate_and_eta_use_only_finished_measured_records_and_include_retries(paths):
    with ProjectRepository(paths) as repo:
        repo.ingest(
            [
                draft(key="UI/a", text="a" * 10),
                draft(key="UI/b", text="b" * 20),
                draft(key="UI/c", text="c" * 30),
            ],
            {},
        )
        store = JobStore(repo)
        job = store.create([r["unit_id"] for r in repo.page()], profile())
        initial = store.progress(job)
        assert initial["records_per_minute"] is None
        assert initial["active_generation_eta_seconds"] is None
        store.start(job)
        item = store.claim(job)
        first = store.attempt(item, {})
        store.record_attempt(first, "timeout", 2.0, {})
        store.fail(item, "timeout", retry=True)
        item = store.claim(job)
        second = store.attempt(item, {})
        store.record_attempt(second, "accepted", 4.0, {})
        assert store.finish(item, {"translation": "Çeviri", "issues": []}, second)
        measured = store.progress(job)
        assert measured["records_per_minute"] == 10.0
        assert measured["active_generation_eta_seconds"] == 30.0
        assert measured["measured_records"] == 1
        processing = store.claim(job)
        run = store.attempt(processing, {})
        store.record_attempt(run, "interrupted", 100, {})
        assert store.progress(job)["records_per_minute"] == 10.0


def test_plural_retry_is_three_requests_for_whole_record_and_never_saves_partial_branch(paths):
    requests = []

    def handler(request):
        user = json.loads(json.loads(request.content)["messages"][1]["content"])
        requests.append(user)
        first = user["branches"][0]
        raw = json.dumps({"translations": [{"id": first["id"], "text": first["source"]}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": raw}}]})

    with ProjectRepository(paths) as repo:
        repo.ingest([draft(text="{[N]} turns[i2p_One]One turn")], {})
        job = JobStore(repo).create(["UI/start"], profile())
        adapter = LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))
        result = asyncio.run(TranslationJobService(repo, lambda _: adapter).run(job))
        assert result["counts"] == {"failed": 1}
        assert len(requests) == 3
        assert all(len(request["branches"]) == 2 for request in requests)
        assert repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == 0
        assert repo.page()[0]["translation"] is None


class FakeProvider:
    def __init__(self) -> None:
        self.requests: list[str] = []

    async def translate_record(
        self, model: str, text: str, *args: object, **kwargs: object
    ) -> dict:
        self.requests.append(text)
        return {"translation": "Başla" if text == "Start" else "Devam", "issues": []}


def test_completed_records_not_retranslated_and_run_persisted(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        job = store.create(["UI/start"], profile())
        fake = FakeProvider()
        result = asyncio.run(TranslationJobService(repo, lambda _: fake).run(job))
        assert result["status"] == "completed"
        assert result["counts"] == {"completed": 1}
        assert repo.page()[0]["translation"] == "Başla"
        assert repo.db.execute("SELECT status FROM translation_runs").fetchone()[0] == "accepted"
        with pytest.raises(ValueError, match="bekleyen"):
            store.create(["UI/start"], profile())
        assert fake.requests == ["Start"]


def test_pause_finishes_inflight_and_resume_only_remaining(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft(), draft("UI/continue", "Continue")], {})
        store = JobStore(repo)
        job = store.create(["UI/start", "UI/continue"], profile())
        fake = FakeProvider()
        service = TranslationJobService(repo, lambda _: fake)
        original = fake.translate_record

        async def pause_after_first(*args: object, **kwargs: object) -> dict:
            service.pause()
            return await original(*args, **kwargs)

        fake.translate_record = pause_after_first
        result = asyncio.run(service.run(job))
        assert result["status"] == "paused"
        assert result["counts"] == {"completed": 1, "queued": 1}
        fake.translate_record = original
        assert asyncio.run(service.run(job))["status"] == "completed"
        assert fake.requests == ["Start", "Continue"]


def test_late_answer_after_manual_approval_is_skipped(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        job = store.create(["UI/start"], profile())
        fake = FakeProvider()

        async def approve_during_request(*args: object, **kwargs: object) -> dict:
            item = repo.page()[0]
            assert repo.candidate(
                item["unit_id"],
                item["source_revision"],
                item["version"],
                "Elle onay",
                "manual",
                {},
                [],
            )
            repo.approve(item["unit_id"], repo.page()[0]["version"])
            return {"translation": "Geç model", "issues": []}

        fake.translate_record = approve_during_request
        result = asyncio.run(TranslationJobService(repo, lambda _: fake).run(job))
        assert result["counts"] == {"skipped": 1}
        assert repo.page()[0]["translation"] == "Elle onay"
        assert repo.page()[0]["status"] == "approved"


def test_cancel_during_http_never_activates_late_result(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        job = store.create(["UI/start"], profile())
        fake = FakeProvider()
        service = TranslationJobService(repo, lambda _: fake)

        async def delayed(*args: object, **kwargs: object) -> dict:
            service.cancel()
            await asyncio.sleep(0)
            return {"translation": "Geç model", "issues": []}

        fake.translate_record = delayed
        result = asyncio.run(service.run(job))
        assert result["status"] == "cancelled"
        assert repo.page()[0]["translation"] is None
        assert repo.page()[0]["status"] == "pending"


@pytest.mark.parametrize(
    "code",
    [
        "validation_error",
        "response_schema_error",
        "protected_content_error",
        "output_truncated",
        "unexpected_tool_call",
    ],
)
def test_retry_budget_persists_and_is_three_total(paths: ProjectPaths, code: str) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        job = store.create(["UI/start"], profile())
        fake = FakeProvider()

        async def broken(*args: object, **kwargs: object) -> dict:
            raise ProviderError(code, "synthetic", {"completion_tokens": 128})

        fake.translate_record = broken
        result = asyncio.run(TranslationJobService(repo, lambda _: fake).run(job))
        assert result["status"] == "completed_with_errors"
        assert repo.db.execute("SELECT attempts FROM job_items").fetchone()[0] == 3
        assert repo.db.execute("SELECT count(*) FROM translation_runs").fetchone()[0] == 3
        saved = json.loads(
            repo.db.execute("SELECT metadata_json FROM translation_runs LIMIT 1").fetchone()[0]
        )
        assert saved["error_diagnostics"] == {"completion_tokens": 128}
        assert repo.page()[0]["status"] == "validation_error"
        from unitytranslator.reports import job_report

        metrics = job_report(repo, job)["validation_metrics"]
        metric = {
            "validation_error": "legacy_unclassified_validation_errors",
            "response_schema_error": "response_schema_errors",
            "protected_content_error": "protected_content_errors",
            "output_truncated": "output_truncated_errors",
            "unexpected_tool_call": "unexpected_tool_call_errors",
        }[code]
        assert metrics[metric] == 3


def test_reopen_recovers_claim_without_resetting_attempt_budget(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        job = store.create(["UI/start"], profile())
        store.start(job)
        item = store.claim(job)
        assert item is not None
        store.attempt(item, {})
    with ProjectRepository(paths) as repo:
        assert repo.page()[0]["status"] == "pending"
        store = JobStore(repo)
        assert store.job(job)["status"] == "paused"
        assert repo.db.execute("SELECT status FROM translation_runs").fetchone()[0] == "interrupted"
        result = asyncio.run(TranslationJobService(repo, lambda _: FakeProvider()).run(job))
        assert result["status"] == "completed"
        assert repo.db.execute("SELECT attempts FROM job_items").fetchone()[0] == 2


def test_bulk_gate_is_bound_to_profile_and_source(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        with pytest.raises(ValueError, match="pilot"):
            store.create(["UI/start"], profile(), "bulk")


def test_queued_job_does_not_overwrite_intervening_user_edit(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        job = store.create(["UI/start"], profile())
        item = repo.page()[0]
        repo.candidate(
            item["unit_id"], item["source_revision"], item["version"], "Elle", "manual", {}, []
        )
        fake = FakeProvider()
        result = asyncio.run(TranslationJobService(repo, lambda _: fake).run(job))
        assert result["counts"] == {"skipped": 1}
        assert fake.requests == []
        assert repo.page()[0]["translation"] == "Elle"


def test_explicit_generation_for_approved_record_preserves_approval(paths: ProjectPaths) -> None:
    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        repo.edit("UI/start", 0, "Elle onay")
        repo.approve("UI/start", repo.page()[0]["version"])
        version = repo.page()[0]["version"]
        store = JobStore(repo)
        job = store.create(["UI/start"], profile(), retranslate=True, approved_candidates=True)
        result = asyncio.run(TranslationJobService(repo, lambda _: FakeProvider()).run(job))
        assert result["counts"] == {"completed": 1}
        row = repo.page()[0]
        assert row["translation"] == "Elle onay"
        assert row["status"] == "approved"
        assert row["version"] == version
        candidate = repo.db.execute(
            "SELECT t.text FROM job_items j JOIN translation_revisions t "
            "ON t.id=j.result_revision WHERE j.job_id=?",
            (job,),
        ).fetchone()[0]
        assert candidate == "Başla"
        from unitytranslator.reports import job_report

        report = job_report(repo, job)
        assert report["human_approved_records"] == 0
        assert report["changed_after_generation"] == 0
        assert report["records"][0]["review_status"] == "needs_review"


def test_pilot_acknowledgement_does_not_approve_records_and_gate_is_source_bound(
    paths: ProjectPaths,
) -> None:
    from dataclasses import replace

    with ProjectRepository(paths) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        job = store.create(["UI/start"], profile(), "pilot")
        asyncio.run(TranslationJobService(repo, lambda _: FakeProvider()).run(job))
        store.acknowledge_pilot(job)
        assert repo.page()[0]["status"] == "translated"
        repo.ingest([replace(draft(), context="changed")], {})
        with pytest.raises(ValueError, match="Kaynak"):
            store.acknowledge_pilot(job)
