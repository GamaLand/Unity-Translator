"""T3 request efficiency: commits per record, live progress, one HTTP client per job and
the server slot warning. Synthetic providers and local fake servers only."""

import asyncio
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_jobs import FakeProvider, profile
from test_repository import draft

import unitytranslator.jobs as jobs_module
import unitytranslator.providers as providers_module
from unitytranslator.domain import GenerationProfile
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import (
    SERVER_SLOT_WARNING,
    JobStore,
    TranslationJobService,
    slot_warning,
)
from unitytranslator.providers import LocalProvider, slot_count
from unitytranslator.reports import job_report
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def paths(tmp_path: Path) -> ProjectPaths:
    game = tmp_path / "game"
    game.mkdir()
    return ProjectPaths(game, tmp_path / "project")


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr(jobs_module, "retry_delay", lambda failures, base: 0.0)


def records(repo: ProjectRepository, count: int, job_profile: GenerationProfile | None = None):
    repo.ingest([draft(f"UI/{i}", f"Text {i}") for i in range(count)], {})
    return JobStore(repo).create(
        [r["unit_id"] for r in repo.page()],
        job_profile or profile(),
        kind="pilot",
    )


def runs(repo: ProjectRepository, unit_id: str) -> list[tuple[int, str]]:
    return [
        tuple(row)
        for row in repo.db.execute(
            "SELECT attempt,status FROM translation_runs WHERE unit_id=? ORDER BY attempt",
            (unit_id,),
        )
    ]


def item_states(repo: ProjectRepository, job: str) -> dict[str, tuple[str, int]]:
    return {
        row[0]: (row[1], row[2])
        for row in repo.db.execute(
            "SELECT unit_id,status,attempts FROM job_items WHERE job_id=?",
            (job,),
        )
    }


class WriteCounter:
    """Counts write transactions and any write that would autocommit on its own."""

    def __init__(self, repo: ProjectRepository) -> None:
        self.repo = repo
        self.transactions = 0
        self.autocommits: list[str] = []

    def __call__(self, statement: str) -> None:
        words = statement.lstrip().split(None, 1)
        head = words[0].upper() if words else ""
        if head == "BEGIN":
            self.transactions += 1
        elif head in ("INSERT", "UPDATE", "DELETE", "REPLACE") and not self.repo.db.in_transaction:
            self.autocommits.append(statement)

    def __enter__(self) -> "WriteCounter":
        self.repo.db.set_trace_callback(self)
        return self

    def __exit__(self, *args: object) -> None:
        self.repo.db.set_trace_callback(None)


# --- Two commits per successful record ---------------------------------------------------


@pytest.mark.parametrize("parallel", [1, 3])
@pytest.mark.parametrize("count", [4, 9])
def test_a_successful_record_costs_exactly_two_write_transactions(paths, parallel, count):
    with ProjectRepository(paths) as repo:
        job = records(repo, count)
        with WriteCounter(repo) as writes:
            result = asyncio.run(
                TranslationJobService(repo, lambda _: FakeProvider()).run(
                    job,
                    parallel_requests=parallel,
                )
            )
        assert result["counts"] == {"completed": count}
        assert writes.autocommits == []
        # Per record: claim with attempt start, then result with run record. Per job: the
        # start, one empty final claim per worker and the settle.
        assert writes.transactions == 2 * count + 1 + parallel + 1
        assert {runs(repo, f"UI/{i}")[0] for i in range(count)} == {(1, "accepted")}
        assert set(item_states(repo, job).values()) == {("completed", 1)}


