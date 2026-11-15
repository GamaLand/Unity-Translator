"""Optional request reasoning controls preserve legacy profiles and provider defaults."""

import asyncio
import json
import os
import subprocess
import sys

import httpx
import pytest
from test_repository import draft

from unitytranslator.domain import GenerationProfile
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore
from unitytranslator.providers import (
    ADAPTIVE_REASONING_BASE,
    ADAPTIVE_REASONING_MAX,
    LocalProvider,
    ProviderError,
    adaptive_reasoning_budget,
)
from unitytranslator.repository import ProjectRepository


def test_default_profile_retains_legacy_encoding_and_old_pilot_identity(tmp_path):
    legacy = {
        "provider": "lm-studio",
        "address": "http://localhost:1234",
        "model": "synthetic",
        "context_tokens": 8192,
        "output_tokens": 2048,
        "temperature": 0.2,
        "structured_output": True,
        "glossary_version": None,
        "style_version": None,
        "prompt_version": "translate-v1",
    }
    profile = GenerationProfile(**legacy)
    assert profile.to_dict() == legacy
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        identifier = store.create([repo.page()[0]["unit_id"]], profile, kind="pilot")
        assert json.loads(store.job(identifier)["profile_json"]) == legacy
        repo.db.execute(
            "UPDATE jobs SET status='completed',report_seen=1 WHERE id=?", (identifier,)
        )
        assert store.pilot_reviewed(profile)
        changed = GenerationProfile(**legacy, reasoning_effort="none")
        assert not store.pilot_reviewed(changed)


@pytest.mark.parametrize("effort", ["default", "none"])
def test_explicit_request_flag_and_result_metadata(effort):
    def handler(request):
        payload = json.loads(request.content)
        if effort == "none":
            assert payload["reasoning_effort"] == "none"
        else:
            assert "reasoning_effort" not in payload
        user = json.loads(payload["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {"translations": [{"id": user["id"], "text": "Kırmızı"}]}
                            )
                        },
                    }
                ]
            },
        )

    provider = LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))
    result = asyncio.run(provider.translate_sample("synthetic", "Red", reasoning_effort=effort))
    assert result["translation"] == "Kırmızı"
    assert result["human_approved"] is False
    assert result["settings"].get("reasoning_effort", "default") == effort


