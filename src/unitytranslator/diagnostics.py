"""Stable English diagnostics that interface catalogs localize by reason code.

A diagnostic's reason code is its English message template: the key of the bundled
interface catalogs. Parameters are rendered into the English text for logs and the
command line, and are passed separately so each interface language can place them.
Renaming a template requires a legacy alias, because stored messages and catalog
translations refer to it. Legacy aliases map messages written by earlier versions,
which are stored verbatim, to the current template; they never rewrite stored data.
"""

import json
import re
from functools import lru_cache
from importlib.resources import files
from string import Formatter
from typing import Any

MAX_PARAMETER_CHARACTERS = 4096


def template_fields(template: str) -> list[str]:
    return [name for _, name, _, _ in Formatter().parse(template) if name is not None]


class Diagnostic(ValueError):
    """A ValueError whose English template is a catalogued reason code."""

    def __init__(self, template: str, /, **params: object) -> None:
        # Without parameters the template is literal text and may contain braces.
        if params and sorted(set(template_fields(template))) != sorted(params):
            raise TypeError("Diagnostic parameters must match the template fields.")
        self.template = template
        self.params = {
            name: str(value)[:MAX_PARAMETER_CHARACTERS] for name, value in params.items()
        }
        super().__init__(template.format(**self.params) if self.params else template)


class Failure(str):
    """English failure text that also carries its reason code and request identity.

    It is a ``str`` so existing consumers can keep displaying or storing it.
    """

    code: str | None
    params: dict[str, str]
    command: str
    request_token: Any
    project_id: str | None

    def __new__(
        cls, message: str, *, code: str | None = None, params: dict[str, str] | None = None,
        command: str = "", request_token: Any = None, project_id: str | None = None,
    ) -> "Failure":
        value = super().__new__(cls, message)
        value.code = code
        value.params = dict(params or {})
        value.command = command
        value.request_token = request_token
        value.project_id = project_id
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command, "code": self.code, "params": dict(self.params),
            "message": str(self), "request_token": self.request_token,
            "project_id": self.project_id,
        }


@lru_cache(maxsize=1)
def english_catalog() -> frozenset[str]:
    content = files("unitytranslator.resources").joinpath("locales", "en.json")
    data = json.loads(content.read_text(encoding="utf-8"))
    return frozenset(data)


@lru_cache(maxsize=1)
def legacy_aliases() -> dict[str, str]:
    """Messages of earlier versions mapped to current English templates."""
    content = files("unitytranslator.resources").joinpath("locales", "legacy-messages.json")
    data = json.loads(content.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != 1 or not isinstance(
        data.get("aliases"), dict
    ):
        raise ValueError("Invalid legacy message table.")
    aliases: dict[str, str] = data["aliases"]
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in aliases.items()):
        raise ValueError("Invalid legacy message table.")
    return aliases


def _pattern(template: str) -> re.Pattern[str] | None:
    names = template_fields(template)
    if not names:
        return None
    pattern = re.escape(template)
    for name in dict.fromkeys(names):
        placeholder = re.escape("{" + name + "}")
        pattern = pattern.replace(placeholder, "(?P<" + name + ">.+?)", 1)
        pattern = pattern.replace(placeholder, "(?P=" + name + ")")
    return re.compile(pattern, flags=re.DOTALL)


# Rendered templates whose fixed text is shorter than this are too generic to match.
MIN_PATTERN_TEXT = 12
# Lazy groups backtrack polynomially; diagnostics have at most two parameters, and
# longer text is shown verbatim instead of being matched.
MAX_PATTERN_FIELDS = 2
MAX_MATCHED_MESSAGE = 2048


@lru_cache(maxsize=1)
def _template_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    """Current English templates, so stored rendered English text keeps its code."""
    found = []
    for template in sorted(english_catalog()):
        try:
            fields = template_fields(template) if "{" in template else []
        except ValueError:
            continue  # Interface labels may contain literal braces.
        fixed = re.sub(r"\{[^{}]*\}", "", template)
        if (
            fields and all(re.fullmatch(r"p\d+", name) for name in fields)
            and len(set(fields)) <= MAX_PATTERN_FIELDS
            and len(fixed.strip()) >= MIN_PATTERN_TEXT
            and (pattern := _pattern(template)) is not None
        ):
            found.append((pattern, template))
    return tuple(found)


@lru_cache(maxsize=1)
def _legacy_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    return tuple(
        (pattern, target) for old, target in legacy_aliases().items()
        if (pattern := _pattern(old)) is not None
    )


@lru_cache(maxsize=4096)
def classify_message(message: str) -> tuple[str | None, dict[str, str]]:
    """Find the reason code of a plain English or legacy message, if it has one."""
    if message in english_catalog():
        return message, {}
    aliases = legacy_aliases()
    if message in aliases:
        return aliases[message], {}
    if len(message) > MAX_MATCHED_MESSAGE:
        return None, {}
    for pattern, target in (*_template_patterns(), *_legacy_patterns()):
        matched = pattern.fullmatch(message)
        if matched:
            return target, matched.groupdict()
    return None, {}


def describe(
    exc: BaseException, *, command: str = "", request_token: Any = None,
    project_id: str | None = None,
) -> Failure:
    """The bridge representation of a failed command."""
    code: str | None = None
    params: dict[str, str] = {}
    if isinstance(exc, Diagnostic):
        code, params = exc.template, exc.params
    else:
        try:
            code, params = classify_message(str(exc))
        except Exception:  # noqa: BLE001 - a failure must always reach the interface.
            code, params = None, {}
    return Failure(
        str(exc), code=code, params=params, command=command,
        request_token=request_token, project_id=project_id,
    )
