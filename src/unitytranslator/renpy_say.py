"""Fixed data-only grammar for symbolic Ren'Py say statement structure."""

import keyword
import re
from dataclasses import dataclass

SYNTAX_VERSION = "renpy-symbolic-say-v2"
_NAME = r"[A-Za-z_][A-Za-z_0-9]*"
_ATTRIBUTE = re.compile(r"-?" + _NAME)
_SPEAKER = re.compile(_NAME)
_RESERVED = {
    "None", "python", "init", "style", "define", "default", "jump", "call", "return",
    "show", "scene", "hide", "with", "image", "menu", "screen", "translate", "old",
    "new", "pass", "extend", "label", "transform", "pause", "play", "stop", "voice",
    "nvl", "window", "camera", "layeredimage", "rpy", "nointeract", "id",
}


@dataclass(frozen=True)
class SayShape:
    speaker: str = ""
    attributes: tuple[str, ...] = ()
    temporary_attributes: tuple[str, ...] = ()
    nointeract: bool = False

    def prefix(self) -> str:
        parts = [self.speaker, *self.attributes] if self.speaker else []
        if self.temporary_attributes:
            parts.extend(("@", *self.temporary_attributes))
        return " ".join(parts) + (" " if parts else "")

    def statement(self, literal: str) -> str:
        return self.prefix() + literal + (" nointeract" if self.nointeract else "")


def symbolic_prefix(value: str) -> SayShape:
    """Accept identifiers and attribute removals only; never expressions or calls."""
    if not value:
        return SayShape()
    parts = value.split(" ")
    speaker, *attributes = parts
    if (
        not _SPEAKER.fullmatch(speaker) or speaker in _RESERVED
        or keyword.iskeyword(speaker) or any(not part for part in parts)
        or attributes.count("@") > 1
    ):
        raise ValueError("Unsupported Ren'Py symbolic say prefix.")
    split = attributes.index("@") if "@" in attributes else len(attributes)
    permanent = attributes[:split]
    temporary = attributes[split + 1:] if split < len(attributes) else []
    if split < len(attributes) and not temporary:
        raise ValueError("Ren'Py temporary attributes must not be empty.")
    if any(
        not _ATTRIBUTE.fullmatch(part) or part.lstrip("-") in _RESERVED
        or keyword.iskeyword(part.lstrip("-"))
        for part in (*permanent, *temporary)
    ):
        raise ValueError("Unsupported Ren'Py character attribute.")
    return SayShape(speaker, tuple(permanent), tuple(temporary))
