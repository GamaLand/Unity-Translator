"""Optional request reasoning controls preserve legacy profiles and provider defaults."""

import asyncio
import json

import httpx
import pytest
from test_repository import draft

from unitytranslator.domain import GenerationProfile
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore
from unitytranslator.providers import LocalProvider, ProviderError
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


@pytest.mark.parametrize("provider,effort", [("llama-cpp", "none"), ("lm-studio", "arbitrary")])
def test_unknown_or_unscoped_reasoning_option_is_rejected(provider, effort):
    def handler(request):
        raise AssertionError("An unsupported option must not reach the server")

    local = LocalProvider(provider, "http://localhost:1234", httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(local.translate_sample("synthetic", "Red", reasoning_effort=effort))
    assert caught.value.code == "unsupported_option"
