"""Narrow I2 placeholder/rich-text protection; unknown grammars are rejected."""

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, StrictStr

from unitytranslator.json_boundary import strict_json
from unitytranslator.language import turkish_lower

PARAMETER = r"\{\[[A-Za-z_0-9]+\]\}|\{[0-9]+:[fF][0-9]{1,2}\}|\{[A-Za-z_0-9]+\}"
TOKEN = re.compile(
    PARAMETER
    + r'|<sprite name="[A-Za-z_0-9-]{1,128}">'
    + r"|<size=[1-9][0-9]{0,2}%?>|</size>"
    + r"|</?(?:b|i|color)(?:=[^<>\r\n]+)?>|(?<=\s)[<>](?=\s)|\r\n|\r|\n"
)
MARKER = re.compile(r"__UT_[a-f0-9]+_\d+__")
PROTECTED_FORMAT_VERSION = "protected-i2-v4"
PLURAL_MARKER = re.compile(r"\[i2p_(Zero|One)\]")
NUMBER = r"[+\-−]?\d+(?:[.,]\d+)*"
REVIEW_CHECKS_VERSION = "review-multilingual-v5"
EN_NEGATION = re.compile(
    r"\b(?:not|no|never|none|nothing|nowhere|neither|nor|without|cannot|unable)\b|"
    r"\b\w+n['’]t\b"
)
TR_NEGATION = re.compile(
    r"\b(?:asla|hayır|hiç\w*|değil\w*|yok(?:tur|turlar|tu|muş)?)\b|"
    r"\b[a-zçğıöşü]+(?:ma|me)(?:z(?:lar|ler|sın|sin|sınız|siniz)?|"
    r"dı\w*|di\w*|mış\w*|miş\w*|dan|den|yacak\w*|yecek\w*|yın|yin)\b|"
    r"\b[a-zçğıöşü]+m[ıiuü]yor\w*\b"
)
CONDITION_CUES = (
    (r"\bat least\b", r"\b(?:en az|asgari|minimum)\b"),
    (r"\bat most\b", r"\b(?:en fazla|azami|maksimum)\b"),
    (r"\bmore than\b", r"(?:den|dan|ten|tan)\s+(?:daha )?fazla\b"),
    (r"\bless than\b", r"(?:den|dan|ten|tan)\s+(?:daha )?az\b"),
    (r"\bonly\b", r"\b(?:yalnızca|sadece|ancak)\b"),
    (
        r"\b(?:if|unless)\b",
        r"\b(?:eğer|şayet|koşuluyla|durumunda|halinde)\b|"
        r"\b[a-zçğıöşü]+(?:sa|se)(?:nız|niz|lar|ler)?\b",
    ),
    (r"\bbefore\b", r"\bönce\b"),
    (r"\bafter\b", r"\bsonra\b"),
    (r"\buntil\b", r"\bkadar\b"),
)
ISSUE_LABELS = {
    "unchanged_source": "Kaynakla aynı metin",
    "numeric_content_review": "Sayı veya işaret değişikliği: inceleyin",
    "percentage_content_review": "Yüzde değeri veya yüzde işareti değişikliği: inceleyin",
    "negation_content_review": "Olumsuzluk değişmiş olabilir: inceleyin",
    "mechanical_condition_review": "Koşul veya sınır değişmiş olabilir: inceleyin",
    "unsupported_or_unbalanced_format": "Desteklenmeyen veya dengesiz biçim",
    "protected_content_mismatch": "Değişken veya etiket eşleşmiyor",
    "response_schema_error": "Model cevabının JSON yapısı veya kayıt kimliği geçersiz",
    "protected_content_error": "Model cevabında değişken veya etiket korunmadı",
    "output_truncated": "Model cevabı token sınırında kesildi; üretim ayarlarını inceleyin",
    "unexpected_tool_call": "Modelin beklenmeyen araç çağrısı reddedildi; çalıştırılmadı",
    "unsupported_format": "Henüz desteklenmeyen kaynak biçimi",
    "validation_error": "Eski doğrulama hatası; ayrıntılı sınıfı kaydedilmemiş",
    "plural_content_review": "Çoğul dallarını ve 0/1/2 değerlerini inceleyin",
    "plural_structure_mismatch": "Çoğul dalları veya dal sırası eşleşmiyor",
}


def plural_branches(text: str) -> dict[str, str]:
    """Parse verified I2 Plural/One/Zero branches; the model never selects tags."""
    matches = list(PLURAL_MARKER.finditer(text))
    if "[i2" in PLURAL_MARKER.sub("", text).lower():
        raise ValueError("Doğrulanmamış I2 çoğul biçimi.")
    branches = {"Plural": text[: matches[0].start()] if matches else text}
    for index, match in enumerate(matches):
        form = match.group(1)
        if form in branches:
            raise ValueError("Yinelenen I2 çoğul dalı.")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        branches[form] = text[match.end() : end]
    if any(not branch.strip() for branch in branches.values()):
        raise ValueError("Boş I2 çoğul/metin dalı.")
    return branches


