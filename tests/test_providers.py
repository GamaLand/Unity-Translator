import asyncio
import json

import httpx
import pytest

from unitytranslator.providers import (
    LocalProvider,
    ProviderError,
    local_endpoint,
    response_diagnostics,
)


def test_generation_has_queue_budget_but_discovery_keeps_short_timeout(monkeypatch):
    deadlines = []
    real_timeout = asyncio.timeout

    def timeout(seconds):
        deadlines.append(seconds)
        return real_timeout(seconds)

    def handler(request):
        assert request.extensions["timeout"]["connect"] == 5
        if request.url.path == "/v1/models":
            assert request.extensions["timeout"]["read"] == 110
            return httpx.Response(200, json={"data": []})
        assert request.extensions["timeout"]["read"] == 1800
        user = json.loads(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"translations": [{"id": user["id"], "text": "Başla"}]}
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(asyncio, "timeout", timeout)
    provider = LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))
    assert asyncio.run(provider.list_models()) == []
    assert asyncio.run(provider.translate_sample("synthetic", "Start"))["translation"] == "Başla"
    assert deadlines == [120, 1800]


def test_queued_generation_cancels_without_waiting_for_deadline():
    async def run():
        entered = asyncio.Event()
        released = asyncio.Event()

        async def handler(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                released.set()

        provider = LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))
        task = asyncio.create_task(provider.translate_sample("synthetic", "Start"))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert released.is_set()

    asyncio.run(run())


def test_response_diagnostics_does_not_include_model_text_or_unknown_usage_fields():
    raw = {
        "choices": [{"finish_reason": "length", "message": {"content": "private-secret"}}],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 128,
            "total_tokens": "private-secret",
            "completion_tokens_details": {"reasoning_tokens": 90, "secret": "private-secret"},
        },
    }
    details = response_diagnostics(raw)
    assert details == {
        "finish_reason": "length",
        "response_content_bytes": 14,
        "prompt_tokens": 12,
        "completion_tokens": 128,
        "reasoning_tokens": 90,
    }
    assert "private-secret" not in json.dumps(details)
    adapter = LocalProvider(
        "lm-studio",
        "http://localhost:1234",
        httpx.MockTransport(lambda request: httpx.Response(200, json=raw)),
    )
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter.translate_sample("synthetic-model", "Value"))
    assert all(error.value.diagnostics[key] == value for key, value in details.items())
    assert error.value.diagnostics["format_prompt_version"] == "sample-v1"
    assert error.value.diagnostics["schema_mode"] == "disabled"
    assert "private-secret" not in json.dumps(error.value.diagnostics)


@pytest.mark.parametrize(
    "address",
    [
        "https://example.com",
        "http://127.0.0.2:1234",
        "http://user:secret@localhost",
        "file:///tmp/model",
        "http://localhost/v1?remote=true",
    ],
)
def test_remote_or_ambiguous_endpoint_rejected(address: str) -> None:
    with pytest.raises(ProviderError):
        local_endpoint(address)


