"""Optional local reviewer pass against a fake OpenAI-compatible server on 127.0.0.1.

No real model server is contacted: every test starts its own synthetic server on a free
local port, or uses a port with no listener.
"""

import asyncio
import json
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_repository import draft

from unitytranslator import local_review
from unitytranslator.application import (
    LOCAL_REVIEW_BUSY,
    LOCAL_REVIEW_PROJECT_CHANGED,
    ApplicationSession,
)
from unitytranslator.diagnostics import Diagnostic, english_catalog
from unitytranslator.domain import GenerationProfile
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.local_review import (
    MAX_RUN_RECORDS,
    MODEL_MISSING_MESSAGE,
    RESPONSE_MESSAGE,
    STOP_MODEL_MISSING,
    STOP_OUT_OF_MEMORY,
    STOP_SERVER,
    STOP_UNAUTHORIZED,
    STOP_UNREACHABLE,
    STOP_UNSUPPORTED,
    UNREACHABLE_MESSAGE,
    LocalReviewRun,
    parse_verdict,
)
from unitytranslator.providers import ProviderError
from unitytranslator.reports import job_report, save_current_quality_audit, save_review_html

Reply = Callable[[dict[str, Any], dict[str, Any]], Awaitable[tuple[int, Any]]]


def completion(content: Any, **choice: Any) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}, **choice}]}


def verdict(request: dict[str, Any], issues: list[str], note: str = "") -> dict[str, Any]:
    return completion(json.dumps({"id": request["id"], "issues": issues, "note": note}))


async def by_source(payload: dict[str, Any], request: dict[str, Any]) -> tuple[int, Any]:
    """Flags 'Start' for meaning and tone; everything else is fine."""
    if request["source"] == "Start":
        return 200, verdict(request, ["tone_review", "meaning_review"], "Verb differs.")
    return 200, verdict(request, [])


class FakeServer:
    """A minimal HTTP/1.1 server with /v1/models and /v1/chat/completions routes."""

    def __init__(self, reply: Reply = by_source, models: tuple[str, ...] = ("synthetic",)):
        self.reply = reply
        self.models = models
        self.reviews: list[dict[str, Any]] = []
        self.translations = 0
        self.listener: asyncio.Server | None = None
        self.port = 0
        self.handlers: set[asyncio.Task[Any]] = set()
        # When set, /v1/models answers only after the gate opens: a slow server check.
        self.models_gate: asyncio.Event | None = None
        self.model_requests = 0

    async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self.handlers.add(task)
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
                status: int
                value: Any
                if method == "GET" and path == "/v1/models":
                    self.model_requests += 1
                    if self.models_gate is not None:
                        await self.models_gate.wait()
                    status, value = 200, {"data": [{"id": model} for model in self.models]}
                elif method == "POST" and path == "/v1/chat/completions":
                    payload = json.loads(body)
                    request = json.loads(payload["messages"][1]["content"])
                    if "translation" in request:
                        self.reviews.append(payload)
                        status, value = await self.reply(payload, request)
                    else:
                        self.translations += 1
                        raw = json.dumps({"translations": [{"id": request["id"], "text": "Ç"}]})
                        status, value = 200, completion(raw)
                else:
                    status, value = 404, {}
                data = value if isinstance(value, bytes) else json.dumps(value).encode()
                writer.write(
                    f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(data)}\r\n\r\n".encode() + data
                )
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            return
        finally:
            writer.close()

    async def __aenter__(self) -> "FakeServer":
        self.listener = await asyncio.start_server(self.serve, "127.0.0.1", 0)
        self.port = self.listener.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *args: object) -> None:
        assert self.listener is not None
        self.listener.close()
        # Handlers still waiting on a reply would keep wait_closed() from returning.
        for task in self.handlers:
            task.cancel()
        await asyncio.gather(*self.handlers, return_exceptions=True)
        await self.listener.wait_closed()