def join_plural_branches(branches: dict[str, str]) -> str:
    if (
        not branches
        or next(iter(branches)) != "Plural"
        or not set(branches) <= {"Plural", "One", "Zero"}
    ):
        raise ValueError("Çoğul dal kümesi geçersiz.")
    return branches["Plural"] + "".join(
        "[i2p_" + form + "]" + text for form, text in branches.items() if form != "Plural"
    )


def issue_label(code: str) -> str:
    if code.startswith("glossary_violation:"):
        return "Sözlük karşılığı bulunamadı: " + code.split(":", 1)[1]
    return ISSUE_LABELS.get(code, code)


def numeric_value(value: str, language: str) -> str:
    """Normalize unambiguous separators for common language conventions."""
    value = value.replace("−", "-")
    primary = language.lower().split("-")[0]
    dot_decimal = {"en", "ja", "ko", "zh", "hi", "th"}
    comma_decimal = {"tr", "de", "es", "it", "pt", "nl", "da", "el", "ro", "id", "vi"}
    if language.lower() == "pt-pt" or primary in {"fr", "ru", "uk", "pl", "cs", "sv", "fi", "hu"}:
        # These commonly use a space grouping separator; do not treat '.' as grouping.
        decimal, grouping = ",", " "
    elif primary in dot_decimal:
        decimal, grouping = ".", ","
    elif primary in comma_decimal:
        decimal, grouping = ",", "."
    else:
        return value
    if value.count(decimal) > 1 or (decimal in value and grouping in value.split(decimal)[1]):
        return value
    integer = value.lstrip("+-").split(decimal)[0]
    if grouping in integer:
        groups = integer.split(grouping)
        if not (1 <= len(groups[0]) <= 3 and all(len(group) == 3 for group in groups[1:])):
            return value  # Do not declare an ambiguous numeric format equivalent.
    canonical = value.replace(grouping, "").replace(decimal, ".")
    try:
        number = Decimal(canonical)
        if number == 0:
            return "0"
        encoded = format(number, "f")
        return encoded.rstrip("0").rstrip(".") if "." in encoded else encoded
    except InvalidOperation:
        return value


def percentages(text: str, language: str) -> Counter[str]:
    # Recognize symbolic percentages and the supported English/Turkish word forms.
    pattern = rf"(?:%|\byüzde)\s*({NUMBER})|({NUMBER})\s*(?:%|\bpercent\b)"
    return Counter(
        numeric_value(before or after, language) for before, after in re.findall(pattern, text)
    )


def numeric_mismatch(source: str, target: str, source_language: str, target_language: str) -> bool:
    original = Counter(re.findall(NUMBER, source))
    result = Counter(re.findall(NUMBER, target))
    # Identical numeric spelling is preserved, including brand/version numbers.
    # Changed spelling is compared using known decimal/grouping conventions.
    shared = original & result
    return Counter(numeric_value(v, source_language) for v in (original - shared).elements()) != (
        Counter(numeric_value(v, target_language) for v in (result - shared).elements())
    )


class Translation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: StrictStr
    text: StrictStr


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    translations: list[Translation]


