"""Optional local reviewer pass: model-suggested issue codes for current translations.

It runs only on an explicit user action and only against a model server the user has
already started; it never starts, loads or downloads a server or model. The model's
reply is untrusted data: one strict JSON object whose codes come from a closed set.
A review only adds codes bound to one immutable translation revision. It never edits
text, approves, changes a status or removes a stored issue, and codes of an earlier
revision stay with that revision, so they no longer apply once the text changes.
"""

import asyncio
import json
import unicodedata
from collections import Counter, deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from hashlib import sha256
from importlib.resources import files
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError

from unitytranslator.diagnostics import Diagnostic
from unitytranslator.jobs import MAX_PARALLEL_REQUESTS
from unitytranslator.json_boundary import strict_json
from unitytranslator.providers import (
    ADAPTIVE_REASONING_POLICY,
    REASONING_MODES,
    LocalProvider,
    ProviderError,
    adaptive_reasoning_budget,
    local_endpoint,
    reasoning_supported,
    response_diagnostics,
)
from unitytranslator.repository import ProjectRepository, canonical, now

PROMPT_VERSION = "review-v1"
# The closed code set; a reply with any other code is rejected as a whole.
CODES = (
    "meaning_review",
    "omission_review",
    "addition_review",
    "terminology_review",
    "tone_review",
    "grammar_review",
)
Code = Literal[
    "meaning_review",
    "omission_review",
    "addition_review",
    "terminology_review",
    "tone_review",
    "grammar_review",
]
# English templates; interface catalogs localize them by this text.
LABELS = {
    "meaning_review": "Local reviewer: meaning",
    "omission_review": "Local reviewer: omission",
    "addition_review": "Local reviewer: addition",
    "terminology_review": "Local reviewer: terminology",
    "tone_review": "Local reviewer: tone",
    "grammar_review": "Local reviewer: grammar",
}
MAX_RUN_RECORDS = 500
MAX_NOTE_CHARACTERS = 300
MAX_REPLY_BYTES = 64 * 1024
MAX_SAMPLES = 20
PROGRESS_INTERVAL = 0.2
# Fields that identify a reviewer; the server address is recorded but not part of it.
REVIEWER_KEY_FIELDS = (
    "prompt_version", "provider", "model", "reasoning_effort", "temperature",
    "structured_output",
)
# Server-wide failures stop the run; other failures skip one record without a write.
STOP_CODES = frozenset({
    "connection", "server_unavailable", "out_of_memory", "not_found", "unauthorized",
    "unsupported_option",
})
UNREACHABLE_CODES = frozenset({"connection", "server_unavailable", "timeout"})

PROFILE_MESSAGE = "Select a local server and model in Model before the local review."
UNREACHABLE_MESSAGE = (
    "The local reviewer could not reach a running model server at {p0}. Start the server "
    "and load the model yourself, then try again; nothing was written."
)
MODEL_MISSING_MESSAGE = (
    "The model {p0} is not available on the server at {p1}. Load it on the server yourself, "
    "then try again; nothing was written."
)
SELECTION_MESSAGE = "The local review selection is invalid."
SELECTION_LIMIT_MESSAGE = "Select at most {p0} records for one local review."
RESPONSE_MESSAGE = (
    "The local reviewer response has an invalid JSON structure, record ID or issue code."
)
TRUNCATED_MESSAGE = (
    "The local reviewer response was cut off at the output token limit; no codes were stored."
)
STOP_UNREACHABLE = (
    "The local review stopped: the model server at {p0} is not reachable or not ready. "
    "Completed reviews were kept; start the server yourself and run the review again."
)
STOP_OUT_OF_MEMORY = (
    "The local review stopped: the model server ran out of memory. "
    "Completed reviews were kept."
)
STOP_MODEL_MISSING = (
    "The local review stopped: the model server did not find the model or endpoint. "
    "Completed reviews were kept."
)
STOP_UNAUTHORIZED = (
    "The local review stopped: the model server refused the request as unauthorized. "
    "Completed reviews were kept."
)
STOP_UNSUPPORTED = (
    "The local review stopped: the model server does not support a requested option. "
    "Completed reviews were kept."
)
STOP_SERVER = (
    "The local review stopped because the model server reported an error. "
    "Completed reviews were kept."
)
# Catalogued stop messages by provider code; the raw code never reaches interface text.
STOP_MESSAGES = {
    "out_of_memory": STOP_OUT_OF_MEMORY,
    "not_found": STOP_MODEL_MISSING,
    "unauthorized": STOP_UNAUTHORIZED,
    "unsupported_option": STOP_UNSUPPORTED,
}


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: StrictStr
    issues: list[Code]
    note: StrictStr = ""