@pytest.mark.parametrize(
    "provider,effort",
    [("lm-studio", "adaptive"), ("lm-studio", "arbitrary"), ("llama-cpp", "low")],
)
def test_unknown_or_unscoped_reasoning_option_is_rejected(provider, effort):
    def handler(request):
        raise AssertionError("An unsupported option must not reach the server")

    local = LocalProvider(provider, "http://localhost:1234", httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(local.translate_sample("synthetic", "Red", reasoning_effort=effort))
    assert caught.value.code == "unsupported_option"


def reply(payload, reasoning=None):
    user = json.loads(payload["messages"][1]["content"])
    message = {"content": json.dumps({"translations": [{"id": user["id"], "text": "Kırmızı"}]})}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return httpx.Response(200, json={
        "choices": [{"finish_reason": "stop", "message": message}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 30, "total_tokens": 40},
    })


def test_llama_cpp_can_switch_thinking_off_through_the_chat_template():
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        return reply(payload)

    local = LocalProvider("llama-cpp", "http://localhost:8080", httpx.MockTransport(handler))
    asyncio.run(local.translate_sample("synthetic", "Red", reasoning_effort="none"))
    assert seen[0]["reasoning_effort"] == "none"
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "thinking_budget_tokens" not in seen[0]


def test_adaptive_budget_is_sent_added_to_the_output_budget_and_reported():
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        return reply(payload, reasoning="private chain of thought " * 4)

    local = LocalProvider("llama-cpp", "http://localhost:8080", httpx.MockTransport(handler))
    result = asyncio.run(local.translate_record(
        "synthetic", "Red", "r1", "en", "tr", context_tokens=8192, output_tokens=512,
        reasoning_effort="adaptive",
    ))
    budget = adaptive_reasoning_budget("Red", [])
    assert seen[0]["thinking_budget_tokens"] == budget
    assert seen[0]["max_tokens"] == 512 + budget
    assert "reasoning_effort" not in seen[0] and "chat_template_kwargs" not in seen[0]
    assert result["reasoning"] == {
        "mode": "adaptive", "policy": "adaptive-v1", "budget_tokens": budget,
        "reasoning_characters": len("private chain of thought " * 4),
    }
    assert "private chain" not in json.dumps(result)


def test_default_requests_are_unchanged_and_report_reasoning_size_only():
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        return reply(payload, reasoning="x" * 700)

    local = LocalProvider("llama-cpp", "http://localhost:8080", httpx.MockTransport(handler))
    result = asyncio.run(local.translate_record(
        "synthetic", "Red", "r1", "en", "tr", context_tokens=8192, output_tokens=512,
    ))
    assert seen[0]["max_tokens"] == 512
    assert not {"thinking_budget_tokens", "reasoning_effort", "chat_template_kwargs"} & set(
        seen[0]
    )
    assert result["reasoning"] == {"mode": "default", "reasoning_characters": 700}


def test_adaptive_budget_grows_with_text_and_dialogue_and_is_capped():
    short = adaptive_reasoning_budget("Ambiguous RPA member path.", [])
    longer = adaptive_reasoning_budget("A longer line of dialogue. " * 6, [])
    references = [{"source": "Where were you last night?", "offset": -1, "speaker": "e"},
                  {"source": "We have to leave now.", "offset": 1, "speaker": "e"}]
    with_context = adaptive_reasoning_budget("A longer line of dialogue. " * 6, references)
    assert ADAPTIVE_REASONING_BASE < short < longer < with_context
    assert adaptive_reasoning_budget("x" * 100000, references) == ADAPTIVE_REASONING_MAX


def test_adaptive_budget_fits_around_the_context_instead_of_failing():
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        return reply(payload)

    local = LocalProvider("llama-cpp", "http://localhost:8080", httpx.MockTransport(handler))
    text = "A long record that needs reasoning room. " * 4

    def run(context, effort="default"):
        try:
            return asyncio.run(local.translate_record(
                "synthetic", text, "r1", "en", "tr", context_tokens=context,
                output_tokens=300, reasoning_effort=effort,
            ))
        except ProviderError as exc:
            assert exc.code == "context"
            return None

    smallest = next(c for c in range(512, 8192, 8) if run(c) is not None)
    wanted = adaptive_reasoning_budget(text, [])
    result = run(smallest + wanted // 2, "adaptive")
    sent = seen[-1]["thinking_budget_tokens"]
    assert 0 < sent < wanted and seen[-1]["max_tokens"] == 300 + sent
    assert result["reasoning"]["budget_reduced"] == wanted - sent
    assert run(smallest + 2 * wanted, "adaptive")["reasoning"]["budget_tokens"] == wanted
    assert "budget_reduced" not in seen[-1] and seen[-1]["thinking_budget_tokens"] == wanted
    assert run(smallest - 64, "adaptive") is None  # The answer itself must still fit.


def test_adaptive_budget_never_drops_verified_dialogue_references():
    from unitytranslator.dialogue_context import CONTEXT_VERSION

    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(json.loads(payload["messages"][1]["content"]))
        return reply(payload)

    local = LocalProvider("llama-cpp", "http://localhost:8080", httpx.MockTransport(handler))
    references = [
        {"offset": offset, "source": "Reference line. " * 40, "speaker": "e",
         "unit_id": f"u{offset}"}
        for offset in (-2, -1, 1, 2)
    ]
    window = {"version": CONTEXT_VERSION, "references": references, "speaker": "e"}
    counts = {}
    for effort in ("default", "adaptive"):
        asyncio.run(local.translate_record(
            "synthetic", "Hello there.", "r1", "en", "tr", context_tokens=4096,
            output_tokens=512, reasoning_effort=effort, dialogue_context=window,
        ))
        counts[effort] = len(seen[-1].get("dialogue_reference", {}).get("utterances", []))
    assert counts["adaptive"] == counts["default"] > 0


@pytest.mark.parametrize("provider,effort,allowed", [
    ("llama-cpp", "adaptive", True), ("llama-cpp", "none", True),
    ("lm-studio", "none", True), ("lm-studio", "adaptive", False),
])
def test_job_profiles_accept_only_supported_reasoning_modes(tmp_path, provider, effort, allowed):
    game = tmp_path / "game"
    game.mkdir()
    profile = GenerationProfile(
        provider, "http://localhost:8080", "synthetic", 8192, reasoning_effort=effort,
    )
    assert profile.to_dict()["reasoning_effort"] == effort
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        unit = repo.page()[0]["unit_id"]
        if allowed:
            store.create([unit], profile, kind="pilot")
        else:
            with pytest.raises(ValueError, match="not available for the selected provider"):
                store.create([unit], profile, kind="pilot")


def test_report_summarizes_reasoning_budgets_and_sizes():
    from unitytranslator.reports import reasoning_metrics

    metrics = reasoning_metrics("adaptive", [
        {"mode": "adaptive", "budget_tokens": 100, "reasoning_characters": 300},
        {"mode": "adaptive", "budget_tokens": 140, "reasoning_characters": 500},
        {"mode": "adaptive", "budget_tokens": 120},
    ])
    assert metrics["mode"] == "adaptive" and metrics["reported_attempts"] == 3
    assert metrics["failed_attempts"] == 0
    assert metrics["budget_tokens"] == {"attempts": 3, "median": 120, "max": 140}
    assert metrics["reasoning_characters"] == {"attempts": 2, "median": 400.0, "max": 500}
    assert metrics["reasoning_tokens"] is None


UI_CHECK = """
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from unitytranslator.ui.window import MainWindow

class Bridge(QObject):
    completed = Signal(str, object)
    failed = Signal(str, object)
    progress = Signal(object)
    stopped = Signal()
    def submit(self, *args):
        pass
    def shutdown(self):
        self.stopped.emit()

app = QApplication([])
window = MainWindow(Bridge())
assert window.provider.currentData() == "lm-studio"
assert not window.reasoning.model().item(window.reasoning.findData("adaptive")).isEnabled()
window.provider.setCurrentIndex(window.provider.findData("llama-cpp"))
window.reasoning.setCurrentIndex(window.reasoning.findData("adaptive"))
assert window.model_data()["reasoning_effort"] == "adaptive"
window.provider.setCurrentIndex(window.provider.findData("lm-studio"))
adaptive = window.reasoning.findData("adaptive")
assert not window.reasoning.model().item(adaptive).isEnabled()
assert window.reasoning.currentData() == "default"
assert "reasoning_effort" not in window.model_data()
window.reasoning.setCurrentIndex(window.reasoning.findData("none"))
assert window.model_data()["reasoning_effort"] == "none"
profile = {**window.profile(), "provider": "llama-cpp", "reasoning_effort": "adaptive"}
window.apply_profile(profile)
assert window.reasoning.currentData() == "adaptive"
print("ok")
"""


def test_reasoning_selector_offers_adaptive_only_for_llama_cpp(tmp_path):
    pytest.importorskip("PySide6")
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="offscreen", UNITYTRANSLATOR_CONFIG_HOME=str(tmp_path),
        UNITYTRANSLATOR_UI_LANGUAGE="en",
    )
    result = subprocess.run(
        [sys.executable, "-c", UI_CHECK], capture_output=True, text=True, env=environment,
        timeout=120, check=False,
    )
    assert result.returncode == 0 and result.stdout.strip().endswith("ok"), result.stderr


def test_failed_attempts_count_in_reasoning_metrics(tmp_path, monkeypatch):
    from unitytranslator.jobs import TranslationJobService
    from unitytranslator.reports import job_report

    def handler(request):
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "length", "message": {"content": "{"}}],
            "usage": {"completion_tokens": 2048, "completion_tokens_details": {
                "reasoning_tokens": 2040}},
        })

    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft()], {})
        profile = GenerationProfile("llama-cpp", "http://localhost:8080", "synthetic", 8192)
        service = TranslationJobService(
            repo, provider_factory=lambda profile: LocalProvider(
                "llama-cpp", "http://localhost:8080", httpx.MockTransport(handler),
            ),
        )
        job = service.store.create([repo.page()[0]["unit_id"]], profile, kind="pilot")
        monkeypatch.setattr("unitytranslator.jobs.retry_delay", lambda failures, base: 0)
        asyncio.run(service.run(job))
        metrics = job_report(repo, job)["reasoning_metrics"]
    assert metrics["failed_attempts"] == metrics["reported_attempts"] >= 1
    assert metrics["reasoning_tokens"]["max"] == 2040
