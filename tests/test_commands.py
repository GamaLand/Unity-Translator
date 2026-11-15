"""Session command registry: unchanged names, declared guards and their order."""

import asyncio
import inspect

import pytest
from test_repository import draft

from unitytranslator.application import COMMANDS, ApplicationSession
from unitytranslator.commands import Guard
from unitytranslator.domain import OperationCancelled

LEGACY_COMMANDS = {
    "cancel_preparation", "cancel_extract", "open", "deployment_status", "deployment_prepare",
    "deployment_install", "deployment_remove", "backup", "editor_draft_get",
    "editor_draft_put", "editor_draft_commit", "editor_draft_discard", "page", "scan",
    "game_process", "extract", "models", "connection_test", "policies", "set_policies",
    "edit", "approve", "matching_review_preview", "matching_review_apply",
    "approve_all_preview", "approve_all", "approve_selection", "bulk_readiness",
    "use_pilot_profile", "history", "select_candidate", "textasset_export", "renpy_export",
    "renpy_package", "export", "runtime_export", "import_preview", "import_apply",
    "import_restore", "create_job", "create_affected_job", "create_page_job", "run_job",
    "pause", "cancel", "jobs", "job_report", "quality_audit", "shareable_export",
    "pilot_seen",
    # Added in 0.7.0 with the explicit project translation memory (T1).
    "translation_memory_preview", "translation_memory_apply",
    # Added with the optional local reviewer pass (T4).
    "local_review_preview", "local_review_run", "local_review_cancel",
}
NO_PROJECT = {
    "cancel_preparation", "cancel_extract", "open", "models", "connection_test", "run_job",
    "pause", "cancel", "local_review_cancel",
}
WORK = "work"
EXPECTED_IDENTITY = {
    **dict.fromkeys(
        ("deployment_status", "deployment_prepare", "deployment_install", "deployment_remove"),
        "Installation request project identity does not match.",
    ),
    **dict.fromkeys(
        ("editor_draft_get", "editor_draft_put", "editor_draft_commit", "editor_draft_discard"),
        "Draft request project identity does not match.",
    ),
    **dict.fromkeys(("matching_review_preview", "matching_review_apply"),
                    "Bulk review project identity does not match."),
    **dict.fromkeys(("approve_all_preview", "approve_all"),
                    "Approve-all request project identity does not match."),
    "approve_selection": "Group review project identity does not match.",
    "bulk_readiness": "Pilot query project identity does not match.",
    "use_pilot_profile": "Explicitly select pilot settings for the current project.",
    **dict.fromkeys(("textasset_export", "renpy_export", "renpy_package"),
                    "Project changed or extraction is active; retry when it finishes."),
    **dict.fromkeys(("translation_memory_preview", "translation_memory_apply"),
                    "Translation memory request project identity does not match."),
    **dict.fromkeys(("local_review_preview", "local_review_run"),
                    "Local review request project identity does not match."),
    "runtime_export": "Trial request project identity does not match.",
    "shareable_export": "Distribution request project identity does not match.",
}
EXPECTED_IDLE = {
    "open": ("extraction", "Extraction is running; wait for it to finish."),
    **dict.fromkeys(
        ("deployment_prepare", "deployment_install", "deployment_remove"),
        (WORK, "Wait for extraction or translation to finish before installing or removing."),
    ),
    "extract": (WORK, "Another extraction or translation is running."),
    **dict.fromkeys(
        ("models", "connection_test"),
        ("job", "A second model request cannot start while a generation job is running."),
    ),
    **dict.fromkeys(("matching_review_preview", "matching_review_apply"),
                    (WORK, "Wait for extraction or translation to finish before bulk review.")),
    **dict.fromkeys(("textasset_export", "renpy_export", "renpy_package"),
                    ("extraction",
                     "Project changed or extraction is active; retry when it finishes.")),
    **dict.fromkeys(("translation_memory_preview", "translation_memory_apply"),
                    (WORK, "Wait for extraction or translation to finish before reusing "
                     "translation memory.")),
    **dict.fromkeys(("local_review_preview", "local_review_run"),
                    (WORK, "Wait for extraction or translation to finish before the local "
                     "review.")),
    **dict.fromkeys(("import_preview", "import_apply", "import_restore"),
                    (WORK, "Stop the running extraction or translation job before importing.")),
}


def test_every_previous_command_name_is_registered_and_nothing_else():
    assert set(COMMANDS) == LEGACY_COMMANDS


