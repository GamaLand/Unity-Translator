"""Server outages, backoff claims and close-time pausing with synthetic providers only."""

import asyncio
import time
from pathlib import Path

import pytest
from test_jobs import FakeProvider, profile
from test_repository import draft

import unitytranslator.jobs as jobs_module
from unitytranslator.application import ApplicationSession
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.providers import ProviderError
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def paths(tmp_path: Path) -> ProjectPaths:
    game = tmp_path / "game"
    game.mkdir()
    return ProjectPaths(game, tmp_path / "project")


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr(jobs_module, "retry_delay", lambda failures, base: 0.0)


def records(repo: ProjectRepository, count: int) -> str:
    repo.ingest([draft(f"UI/{i}", f"Text {i}") for i in range(count)], {})
    return JobStore(repo).create([r["unit_id"] for r in repo.page()], profile(), kind="pilot")


def runs(repo: ProjectRepository, unit_id: str) -> list[tuple[int, str]]:
    return [
        tuple(row) for row in repo.db.execute(
            "SELECT attempt,status FROM translation_runs WHERE unit_id=? ORDER BY attempt",
            (unit_id,),
        )
    ]


def test_model_loading_retries_without_spending_the_attempt_budget(paths) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 1)

        class Loading(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                if len(self.requests) <= 2:
                    raise ProviderError("server_unavailable", "Loading model")
                return {"translation": "Çeviri", "issues": []}

        provider = Loading()
        result = asyncio.run(TranslationJobService(repo, lambda _: provider).run(job))
        assert result["status"] == "completed"
        assert repo.db.execute("SELECT attempts FROM job_items").fetchone()[0] == 1
        # Outage attempts stay in history with unique run numbers.
        assert runs(repo, "UI/0") == [
            (1, "server_unavailable"), (2, "server_unavailable"), (3, "accepted"),
        ]
        assert repo.page()[0]["translation"] == "Çeviri"


@pytest.mark.parametrize("code", ["connection", "server_unavailable"])
@pytest.mark.parametrize("parallel", [1, 3])
def test_consecutive_outages_pause_job_with_queue_intact_and_resume(
    paths, code, parallel,
) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 4)

        class Down(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                await asyncio.sleep(0)
                raise ProviderError(code, "synthetic outage")

        down = Down()
        result = asyncio.run(
            TranslationJobService(repo, lambda _: down).run(job, parallel_requests=parallel)
        )
        assert result["status"] == "paused"
        assert result["pause_reason"] == code
        assert result["counts"] == {"queued": 4}
        assert len(down.requests) >= jobs_module.OUTAGE_PAUSE_STREAK
        assert repo.db.execute("SELECT max(attempts) FROM job_items").fetchone()[0] == 0
        assert {row["status"] for row in repo.page()} == {"pending"}

        healthy = FakeProvider()
        resumed = asyncio.run(
            TranslationJobService(repo, lambda _: healthy).run(job, parallel_requests=parallel)
        )
        assert resumed["status"] == "completed"
        assert resumed["pause_reason"] is None
        assert repo.db.execute("SELECT max(attempts) FROM job_items").fetchone()[0] == 1


@pytest.mark.parametrize("parallel", [1, 2])
def test_record_that_alone_keeps_failing_is_failed_while_others_complete(paths, parallel) -> None:
    # Default constants and the default single request: one bad record must neither pause
    # the job on every resume nor starve the records queued after it.
    with ProjectRepository(paths) as repo:
        job = records(repo, 3)

        class CrashesOnFirst(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                if text == "Text 0":
                    raise ProviderError("server_unavailable", "HTTP 500")
                return {"translation": "Çeviri", "issues": []}

        provider = CrashesOnFirst()
        result = asyncio.run(
            TranslationJobService(repo, lambda _: provider).run(job, parallel_requests=parallel)
        )
        assert result["status"] == "completed_with_errors"
        assert provider.requests.count("Text 0") == jobs_module.MAX_RECORD_OUTAGES
        failed = repo.db.execute(
            "SELECT status,error_code,attempts FROM job_items WHERE unit_id='UI/0'"
        ).fetchone()
        assert tuple(failed) == ("failed", "server_unavailable", 0)
        assert result["counts"] == {"failed": 1, "completed": 2}
        # An outage is not a bad translation: the record stays Pending for a later job.
        assert next(r for r in repo.page() if r["unit_id"] == "UI/0")["status"] == "pending"


def test_outages_of_every_record_end_in_bounded_failures_across_resumes(paths) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 2)

        class Down(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                raise ProviderError("connection", "synthetic outage")

        down = Down()
        statuses = []
        for _ in range(6):
            result = asyncio.run(TranslationJobService(repo, lambda _: down).run(job))
            statuses.append(result["status"])
            if result["status"] != "paused":
                break
        assert statuses[0] == "paused" and statuses[-1] == "completed_with_errors"
        assert len(statuses) <= 4
        # Per-record outage counts persist across resumes, so requests stay bounded.
        assert len(down.requests) <= 2 * jobs_module.MAX_RECORD_OUTAGES + 2


def test_outages_interleaved_with_successes_never_pause(paths) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 14)

        class BriefOutages(FakeProvider):
            """Every even record hits one transient outage; successes come in between."""

            outages = 0

            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                if int(text.split()[1]) % 2 == 0 and self.requests.count(text) == 1:
                    self.outages += 1
                    raise ProviderError("server_unavailable", "busy")
                return {"translation": "Çeviri", "issues": []}

        provider = BriefOutages()
        result = asyncio.run(TranslationJobService(repo, lambda _: provider).run(job))
        assert provider.outages > jobs_module.OUTAGE_PAUSE_STREAK
        assert result["status"] == "completed" and result["pause_reason"] is None


def test_a_non_outage_failure_resets_the_outage_streak(paths) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 6)
        codes = iter(["connection"] * 4 + ["response_schema_error"] + ["connection"] * 4)

        class Mixed(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                code = next(codes, None)
                if code:
                    raise ProviderError(code, "synthetic")
                return {"translation": "Çeviri", "issues": []}

        provider = Mixed()
        result = asyncio.run(TranslationJobService(repo, lambda _: provider).run(job))
        assert result["status"] == "completed"


def test_outage_backoff_also_keeps_the_claim(paths, monkeypatch) -> None:
    monkeypatch.setattr(jobs_module, "retry_delay", lambda failures, base: 0.05)
    with ProjectRepository(paths) as repo:
        job = records(repo, 1)
        during: list[str] = []
        original_sleep = asyncio.sleep

        async def observing_sleep(delay, *args, **kwargs):
            if delay:
                during.append(repo.db.execute("SELECT status FROM job_items").fetchone()[0])
            return await original_sleep(delay, *args, **kwargs)

        monkeypatch.setattr(jobs_module.asyncio, "sleep", observing_sleep)

        class LoadingOnce(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                if len(self.requests) == 1:
                    raise ProviderError("server_unavailable", "Loading model")
                return {"translation": "Çeviri", "issues": []}

        provider = LoadingOnce()
        result = asyncio.run(
            TranslationJobService(repo, lambda _: provider).run(job, parallel_requests=3)
        )
        assert result["status"] == "completed"
        assert during == ["processing"]


def test_repeated_pause_keeps_an_active_run_pausing(paths) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 1)
        store = JobStore(repo)
        store.start(job)
        store.pause(job, "server_unavailable")
        store.pause(job, "server_unavailable")
        assert store.job(job)["status"] == "pausing"


def test_cancelled_pilot_counts_outage_failed_record_as_attempted(paths, monkeypatch) -> None:
    monkeypatch.setattr(jobs_module, "MAX_RECORD_OUTAGES", 1)
    with ProjectRepository(paths) as repo:
        job = records(repo, 3)
        service = TranslationJobService(repo, lambda _: provider)

        class Pilot(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                if text == "Text 0":
                    raise ProviderError("server_unavailable", "HTTP 500")
                if text == "Text 2":
                    service.cancel()
                    await asyncio.sleep(1)
                return {"translation": "Çeviri", "issues": []}

        provider = Pilot()
        result = asyncio.run(service.run(job))
        assert result["status"] == "cancelled"
        assert JobStore(repo).pilot_review_blocker(job) is None


def test_retry_backoff_keeps_the_claim_so_no_worker_retries_at_once(
    paths, monkeypatch,
) -> None:
    monkeypatch.setattr(jobs_module, "retry_delay", lambda failures, base: 0.2)
    with ProjectRepository(paths) as repo:
        job = records(repo, 1)
        calls: list[float] = []
        claims_during_backoff: list[str] = []

        class FlakyOnce(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                calls.append(time.perf_counter())
                if len(calls) == 1:
                    raise ProviderError("response_schema_error", "synthetic")
                return {"translation": "Çeviri", "issues": []}

        original_sleep = asyncio.sleep

        async def observing_sleep(delay, *args, **kwargs):
            if delay:
                claims_during_backoff.append(
                    repo.db.execute("SELECT status FROM job_items").fetchone()[0]
                )
            return await original_sleep(delay, *args, **kwargs)

        monkeypatch.setattr(jobs_module.asyncio, "sleep", observing_sleep)
        provider = FlakyOnce()
        result = asyncio.run(
            TranslationJobService(repo, lambda _: provider).run(job, parallel_requests=4)
        )
        assert result["status"] == "completed"
        assert claims_during_backoff == ["processing"]
        assert len(calls) == 2 and calls[1] - calls[0] >= 0.15
        assert repo.db.execute("SELECT attempts FROM job_items").fetchone()[0] == 2


def test_closing_project_pauses_running_job_and_refunds_interrupted_attempt(paths) -> None:
    started = asyncio.Event()

    class Waiting(FakeProvider):
        async def translate_record(self, model, text, *args, **kwargs):
            self.requests.append(text)
            started.set()
            await asyncio.sleep(30)
            raise AssertionError("closing must interrupt the request")

    async def run() -> None:
        session = ApplicationSession()
        await session.dispatch("open", {"game": str(paths.game), "project": str(paths.project)})
        job = records(session.repo, 2)
        session.jobs.provider_factory = lambda _: Waiting()
        task = asyncio.create_task(session.dispatch("run_job", {"job_id": job}))
        await asyncio.wait_for(started.wait(), timeout=5)
        await asyncio.wait_for(session.close(), timeout=5)
        result = await asyncio.wait_for(task, timeout=5)
        assert result["status"] == "paused"
        assert result["pause_reason"] == "shutdown"

    asyncio.run(run())
    with ProjectRepository(paths) as repo:
        store = JobStore(repo)
        job = repo.db.execute("SELECT id FROM jobs").fetchone()[0]
        assert store.job(job)["status"] == "paused"
        assert store.progress(job)["counts"] == {"queued": 2}
        assert runs(repo, "UI/0") == [(1, "cancelled")]
        assert repo.db.execute("SELECT sum(attempts) FROM job_items").fetchone()[0] == 0
        assert {row["status"] for row in repo.page()} == {"pending"}
        # Reopening never resumes on its own; an explicit run continues the same queue.
        healthy = FakeProvider()
        result = asyncio.run(TranslationJobService(repo, lambda _: healthy).run(job))
        assert result["status"] == "completed"
        assert runs(repo, "UI/0") == [(1, "cancelled"), (2, "accepted")]


def test_closing_keeps_an_automatic_pause_reason(paths) -> None:
    started = asyncio.Event()
    holder: dict[str, str] = {}
    session = ApplicationSession()

    class PausesThenWaits(FakeProvider):
        async def translate_record(self, model, text, *args, **kwargs):
            self.requests.append(text)
            JobStore(session.repo).pause(holder["job"], "timeout")
            started.set()
            await asyncio.sleep(30)
            raise AssertionError("closing must interrupt the request")

    async def run() -> None:
        await session.dispatch("open", {"game": str(paths.game), "project": str(paths.project)})
        holder["job"] = records(session.repo, 1)
        session.jobs.provider_factory = lambda _: PausesThenWaits()
        task = asyncio.create_task(session.dispatch("run_job", {"job_id": holder["job"]}))
        await asyncio.wait_for(started.wait(), timeout=5)
        await asyncio.wait_for(session.close(), timeout=5)
        result = await asyncio.wait_for(task, timeout=5)
        assert result["status"] == "paused"
        assert result["pause_reason"] == "timeout"

    asyncio.run(run())


def test_explicit_cancel_still_cancels(paths) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 2)
        service = TranslationJobService(repo, lambda _: provider)

        class CancelInFlight(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                service.cancel()
                await asyncio.sleep(1)
                return {"translation": "Çeviri", "issues": []}

        provider = CancelInFlight()
        result = asyncio.run(service.run(job))
        assert result["status"] == "cancelled"
        assert result["counts"] == {"cancelled": 2}


def test_one_concurrent_wave_of_loading_errors_does_not_pause(paths) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 12)

        class LoadingWave(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                await asyncio.sleep(0)
                if len(self.requests) <= 6:
                    raise ProviderError("server_unavailable", "Loading model")
                return {"translation": "Çeviri", "issues": []}

        provider = LoadingWave()
        result = asyncio.run(
            TranslationJobService(repo, lambda _: provider).run(job, parallel_requests=6)
        )
        assert result["status"] == "completed" and result["pause_reason"] is None


def test_first_pause_reason_of_an_active_run_is_kept(paths) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 1)
        store = JobStore(repo)
        store.start(job)
        store.pause(job, "server_unavailable")
        store.pause(job, "user")
        assert store.pause_reason(job) == "server_unavailable"
        store.settle(job)
        store.start(job)
        assert store.pause_reason(job) is None


def test_claim_keeps_index_order_and_puts_avoided_records_last(paths) -> None:
    with ProjectRepository(paths) as repo:
        job = records(repo, 3)
        store = JobStore(repo)
        statements: list[str] = []
        repo.db.set_trace_callback(statements.append)
        try:
            first = store.claim(job, frozenset({"UI/0", "UI/1"}))
        finally:
            repo.db.set_trace_callback(None)
        assert first is not None and first["unit_id"] == "UI/2"
        for statement in (s for s in statements if "FROM job_items j" in s):
            plan = " ".join(
                str(row[3]) for row in repo.db.execute("EXPLAIN QUERY PLAN " + statement)
            )
            assert "TEMP B-TREE" not in plan
        # Avoided records are still claimed once nothing else is queued.
        assert store.claim(job, frozenset({"UI/0", "UI/1"}))["unit_id"] == "UI/0"


def test_report_counts_outage_retries_from_history(paths) -> None:
    from unitytranslator.reports import job_report

    with ProjectRepository(paths) as repo:
        job = records(repo, 1)

        class LoadingTwice(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                if len(self.requests) <= 2:
                    raise ProviderError("server_unavailable", "Loading model")
                return {"translation": "Çeviri", "issues": []}

        provider = LoadingTwice()
        asyncio.run(TranslationJobService(repo, lambda _: provider).run(job))
        report = job_report(repo, job)
        assert report["retry_count"] == 2
        assert report["outage_attempts"] == 2
        assert report["measured_attempts"] == 1
