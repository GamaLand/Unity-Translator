"""Language tags shared by project creation, extraction and runtime export."""

import re

# Editable suggestions, not a support allowlist.
LANGUAGE_NAMES = {
    "en": "English",
    "tr": "Türkçe",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "pt-BR": "Português (Brasil)",
    "ru": "Русский",
    "uk": "Українська",
    "pl": "Polski",
    "cs": "Čeština",
    "nl": "Nederlands",
    "sv": "Svenska",
    "fi": "Suomi",
    "da": "Dansk",
    "ja": "日本語",
    "ko": "한국어",
    "zh": "中文",
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "ar": "العربية",
    "he": "עברית",
    "hi": "हिन्दी",
    "id": "Bahasa Indonesia",
    "vi": "Tiếng Việt",
    "th": "ไทย",
    "el": "Ελληνικά",
    "ro": "Română",
    "hu": "Magyar",
    "bg": "Български",
    "fa": "فارسی",
}
I2_NAMES = dict(
    zip(
        ("en", "tr", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "zh", "ar", "he"),
        (
            "English",
            "Turkish",
            "German",
            "French",
            "Spanish",
            "Italian",
            "Portuguese",
            "Russian",
            "Japanese",
            "Korean",
            "Chinese",
            "Arabic",
            "Hebrew",
        ),
        strict=True,
    )
)
DEFAULT_STYLE = (
    "Preserve the source meaning and tone. Use clear, natural language in the specified "
    "target language. Do not add, omit or soften content."
)


def normalize_language(value: str) -> str:
    value = value.strip().replace("_", "-")
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}", value):
        raise ValueError("Use a language code such as en, ja, it or pt-BR.")
    parts = value.split("-")
    parts[0] = {"jp": "ja", "iw": "he", "in": "id"}.get(parts[0].lower(), parts[0].lower())
    for i in range(1, len(parts)):
        parts[i] = (
            parts[i].upper()
            if len(parts[i]) == 2
            else parts[i].title()
            if len(parts[i]) == 4
            else parts[i].lower()
        )
    return "-".join(parts)


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def language_index(languages: list[object], code: str) -> int:
    code = normalize_language(code)
    candidates = []
    for index, language in enumerate(languages):
        if not isinstance(language, dict):
            continue
        raw = language.get("Code")
        if not raw:
            raw = next((key for key, name in I2_NAMES.items() if language.get("Name") == name), "")
        if not isinstance(raw, str):
            continue
        try:
            candidate = normalize_language(raw)
        except ValueError:
            continue
        candidates.append((index, candidate))
    exact = [index for index, candidate in candidates if candidate == code]
    matches = exact or [
        index
        for index, candidate in candidates
        if (candidate == code.split("-")[0] if "-" in code else candidate.split("-")[0] == code)
    ]
    if len(matches) != 1:
        raise ValueError(f"Source language {code} is missing or ambiguous in this I2 source.")
    return matches[0]


def turkish_lower(value: str) -> str:
    return value.replace("I", "ı").replace("İ", "i").lower()


def language_fold(value: str, language: str) -> str:
    return turkish_lower(value) if language.split("-")[0].lower() == "tr" else value.casefold()