def test_declared_guards_match_the_previous_checks():
    for name, spec in COMMANDS.items():
        assert spec.guard == Guard(
            name not in NO_PROJECT, EXPECTED_IDENTITY.get(name), EXPECTED_IDLE.get(name),
            name.startswith("deployment_"),
        ), name


def test_missing_installation_session_fails_identity_before_busy_state(tmp_path):
    session = ApplicationSession()
    game = tmp_path / "game"
    game.mkdir()
    opened = run(session, "open", {"game": str(game), "project": str(tmp_path / "project")})
    session.installation = None
    session.extracting = True
    try:
        for name in ("deployment_install", "deployment_unknown"):
            with pytest.raises(ValueError, match="Installation request project identity"):
                run(session, name, {"project_id": opened["project_id"], "review_id": "x"})
    finally:
        session.extracting = False
        asyncio.run(session.close())


def test_guard_messages_are_catalogued_reason_codes():
    from unitytranslator.commands import FAMILY_FALLBACKS
    from unitytranslator.diagnostics import english_catalog

    guards = [spec.guard for spec in COMMANDS.values()]
    guards += [guard for guard, _ in FAMILY_FALLBACKS.values()]
    messages = {g.identity for g in guards if g.identity} | {g.idle[1] for g in guards if g.idle}
    messages |= {message for _, message in FAMILY_FALLBACKS.values()}
    assert messages and messages <= english_catalog()


def test_handlers_are_prefixed_and_take_a_typed_payload():
    for name, spec in COMMANDS.items():
        assert spec.handler.__name__.startswith("command_"), name
        assert inspect.iscoroutinefunction(spec.handler), name
        assert "data" in inspect.signature(spec.handler).parameters, name


def run(session, command, data=None):
    return asyncio.run(session.dispatch(command, data or {}))


def test_unknown_commands_keep_their_family_messages(tmp_path):
    session = ApplicationSession()
    with pytest.raises(ValueError, match="Unknown application action"):
        run(session, "unknown")
    with pytest.raises(ValueError, match="Open a project first"):
        run(session, "deployment_unknown")
    game = tmp_path / "game"
    game.mkdir()
    opened = run(session, "open", {"game": str(game), "project": str(tmp_path / "project")})
    identity = {"project_id": opened["project_id"]}
    with pytest.raises(ValueError, match="Installation request project identity"):
        run(session, "deployment_unknown", {"project_id": "other"})
    with pytest.raises(ValueError, match="Unknown installation action"):
        run(session, "deployment_unknown", identity)
    with pytest.raises(ValueError, match="Draft request project identity"):
        run(session, "editor_draft_unknown")
    with pytest.raises(ValueError, match="Unknown draft action"):
        run(session, "editor_draft_unknown", identity)
    asyncio.run(session.close())


def test_guard_order_is_project_identity_then_idle(tmp_path):
    session = ApplicationSession()
    with pytest.raises(ValueError, match="Open a project first"):
        run(session, "matching_review_preview", {"project_id": "other"})
    game = tmp_path / "game"
    game.mkdir()
    opened = run(session, "open", {"game": str(game), "project": str(tmp_path / "project")})
    session.repo.ingest([draft()], {})
    session.extracting = True
    try:
        with pytest.raises(ValueError, match="Bulk review project identity"):
            run(session, "matching_review_preview", {"project_id": "other"})
        with pytest.raises(ValueError, match="before bulk review"):
            run(session, "matching_review_preview", {"project_id": opened["project_id"]})
        # Explicit selection is still checked before the busy state for pilot settings.
        with pytest.raises(ValueError, match="Explicitly select pilot settings"):
            run(session, "use_pilot_profile",
                {"project_id": opened["project_id"], "job_id": "x"})
        with pytest.raises(ValueError, match="Stop extraction or translation"):
            run(session, "use_pilot_profile",
                {"project_id": opened["project_id"], "job_id": "x", "user_action": True})
        # Without project state checks of its own, run_job keeps its own message.
        with pytest.raises(ValueError, match="does not allow translation"):
            run(session, "run_job", {"job_id": "x"})
    finally:
        session.extracting = False
        asyncio.run(session.close())
    with pytest.raises(ValueError, match="does not allow translation"):
        run(session, "run_job", {"job_id": "x"})


def test_commands_without_a_project_and_shutdown():
    session = ApplicationSession()
    assert run(session, "cancel_preparation") is True
    assert run(session, "cancel_extract") == {"cancel_requested": True}
    assert run(session, "pause") is True
    assert run(session, "cancel") is True
    assert run(session, "local_review_cancel") is True
    session.request_shutdown()
    with pytest.raises(OperationCancelled, match="closing"):
        run(session, "page")