def label(code: str) -> str:
    """English label of a local reviewer code; unknown stored values stay verbatim."""
    return LABELS.get(code, code)


def parse_verdict(raw: str, expected_id: str) -> tuple[list[str], str]:
    """Validate one reply: the requested ID, known unique codes and a short plain note."""
    if len(raw.encode("utf-8")) > MAX_REPLY_BYTES:
        raise ValueError(RESPONSE_MESSAGE)
    try:
        verdict = Verdict.model_validate(strict_json(raw))
    except ValidationError as exc:
        raise ValueError(RESPONSE_MESSAGE) from exc
    note = verdict.note.strip()
    if (
        verdict.id != expected_id
        or len(set(verdict.issues)) != len(verdict.issues)
        or len(note) > MAX_NOTE_CHARACTERS
        # Control, format (including bidirectional) and unassigned characters are refused.
        or any(unicodedata.category(character).startswith("C") for character in note)
    ):
        raise ValueError(RESPONSE_MESSAGE)
    return sorted(verdict.issues), note


def reviewer_profile(profile: Any) -> dict[str, Any]:
    """The validated reviewer settings from the selected model profile."""
    if not isinstance(profile, Mapping):
        raise ValueError(PROFILE_MESSAGE)
    provider, address, model = (profile.get(k) for k in ("provider", "address", "model"))
    if (
        provider not in ("lm-studio", "llama-cpp")
        or not isinstance(address, str)
        or not isinstance(model, str)
        or not model.strip()
        or len(model) > 512
    ):
        raise ValueError(PROFILE_MESSAGE)
    endpoint = local_endpoint(address)
    context_tokens = profile.get("context_tokens", 8192)
    output_tokens = profile.get("output_tokens", 2048)
    if (
        type(context_tokens) is not int
        or type(output_tokens) is not int
        or not 512 <= context_tokens <= 1_048_576
        or not 128 <= output_tokens <= 8192
    ):
        raise ProviderError("context", "The context or output token limit is invalid.")
    temperature = profile.get("temperature", 0.2)
    structured = profile.get("structured_output", True)
    if (
        type(temperature) not in (int, float)
        or not 0 <= temperature <= 2
        or type(structured) is not bool
    ):
        raise ValueError(PROFILE_MESSAGE)
    reasoning = profile.get("reasoning_effort", "default")
    if reasoning not in REASONING_MODES or not reasoning_supported(provider, reasoning):
        raise ValueError("Unsupported provider reasoning option.")
    return {
        "prompt_version": PROMPT_VERSION,
        "provider": provider,
        "address": endpoint,
        "model": model,
        "context_tokens": context_tokens,
        "output_tokens": output_tokens,
        "temperature": float(temperature),
        "reasoning_effort": reasoning,
        "structured_output": structured,
    }


def reviewer_key(reviewer: Mapping[str, Any]) -> str:
    identity = {field: reviewer[field] for field in REVIEWER_KEY_FIELDS}
    return sha256(canonical(identity).encode("utf-8")).hexdigest()