def test_failed_attempts_also_commit_less_and_keep_the_budget(paths):
    with ProjectRepository(paths) as repo:
        job = records(repo, 1)

        class Flaky(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                if len(self.requests) == 1:
                    raise providers_module.ProviderError("timeout", "Synthetic timeout")
                return {"translation": "Çeviri", "issues": []}

        with WriteCounter(repo) as writes:
            result = asyncio.run(TranslationJobService(repo, lambda _: Flaky()).run(job))
        assert result["counts"] == {"completed": 1}
        assert writes.autocommits == []
        # start; claim+attempt, failure record (claim kept during backoff), requeue;
        # claim+attempt, result; empty claim; settle.
        assert writes.transactions == 8
        assert runs(repo, "UI/0") == [(1, "timeout"), (2, "accepted")]
        assert item_states(repo, job) == {"UI/0": ("completed", 2)}


# --- Incremental progress ----------------------------------------------------------------


def comparable(progress: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in progress.items()
        if k
        not in (
            "generation_seconds",
            "records_per_minute",
            "active_generation_eta_seconds",
            "warnings",
        )
    }


@pytest.mark.parametrize("parallel", [1, 4])
def test_live_progress_matches_a_full_scan_after_every_commit_without_rescanning(
    paths,
    monkeypatch,
    parallel,
):
    monkeypatch.setattr(jobs_module, "PROGRESS_INTERVAL", 0.0)
    scans = []
    real_state = JobStore.progress_state

    def counted(self, job_id):
        scans.append(job_id)
        return real_state(self, job_id)

    with ProjectRepository(paths) as repo:
        job = records(repo, 12)
        store = JobStore(repo)
        events = []

        class Mixed(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                await asyncio.sleep(0.001)  # Measurable request time for rate and ETA.
                if text == "Text 3" and self.requests.count(text) == 1:
                    raise providers_module.ProviderError("timeout", "Synthetic timeout")
                if text == "Text 5":
                    raise providers_module.ProviderError("http_error", "Synthetic failure")
                return {"translation": "Çeviri", "issues": []}

        def report(progress):
            events.append(progress)
            full = store.progress_view(job, real_state(store, job))
            assert comparable(progress) == comparable(full)
            # Sums of the same floats in another order round alike up to the last digit.
            for key, tolerance in (
                ("generation_seconds", 0.0011),
                ("records_per_minute", 0.011),
                ("active_generation_eta_seconds", 0.11),
            ):
                if full[key] is None:
                    assert progress[key] is None
                else:
                    assert progress[key] == pytest.approx(full[key], abs=tolerance)
            assert progress["warnings"] == []

        monkeypatch.setattr(JobStore, "progress_state", counted)
        result = asyncio.run(
            TranslationJobService(repo, lambda _: Mixed()).run(
                job,
                report,
                parallel_requests=parallel,
            )
        )
        # One record event per finished or requeued record, each matching a full scan,
        # with a single scan at the first report; settle scans again at the end.
        assert len(events) >= 12
        assert scans.count(job) == 1 + 2
        assert result["counts"] == {"completed": 11, "failed": 1}
        assert events[-1]["counts"] == {"completed": 11, "failed": 1}


# --- Pause, cancel and shutdown keep completed results -----------------------------------


@pytest.mark.parametrize("action", ["pause", "cancel", "shutdown"])
def test_stopping_mid_job_keeps_completed_results_and_inflight_records_retryable(
    paths,
    action,
):
    with ProjectRepository(paths) as repo:
        job = records(repo, 6)
        service = TranslationJobService(repo, lambda _: provider)
        returned: list[str] = []

        class Stopping(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                self.requests.append(text)
                if text == "Text 2":
                    {"pause": service.pause, "cancel": service.cancel, "shutdown": service.suspend}[
                        action
                    ]()
                    await asyncio.sleep(0.05 if action == "pause" else 30)
                returned.append(text)
                return {"translation": "Çeviri " + text, "issues": []}

        provider = Stopping()
        result = asyncio.run(service.run(job, parallel_requests=2))
        states = item_states(repo, job)
        translations = {row["unit_id"]: row["translation"] for row in repo.page()}
        completed = {f"UI/{text.split()[1]}" for text in returned}
        # Every response that arrived is stored, counted once and charged once.
        assert {u for u, (s, _) in states.items() if s == "completed"} == completed
        assert all(states[u] == ("completed", 1) for u in completed)
        assert all(translations[u] == "Çeviri Text " + u[3:] for u in completed)
        assert result["counts"].get("completed", 0) == len(completed)
        assert not result["counts"].get("processing")
        untouched = set(states) - completed - {"UI/2"}
        if action == "pause":
            assert result["status"] == "paused"
            assert "UI/2" in completed
            assert all(states[u] == ("queued", 0) for u in untouched)
        elif action == "cancel":
            assert result["status"] == "cancelled"
            assert states["UI/2"] == ("cancelled", 1)
            assert runs(repo, "UI/2") == [(1, "cancelled")]
            assert all(states[u][0] == "cancelled" for u in untouched)
            # Cancelled records are Pending again, so a new job can translate them.
            statuses = {row["unit_id"]: row["status"] for row in repo.page()}
            assert statuses["UI/2"] == "pending"
            follow_up = JobStore(repo).create(
                sorted(set(states) - completed),
                profile(),
                kind="pilot",
            )
            again = asyncio.run(
                TranslationJobService(repo, lambda _: FakeProvider()).run(
                    follow_up,
                    parallel_requests=2,
                )
            )
            assert again["counts"] == {"completed": 6 - len(completed)}
            assert item_states(repo, follow_up)["UI/2"] == ("completed", 1)
        else:
            assert result["status"] == "paused" and result["pause_reason"] == "shutdown"
            # The interrupted request is refunded, so its retry is not double-charged.
            assert states["UI/2"] == ("queued", 0)
            assert runs(repo, "UI/2") == [(1, "cancelled")]
            assert all(states[u] == ("queued", 0) for u in untouched)
        if action != "cancel":
            resumed = asyncio.run(
                TranslationJobService(repo, lambda _: FakeProvider()).run(
                    job,
                    parallel_requests=2,
                )
            )
            assert resumed["counts"] == {"completed": 6}
            final = item_states(repo, job)
            assert all(final[u] == ("completed", 1) for u in final)
            assert translations_kept(repo, completed, translations)


def translations_kept(repo, completed, before) -> bool:
    after = {row["unit_id"]: row["translation"] for row in repo.page()}
    return all(after[u] == before[u] for u in completed)


# --- A process killed at any point recovers to a retryable state -------------------------

CRASHING_CHILD = textwrap.dedent("""
    import asyncio, os, sys
    from pathlib import Path
    from unitytranslator.filesystem import ProjectPaths
    from unitytranslator.jobs import JobStore, TranslationJobService
    from unitytranslator.repository import ProjectRepository

    game, project, job, point = sys.argv[1:5]

    class Provider:
        async def translate_record(self, model, text, *args, **kwargs):
            if point == "request" and text == "Text 1":
                os._exit(3)  # Between the claim-and-attempt commit and the result commit.
            return {"translation": "Çeviri " + text, "issues": []}

    start_run, record_run = JobStore._start_run, JobStore._record_run

    def crash_in_claim(self, db, item, metadata):
        if item["unit_id"] == "UI/1":
            os._exit(3)  # Inside the first transaction, before its commit.
        return start_run(self, db, item, metadata)

    def crash_in_result(db, run_id, status, elapsed, metadata):
        unit = db.execute("SELECT unit_id FROM translation_runs WHERE id=?", (run_id,))
        if unit.fetchone()[0] == "UI/1" and status == "accepted":
            os._exit(3)  # Result and revision written, commit not yet reached.
        return record_run(db, run_id, status, elapsed, metadata)

    if point == "claim":
        JobStore._start_run = crash_in_claim
    elif point == "result":
        JobStore._record_run = staticmethod(crash_in_result)
    with ProjectRepository(ProjectPaths(Path(game), Path(project))) as repo:
        asyncio.run(TranslationJobService(repo, lambda _: Provider()).run(job))
    os._exit(0)
""")


def work_version(repo: ProjectRepository, unit_id: str) -> int:
    row = repo.db.execute("SELECT version FROM work_items WHERE unit_id=?", (unit_id,)).fetchone()
    return int(row[0])


@pytest.mark.parametrize("point", ["claim", "request", "result"])
def test_a_killed_run_recovers_without_lost_or_double_charged_attempts(paths, point):
    with ProjectRepository(paths) as repo:
        job = records(repo, 3)
        version_before = work_version(repo, "UI/1")
    child = subprocess.run(
        [sys.executable, "-c", CRASHING_CHILD, str(paths.game), str(paths.project), job, point],
        capture_output=True,
        timeout=60,
    )
    assert child.returncode == 3, child.stderr.decode(errors="replace")
    with ProjectRepository(paths) as repo:
        store = JobStore(repo)
        assert store.job(job)["status"] == "paused"
        states = item_states(repo, job)
        assert states["UI/0"] == ("completed", 1)
        assert repo.page()[0]["translation"] == "Çeviri Text 0"
        if point == "claim":
            # The first transaction never committed: no claim, no attempt, no run. A claim
            # committed on its own would have been recovered with a new work version.
            assert states["UI/1"] == ("queued", 0)
            assert runs(repo, "UI/1") == []
            assert work_version(repo, "UI/1") == version_before
        else:
            # The claim and its attempt committed together; the result never did.
            assert states["UI/1"] == ("queued", 1)
            assert runs(repo, "UI/1") == [(1, "interrupted")]
        assert states["UI/2"] == ("queued", 0)
        assert (
            repo.db.execute(
                "SELECT count(*) FROM translation_revisions t JOIN source_revisions s "
                "ON s.id=t.source_revision WHERE s.unit_id='UI/1'"
            ).fetchone()[0]
            == 0
        )
        assert {row["unit_id"]: row["status"] for row in repo.page()}["UI/1"] == "pending"
        result = asyncio.run(TranslationJobService(repo, lambda _: FakeProvider()).run(job))
        assert result["counts"] == {"completed": 3}
        final = item_states(repo, job)
        assert final["UI/0"] == ("completed", 1)
        assert final["UI/1"] == ("completed", 1 if point == "claim" else 2)
        assert runs(repo, "UI/0") == [(1, "accepted")]


# --- One HTTP client per job -------------------------------------------------------------


def chat_reply(request: httpx.Request) -> httpx.Response:
    user = json.loads(json.loads(request.content)["messages"][1]["content"])
    raw = json.dumps({"translations": [{"id": user["id"], "text": "Çeviri"}]})
    return httpx.Response(200, json={"choices": [{"message": {"content": raw}}]})


@pytest.fixture
def clients(monkeypatch) -> list[httpx.AsyncClient]:
    created: list[httpx.AsyncClient] = []

    class Counting(httpx.AsyncClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(httpx, "AsyncClient", Counting)
    return created


@pytest.mark.parametrize("exit_path", ["complete", "pause", "cancel", "shutdown", "error"])
def test_one_client_serves_the_whole_job_and_closes_on_every_exit(paths, clients, exit_path):
    with ProjectRepository(paths) as repo:
        job = records(
            repo,
            6,
            GenerationProfile(
                "llama-cpp",
                "http://127.0.0.1:8080",
                "synthetic",
                8192,
            ),
        )
        service = TranslationJobService(
            repo,
            lambda p: LocalProvider(
                p.provider,
                p.address,
                httpx.MockTransport(handler),
            ),
        )
        seen: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.path)
            if request.url.path in ("/props", "/slots"):
                return httpx.Response(404)
            if seen.count("/v1/chat/completions") == 3 and exit_path != "complete":
                if exit_path == "error":
                    raise RuntimeError("synthetic transport defect")
                {"pause": service.pause, "cancel": service.cancel, "shutdown": service.suspend}[
                    exit_path
                ]()
                if exit_path != "pause":
                    await asyncio.sleep(30)
            return chat_reply(request)

        if exit_path == "error":
            with pytest.raises(RuntimeError):
                asyncio.run(service.run(job, parallel_requests=3))
        else:
            result = asyncio.run(service.run(job, parallel_requests=3))
            expected = {
                "complete": "completed",
                "pause": "paused",
                "cancel": "cancelled",
                "shutdown": "paused",
            }[exit_path]
            assert result["status"] == expected
        assert len(clients) == 1
        assert clients[0].is_closed
        assert service.active_job is None
        # The slot probe went through the same client before any generation request.
        assert seen[:2] == ["/props", "/slots"]
        assert seen.count("/v1/chat/completions") >= 3


def test_non_job_calls_keep_their_own_short_lived_clients(clients):
    provider = LocalProvider(
        "lm-studio",
        "http://localhost:1234",
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": "synthetic"}]}),
        ),
    )
    assert asyncio.run(provider.list_models()) == ["synthetic"]
    assert asyncio.run(provider.list_models()) == ["synthetic"]
    assert len(clients) == 2 and all(client.is_closed for client in clients)
    assert provider.client is None


class FakeOpenAIServer:
    """A minimal keep-alive HTTP/1.1 server with llama.cpp-style /props and chat routes."""

    def __init__(self, props: bytes) -> None:
        self.props = props
        self.connections = 0
        self.requests: list[str] = []
        self.active = 0
        self.max_active = 0

    async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        try:
            while True:
                try:
                    head = await reader.readuntil(b"\r\n\r\n")
                except (asyncio.IncompleteReadError, ConnectionError):
                    return
                lines = head.decode("latin-1").split("\r\n")
                method, path, _ = lines[0].split(" ", 2)
                headers = {
                    k.strip().casefold(): v.strip()
                    for k, v in (line.split(":", 1) for line in lines[1:] if ":" in line)
                }
                body = await reader.readexactly(int(headers.get("content-length", "0")))
                self.requests.append(f"{method} {path}")
                if path == "/props":
                    status, payload = 200, self.props
                elif path == "/v1/chat/completions":
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                    await asyncio.sleep(0.01)
                    self.active -= 1
                    user = json.loads(json.loads(body)["messages"][1]["content"])
                    raw = json.dumps({"translations": [{"id": user["id"], "text": "Çeviri"}]})
                    status = 200
                    payload = json.dumps({"choices": [{"message": {"content": raw}}]}).encode()
                else:
                    status, payload = 404, b"{}"
                writer.write(
                    f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(payload)}\r\n\r\n".encode()
                    + payload
                )
                await writer.drain()
        finally:
            writer.close()


def run_against_server(paths: ProjectPaths, props: bytes, parallel: int, count: int):
    server = FakeOpenAIServer(props)

    async def main() -> dict[str, Any]:
        listener = await asyncio.start_server(server.serve, "127.0.0.1", 0)
        port = listener.sockets[0].getsockname()[1]
        try:
            with ProjectRepository(paths) as repo:
                job = records(
                    repo,
                    count,
                    GenerationProfile(
                        "llama-cpp",
                        f"http://127.0.0.1:{port}",
                        "synthetic",
                        8192,
                    ),
                )
                result = await TranslationJobService(repo).run(job, parallel_requests=parallel)
                return {"result": result, "report": job_report(repo, job), "job": job}
        finally:
            listener.close()
            await listener.wait_closed()

    return server, asyncio.run(main())


def test_fake_server_sees_pooled_connections_and_the_slot_warning(paths):
    server, outcome = run_against_server(paths, b'{"total_slots": 2}', parallel=3, count=9)
    result = outcome["result"]
    assert result["counts"] == {"completed": 9}
    assert server.requests.count("GET /props") == 1
    assert server.requests.count("POST /v1/chat/completions") == 9
    # One pooled client: at most one connection per parallel request, not one per record.
    assert 1 <= server.connections <= 3
    assert server.max_active <= 3
    warning = slot_warning(3, 2)
    assert result["warnings"] == [warning]
    assert warning["code"] == SERVER_SLOT_WARNING
    assert warning["params"] == {"p0": "3", "p1": "2"}
    assert "3 parallel requests" in warning["message"] and "2 slots" in warning["message"]
    assert outcome["report"]["warnings"] == [warning]


# --- Server slot warning -----------------------------------------------------------------


@pytest.mark.parametrize(
    "value,route,expected",
    [
        ({"total_slots": 4}, "/props", 4),
        ({"total_slots": 4096}, "/props", 4096),
        ({"total_slots": 4097}, "/props", None),
        ({"total_slots": 0}, "/props", None),
        ({"total_slots": -2}, "/props", None),
        ({"total_slots": "4"}, "/props", None),
        ({"total_slots": True}, "/props", None),
        ({"total_slots": 4.0}, "/props", None),
        ({"total_slots": None}, "/props", None),
        ({}, "/props", None),
        ([{"total_slots": 4}], "/props", None),
        ([{"id": 0}, {"id": 1}, {"id": 2}], "/slots", 3),
        ([{"id": 0}, 1], "/slots", None),
        ([], "/slots", None),
        ({"slots": 3}, "/slots", None),
    ],
)
def test_slot_count_accepts_only_bounded_integer_fields(value, route, expected):
    assert slot_count(value, route) == expected


def probe(handler, provider="llama-cpp") -> tuple[int | None, list[str]]:
    seen: list[str] = []

    async def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return await handler(request)

    local = LocalProvider(provider, "http://127.0.0.1:8080", httpx.MockTransport(wrapped))
    return asyncio.run(local.server_slots()), seen


def respond(props: httpx.Response | None = None, slots: httpx.Response | None = None):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/props" and props is not None:
            return props
        if request.url.path == "/slots" and slots is not None:
            return slots
        return httpx.Response(404)

    return handler


def test_slot_probe_reads_props_first_and_falls_back_to_slots():
    assert probe(respond(httpx.Response(200, json={"total_slots": 6}))) == (6, ["/props"])
    assert probe(
        respond(
            httpx.Response(200, json={"n_ctx": 4096}),
            httpx.Response(200, json=[{}, {}]),
        )
    ) == (2, ["/props", "/slots"])
    assert probe(respond()) == (None, ["/props", "/slots"])


@pytest.mark.parametrize(
    "props",
    [
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, content=b"[" * 200_000 + b"]" * 200_000),
        httpx.Response(200, content=b'{"total_slots": 2, "pad": "' + b"x" * (1024 * 1024) + b'"}'),
        httpx.Response(200, json=["total_slots", 2]),
        httpx.Response(500, json={"error": "loading"}),
        httpx.Response(501, json={"error": {"message": "This server does not support slots"}}),
    ],
)
def test_malformed_or_oversized_slot_reports_are_ignored(props):
    slots, seen = probe(respond(props, httpx.Response(501)))
    assert slots is None and seen == ["/props", "/slots"]


