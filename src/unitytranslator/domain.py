"""Domain records independent of reader and provider libraries."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TextUnitDraft:
    unit_id: str
    original_key: str
    source_file: str
    source_object: int
    source_language: str
    source_text: str
    source_hash: str
    category: str = "unknown"
    context: str = ""


@dataclass(frozen=True)
class GenerationProfile:
    provider: Literal["lm-studio", "llama-cpp"]
    address: str
    model: str
    context_tokens: int
    output_tokens: int = 2048
    temperature: float = 0.2
    structured_output: bool = True
    glossary_version: str | None = None
    style_version: str | None = None
    prompt_version: str = "translate-v1"