def selection(
    repo: ProjectRepository, reviewer: Mapping[str, Any], filters: Any, units: Any,
) -> dict[str, Any]:
    """Records in the review filter (and optional unit list) and the first ones to review."""
    if not isinstance(filters, Mapping) or not set(filters) <= {
        "search", "status", "category", "affected",
    }:
        raise ValueError(SELECTION_MESSAGE)
    search, status = filters.get("search", ""), filters.get("status")
    category, affected = filters.get("category"), filters.get("affected", False)
    if (
        not isinstance(search, str)
        or not (status is None or isinstance(status, str))
        or not (category is None or isinstance(category, str))
        or type(affected) is not bool
    ):
        raise ValueError(SELECTION_MESSAGE)
    where, parameters = repo.filters(search, status, category, affected)
    if units is not None:
        if not isinstance(units, list) or not units or any(
            not isinstance(unit, str) for unit in units
        ):
            raise ValueError(SELECTION_MESSAGE)
        if len(set(units)) > MAX_RUN_RECORDS:
            raise Diagnostic(SELECTION_LIMIT_MESSAGE, p0=MAX_RUN_RECORDS)
        where += f" AND u.unit_id IN ({','.join('?' * len(set(units)))})"
        parameters = [*parameters, *sorted(set(units))]
    key = reviewer_key(reviewer)
    rows = repo.db.execute(
        "SELECT u.unit_id,u.original_key,w.translation_revision,"
        "t.source_revision IS u.source_revision AS current,"
        "EXISTS(SELECT 1 FROM local_reviews r WHERE r.translation_revision="
        "w.translation_revision AND r.reviewer_key=?) AS reviewed "
        "FROM text_units u JOIN source_revisions s ON s.id=u.source_revision "
        "JOIN work_items w ON w.unit_id=u.unit_id "
        "LEFT JOIN translation_revisions t ON t.id=w.translation_revision "
        f"WHERE {where} ORDER BY u.original_key,u.unit_id",
        (key, *parameters),
    ).fetchall()
    translated = [row for row in rows if row["translation_revision"] and row["current"]]
    eligible = [row for row in translated if not row["reviewed"]]
    chosen = eligible[:MAX_RUN_RECORDS]
    return {
        "in_scope": len(rows),
        "without_translation": len(rows) - len(translated),
        "already_reviewed": len(translated) - len(eligible),
        "eligible": len(eligible),
        "selected": len(chosen),
        "remaining": len(eligible) - len(chosen),
        "samples": [row["original_key"] for row in chosen[:MAX_SAMPLES]],
        "units": [[row["unit_id"], row["translation_revision"]] for row in chosen],
    }


async def check_server(
    reviewer: Mapping[str, Any], transport: Any = None,
) -> None:
    """Confirm the already running server answers and lists the model; starts nothing."""
    provider = LocalProvider(reviewer["provider"], reviewer["address"], transport)
    try:
        models = await provider.list_models()
    except ProviderError as exc:
        if exc.code in UNREACHABLE_CODES:
            raise Diagnostic(UNREACHABLE_MESSAGE, p0=reviewer["address"]) from exc
        raise
    if reviewer["model"] not in models:
        raise Diagnostic(MODEL_MISSING_MESSAGE, p0=reviewer["model"], p1=reviewer["address"])


def response_schema(request_id: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string", "enum": [request_id]},
            "issues": {
                "type": "array",
                "items": {"type": "string", "enum": list(CODES)},
                "uniqueItems": True,
                "maxItems": len(CODES),
            },
            "note": {"type": "string", "maxLength": MAX_NOTE_CHARACTERS},
        },
        "required": ["id", "issues", "note"],
        "additionalProperties": False,
    }


