"""Declarative session commands: stable names, typed payloads and guards.

Command names and payload keys are the interface contract between the UI and the
session and must not change. Guards are checked in a fixed order before a handler
runs: an open project, then the payload's project identity, then idle state. Each
guard raises the same message the previous hand-written checks raised.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, Required, TypedDict, TypeVar

from unitytranslator.diagnostics import Diagnostic

IdleScope = Literal["work", "extraction", "job"]


@dataclass(frozen=True)
class Guard:
    # Requires an open project ("Open a project first.").
    project: bool = True
    # Message raised when the payload's project_id is not the open project.
    identity: str | None = None
    # Busy scope and message: work = extraction or a running job.
    idle: tuple[IdleScope, str] | None = None
    # A missing installation session fails the identity check (installation commands).
    installation: bool = False


@dataclass(frozen=True)
class CommandSpec:
    name: str
    handler: Callable[[Any, Any], Awaitable[Any]]
    guard: Guard


# Unknown names in these families keep their family guard and message.
FAMILY_FALLBACKS: dict[str, tuple[Guard, str]] = {
    "deployment_": (
        Guard(
            identity="Installation request project identity does not match.",
            idle=("work", "Wait for extraction or translation to finish before installing or "
                  "removing."),
            installation=True,
        ),
        "Unknown installation action.",
    ),
    "editor_draft_": (
        Guard(identity="Draft request project identity does not match."),
        "Unknown draft action.",
    ),
}

Handler = TypeVar("Handler", bound=Callable[..., Awaitable[Any]])


def command(
    *names: str, project: bool = True, identity: str | None = None,
    idle: tuple[IdleScope, str] | None = None, installation: bool = False,
) -> Callable[[Handler], Handler]:
    """Register a session method under one or more command names."""
    guard = Guard(project, identity, idle, installation)

    def register(function: Handler) -> Handler:
        existing: list[tuple[str, Guard]] = getattr(function, "__commands__", [])
        function.__commands__ = [*existing, *((name, guard) for name in names)]  # type: ignore[attr-defined]
        return function

    return register


def registry(cls: type) -> dict[str, CommandSpec]:
    """Collect the commands declared on a session class; names must be unique."""
    found: dict[str, CommandSpec] = {}
    for attribute in vars(cls).values():
        for name, guard in getattr(attribute, "__commands__", ()):
            if name in found:
                raise Diagnostic("Duplicate session command: {p0}", p0=name)
            found[name] = CommandSpec(name, attribute, guard)
    return found


class Identified(TypedDict, total=False):
    project_id: Required[str]
    request_token: Any


class OpenPayload(TypedDict, total=False):
    game: str
    project: Required[str]
    existing_only: bool
    source_language: str
    target_language: str


class DeploymentPayload(Identified, total=False):
    log_file: str
    log_reviewed: bool
    review_id: str
    plan_id: str
    user_action: bool
    experimental_reviewed: bool


class DraftPayload(Identified, total=False):
    unit_id: Required[str]
    source_revision: str
    base_version: int
    text: str
    expected_revision: int


class PagePayload(TypedDict, total=False):
    offset: int
    search: str
    status: str
    category: str
    affected: bool
    dialogue_context: str
    request_token: Any


class EnginePayload(TypedDict, total=False):
    engine: str


class ExtractPayload(TypedDict, total=False):
    source: Required[str]
    engine: str
    format_rules: str


class ModelPayload(TypedDict, total=False):
    provider: Required[Literal["lm-studio", "llama-cpp"]]
    address: Required[str]
    model: str
    structured_output: bool
    context_tokens: int
    output_tokens: int
    temperature: float
    reasoning_effort: str


class PolicyPayload(TypedDict):
    glossary: list[dict[str, Any]]
    styles: dict[str, Any]


class EditPayload(TypedDict):
    unit_id: str
    version: int
    text: str


class ApprovePayload(TypedDict):
    unit_id: str
    version: int


class UnitPayload(TypedDict):
    unit_id: str


class CandidatePayload(TypedDict, total=False):
    unit_id: Required[str]
    version: Required[int]
    revision: Required[str]
    replace_approved: bool


class MatchingReviewPayload(Identified, total=False):
    action: str
    filters: dict[str, Any]
    token: str
    user_action: bool


class ApproveAllPayload(Identified, total=False):
    token: str
    user_action: bool
    confirmation: str


class SelectionPayload(Identified, total=False):
    records: Required[list[dict[str, Any]]]
    user_action: bool
    reviewed: bool


class ReadinessPayload(Identified, total=False):
    profile: Required[dict[str, Any]]


class PilotProfilePayload(Identified, total=False):
    job_id: Required[str]
    user_action: bool


class LanguagePayload(Identified, total=False):
    language: Required[str]


class RecordsPayload(Identified, total=False):
    records: Required[list[dict[str, Any]]]


class ImportPayload(TypedDict):
    path: str


class JobPayload(TypedDict, total=False):
    profile: dict[str, Any]
    kind: str
    units: list[str]
    retranslate: bool
    approved_candidates: bool
    records: list[dict[str, Any]]
    project_id: str


class RunPayload(TypedDict, total=False):
    job_id: Required[str]
    model_selection: dict[str, Any]
    parallel_requests: int


class JobIdPayload(TypedDict):
    job_id: str


class CancelPayload(TypedDict, total=False):
    job_id: NotRequired[str]
