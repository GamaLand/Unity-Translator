"""Strict Ren'Py text subset, based on the upstream 8.5.4 text documentation.

Interpolation is opaque source data: it is balanced and preserved, never evaluated.
Tags must belong to the fixed allowlist and close explicitly in stack order.
"""

import re
from dataclasses import dataclass

RENPY_FORMAT = "renpy-text-v1"
MAX_TEXT = 1_000_000
MAX_TOKEN = 8192
MAX_NESTING = 32
_SIMPLE = {"b", "i", "u", "s", "alt", "noalt"}
_ARGUMENT = {"color", "outlinecolor", "size", "alpha", "cps", "k", "font", "a"}
_CONTROL = {"w", "p", "nw", "fast", "done"}
_SINGLE_ARGUMENT = {"image", "space", "vspace"}


@dataclass(frozen=True)
class TextToken:
    start: int
    end: int
    text: str


def tokens(text: str) -> tuple[TextToken, ...]:
    """Tokenize a bounded supported string, rejecting unknown executable constructs."""
    if len(text) > MAX_TEXT or "__UT_" in text or any(
        (ord(c) < 32 and c not in "\r\n") or 0xD800 <= ord(c) <= 0xDFFF
        or c in "\x85\u2028\u2029" for c in text
    ):
        raise ValueError("Invalid or oversized Ren'Py text.")
    result: list[TextToken] = []
    stack: list[str] = []
    index = 0
    while index < len(text):
        start = index
        character = text[index]
        if text.startswith(("[[", "{{", "%%", "\r\n"), index):
            index += 2
        elif character in "\r\n":
            index += 1
        elif character == "[":
            depth, quote, escaped = 1, "", False
            index += 1
            while index < len(text) and depth:
                current = text[index]
                if index - start > MAX_TOKEN or current in "\r\n":
                    raise ValueError("Unsupported Ren'Py interpolation bounds.")
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif quote:
                    if current == quote:
                        quote = ""
                elif current in "\"'":
                    quote = current
                elif current == "[":
                    depth += 1
                    if depth > MAX_NESTING:
                        raise ValueError("Ren'Py interpolation nesting limit exceeded.")
                elif current == "]":
                    depth -= 1
                index += 1
            if depth or quote or not text[start + 1:index - 1].strip():
                raise ValueError("Unbalanced or empty Ren'Py interpolation.")
        elif character == "{":
            end = text.find("}", start + 1, start + MAX_TOKEN + 1)
            if end < 0:
                raise ValueError("Unclosed or oversized Ren'Py text tag.")
            value = text[start + 1:end]
            if any(c in value for c in "{[\r\n\\"):
                raise ValueError("Unsupported Ren'Py text tag argument.")
            if value.startswith("#"):
                if not value[1:] or len(value) > 1024:
                    raise ValueError("Invalid Ren'Py string context tag.")
            elif value.startswith("/"):
                name = value[1:]
                if not stack or stack.pop() != name:
                    raise ValueError("Unbalanced Ren'Py text tags.")
            else:
                name, separator, argument = value.partition("=")
                if name in _SIMPLE and not separator:
                    stack.append(name)
                elif name in _ARGUMENT and separator and argument:
                    if name in {"color", "outlinecolor"} and not re.fullmatch(
                        r"#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}", argument
                    ):
                        raise ValueError("Unsupported Ren'Py color argument.")
                    if name in {"size", "alpha", "cps", "k"} and not re.fullmatch(
                        r"[+*\-]?(?:\d+(?:\.\d+)?|\.\d+)", argument
                    ):
                        raise ValueError("Unsupported Ren'Py numeric tag argument.")
                    stack.append(name)
                elif name in _CONTROL and (
                    not separator or (
                        name in {"w", "p"} and re.fullmatch(r"\d+(?:\.\d+)?", argument)
                    )
                ):
                    pass
                elif name in _SINGLE_ARGUMENT and separator and argument:
                    if name != "image" and not re.fullmatch(r"\d+", argument):
                        raise ValueError("Unsupported Ren'Py spacing tag argument.")
                else:
                    raise ValueError("Unknown or unsupported Ren'Py text tag.")
                if len(stack) > MAX_NESTING:
                    raise ValueError("Ren'Py text-tag nesting limit exceeded.")
            index = end + 1
        elif character in "〖〗":
            raise ValueError("Ren'Py ruby text is outside the supported subset.")
        else:
            index += 1
            continue
        result.append(TextToken(start, index, text[start:index]))
    if stack:
        raise ValueError("Ren'Py text tags must close explicitly in the supported subset.")
    return tuple(result)


def visible_text(text: str) -> str:
    output: list[str] = []
    cursor = 0
    for token in tokens(text):
        output.extend((text[cursor:token.start], " "))
        cursor = token.end
    output.append(text[cursor:])
    return "".join(output)


def format_matches(source: str, translated: str) -> bool:
    return [t.text for t in tokens(source)] == [t.text for t in tokens(translated)]