async def review_record(
    provider: LocalProvider, reviewer: Mapping[str, Any], item: Mapping[str, Any],
) -> dict[str, Any]:
    """One bounded review request; returns validated codes, note and bounded metrics."""
    request_id = str(item["request_id"])
    prompt = files("unitytranslator.resources").joinpath(
        PROMPT_VERSION + ".txt"
    ).read_text(encoding="utf-8")
    data = {
        "id": request_id,
        "source_language": item["source_language"],
        "target_language": item["target_language"],
        "category": item["category"],
        "context": item["context"],
        "source": item["source_text"],
        "translation": item["text"],
    }
    output_tokens = int(reviewer["output_tokens"])
    payload: dict[str, Any] = {
        "model": reviewer["model"],
        "temperature": reviewer["temperature"],
        "max_tokens": output_tokens,
        "stream": False,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ],
    }
    reasoning = reviewer["reasoning_effort"]
    if reasoning == "none":
        payload["reasoning_effort"] = "none"
        if reviewer["provider"] == "llama-cpp":
            payload["chat_template_kwargs"] = {"enable_thinking": False}
    if reviewer["structured_output"]:
        schema = response_schema(request_id)
        payload["response_format"] = (
            {"type": "json_schema", "json_schema": {
                "name": "review_response", "strict": True, "schema": schema,
            }}
            if reviewer["provider"] == "lm-studio"
            else {"type": "json_object", "schema": schema}
        )
    measured = {"messages": payload["messages"], **(
        {"response_format": payload["response_format"]} if "response_format" in payload else {}
    )}
    size = len(json.dumps(measured, ensure_ascii=False).encode("utf-8"))
    safe = int(int(reviewer["context_tokens"]) * 0.8)
    budget = 0
    if reasoning == "adaptive":
        wanted = adaptive_reasoning_budget(item["source_text"] + item["text"], [])
        budget = max(0, min(wanted, safe - output_tokens - size))
        payload["thinking_budget_tokens"] = budget
        payload["max_tokens"] = output_tokens + budget
    if size + output_tokens + budget > safe:
        raise ProviderError(
            "context",
            "The prompt and output schema exceed the safe context budget; "
            "the text was not truncated.",
        )
    started = perf_counter()
    result = await provider.request("POST", "/chat/completions", payload, generation=True)
    diagnostics: dict[str, Any] = dict(response_diagnostics(result))
    if reasoning == "adaptive":
        diagnostics["reasoning_policy"] = ADAPTIVE_REASONING_POLICY
        diagnostics["reasoning_budget_tokens"] = budget
    try:
        choice = result["choices"][0]
        message = choice["message"]
        if not isinstance(choice, dict) or not isinstance(message, dict):
            raise ValueError(RESPONSE_MESSAGE)
        if (
            message.get("tool_calls")
            or message.get("function_call")
            or choice.get("finish_reason") in ("tool_calls", "function_call")
        ):
            raise ProviderError(
                "unexpected_tool_call",
                "The model returned a tool call; it was not executed.",
                diagnostics,
            )
        if choice.get("finish_reason") == "length":
            raise ProviderError("output_truncated", TRUNCATED_MESSAGE, diagnostics)
        raw = message["content"]
        if not isinstance(raw, str):
            raise ValueError(RESPONSE_MESSAGE)
        issues, note = parse_verdict(raw, request_id)
    except ProviderError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, RecursionError) as exc:
        raise ProviderError("response_schema_error", RESPONSE_MESSAGE, diagnostics) from exc
    return {
        "issues": issues,
        "note": note,
        "metadata": {
            "elapsed_seconds": round(perf_counter() - started, 3),
            "diagnostics": diagnostics,
        },
    }


def store(
    repo: ProjectRepository, item: Mapping[str, Any], reviewer: Mapping[str, Any], key: str,
    result: Mapping[str, Any],
) -> bool:
    """Add one review row in its own transaction; nothing else is written or changed."""
    with repo.transaction() as db:
        cursor = db.execute(
            "INSERT OR IGNORE INTO local_reviews VALUES(?,?,?,?,?,?,?,?,?)",
            (
                uuid4().hex, item["unit_id"], item["translation_revision"], key,
                canonical(dict(reviewer)), canonical(list(result["issues"])), result["note"],
                canonical(dict(result["metadata"])), now(),
            ),
        )
        return cursor.rowcount == 1