@pytest.mark.parametrize("provider", ["lm-studio", "llama-cpp"])
def test_provider_data_only_request_and_validation(provider: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "synthetic-model"}]})
        payload = json.loads(request.content)
        assert "tools" not in payload
        user = json.loads(payload["messages"][1]["content"])
        raw = json.dumps({"translations": [{"id": "sample", "text": user["source"]}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": raw}}]})

    adapter = LocalProvider(provider, "http://127.0.0.1:1234", httpx.MockTransport(handler))
    assert asyncio.run(adapter.list_models()) == ["synthetic-model"]
    result = asyncio.run(adapter.translate_sample("synthetic-model", "Value {0}"))
    assert result["translation"] == "Value {0}"
    assert result["human_approved"] is False


@pytest.mark.parametrize(
    "status,code",
    [(302, "http_error"), (401, "unauthorized"), (404, "not_found"), (500, "http_error")],
)
def test_http_errors_and_redirects(status: int, code: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"Location": "https://example.com"})

    adapter = LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter.list_models())
    assert error.value.code == code


@pytest.mark.parametrize(
    "provider,kind", [("lm-studio", "json_schema"), ("llama-cpp", "json_object")]
)
def test_provider_specific_schema_mapping(provider: str, kind: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        formatting = payload["response_format"]
        assert formatting["type"] == kind
        schema = (
            formatting["json_schema"]["schema"] if provider == "lm-studio" else formatting["schema"]
        )
        assert schema["$defs"]["Translation"]["properties"]["id"]["enum"] == ["sample"]
        raw = json.dumps({"translations": [{"id": "sample", "text": "Değer"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": raw}}]})

    adapter = LocalProvider(
        provider, "http://localhost:1234", httpx.MockTransport(handler), structured_output=True
    )
    result = asyncio.run(adapter.translate_sample("synthetic-model", "Value"))
    assert result["schema_capability"] == "tested_supported"


@pytest.mark.parametrize(
    "message,code",
    [
        ("CUDA out of memory", "out_of_memory"),
        ("context length exceeded", "context"),
        ("model not loaded", "not_found"),
        ("unsupported response format", "unsupported_option"),
    ],
)
def test_server_errors_have_actionable_codes(message: str, code: str) -> None:
    adapter = LocalProvider(
        "lm-studio",
        "http://localhost:1234",
        httpx.MockTransport(
            lambda request: httpx.Response(400, json={"error": {"message": message}})
        ),
    )
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter.list_models())
    assert error.value.code == code


@pytest.mark.parametrize(
    "reply,code",
    [
        ('{"translations":', "response_schema_error"),
        ('{"translations":[{"id":"wrong","text":"x"}]}', "response_schema_error"),
        ('{"translations":[{"id":"sample","text":"Değer"}]}', "protected_content_error"),
    ],
)
def test_json_and_protected_content_failures_are_distinct(reply: str, code: str) -> None:
    adapter = LocalProvider(
        "lm-studio",
        "http://localhost:1234",
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})
        ),
    )
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter.translate_sample("synthetic-model", "Value {0}"))
    assert error.value.code == code


@pytest.mark.parametrize(
    "extra,finish,code",
    [
        ({}, "length", "output_truncated"),
        ({"tool_calls": [{"name": "never_execute"}]}, "stop", "unexpected_tool_call"),
        ({"function_call": {"name": "never_execute"}}, "stop", "unexpected_tool_call"),
        ({}, "tool_calls", "unexpected_tool_call"),
    ],
)
def test_truncated_output_and_tool_calls_are_not_accepted_as_translations(extra, finish, code):
    raw = json.dumps({"translations": [{"id": "sample", "text": "Değer"}]})
    adapter = LocalProvider(
        "lm-studio",
        "http://localhost:1234",
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": raw, **extra}, "finish_reason": finish}]},
            )
        ),
    )
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter.translate_sample("synthetic-model", "Value"))
    assert error.value.code == code


@pytest.mark.parametrize(
    "choices", [[], [None], [{}], [{"message": None}], [{"message": "invalid"}], [{"message": []}]]
)
def test_malformed_choice_or_message_is_a_mapped_provider_error(choices):
    adapter = LocalProvider(
        "lm-studio",
        "http://localhost:1234",
        httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": choices})),
    )
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter.translate_sample("synthetic-model", "Value"))
    assert error.value.code == "response_schema_error"


def test_plural_branches_use_one_request_and_reconstruct_source_order():
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        user = json.loads(payload["messages"][1]["content"])
        calls.append(payload)
        assert "tools" not in payload and "source" not in user
        branches = user["branches"]
        assert [b["plural_form"] for b in branches] == ["Plural", "One", "Zero"]
        schema = payload["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["translations"]["minItems"] == 3
        assert schema["properties"]["translations"]["maxItems"] == 3
        assert [
            item["properties"]["id"]["enum"]
            for item in schema["properties"]["translations"]["items"]
        ] == [[b["id"]] for b in branches]
        replies = [
            {
                "id": b["id"],
                "text": b["source"]
                .replace("turns", "tur")
                .replace("One turn", "Bir tur")
                .replace("No tur", "Tur yok"),
            }
            for b in reversed(branches)
        ]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"translations": replies})}}]}
        )

    adapter = LocalProvider(
        "lm-studio", "http://localhost:1234", httpx.MockTransport(handler), structured_output=True
    )
    result = asyncio.run(
        adapter.translate_sample(
            "synthetic-model", "{[COUNT]} turns[i2p_One]One turn[i2p_Zero]No turns"
        )
    )
    assert len(calls) == 1
    assert result["translation"] == "{[COUNT]} tur[i2p_One]Bir tur[i2p_Zero]Tur yok"
    assert result["format_prompt_version"] == "translate-plural-v2"
    assert result["status"] == "needs_review"
    assert "plural_content_review" in result["issues"]


@pytest.mark.parametrize(
    "mode,code", [("missing", "response_schema_error"), ("swap", "protected_content_error")]
)
def test_plural_reply_cannot_drop_branch_or_transfer_markers(mode, code):
    def handler(request):
        payload = json.loads(request.content)
        branches = json.loads(payload["messages"][1]["content"])["branches"]
        replies = [{"id": b["id"], "text": b["source"]} for b in branches]
        if mode == "missing":
            replies.pop()
        else:
            replies[0]["text"], replies[1]["text"] = replies[1]["text"], replies[0]["text"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"translations": replies})}}]}
        )

    adapter = LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter.translate_sample("synthetic-model", "{[A]} turns[i2p_One]{[B]} turn"))
    assert error.value.code == code
