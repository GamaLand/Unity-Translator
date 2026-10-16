"""Mevcut yerel sunuculara async HTTP; sunucu/model başlatılmaz."""

import asyncio
import json
from importlib.resources import files
from time import perf_counter
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from unitytranslator.validation import (
    PROTECTED_FORMAT_VERSION,
    REVIEW_CHECKS_VERSION,
    Envelope,
    join_plural_branches,
    mask,
    parse_reply,
    plural_branches,
    review_issues,
)


class ProviderError(ValueError):
    def __init__(self, code: str, message: str, diagnostics: dict[str, int | str] | None = None):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics or {}


def response_diagnostics(result: dict[str, Any]) -> dict[str, int | str]:
    """Ham cevap/istem yerine sadece sabit enum ve sınırlı sayısal ölçümler."""
    details: dict[str, int | str] = {}
    choices = result.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        finish = choices[0].get("finish_reason")
        if finish in ("stop", "length", "tool_calls", "function_call", "content_filter"):
            details["finish_reason"] = finish
        message = choices[0].get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            details["response_content_bytes"] = len(
                message["content"].encode("utf-8", errors="replace")
            )
    usage = result.get("usage")
    if isinstance(usage, dict):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if type(value) is int and 0 <= value <= 1_000_000_000:
                details[key] = value
        nested = usage.get("completion_tokens_details")
        if isinstance(nested, dict):
            value = nested.get("reasoning_tokens")
            if type(value) is int and 0 <= value <= 1_000_000_000:
                details["reasoning_tokens"] = value
    return details


def local_endpoint(address: str) -> str:
    parsed = urlsplit(address)
    if (
        parsed.scheme not in ("http", "https")
        or parsed.hostname not in ("localhost", "127.0.0.1", "::1")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/", "/v1", "/v1/")
    ):
        raise ProviderError(
            "unsafe_endpoint", "Bu prototip yalnızca yerel model adresi kabul eder."
        )
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ProviderError("unsafe_endpoint", "Sunucu portu geçersiz.") from exc
    return f"{parsed.scheme}://{parsed.netloc}/v1"