def current_item(repo: ProjectRepository, unit_id: str, revision: str) -> dict[str, Any] | None:
    """The planned revision if it is still the record's current translation."""
    row = repo.db.execute(
        "SELECT u.unit_id,u.active,w.translation_revision,t.id AS revision,t.text,"
        "t.target_language,s.source_text,s.source_language,s.category,s.context "
        "FROM text_units u JOIN work_items w ON w.unit_id=u.unit_id "
        "JOIN translation_revisions t ON t.id=? "
        "JOIN source_revisions s ON s.id=t.source_revision "
        "WHERE u.unit_id=? AND s.id=u.source_revision",
        (revision, unit_id),
    ).fetchone()
    if row is None or not row["active"] or row["translation_revision"] != revision:
        return None
    return {
        "unit_id": unit_id,
        "translation_revision": revision,
        "text": row["text"],
        "target_language": row["target_language"],
        "source_text": row["source_text"],
        "source_language": row["source_language"],
        "category": row["category"],
        "context": row["context"],
        "request_id": uuid4().hex[:12],
    }


class LocalReviewRun:
    """One explicit run: bounded parallel requests through one client, per-record commits.

    Cancelling keeps every completed review; a later run skips revisions this reviewer
    already reviewed, so it resumes where the cancelled run stopped.
    """

    def __init__(
        self,
        repo: ProjectRepository,
        plan: Mapping[str, Any],
        *,
        parallel_requests: int = 1,
        transport: Any = None,
    ):
        if (
            type(parallel_requests) is not int
            or not 1 <= parallel_requests <= MAX_PARALLEL_REQUESTS
        ):
            raise Diagnostic(
                "Parallel requests must be between 1 and {p0}.", p0=MAX_PARALLEL_REQUESTS
            )
        self.repo = repo
        self.reviewer = dict(plan["reviewer"])
        self.key = reviewer_key(self.reviewer)
        self.units = [(str(unit), str(revision)) for unit, revision in plan["units"]]
        self.parallel_requests = parallel_requests
        self.transport = transport
        self.cancelled = False
        self.workers: list[asyncio.Task[None]] = []
        self.counts: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()
        self.codes: Counter[str] = Counter()
        self.stop: dict[str, Any] | None = None

    def cancel(self) -> None:
        """Stop sending; in-flight requests are abandoned and write nothing."""
        self.cancelled = True
        for task in self.workers:
            task.cancel()

    def snapshot(self, status: str) -> dict[str, Any]:
        return {
            "kind": "local_review",
            "project_id": self.repo.project_id,
            "status": status,
            "total": len(self.units),
            "reviewed": self.counts["reviewed"],
            "flagged": self.counts["flagged"],
            "changed": self.counts["changed"],
            "failed": sum(self.failures.values()),
            "failure_codes": dict(self.failures),
            "code_counts": dict(self.codes),
            "stop": self.stop,
            "model": self.reviewer["model"],
            "address": self.reviewer["address"],
            "prompt_version": PROMPT_VERSION,
        }

    def stopped(self, exc: ProviderError) -> dict[str, Any]:
        if exc.code in UNREACHABLE_CODES:
            template, params = STOP_UNREACHABLE, {"p0": self.reviewer["address"]}
        else:
            template, params = STOP_MESSAGES.get(exc.code, STOP_SERVER), {}
        return {
            "code": template, "params": params, "reason": exc.code,
            "message": template.format(**params),
        }

    async def run(
        self, progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        provider = LocalProvider(
            self.reviewer["provider"], self.reviewer["address"], self.transport,
            structured_output=self.reviewer["structured_output"],
        )
        client = provider.job_client(self.parallel_requests)
        provider = provider.with_client(client)
        queue = deque(self.units)
        last_event = 0.0

        async def worker() -> None:
            nonlocal last_event
            while queue and not self.cancelled and self.stop is None:
                unit_id, revision = queue.popleft()
                item = current_item(self.repo, unit_id, revision)
                if item is None:
                    self.counts["changed"] += 1
                    continue
                try:
                    result = await review_record(provider, self.reviewer, item)
                except ProviderError as exc:
                    if exc.code in STOP_CODES:
                        if self.stop is None:
                            self.stop = self.stopped(exc)
                        return
                    self.failures[exc.code] += 1
                else:
                    # Bound to the revision that was reviewed, even if the text changed since.
                    if store(self.repo, item, self.reviewer, self.key, result):
                        self.counts["reviewed"] += 1
                        if result["issues"]:
                            self.counts["flagged"] += 1
                        self.codes.update(result["issues"])
                current = perf_counter()
                if progress is not None and current - last_event >= PROGRESS_INTERVAL:
                    progress(self.snapshot("running"))
                    last_event = current

        try:
            self.workers = [
                asyncio.create_task(worker()) for _ in range(self.parallel_requests)
            ]
            outcomes = await asyncio.gather(*self.workers, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, BaseException) and not isinstance(
                    outcome, asyncio.CancelledError
                ):
                    raise outcome
        except BaseException:
            for task in self.workers:
                task.cancel()
            await asyncio.gather(*self.workers, return_exceptions=True)
            raise
        finally:
            self.workers = []
            # Shielded so a second cancellation cannot leave the pool open.
            await asyncio.shield(client.aclose())
        status = (
            "stopped" if self.stop is not None else "cancelled" if self.cancelled else "completed"
        )
        result = self.snapshot(status)
        if progress is not None:
            progress(result)
        return result


def reviews_for(
    repo: ProjectRepository, revisions: Iterable[str | None],
) -> dict[str, list[dict[str, Any]]]:
    """Stored local reviews by translation revision, oldest first."""
    identifiers = sorted({revision for revision in revisions if revision})
    found: dict[str, list[dict[str, Any]]] = {}
    for start in range(0, len(identifiers), 500):
        chunk = identifiers[start:start + 500]
        for row in repo.db.execute(
            "SELECT translation_revision,reviewer_json,issues_json,note,created_at "
            f"FROM local_reviews WHERE translation_revision IN ({','.join('?' * len(chunk))}) "
            "ORDER BY created_at,rowid",
            chunk,
        ):
            reviewer = json.loads(row["reviewer_json"])
            found.setdefault(row["translation_revision"], []).append({
                "issues": json.loads(row["issues_json"]),
                "note": row["note"],
                "created_at": row["created_at"],
                "model": reviewer.get("model"),
                "provider": reviewer.get("provider"),
                "prompt_version": reviewer.get("prompt_version"),
                "reasoning_effort": reviewer.get("reasoning_effort"),
            })
    return found


def coded_revisions(repo: ProjectRepository) -> set[str]:
    """Translation revisions with at least one stored local reviewer code."""
    return {
        row["translation_revision"]
        for row in repo.db.execute("SELECT translation_revision,issues_json FROM local_reviews")
        if json.loads(row["issues_json"])
    }


def attach(rows: Sequence[dict[str, Any]], repo: ProjectRepository, field: str) -> None:
    """Add each row's local reviews of the revision named by ``field`` as local_reviews."""
    reviews = reviews_for(repo, (row.get(field) for row in rows))
    for row in rows:
        row["local_reviews"] = reviews.get(row.get(field) or "", [])


def summary(reviews: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Counts kept apart from deterministic checks: reviewed revisions and their codes."""
    # A revision counts once per code, however many reviewers reported it.
    codes = Counter(code for items in reviews.values() for code in issues_of(items))
    return {
        "prompt_version": PROMPT_VERSION,
        "reviewed_revisions": sum(bool(items) for items in reviews.values()),
        "revisions_with_codes": sum(
            any(review["issues"] for review in items) for items in reviews.values()
        ),
        "code_counts": dict(sorted(codes.items())),
    }


def issues_of(reviews: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({code for review in reviews for code in review["issues"]})
