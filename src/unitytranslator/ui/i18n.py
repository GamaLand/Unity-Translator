"""Offline interface catalogs. Interface language never changes project/model data."""

import json
import os
import re
import tempfile
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

LANGUAGES = {
    "en": "English",
    "tr": "Türkçe",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "pt": "Português (Brasil)",
    "ru": "Русский",
    "zh": "简体中文",
}


def settings_path() -> Path:
    base = os.environ.get("UNITYTRANSLATOR_CONFIG_HOME") or os.environ.get("APPDATA")
    return (Path(base) if base else Path.home() / ".config") / "UnityTranslator/ui.json"


def preferred_language() -> str:
    override = os.environ.get("UNITYTRANSLATOR_UI_LANGUAGE")
    if override in LANGUAGES:
        return override
    try:
        path = settings_path()
        if path.stat().st_size <= 65536:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("language") in LANGUAGES:
                return str(data["language"])
    except (OSError, ValueError, TypeError):
        pass
    return "en"


@lru_cache(maxsize=1)
def active_language() -> str:
    # Held for this process: changing the preference never interrupts a job or draft.
    return preferred_language()


def save_language(code: str) -> None:
    if code not in LANGUAGES:
        raise ValueError("Unsupported interface language")
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".ui-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"language": code}, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@lru_cache(maxsize=8)
def catalog(code: str) -> dict[str, str]:
    if code not in LANGUAGES:
        raise ValueError("Unsupported interface language")
    content = files("unitytranslator.resources").joinpath("locales", code + ".json")
    data = json.loads(content.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in data.items()
    ):
        raise ValueError("Invalid interface catalog")
    return data


def tr(message: str, **values: Any) -> str:
    translated = catalog(active_language()).get(message, message)
    return translated.format(**values) if values else translated


@lru_cache(maxsize=2048)
def diagnostic(message: str) -> str:
    """Translate known app diagnostics; preserve unknown OS/server details verbatim."""
    for source, turkish in catalog("tr").items():
        if source == message or turkish == message:
            return tr(source)
        names = re.findall(r"\{(p\d+)\}", turkish)
        if names:
            pattern = re.escape(turkish)
            for name in set(names):
                pattern = pattern.replace(re.escape("{" + name + "}"), "(?P<" + name + ">.+?)", 1)
                pattern = pattern.replace(re.escape("{" + name + "}"), "(?P=" + name + ")")
            matched = re.fullmatch(pattern, message, flags=re.DOTALL)
            if matched:
                return tr(source, **matched.groupdict())
    return message


def localized_issue_label(code: str) -> str:
    from unitytranslator.validation import issue_label

    if code.startswith("glossary_violation:"):
        return tr("Missing glossary term: {p0}", p0=code.split(":", 1)[1])
    return diagnostic(issue_label(code))