def parse_reply(raw: str, expected: set[str]) -> dict[str, str]:
    if len(raw.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Model cevabı boyut sınırını aşıyor.")

    payload = strict_json(raw)
    envelope = Envelope.model_validate(payload)
    ids = [item.id for item in envelope.translations]
    if len(set(ids)) != len(ids) or set(ids) != expected:
        raise ValueError("Model cevabındaki kayıt kimlikleri tam ve tekil eşleşmiyor.")
    if any(not item.text.strip() for item in envelope.translations):
        raise ValueError("Boş çeviri kabul edilmiyor.")
    return {item.id: item.text for item in envelope.translations}


def check_format(text: str) -> None:
    for branch in plural_branches(text).values():
        check_plain_format(branch)


def check_plain_format(text: str) -> None:
    if "__UT_" in text:
        raise ValueError("Korumalı belirteç önekiyle çakışma.")
    remainder = TOKEN.sub("", text)
    if any(character in remainder for character in "{}<>") or "[i2" in text.lower():
        raise ValueError("Bilinmeyen korumalı biçim; okuyucu kuralı gerekiyor.")
    stack: list[str] = []
    for match in TOKEN.finditer(text):
        token = match.group()
        if token in ("<", ">") or token.startswith("<sprite ") or not token.startswith("<"):
            continue
        attribute = re.sub(PARAMETER, "", token)
        if "{" in attribute or "}" in attribute:
            raise ValueError("Etiket içinde bilinmeyen değişken biçimi.")
        name = re.split(r"[=>]", token.lstrip("</"))[0]
        if "=" in token and (token.startswith("</") or name in ("b", "i")):
            raise ValueError("Desteklenmeyen etiket parametresi.")
        if token.startswith("</"):
            if not stack or stack.pop() != name:
                raise ValueError("Etiket dengesi/sırası bozuk.")
        else:
            stack.append(name)
    if stack:
        raise ValueError("Kapanmamış etiket.")


@dataclass(frozen=True)
class MaskedText:
    text: str
    replacements: dict[str, str]

    def restore(self, translated: str) -> str:
        if len(plural_branches(translated)) != 1:
            raise ValueError("Tek dala yeni çoğul etiketi eklenemez.")
        found = Counter(MARKER.findall(translated))
        if found != Counter(self.replacements.keys()):
            raise ValueError("Korumalı belirteç eksik/fazla/bozuk.")
        for marker, original in self.replacements.items():
            translated = translated.replace(marker, original)
        if "__UT_" in translated:
            raise ValueError("Bilinmeyen/bozuk koruma belirteci.")
        check_format(translated)
        if Counter(TOKEN.findall(translated)) != Counter(self.replacements.values()):
            raise ValueError("Geri yüklenen değişken/etiket kümesi uyuşmuyor.")
        return translated


def mask(text: str) -> MaskedText:
    check_format(text)
    if len(plural_branches(text)) != 1:
        raise ValueError("Çoğul metin dallar halinde maskelenmeli.")
    if "__UT_" in text:
        raise ValueError("Kaynak korumalı belirteç önekiyle çakışıyor.")
    prefix = uuid4().hex[:8]
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        marker = f"__UT_{prefix}_{len(replacements)}__"
        replacements[marker] = match.group()
        return marker

    return MaskedText(TOKEN.sub(replace, text), replacements)


def review_issues(
    source: str, translated: str, *, source_language: str = "en", target_language: str = "tr"
) -> list[str]:
    """Numeric checks and narrow en-to-tr hints; not semantic or approval proof."""
    try:
        original_branches, target_branches = plural_branches(source), plural_branches(translated)
    except ValueError:
        return ["plural_content_review"]
    if len(original_branches) > 1 or len(target_branches) > 1:
        branch_issues = {"plural_content_review"}
        if list(original_branches) == list(target_branches):
            for form, branch in original_branches.items():
                branch_issues.update(
                    review_issues(
                        branch,
                        target_branches[form],
                        source_language=source_language,
                        target_language=target_language,
                    )
                )
        return sorted(branch_issues)
    issues = []
    if source.strip() == translated.strip():
        issues.append("unchanged_source")
    # Tag parameters and placeholder identifiers are not numeric content.
    original_text, result_text = TOKEN.sub(" ", source), TOKEN.sub(" ", translated)
    if numeric_mismatch(original_text, result_text, source_language, target_language):
        issues.append("numeric_content_review")
    if percentages(original_text.casefold(), source_language) != percentages(
        turkish_lower(result_text), target_language
    ):
        issues.append("percentage_content_review")
    if (source_language.lower().split("-")[0], target_language.lower().split("-")[0]) == (
        "en",
        "tr",
    ):
        english, turkish = original_text.casefold(), turkish_lower(result_text)
        # Flag a missing negative cue or negation added to an explicit can statement.
        # Turkish suffixes do not prove absence of implicit English lexical negation.
        english_negative = bool(EN_NEGATION.search(english))
        # Exclude affirmative destroy/count phrases while retaining later negative verbs.
        negation_text = re.sub(r"\byok(?=\s+(?:et|ed|say|oluş))", " ", turkish)
        turkish_negative = bool(TR_NEGATION.search(negation_text))
        if (english_negative and not turkish_negative) or (
            not english_negative and re.search(r"\bcan\b", english) and turkish_negative
        ):
            issues.append("negation_content_review")
        if any(re.search(en, english) and not re.search(tr, turkish) for en, tr in CONDITION_CUES):
            issues.append("mechanical_condition_review")
    return issues


def format_issues(source: str, translated: str) -> list[str]:
    try:
        check_format(source)
        check_format(translated)
    except ValueError:
        return ["unsupported_or_unbalanced_format"]
    original, result = plural_branches(source), plural_branches(translated)
    if list(original) != list(result):
        return ["plural_structure_mismatch"]
    for form, branch in original.items():
        if Counter(TOKEN.findall(branch)) != Counter(TOKEN.findall(result[form])):
            return ["protected_content_mismatch"]
    return []
