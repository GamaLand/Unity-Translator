"""Domain records independent of reader and provider libraries."""

from dataclasses import asdict, dataclass
from typing import Any, Literal


class OperationCancelled(ValueError):
    """A cooperative local operation stopped before publishing its result."""


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
    reasoning_effort: Literal["default", "none"] = "default"
    dialogue_context: Literal["none", "source-window-v1"] = "none"

    def to_dict(self) -> dict[str, Any]:
        """Keep the legacy default profile encoding byte-compatible."""
        value = asdict(self)
        if self.reasoning_effort == "default":
            value.pop("reasoning_effort")
        if self.dialogue_context == "none":
            value.pop("dialogue_context")
        return value