def test_slot_probe_times_out_quietly(monkeypatch):
    monkeypatch.setattr(providers_module, "SLOT_PROBE_SECONDS", 0.05)

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json={"total_slots": 1})

    assert probe(slow)[0] is None


def test_lm_studio_is_not_probed():
    assert probe(respond(httpx.Response(200, json={"total_slots": 1})), "lm-studio") == (None, [])


@pytest.mark.parametrize(
    "parallel,props,warned",
    [
        (4, {"total_slots": 2}, True),
        (4, {"total_slots": 4}, False),
        (4, {"total_slots": 8}, False),
        (4, None, False),
        (4, {"total_slots": "2"}, False),
        (1, {"total_slots": 1}, False),
    ],
)
def test_job_warns_only_when_parallel_requests_exceed_reported_slots(
    paths,
    parallel,
    props,
    warned,
):
    probes: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in ("/props", "/slots"):
            probes.append(request.url.path)
            if props is None:
                return httpx.Response(404)
            return httpx.Response(200, json=props)
        return chat_reply(request)

    with ProjectRepository(paths) as repo:
        job = records(
            repo,
            3,
            GenerationProfile(
                "llama-cpp",
                "http://127.0.0.1:8080",
                "synthetic",
                8192,
            ),
        )
        service = TranslationJobService(
            repo,
            lambda p: LocalProvider(
                p.provider,
                p.address,
                httpx.MockTransport(handler),
            ),
        )
        events: list[dict[str, Any]] = []
        result = asyncio.run(service.run(job, events.append, parallel_requests=parallel))
        expected = [slot_warning(parallel, props["total_slots"])] if warned else []
        assert result["status"] == "completed"
        assert result["warnings"] == expected
        assert all(event["warnings"] == expected for event in events)
        assert job_report(repo, job)["warnings"] == expected
        stored = {
            json.loads(row[0]).get("server_slots")
            for row in repo.db.execute("SELECT metadata_json FROM translation_runs")
        }
        valid = props is not None and type(props.get("total_slots")) is int
        assert stored == ({props["total_slots"]} if valid and parallel > 1 else {None})
        # A single request cannot exceed any slot count, so it is never probed.
        assert (probes == []) == (parallel == 1)
