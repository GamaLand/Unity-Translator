"""Strict Ren'Py text subset, based on the upstream 8.5.4 text documentation.

Interpolation is opaque source data: it is balanced and preserved, never evaluated.
Tags must belong to the fixed allowlist and close explicitly in stack order.
renpy-text-v2 is a descriptor rule: dialogue keeps renpy-text-v1, while string keys
also protect Python printf conversions, because game code may apply `%` to them.
"""

import re
from dataclasses import dataclass

RENPY_FORMAT = "renpy-text-v1"
RENPY_STRING_FORMAT = "renpy-text-v2"
RENPY_FORMATS = (RENPY_FORMAT, RENPY_STRING_FORMAT)
# Python %-conversions. The space flag is excluded so prose such as '100% done' stays
# text; str.format braces remain Ren'Py tags and are rejected as before.
_PRINTF = re.compile(
    r"%(?:\([A-Za-z_][A-Za-z0-9_]{0,127}\))?[#0+\-]{0,8}(?:\*|[0-9]{1,4})?"
    r"(?:\.(?:\*|[0-9]{1,4}))?[hlL]?[diouxXeEfFgGcrsa]"
)
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


def unit_rules(descriptor_rules: str, original_key: str) -> str:
    """Effective rule of one record: renpy-text-v2 applies only to string keys."""
    if descriptor_rules == RENPY_STRING_FORMAT and not original_key.startswith("string/"):
        return RENPY_FORMAT
    return descriptor_rules


def tokens(text: str, *, printf: bool = False) -> tuple[TextToken, ...]:
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
        elif printf and character == "%" and (match := _PRINTF.match(text, index)):
            # Never raises: every v1-readable text stays readable under v2.
            index = match.end()
        else:
            index += 1
            continue
        result.append(TextToken(start, index, text[start:index]))
    if stack:
        raise ValueError("Ren'Py text tags must close explicitly in the supported subset.")
    return tuple(result)


def stray_percent(text: str, *, printf: bool = False) -> int:
    """Count `%` characters outside protected tokens."""
    covered = sum(token.text.count("%") for token in tokens(text, printf=printf))
    return text.count("%") - covered


def visible_text(text: str, *, printf: bool = False) -> str:
    output: list[str] = []
    cursor = 0
    for token in tokens(text, printf=printf):
        output.extend((text[cursor:token.start], " "))
        cursor = token.end
    output.append(text[cursor:])
    return "".join(output)


def _conversions(text: str) -> list[str]:
    return [t.text for t in tokens(text, printf=True) if t.text.startswith("%") and t.text != "%%"]


def format_matches(source: str, translated: str, *, printf: bool = False) -> bool:
    """v1 tokens keep their order; under v2, printf conversions also keep theirs.

    `%%` is a v1 token whose order is checked with the other v1 tokens only, so a
    conversion may move around it (Turkish writes '%50' for '50%').
    """
    if [t.text for t in tokens(source)] != [t.text for t in tokens(translated)]:
        return False
    if not printf:
        return True
    left = _conversions(source)
    if left != _conversions(translated):
        return False
    # A format template must not gain or lose a bare `%`, which would break `%` at runtime.
    template = bool(left) or "%%" in [t.text for t in tokens(source)]
    return not template or stray_percent(source, printf=True) == stray_percent(
        translated, printf=True
    )