def free_port() -> int:
    """A local port with no listener: connections are refused."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def profile(port: int, **values: Any) -> dict[str, Any]:
    return {
        "provider": "llama-cpp", "address": f"http://127.0.0.1:{port}", "model": "synthetic",
        "context_tokens": 8192, "output_tokens": 512, "temperature": 0.2,
        "structured_output": True, **values,
    }


async def open_session(tmp_path: Path) -> tuple[ApplicationSession, dict[str, Any], list[Any]]:
    events: list[Any] = []
    session = ApplicationSession(events.append)
    game = tmp_path / "game"
    game.mkdir()
    opened = await session.dispatch(
        "open", {"game": str(game), "project": str(tmp_path / "project")},
    )
    repo = session.repo
    repo.ingest(
        [draft("UI/a", "Start"), draft("UI/b", "Options"), draft("UI/c", "Quit"),
         draft("UI/d", "Credits")],
        {},
    )
    repo.edit("UI/a", 0, "Başla")
    repo.edit("UI/b", 0, "Seçenekler")
    repo.edit("UI/c", 0, "Çık")
    repo.approve("UI/c", row(repo, "UI/c")["version"])
    return session, {"project_id": opened["project_id"]}, events


def row(repo: Any, unit_id: str) -> dict[str, Any]:
    return next(item for item in repo.page() if item["unit_id"] == unit_id)


def state(repo: Any) -> dict[str, list[tuple[Any, ...]]]:
    """Everything a local review must never change."""
    return {
        table: [tuple(r) for r in repo.db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        for table in (
            "text_units", "source_revisions", "translation_revisions", "work_items",
            "editor_drafts", "policy_impacts", "jobs", "job_items",
        )
    }


def stored(repo: Any) -> list[tuple[Any, ...]]:
    return [
        tuple(r) for r in repo.db.execute(
            "SELECT unit_id,translation_revision,issues_json,note FROM local_reviews "
            "ORDER BY unit_id"
        )
    ]


async def review(
    session: ApplicationSession, identity: dict[str, Any], port: int, **extra: Any,
) -> dict[str, Any]:
    preview = await session.dispatch("local_review_preview", {
        **identity, "profile": profile(port, **extra.pop("profile", {})),
        "filters": extra.pop("filters", {}), "units": extra.pop("units", None),
    })
    return await session.dispatch("local_review_run", {
        **identity, "token": preview["token"], "user_action": True, **extra,
    })


def test_valid_codes_are_added_and_shown_without_changing_records(tmp_path: Path) -> None:
    async def main() -> None:
        session, identity, events = await open_session(tmp_path)
        try:
            async with FakeServer() as server:
                before = state(session.repo)
                preview = await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port), "filters": {},
                    "request_token": 3,
                })
                assert preview["request_token"] == 3 and preview["units"] is None
                assert (preview["in_scope"], preview["without_translation"]) == (4, 1)
                assert (preview["eligible"], preview["selected"], preview["remaining"]) == (
                    3, 3, 0,
                )
                assert preview["address"] == f"http://127.0.0.1:{server.port}/v1"
                assert preview["model"] == "synthetic" and preview["prompt_version"] == "review-v1"
                assert server.reviews == []  # The preview sends no review request.
                result = await session.dispatch("local_review_run", {
                    **identity, "token": preview["token"], "user_action": True,
                    "parallel_requests": 2,
                })
                assert result["status"] == "completed" and result["stop"] is None
                assert (result["reviewed"], result["flagged"], result["failed"]) == (3, 1, 0)
                assert result["code_counts"] == {"meaning_review": 1, "tone_review": 1}
                assert events and events[-1]["kind"] == "local_review"
                payload = server.reviews[0]
                assert "tools" not in payload and payload["model"] == "synthetic"
                schema = payload["response_format"]["schema"]
                assert schema["properties"]["issues"]["items"]["enum"] == list(
                    local_review.CODES
                )
                assert schema["additionalProperties"] is False
                # Nothing but the added review rows changed: text, status, approval, issues.
                assert state(session.repo) == before
                current = row(session.repo, "UI/a")
                assert stored(session.repo)[0] == (
                    "UI/a", current["translation_revision"],
                    '["meaning_review","tone_review"]', "Verb differs.",
                )
                assert row(session.repo, "UI/c")["status"] == "approved"
                page = await session.dispatch("page", {})
                rows = {item["unit_id"]: item for item in page["rows"]}
                (shown,) = rows["UI/a"]["local_reviews"]
                assert shown["issues"] == ["meaning_review", "tone_review"]
                assert (shown["model"], shown["prompt_version"]) == ("synthetic", "review-v1")
                assert rows["UI/b"]["local_reviews"][0]["issues"] == []
                assert rows["UI/d"]["local_reviews"] == []
                assert json.loads(rows["UI/a"]["issues_json"]) == json.loads(
                    before["translation_revisions"][0][6]
                )
                history = await session.dispatch("history", {"unit_id": "UI/a"})
                assert history["revisions"][0]["local_reviews"][0]["note"] == "Verb differs."
                # A second run with the same settings finds nothing left to review.
                again = await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port), "filters": {},
                })
                assert (again["already_reviewed"], again["selected"]) == (3, 0)
                # Other settings are another reviewer and may review the same revisions.
                other = await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port, temperature=0.0),
                    "filters": {},
                })
                assert other["selected"] == 3
                audit = save_current_quality_audit(session.repo)
                assert audit["local_review"]["code_counts"] == {
                    "meaning_review": 1, "tone_review": 1,
                }
                assert audit["local_review"]["reviewed_revisions"] == 3
                assert "meaning_review" not in audit["issue_counts"]
        finally:
            await session.close()

    asyncio.run(main())


def test_filters_and_explicit_units_bound_the_scope(tmp_path: Path) -> None:
    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer() as server:
                approved = await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port),
                    "filters": {"status": "approved"},
                })
                assert (approved["in_scope"], approved["selected"]) == (1, 1)
                assert approved["samples"] == ["UI/c"]
                result = await review(session, identity, server.port, units=["UI/b", "UI/d"])
                assert (result["total"], result["reviewed"]) == (1, 1)
                assert [item[0] for item in stored(session.repo)] == ["UI/b"]
                too_many = [f"UI/{index}" for index in range(MAX_RUN_RECORDS + 1)]
                with pytest.raises(Diagnostic) as error:
                    await session.dispatch("local_review_preview", {
                        **identity, "profile": profile(server.port), "units": too_many,
                    })
                assert error.value.params == {"p0": str(MAX_RUN_RECORDS)}
                for bad in ({"filters": {"unknown": 1}}, {"units": "UI/a"}, {"units": [1]}):
                    with pytest.raises(ValueError, match="selection is invalid"):
                        await session.dispatch("local_review_preview", {
                            **identity, "profile": profile(server.port), **bad,
                        })
        finally:
            await session.close()

    asyncio.run(main())


BAD_REPLIES: list[Any] = [
    completion("not json"),
    completion('{"id": "%(id)s", "issues": ["style_review"], "note": ""}'),
    completion('{"id": "%(id)s", "issues": [], "note": "", "approve": true}'),
    completion('{"id": "other", "issues": [], "note": ""}'),
    completion('{"id": "%(id)s", "id": "%(id)s", "issues": [], "note": ""}'),
    completion('{"id": "%(id)s", "issues": ["tone_review", "tone_review"], "note": ""}'),
    completion('{"id": "%(id)s", "issues": [], "note": "bad\\u202enote"}'),
    completion('{"id": "%(id)s", "issues": [], "note": "%(long)s"}'),
    completion('{"id": "%(id)s", "issues": "meaning_review", "note": ""}'),
    completion('{"id": "%(id)s", "issues": [], "note": NaN}'),
    completion("[]"),
    completion(None),
    {"choices": [{"message": {"content": "", "tool_calls": [{"id": "x"}]}}]},
    completion('{"id": "%(id)s", "issues": [], "note": ""}', finish_reason="length"),
    {"choices": []},
]


@pytest.mark.parametrize("reply", BAD_REPLIES)
def test_invalid_replies_are_rejected_without_writes(tmp_path: Path, reply: Any) -> None:
    async def respond(payload: dict[str, Any], request: dict[str, Any]) -> tuple[int, Any]:
        value = json.loads(json.dumps(reply))
        choices = value.get("choices") or [{}]
        content = choices[0].get("message", {}).get("content")
        if isinstance(content, str):
            choices[0]["message"]["content"] = content % {"id": request["id"], "long": "x" * 301}
        return 200, value

    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer(respond) as server:
                before = state(session.repo)
                result = await review(session, identity, server.port)
                assert result["status"] == "completed"
                assert (result["reviewed"], result["failed"]) == (0, 3)
                assert set(result["failure_codes"]) <= {
                    "response_schema_error", "unexpected_tool_call", "output_truncated",
                }
                assert stored(session.repo) == [] and state(session.repo) == before
        finally:
            await session.close()

    asyncio.run(main())


def test_parse_verdict_is_strict() -> None:
    assert parse_verdict('{"id": "r", "issues": ["grammar_review"]}', "r") == (
        ["grammar_review"], "",
    )
    assert parse_verdict('{"id": "r", "issues": [], "note": " ok "}', "r") == ([], "ok")
    for raw in (
        '{"id": "r", "issues": ["Meaning_review"]}',
        '{"id": "r", "issues": [null]}',
        '{"id": 1, "issues": []}',
        '{"id": "r"}',
        '{"id": "r", "issues": [], "note": "line\\nbreak"}',
        '{"id": "r", "issues": [], "text": "rewritten"}',
        "x" * (local_review.MAX_REPLY_BYTES + 1),
    ):
        with pytest.raises(ValueError, match="invalid JSON structure"):
            parse_verdict(raw, "r")
    assert RESPONSE_MESSAGE.startswith("The local reviewer response")


def test_unreachable_server_or_missing_model_is_reported_without_writes(tmp_path: Path) -> None:
    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            before = state(session.repo)
            port = free_port()
            with pytest.raises(Diagnostic) as error:
                await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(port), "filters": {},
                })
            assert error.value.template == UNREACHABLE_MESSAGE
            assert error.value.params == {"p0": f"http://127.0.0.1:{port}/v1"}
            assert session.local_review_plan is None
            async with FakeServer(models=("other",)) as server:
                with pytest.raises(Diagnostic) as error:
                    await session.dispatch("local_review_preview", {
                        **identity, "profile": profile(server.port), "filters": {},
                    })
                assert error.value.template == MODEL_MISSING_MESSAGE
            # The server disappears between the preview and the run: the run stops.
            server = FakeServer()
            async with server:
                preview = await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port), "filters": {},
                })
            result = await session.dispatch("local_review_run", {
                **identity, "token": preview["token"], "user_action": True,
            })
            assert result["status"] == "stopped" and result["reviewed"] == 0
            assert result["stop"]["code"] == STOP_UNREACHABLE
            assert result["stop"]["reason"] == "connection"
            assert stored(session.repo) == [] and state(session.repo) == before
            # Only local addresses are accepted.
            with pytest.raises(ValueError, match="only a local model address"):
                await session.dispatch("local_review_preview", {
                    **identity, "profile": {**profile(1), "address": "http://example.com"},
                })
        finally:
            await session.close()

    asyncio.run(main())


def test_server_errors_stop_the_run_and_keep_completed_reviews(tmp_path: Path) -> None:
    calls = 0

    async def respond(payload: dict[str, Any], request: dict[str, Any]) -> tuple[int, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return 200, verdict(request, ["grammar_review"])
        return 500, b"out of memory"

    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer(respond) as server:
                result = await review(session, identity, server.port)
                assert result["status"] == "stopped" and result["reviewed"] == 1
                # A catalogued template; the raw provider code is diagnostic data only.
                assert result["stop"]["code"] == STOP_OUT_OF_MEMORY
                assert result["stop"]["params"] == {}
                assert result["stop"]["reason"] == "out_of_memory"
                assert "out_of_memory" not in result["stop"]["message"]
                assert len(stored(session.repo)) == 1 and calls == 2
        finally:
            await session.close()

    asyncio.run(main())


def test_cancel_mid_run_keeps_completed_reviews_and_a_rerun_resumes(tmp_path: Path) -> None:
    release = asyncio.Event()

    async def respond(payload: dict[str, Any], request: dict[str, Any]) -> tuple[int, Any]:
        if request["source"] != "Options":
            await release.wait()
        return 200, verdict(request, ["omission_review"])

    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer(respond) as server:
                preview = await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port), "filters": {},
                })
                task = asyncio.create_task(session.dispatch("local_review_run", {
                    **identity, "token": preview["token"], "user_action": True,
                    "parallel_requests": 3,
                }))
                for _ in range(500):
                    await asyncio.sleep(0.01)
                    if stored(session.repo) and len(server.reviews) == 3:
                        break
                assert [item[0] for item in stored(session.repo)] == ["UI/b"]
                # Busy while running: other model work and a second run are refused.
                with pytest.raises(ValueError, match="before the local review"):
                    await session.dispatch("local_review_preview", {
                        **identity, "profile": profile(server.port),
                    })
                assert await session.dispatch("local_review_cancel", {}) is True
                result = await task
                assert result["status"] == "cancelled" and result["reviewed"] == 1
                release.set()
                assert [item[0] for item in stored(session.repo)] == ["UI/b"]
                assert session.local_review is None
                resumed = await review(session, identity, server.port)
                assert (resumed["total"], resumed["reviewed"]) == (2, 2)
                assert [item[0] for item in stored(session.repo)] == ["UI/a", "UI/b", "UI/c"]
        finally:
            await session.close()

    asyncio.run(main())


def test_closing_the_session_cancels_a_running_review(tmp_path: Path) -> None:
    async def respond(payload: dict[str, Any], request: dict[str, Any]) -> tuple[int, Any]:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        async with FakeServer(respond) as server:
            preview = await session.dispatch("local_review_preview", {
                **identity, "profile": profile(server.port), "filters": {},
            })
            task = asyncio.create_task(session.dispatch("local_review_run", {
                **identity, "token": preview["token"], "user_action": True,
            }))
            while not server.reviews:
                await asyncio.sleep(0.01)
            await session.close()
            assert (await task)["status"] == "cancelled"
            assert session.repository is None

    asyncio.run(main())


def test_revision_change_leaves_codes_with_the_old_revision(tmp_path: Path) -> None:
    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer() as server:
                await review(session, identity, server.port)
                repo = session.repo
                old = row(repo, "UI/a")
                repo.edit("UI/a", old["version"], "Başlat")
                page = {r["unit_id"]: r for r in (await session.dispatch("page", {}))["rows"]}
                assert page["UI/a"]["local_reviews"] == []
                history = await session.dispatch("history", {"unit_id": "UI/a"})
                by_id = {r["id"]: r["local_reviews"] for r in history["revisions"]}
                assert by_id[old["translation_revision"]][0]["issues"] == [
                    "meaning_review", "tone_review",
                ]
                assert by_id[page["UI/a"]["translation_revision"]] == []
                # Codes belong to the revision: selecting it again shows them again.
                await session.dispatch("select_candidate", {
                    "unit_id": "UI/a", "version": page["UI/a"]["version"],
                    "revision": old["translation_revision"],
                })
                page = {r["unit_id"]: r for r in (await session.dispatch("page", {}))["rows"]}
                assert page["UI/a"]["local_reviews"][0]["issues"] == [
                    "meaning_review", "tone_review",
                ]
                # A record edited after the preview is skipped without a request.
                preview = await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port, temperature=1.0),
                    "filters": {},
                })
                current = row(repo, "UI/b")
                repo.edit("UI/b", current["version"], "Ayarlar")
                sent = len(server.reviews)
                result = await session.dispatch("local_review_run", {
                    **identity, "token": preview["token"], "user_action": True,
                })
                assert (result["changed"], result["reviewed"]) == (1, 2)
                assert len(server.reviews) == sent + 2
        finally:
            await session.close()

    asyncio.run(main())


def test_guards_explicit_action_and_busy_state(tmp_path: Path) -> None:
    async def main() -> None:
        session = ApplicationSession()
        with pytest.raises(ValueError, match="Open a project first"):
            await session.dispatch("local_review_preview", {"project_id": "x"})
        await session.close()
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer() as server:
                with pytest.raises(ValueError, match="Local review request project identity"):
                    await session.dispatch("local_review_preview", {"project_id": "other"})
                session.extracting = True
                with pytest.raises(ValueError, match="before the local review"):
                    await session.dispatch("local_review_run", identity)
                session.extracting = False
                with pytest.raises(ValueError, match="preview expired"):
                    await session.dispatch("local_review_run", {
                        **identity, "token": "x", "user_action": True,
                    })
                with pytest.raises(ValueError, match="Select a local server and model"):
                    await session.dispatch("local_review_preview", identity)
                with pytest.raises(ValueError, match="reasoning option"):
                    await session.dispatch("local_review_preview", {
                        **identity,
                        "profile": profile(server.port, provider="lm-studio",
                                           reasoning_effort="adaptive"),
                    })
                preview = await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port),
                })
                for action in (None, False, "yes", 1):
                    with pytest.raises(ValueError, match="explicit user action"):
                        await session.dispatch("local_review_run", {
                            **identity, "token": preview["token"], "user_action": action,
                        })
                    # A refused run consumed the preview.
                    with pytest.raises(ValueError, match="preview expired"):
                        await session.dispatch("local_review_run", {
                            **identity, "token": preview["token"], "user_action": True,
                        })
                    preview = await session.dispatch("local_review_preview", {
                        **identity, "profile": profile(server.port),
                    })
                assert server.reviews == [] and stored(session.repo) == []
                # While a review runs, translation and other model requests wait for it.
                session.local_review = SimpleNamespace(cancel=lambda: None)  # type: ignore[assignment]
                try:
                    job = JobStore(session.repo).create(
                        ["UI/d"], GenerationProfile("llama-cpp", profile(1)["address"], "m", 8192),
                    )
                    with pytest.raises(ValueError, match="local review to finish"):
                        await session.dispatch("run_job", {"job_id": job})
                    with pytest.raises(ValueError, match="local review to finish"):
                        await session.dispatch("create_job", {
                            "profile": profile(1), "kind": "prototype", "units": ["UI/d"],
                        })
                    with pytest.raises(ValueError, match="second model request"):
                        await session.dispatch("models", profile(1))
                    with pytest.raises(ValueError, match="before reusing translation memory"):
                        await session.dispatch("translation_memory_preview", identity)
                finally:
                    session.local_review = None
                assert LOCAL_REVIEW_BUSY.startswith("Wait for the local review")
        finally:
            await session.close()

    asyncio.run(main())


@pytest.mark.parametrize(
    "provider,mode,expected",
    [
        ("llama-cpp", "none", {"reasoning_effort": "none",
                               "chat_template_kwargs": {"enable_thinking": False}}),
        ("lm-studio", "none", {"reasoning_effort": "none"}),
        ("llama-cpp", "adaptive", {"thinking_budget_tokens": 64 + len("Start") + len("Başla")}),
        ("llama-cpp", "default", {}),
    ],
)
def test_reasoning_options_follow_the_profile(
    tmp_path: Path, provider: str, mode: str, expected: dict[str, Any],
) -> None:
    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer() as server:
                await review(
                    session, identity, server.port, units=["UI/a"],
                    profile={"provider": provider, "reasoning_effort": mode,
                             "structured_output": provider == "lm-studio"},
                )
                (payload,) = server.reviews
                for key in ("reasoning_effort", "chat_template_kwargs", "thinking_budget_tokens"):
                    assert payload.get(key) == expected.get(key), key
                if mode == "adaptive":
                    assert payload["max_tokens"] == 512 + expected["thinking_budget_tokens"]
                if provider == "lm-studio":
                    assert payload["response_format"]["type"] == "json_schema"
                    assert payload["response_format"]["json_schema"]["strict"] is True
                else:
                    assert "response_format" not in payload
                (review_row,) = session.repo.db.execute(
                    "SELECT reviewer_json FROM local_reviews"
                ).fetchall()
                reviewer = json.loads(review_row[0])
                assert (reviewer["provider"], reviewer["reasoning_effort"]) == (provider, mode)
        finally:
            await session.close()

    asyncio.run(main())


def test_job_report_counts_local_codes_apart_from_checks(tmp_path: Path) -> None:
    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer() as server:
                repo = session.repo
                # A source set is complete: keep the earlier records and add two.
                repo.ingest(
                    [draft("UI/a", "Start"), draft("UI/b", "Options"), draft("UI/c", "Quit"),
                     draft("UI/d", "Credits"), draft("UI/e", "Start"), draft("UI/f", "Help")],
                    {},
                )
                job = JobStore(repo).create(
                    ["UI/e", "UI/f"],
                    GenerationProfile("llama-cpp", profile(server.port)["address"],
                                      "synthetic", 8192),
                )
                await TranslationJobService(repo).run(job)
                assert server.translations == 2
                approved_before = row(repo, "UI/c")["status"]
                await review(session, identity, server.port, units=["UI/e", "UI/f"])
                report = job_report(repo, job)
                assert report["local_review"]["code_counts"] == {
                    "meaning_review": 1, "tone_review": 1,
                }
                assert report["local_review"]["reviewed_revisions"] == 2
                assert report["local_review"]["revisions_with_codes"] == 1
                assert "meaning_review" not in report["issue_counts"]
                records = {item["unit_id"]: item for item in report["records"]}
                assert records["UI/e"]["local_review_issues"] == ["meaning_review", "tone_review"]
                assert records["UI/e"]["review_status"] == "translated"
                assert report["human_approved_records"] == 0
                assert row(repo, "UI/c")["status"] == approved_before
                html = save_review_html(repo, job).read_text(encoding="utf-8")
                assert "Local reviewer: meaning" in html
        finally:
            await session.close()

    asyncio.run(main())


def test_preview_refuses_when_another_project_opens_during_the_server_check(
    tmp_path: Path,
) -> None:
    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        other_game = tmp_path / "other-game"
        other_game.mkdir()
        try:
            async with FakeServer() as server:
                server.models_gate = asyncio.Event()
                preview = asyncio.create_task(session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port), "filters": {},
                    "request_token": "r1",
                }))
                for _ in range(500):
                    await asyncio.sleep(0.01)
                    if server.model_requests:
                        break
                assert server.model_requests == 1
                # The user opens another project while the slow server check is pending.
                opened = await session.dispatch("open", {
                    "game": str(other_game), "project": str(tmp_path / "other-project"),
                })
                assert opened["project_id"] != identity["project_id"]
                server.models_gate.set()
                with pytest.raises(ValueError, match="open project changed") as raised:
                    await preview
                assert str(raised.value) == LOCAL_REVIEW_PROJECT_CHANGED
                assert session.local_review_plan is None
                # No plan of the first project can be run in the second one.
                with pytest.raises(ValueError, match="preview expired"):
                    await session.dispatch("local_review_run", {
                        "project_id": opened["project_id"], "token": "any",
                        "user_action": True,
                    })
                assert server.reviews == []
                assert session.repo.db.execute(
                    "SELECT count(*) FROM local_reviews"
                ).fetchone()[0] == 0
        finally:
            await session.close()

    asyncio.run(main())


def test_preview_plan_is_bound_to_the_checked_project_and_revisions(tmp_path: Path) -> None:
    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer() as server:
                preview = await session.dispatch("local_review_preview", {
                    **identity, "profile": profile(server.port), "filters": {},
                })
                plan = session.local_review_plan
                assert plan is not None and plan["token"] == preview["token"]
                assert plan["project_id"] == identity["project_id"] == preview["project_id"]
                assert plan["units"] == [
                    [unit, row(session.repo, unit)["translation_revision"]]
                    for unit in ("UI/a", "UI/b", "UI/c")
                ]
        finally:
            await session.close()

    asyncio.run(main())


@pytest.mark.parametrize(
    ("code", "template"),
    [
        ("out_of_memory", STOP_OUT_OF_MEMORY),
        ("not_found", STOP_MODEL_MISSING),
        ("unauthorized", STOP_UNAUTHORIZED),
        ("unsupported_option", STOP_UNSUPPORTED),
        ("server_unavailable", STOP_UNREACHABLE),
        ("connection", STOP_UNREACHABLE),
        ("some_future_code", STOP_SERVER),
    ],
)
def test_stop_reasons_use_catalogued_templates_without_raw_codes(
    code: str, template: str,
) -> None:
    reviewer = local_review.reviewer_profile(profile(1))
    repo: Any = SimpleNamespace()
    run = LocalReviewRun(repo, {"reviewer": reviewer, "units": []})
    stop = run.stopped(ProviderError(code, "Provider detail."))
    assert stop["code"] == template and stop["reason"] == code
    assert stop["message"] == template.format(**stop["params"])
    # The raw provider code is kept as diagnostic data, never as interface text.
    assert code not in stop["params"].values()
    assert "_" not in stop["message"] and "Provider detail" not in stop["message"]
    assert template in english_catalog()


def test_local_reviewer_labels_and_messages_are_in_every_catalog() -> None:
    """Backend templates shown through the interface catalogs, not scanned by test_i18n."""
    templates = set(local_review.LABELS.values()) | {
        value for name, value in vars(local_review).items()
        if isinstance(value, str) and (name.startswith("STOP_") or name.endswith("_MESSAGE"))
    } | set(local_review.STOP_MESSAGES.values()) | {LOCAL_REVIEW_PROJECT_CHANGED}
    assert len(templates) >= 20
    folder = Path(local_review.__file__).parent / "resources" / "locales"
    for language in ("en", "de", "es", "fr", "pt", "ru", "tr", "zh"):
        catalog = json.loads((folder / f"{language}.json").read_text(encoding="utf-8"))
        assert templates <= catalog.keys(), (language, sorted(templates - catalog.keys()))


def test_quality_audit_lists_records_flagged_only_by_the_local_reviewer(
    tmp_path: Path,
) -> None:
    async def main() -> None:
        session, identity, _ = await open_session(tmp_path)
        try:
            async with FakeServer() as server:
                await review(session, identity, server.port)
                audit = save_current_quality_audit(session.repo)
                content = json.loads(Path(audit["json_path"]).read_text(encoding="utf-8"))
                records = {item["unit_id"]: item for item in content["records"]}
                # 'Start' -> 'Başla' has no deterministic finding; only the model flagged it.
                assert records["UI/a"]["audit_issues"] == []
                assert records["UI/a"]["new_issues"] == []
                assert records["UI/a"]["local_review_issues"] == [
                    "meaning_review", "tone_review",
                ]
                assert "UI/b" not in records  # Reviewed without codes and no findings.
                assert audit["flagged_records"] == sum(
                    bool(item["audit_issues"]) for item in content["records"]
                )
                assert audit["local_review_records"] == 1
                assert audit["local_review_only_records"] == 1
                html = Path(audit["html_path"]).read_text(encoding="utf-8")
                assert "Yerel inceleyici" in html
                assert "Local reviewer: meaning; Local reviewer: tone" in html
                assert row(session.repo, "UI/a")["status"] == "translated"
        finally:
            await session.close()

    asyncio.run(main())