class LocalProvider:
    def __init__(
        self,
        provider: Literal["lm-studio", "llama-cpp"],
        address: str,
        transport: httpx.AsyncBaseTransport | None = None,
        structured_output: bool = False,
    ):
        self.provider = provider
        self.endpoint = local_endpoint(address)
        self.transport = transport
        self.structured_output = structured_output

    async def request(
        self,
        method: str,
        route: str,
        payload: dict[str, Any] | None = None,
        *,
        native: bool = False,
        generation: bool = False,
    ) -> dict[str, Any]:
        # Non-streaming generation includes the server's queue and reasoning time.
        # Keep connection checks short, but allow a bounded 30 minutes for inference.
        deadline = 1800 if generation else 120
        try:
            async with asyncio.timeout(deadline):
                async with httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                    transport=self.transport,
                    timeout=httpx.Timeout(
                        connect=5, read=deadline if generation else 110, write=10, pool=5
                    ),
                ) as client:
                    root = self.endpoint.removesuffix("/v1") if native else self.endpoint
                    async with client.stream(method, root + route, json=payload) as reply:
                        if reply.status_code in (401, 403):
                            raise ProviderError("unauthorized", "Sunucu erişim izni vermedi.")
                        if reply.status_code == 404:
                            raise ProviderError("not_found", "Uç nokta veya model bulunamadı.")
                        data = bytearray()
                        async for block in reply.aiter_bytes():
                            data.extend(block)
                            if len(data) > 1024 * 1024:
                                raise ProviderError(
                                    "invalid_response", "Sunucu cevabı fazla büyük."
                                )
                        if not 200 <= reply.status_code < 300:
                            message = bytes(data).decode("utf-8", errors="replace").casefold()
                            if any(
                                term in message
                                for term in (
                                    "out of memory",
                                    "failed to allocate",
                                    "insufficient memory",
                                )
                            ):
                                raise ProviderError(
                                    "out_of_memory",
                                    "Model sunucusunda bellek yetersiz; model/bağlam ve "
                                    "diğer GPU süreçlerini kontrol edin.",
                                )
                            if "context" in message and any(
                                term in message for term in ("exceed", "length", "too long")
                            ):
                                raise ProviderError(
                                    "context",
                                    "Model sunucusunun bağlam sınırı aşıldı; metin kesilmedi.",
                                )
                            if "model" in message and any(
                                term in message for term in ("not loaded", "not found", "no model")
                            ):
                                raise ProviderError(
                                    "not_found",
                                    "Seçilen model sunucuda yüklü/kullanılabilir değil.",
                                )
                            if "unsupported" in message or "unknown parameter" in message:
                                raise ProviderError(
                                    "unsupported_option",
                                    "Sunucu istenen üretim seçeneğini desteklemiyor.",
                                )
                            raise ProviderError(
                                "http_error", f"Sunucu HTTP {reply.status_code} döndürdü."
                            )
                        result = json.loads(data)
                        if not isinstance(result, dict):
                            raise ProviderError(
                                "invalid_response", "Sunucu JSON nesnesi döndürmedi."
                            )
                        return result
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderError("timeout", "Yerel sunucu isteği zaman aşımına uğradı.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("connection", "Yerel sunucuya bağlanılamadı.") from exc
        except (ValueError, UnicodeError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError("invalid_response", "Sunucu cevabı geçerli JSON değil.") from exc

    async def list_models(self) -> list[str]:
        result = await self.request("GET", "/models")
        data = result.get("data")
        if not isinstance(data, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in data
        ):
            raise ProviderError("invalid_response", "Model listesi çözülemedi.")
        return [item["id"] for item in data]

    async def inspect_models(self) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = [
            {"id": name, "loaded": "unknown", "context_tokens": None, "quantization": None}
            for name in await self.list_models()
        ]
        if self.provider == "lm-studio":
            try:
                metadata = await self.request("GET", "/api/v1/models", native=True)
                for model in models:
                    for info in metadata.get("models", []):
                        instances = info.get("loaded_instances", [])
                        matching = next((i for i in instances if i.get("id") == model["id"]), None)
                        if info.get("key") == model["id"] or matching is not None:
                            model["loaded"] = bool(instances)
                            model["context_tokens"] = (
                                matching.get("config", {}).get("context_length")
                                if matching
                                else None
                            )
                            model["quantization"] = info.get("quantization")
            except (ProviderError, TypeError, AttributeError):
                pass  # Native metaveri temel bağlantının şartı değildir.
        return models

    async def translate_sample(self, model: str, text: str) -> dict[str, Any]:
        return await self.translate_record(
            model,
            text,
            "sample",
            "en",
            "tr",
            context_tokens=8192,
            output_tokens=4096,
            prompt_version="sample-v1",
        )

    async def translate_record(
        self,
        model: str,
        text: str,
        request_id: str,
        source_language: str,
        target_language: str,
        *,
        context_tokens: int,
        output_tokens: int = 2048,
        temperature: float = 0.2,
        context: str = "",
        style: str = "",
        glossary: list[dict[str, Any]] | None = None,
        prompt_version: str = "translate-v1",
    ) -> dict[str, Any]:
        if prompt_version not in ("sample-v1", "translate-v1"):
            raise ProviderError("unsupported_option", "İstem sürümü desteklenmiyor.")
        if not 128 <= output_tokens <= 8192 or not 512 <= context_tokens <= 1_048_576:
            raise ProviderError("context", "Bağlam/çıkış token sınırı geçersiz.")
        branches = plural_branches(text)
        protected = {form: mask(branch) for form, branch in branches.items()}
        ids = {
            form: request_id if len(branches) == 1 else request_id + ":" + form for form in branches
        }
        format_prompt = "translate-plural-v2" if len(branches) > 1 else prompt_version
        started = perf_counter()
        prompt = (
            files("unitytranslator.resources")
            .joinpath(format_prompt + ".txt")
            .read_text(encoding="utf-8")
        )
        input_data: dict[str, Any] = {
            "id": request_id,
            "source": protected["Plural"].text,
            "source_language": source_language,
            "target_language": target_language,
            "context": context,
            "style": style,
            "glossary": glossary or [],
        }
        if len(branches) > 1:
            del input_data["id"]
            del input_data["source"]
            input_data["branches"] = [
                {"id": ids[form], "plural_form": form, "source": item.text}
                for form, item in protected.items()
            ]
        encoded_input = json.dumps(input_data, ensure_ascii=False)
        # Araç tanımı yok; kaynak metin JSON veri alanıdır. Bir deneme, tek kayıt.
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": output_tokens,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": encoded_input,
                },
            ],
        }
        if self.structured_output:
            schema = Envelope.model_json_schema()
            schema["properties"]["translations"].update(
                {"minItems": len(branches), "maxItems": len(branches)}
            )
            schema["$defs"]["Translation"]["properties"]["id"] = {
                "type": "string",
                "enum": list(ids.values()),
            }
            if len(branches) > 1:
                schema["properties"]["translations"]["items"] = [
                    {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "enum": [identifier]},
                            "text": {"type": "string"},
                        },
                        "required": ["id", "text"],
                        "additionalProperties": False,
                    }
                    for identifier in ids.values()
                ]
                schema["properties"]["translations"]["additionalItems"] = False
                schema.pop("$defs", None)
            if self.provider == "lm-studio":
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "translation_response",
                        "strict": True,
                        "schema": schema,
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object", "schema": schema}
        context_payload = {"messages": payload["messages"]}
        if "response_format" in payload:
            context_payload["response_format"] = payload["response_format"]
        estimated = (
            len(json.dumps(context_payload, ensure_ascii=False).encode("utf-8")) + output_tokens
        )
        if estimated > int(context_tokens * 0.8):
            raise ProviderError(
                "context",
                "İstem ve çıktı şeması güvenli bağlam bütçesine sığmıyor; metin kesilmedi.",
            )
        result = await self.request("POST", "/chat/completions", payload, generation=True)
        diagnostics = response_diagnostics(result)
        diagnostics.update(
            {
                "format_prompt_version": format_prompt,
                "protected_format_version": PROTECTED_FORMAT_VERSION,
                "request_branch_count": len(branches),
                "schema_mode": ("ordered-items-v1" if len(branches) > 1 else "single-id-array-v1")
                if self.structured_output
                else "disabled",
            }
        )
        try:
            choice = result["choices"][0]
            message = choice["message"]
            if not isinstance(choice, dict) or not isinstance(message, dict):
                raise ValueError("Cevap choice/message nesnesi değil.")
            if (
                message.get("tool_calls")
                or message.get("function_call")
                or choice.get("finish_reason") in ("tool_calls", "function_call")
            ):
                raise ProviderError(
                    "unexpected_tool_call",
                    "Model araç çağrısı döndürdü; çalıştırılmadı.",
                    diagnostics,
                )
            if choice.get("finish_reason") == "length":
                raise ProviderError(
                    "output_truncated",
                    "Model cevabı çıkış token sınırında kesildi; "
                    "çeviri kabul edilmedi. Çıkış bütçesini ve modelin üretim ayarlarını "
                    "kontrol edin.",
                    diagnostics,
                )
            raw = message["content"]
            if not isinstance(raw, str):
                raise ValueError("Son metin bulunamadı.")
            candidates = parse_reply(raw, set(ids.values()))
        except ProviderError:
            raise
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(
                "response_schema_error",
                "Model cevabının JSON yapısı veya kayıt kimliği geçersiz.",
                diagnostics,
            ) from exc
        try:
            translated = join_plural_branches(
                {form: item.restore(candidates[ids[form]]) for form, item in protected.items()}
            )
        except ValueError as exc:
            raise ProviderError(
                "protected_content_error",
                "Model cevabındaki değişken veya etiket korunmadı.",
                diagnostics,
            ) from exc
        issues = review_issues(
            text, translated, source_language=source_language, target_language=target_language
        )
        return {
            "provider": self.provider,
            "model": model,
            "prompt_version": prompt_version,
            "format_prompt_version": format_prompt,
            "plural_forms": list(branches),
            "plural_schema_version": "ordered-items-v1"
            if len(branches) > 1 and self.structured_output
            else None,
            "glossary_version": None,
            "style_version": None,
            "elapsed_seconds": round(perf_counter() - started, 3),
            "source": text,
            "translation": translated,
            "status": "needs_review" if issues else "translated",
            "issues": issues,
            "human_approved": False,
            "review_checks_version": REVIEW_CHECKS_VERSION,
            "protected_format_version": PROTECTED_FORMAT_VERSION,
            "schema_capability": "tested_supported" if self.structured_output else "unknown",
            "settings": {
                "temperature": temperature,
                "max_tokens": output_tokens,
                "context_tokens": context_tokens,
            },
            "token_budget": {
                "method": "conservative_message_schema_bytes_v2",
                "estimated": estimated,
            },
            "usage": result.get("usage"),
        }
