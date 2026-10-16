"""Read the selected source language from validated I2 fields."""

from hashlib import sha256
from typing import Any

from unitytranslator.domain import TextUnitDraft
from unitytranslator.language import language_index, normalize_language


def extract_i2(
    tree: dict[str, Any],
    source: str,
    object_id: int,
    diagnostics: list[dict[str, Any]] | None = None,
    source_language: str = "en",
) -> list[TextUnitDraft]:
    # Bazı I2 sürümleri LanguageSourceData'yı mSource alanında saklar.
    data = tree.get("mSource", tree)
    if not isinstance(data, dict) or "mTerms" not in data or "mLanguages" not in data:
        return []
    languages = data["mLanguages"]
    terms = data["mTerms"]
    if not isinstance(languages, list) or not isinstance(terms, list):
        raise ValueError("I2 dil/terim listesi çözülemedi.")
    source_language = normalize_language(source_language)
    index = language_index(languages, source_language)
    result = []
    seen: set[str] = set()
    source_set = data.get("mName") or tree.get("m_Name")
    if not isinstance(source_set, str) or not source_set:
        raise ValueError("Kararlı kaynak kümesi adı bulunamadı.")
    for term in terms:
        if not isinstance(term, dict):
            raise ValueError("I2 terim nesnesi çözülemedi.")
        key = term.get("Term")
        # I2 eTermType.Text = 0; font, sprite ve varlık referansları çevrilmez.
        if term.get("TermType") != 0:
            continue
        values = term.get("Languages")
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError("Eksik veya yinelenen I2 terim anahtarı.")
        seen.add(key)
        if not isinstance(values, list) or len(values) != len(languages):
            raise ValueError("I2 terim dil sayısı uyuşmuyor.")
        text = values[index]
        if not isinstance(text, str):
            raise ValueError("Selected source language text is missing.")
        if not text.strip():
            if diagnostics is None:
                raise ValueError("Selected source language text is missing.")
            diagnostics.append({"object": object_id, "key": key, "code": "empty_source_excluded"})
            continue
        identity = "\0".join(("i2-v1", source_set, key))
        result.append(
            TextUnitDraft(
                unit_id=sha256(identity.encode("utf-8")).hexdigest(),
                original_key=key,
                source_file=source,
                source_object=object_id,
                source_language=source_language,
                source_text=text,
                source_hash=sha256(text.encode("utf-8")).hexdigest(),
                category=key.partition("/")[0] if "/" in key else "unknown",
                context=term.get("Description", "")
                if isinstance(term.get("Description", ""), str)
                else "",
            )
        )
    return result
