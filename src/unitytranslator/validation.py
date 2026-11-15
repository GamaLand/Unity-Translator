"""Narrow I2 placeholder/rich-text protection; unknown grammars are rejected."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, StrictStr

from unitytranslator.glossary_match import letter_fold
from unitytranslator.json_boundary import strict_json
from unitytranslator.language import language_fold, turkish_lower
from unitytranslator.renpy_format import (
    RENPY_FORMATS,
    RENPY_STRING_FORMAT,
)
from unitytranslator.renpy_format import format_matches as renpy_format_matches
from unitytranslator.renpy_format import tokens as renpy_tokens
from unitytranslator.renpy_format import visible_text as renpy_visible_text

PARAMETER = r"\{\[[A-Za-z_0-9]+\]\}|\{[0-9]+:[fF][0-9]{1,2}\}|\{[A-Za-z_0-9]+\}"
TOKEN = re.compile(
    PARAMETER
    + r'|<sprite name="[A-Za-z_0-9-]{1,128}">'
    + r"|<size=[1-9][0-9]{0,2}%?>|</size>"
    + r"|</?(?:b|i|color)(?:=[^<>\r\n]+)?>|(?<=\s)[<>](?=\s)|\r\n|\r|\n"
)
MARKER = re.compile(r"__UT_[a-f0-9]+_\d+__")
PROTECTED_FORMAT_VERSION = "protected-i2-v4"
LITERAL_LINE_FORMAT = "literal-lines-v1"
PLURAL_MARKER = re.compile(r"\[i2p_(Zero|One)\]")
NUMBER = r"[+\-−]?\d+(?:[.,]\d+)*"
# v6 added cue tables for more target languages, length ratios by category and
# inflection-tolerant glossary matching; stored revisions keep their recorded version.
REVIEW_CHECKS_VERSION = "review-multilingual-v6"
EN_NEGATION = re.compile(
    r"\b(?:not|no|never|none|nothing|nobody|nowhere|neither|nor|without|cannot|unable)\b|"
    r"\b\w+n['’]t\b"
)
TR_NEGATION = re.compile(
    r"\b(?:asla|hayır|hiç\w*|değil\w*|yok(?:tur|turlar|tu|muş)?)\b|"
    r"\b[a-zçğıöşü]+(?:ma|me)(?:z(?:lar|ler|sın|sin|sınız|siniz)?|"
    r"dı\w*|di\w*|mış\w*|miş\w*|dan|den|yacak\w*|yecek\w*|yın|yin)\b|"
    r"\b[a-zçğıöşü]+m[ıiuü]yor\w*\b"
)
# English source cues; each target table maps these names to its own expressions.
EN_CONDITIONS = {
    "at_least": r"\bat least\b",
    "at_most": r"\bat most\b",
    "more_than": r"\bmore than\b",
    "less_than": r"\bless than\b",
    "only": r"\bonly\b",
    "if": r"\b(?:if|unless)\b",
    "before": r"\bbefore\b",
    "after": r"\bafter\b",
    "until": r"\buntil\b",
}
# Lexical negatives of an English translation, for the reverse direction only.
EN_TARGET_NEGATION = re.compile(
    EN_NEGATION.pattern + r"|\b(?:impossible|lack\w*|absent)\b"
)


NeutralPhrase = tuple[re.Pattern[str], re.Pattern[str] | None]


def neutral_phrases(*phrases: tuple[str, str | None]) -> tuple[NeutralPhrase, ...]:
    """Compile (look-alike phrase, English negative idiom it translates or None) pairs."""
    return tuple(
        (re.compile(phrase), re.compile(idiom) if idiom is not None else None)
        for phrase, idiom in phrases
    )


@dataclass(frozen=True)
class LanguageCues:
    """Conservative negation/condition cues of one language, on language-folded text.

    ``negation`` is broad: a translation without any of its cues is flagged, so wider
    expressions mean fewer false warnings. ``neutral`` removes look-alike phrases
    (Russian "не менее" is "at least") before negation is searched, except a phrase
    whose paired English idiom occurs in the English source ("not less than" is
    translated as "не менее" and stays negative). ``added_negation`` also flags a
    negative translation of an affirmative English "can" sentence, only where the cues
    are unambiguous. ``source_negation`` is a strict expression used when this language
    is the source and English the target; ``None`` skips it. ``source_neutral`` lists
    the idioms and tag questions removed before that strict search (French "n'est-ce
    pas", Spanish "no pasa nada"), whose English translations need no negation.
    """

    negation: re.Pattern[str]
    conditions: dict[str, str]
    neutral: tuple[NeutralPhrase, ...] = ()
    added_negation: bool = True
    source_negation: re.Pattern[str] | None = None
    source_neutral: re.Pattern[str] | None = None

    def negative(
        self, text: str, *, strict: bool = False, english: str | None = None,
    ) -> bool:
        """Whether ``text`` negates; ``english`` is the folded English source, if any."""
        if strict and self.source_neutral is not None:
            text = self.source_neutral.sub(" ", text)
        for phrase, idiom in self.neutral:
            if english is None or idiom is None or not idiom.search(english):
                text = phrase.sub(" ", text)
        pattern = self.source_negation if strict else self.negation
        return bool(pattern is not None and pattern.search(text))


CUE_TABLES = {
    "tr": LanguageCues(
        TR_NEGATION,
        {
            "at_least": r"\b(?:en az|asgari|minimum)\b",
            "at_most": r"\b(?:en fazla|azami|maksimum)\b",
            "more_than": r"(?:den|dan|ten|tan)\s+(?:daha )?fazla\b",
            "less_than": r"(?:den|dan|ten|tan)\s+(?:daha )?az\b",
            "only": r"\b(?:yalnızca|sadece|ancak)\b",
            "if": r"\b(?:eğer|şayet|koşuluyla|durumunda|halinde)\b|"
            r"\b[a-zçğıöşü]+(?:sa|se)(?:nız|niz|lar|ler)?\b",
            "before": r"\bönce\b",
            "after": r"\bsonra\b",
            "until": r"\bkadar\b",
        },
        # Affirmative destroy/count phrases; later negative verbs are retained.
        neutral=neutral_phrases((r"\byok(?=\s+(?:et|ed|say|oluş))", None)),
    ),
    "de": LanguageCues(
        re.compile(
            r"\b(?:nicht|nichts|kein\w*|nie|niemals|niemand\w*|nirgend\w*|weder|"
            r"ohne|nein|unmöglich\w*|unfähig\w*|fehlgeschlagen|unzureichend\w*|"
            r"ungenügend\w*|zu\s+wenig)\b"
        ),
        {
            "at_least": r"\b(?:mindestens|wenigstens|zumindest|minimum|minimal)\b",
            "at_most": r"\b(?:höchstens|maximal|maximum|bis zu)\b",
            "more_than": r"\b(?:mehr|über|größer|höher|oberhalb|mindestens)\b",
            "less_than": r"\b(?:weniger|unter|kleiner|niedriger|geringer|unterhalb)\b",
            "only": r"\b(?:nur|lediglich|allein|ausschließlich|bloß|erst|einzig\w*)\b",
            "if": r"\b(?:wenn|falls|sofern|ob|außer|es sei denn|solange|bei)\b",
            "before": r"\b(?:vor|bevor|zuvor|vorher|ehe)\w*\b",
            "after": r"\b(?:nach|nachdem|danach|anschließend|hinterher)\w*\b",
            "until": r"\b(?:bis|solange)\b",
        },
        source_negation=re.compile(
            r"\b(?:nicht|nichts|kein(?:e|en|em|er|es)?|nie|niemals|niemand\w*|"
            r"nirgend\w*|weder)\b"
        ),
        source_neutral=re.compile(
            r"\bnicht\s+wahr\b|\b(?:gar\s+)?nicht\s+(?:schlecht|übel|nur)\b|"
            r"\bnichts\s+zu\s+danken\b|\bkeine\s+ursache\b|\bkein\s+problem\b|"
            r"\bmacht\s+nichts\b"
        ),
    ),
    "fr": LanguageCues(
        re.compile(
            r"\b(?:pas|jamais|aucun\w*|rien|nul(?:le)?|sans|ni|guère|non(?!-)|"
            r"impossible\w*|insuffisant\w*|indisponible\w*)\b|"
            r"\b(?:ne|n['’])[^.!?]{0,40}?\b(?:plus|personne|nulle part)\b|"
            r"\bpersonne\s+(?:ne\b|n['’])"
        ),
        {
            "at_least": r"\b(?:au moins|minimum|minimal\w*)\b",
            "at_most": r"\b(?:au plus|au maximum|maximum|maximal\w*|jusqu['’])",
            "more_than": r"\b(?:plus|supérieur\w*|au-delà|davantage|dépass\w*)\b",
            "less_than": r"\b(?:moins|inférieur\w*|en dessous|au-dessous)\b",
            "only": r"\b(?:seulement|uniquement|exclusivement|seul(?:e|s|es)?)\b|"
            r"\b(?:ne|n['’])[^.!?]{0,60}?\bqu(?:e\b|['’])",
            "if": r"\b(?:si|sauf|à moins|à condition|en cas|lorsque?|quand|tant que)\b|"
            r"\bs['’]ils?\b",
            "before": r"\b(?:avant|auparavant|préalable\w*)\b",
            "after": r"\b(?:après|ensuite|puis|une fois)\b",
            "until": r"\b(?:jusqu['’]|tant que|avant)",
        },
        source_negation=re.compile(
            r"\b(?:pas|jamais|aucun(?:e|s|es)?|rien|nulle part)\b|"
            r"\bpersonne\s+(?:ne\b|n['’])"
        ),
        source_neutral=re.compile(
            r"\bn['’]est-ce\s+pas\b|\bce\s+n['’]est\s+(?:pas\s+(?:grave|mal)|rien)\b|"
            r"\bpas\s+(?:mal|de\s+(?:problème|souci|quoi))\b|\bde\s+rien\b"
        ),
    ),
    "es": LanguageCues(
        re.compile(
            r"\b(?:no|nunca|jamás|nada|nadie|ningun[oa]?|ningún|ni|sin|tampoco|"
            r"imposible\w*|insuficiente\w*|indisponible\w*)\b"
        ),
        {
            "at_least": r"\b(?:al menos|por lo menos|como mínimo|mínimo)\b",
            "at_most": r"\b(?:como máximo|a lo sumo|máximo|hasta)\b",
            "more_than": r"\b(?:más|superior\w*|mayor\w*|supera\w*|exced\w*)\b",
            "less_than": r"\b(?:menos|inferior\w*|menor\w*|por debajo)\b",
            "only": r"\b(?:solo|sólo|solamente|únicamente|exclusivamente|únic[oa]s?)\b",
            "if": r"\b(?:si|salvo|a menos|siempre que|en caso|cuando|mientras)\b",
            "before": r"\b(?:antes|previ\w*)\b",
            "after": r"\b(?:después|tras|luego)\b",
            "until": r"\b(?:hasta|mientras)\b",
        },
        source_negation=re.compile(
            r"\b(?:no|nunca|jamás|nadie|ningún|ninguna|ninguno)\b"
        ),
        # Tag questions need the opening ¿ or a comma, so "¿No puedes?" stays negative.
        source_neutral=re.compile(
            r"¿\s*no\s*\?|,\s*no\s*\?|\bno\s+pasa\s+nada\b|\bno\s+hay\s+de\s+qué\b|"
            r"\bno\s+hay\s+problema\b|\bno\s+está\s+mal\b|\bno\s+s[oó]lo\b"
        ),
    ),
    "pt": LanguageCues(
        re.compile(
            r"\b(?:não|nunca|jamais|nada|ninguém|nenhum\w*|nem|sem|tampouco|"
            r"impossível|impossíveis|insuficiente\w*|indisponível|indisponíveis)\b"
        ),
        {
            "at_least": r"\b(?:pelo menos|no mínimo|ao menos|mínimo)\b",
            "at_most": r"\b(?:no máximo|máximo|até)\b",
            "more_than": r"\b(?:mais|superior\w*|maior\w*|acima|supera\w*|exced\w*)\b",
            "less_than": r"\b(?:menos|inferior\w*|menor\w*|abaixo)\b",
            "only": r"\b(?:só|somente|apenas|unicamente|exclusivamente|únic[oa]s?)\b",
            "if": r"\b(?:se|salvo|a menos|caso|desde que|quando|enquanto)\b",
            "before": r"\b(?:antes|previ\w*)\b",
            "after": r"\b(?:depois|após|em seguida)\b",
            "until": r"\b(?:até|enquanto)\b",
        },
        source_negation=re.compile(r"\b(?:não|nunca|jamais|ninguém|nenhum|nenhuma)\b"),
        source_neutral=re.compile(
            r",\s*não\s+é(?:\s+mesmo)?\s*\?|,\s*não\s*\?|\bnão\s+(?:há|tem)\s+de\s+quê\b|"
            r"\bnão\s+(?:há|tem)\s+problema\b|\bnão\s+foi\s+nada\b|\bnão\s+faz\s+mal\b|"
            r"\bnão\s+(?:só|somente|apenas)\b"
        ),
    ),
    "ru": LanguageCues(
        # Lexical не- words are a curated list; not every не- word is a negation.
        re.compile(
            r"\b(?:не|нет|ни|никогда|ничего|ничто|никто|никого|никому|нигде|никуда|"
            r"никак\w*|нельзя|без|невозможн\w*|недостат\w*|недоступ\w*|неспособ\w*|"
            r"недопустим\w*|отсутству\w*)\b"
        ),
        {
            "at_least": r"\b(?:не менее|не меньше|минимум|как минимум|по крайней мере|"
            r"хотя бы|минимальн\w*)\b",
            "at_most": r"\b(?:не более|не больше|максимум|самое большее|до|максимальн\w*)\b",
            "more_than": r"\b(?:больше|более|свыше|выше|сверх|превыша\w*)\b",
            "less_than": r"\b(?:меньше|менее|ниже|до|не достига\w*)\b",
            "only": r"\b(?:только|лишь|исключительно|единственн\w*)\b",
            "if": r"\b(?:если|ежели|при условии|в случае|когда|кроме|разве|пока|при)\b",
            "before": r"\b(?:до|перед|прежде|раньше|сначала)\b",
            "after": r"\b(?:после|затем|потом|спустя)\b",
            "until": r"\b(?:до|пока)\b",
        },
        neutral=neutral_phrases(
            (r"\bне\s+(?:менее|меньше)\b", r"\b(?:not|no)\s+(?:less|fewer)\s+than\b"),
            (r"\bне\s+(?:более|больше)\b", r"\b(?:not|no)\s+more\s+than\b"),
            (r"\bне\s+только\b", r"\bnot\s+(?:only|just|merely)\b"),
            (r"\bне\s+раз\b", None),
        ),
        source_negation=re.compile(r"\b(?:не|нет|никогда|ничего|никто|нельзя)\b"),
        source_neutral=re.compile(
            r"\bне\s+(?:правда|так)\s+ли\b|\bне\s+за\s+что\b|"
            r"\bничего\s+(?:страшного|себе)\b|\bнет\s+проблем\b|"
            r"\bне\s+стоит\s+благодарности\b"
        ),
    ),
    # Chinese has no word spaces; compounds such as 非常 ("very") are neutralized and
    # an added negation is not flagged, because 无/不 also form affirmative words.
    "zh": LanguageCues(
        re.compile(r"[不没沒无無别別未勿莫否非]"),
        {
            "at_least": r"至少|最少|起码|起碼|不少于|不少於|以上|最低",
            "at_most": r"至多|最多|不超过|不超過|以下|上限|最高",
            "more_than": r"超过|超過|多于|多於|大于|大於|高于|高於|以上|逾|更多",
            "less_than": r"少于|少於|小于|小於|低于|低於|不足|以下|未满|未滿|更少",
            "only": r"只|仅|僅|唯|才|单|單",
            "if": r"如果|若|假如|倘若|要是|如|除非|当|當|时|時|的话|的話|则|則|只要|一旦",
            "before": r"之前|以前|前|先",
            "after": r"之后|之後|以后|以後|后|後|然后|然後|再",
            "until": r"直到|直至|为止|為止|前|才",
        },
        neutral=neutral_phrases(
            (r"不仅|不僅", r"\bnot\s+(?:only|just|merely)\b"),
            (r"不论|不論|不管|无论|無論", r"\bno\s+matter\b"),
            (r"不过|不過", r"\b(?:not|no)\s+more\s+than\b"),
            (r"非常|不断|不斷", None),
        ),
        added_negation=False,
    ),
}
# Length ratios by category: translated visible length (protected tokens and tags
# excluded, combining and format characters skipped, whitespace runs counted once,
# East Asian wide/fullwidth characters counted LENGTH_WIDE_FACTOR times) above
# source length x category ratio x target/source expansion + slack needs review.
LENGTH_WIDE_FACTOR = 2
LENGTH_RATIO_UI = 1.6
LENGTH_RATIO_DEFAULT = 2.0
LENGTH_RATIO_PROSE = 2.5
LENGTH_RATIO_LIMITS = {
    "ui": LENGTH_RATIO_UI, "default": LENGTH_RATIO_DEFAULT, "prose": LENGTH_RATIO_PROSE,
}
# Shorter sources are skipped: "OK" > "Tamam" is not a layout problem worth a warning.
LENGTH_MIN_SOURCE = {"ui": 6, "default": 10, "prose": 20}
LENGTH_SLACK = 3
# Typical expansion of each language relative to English text; others use the default.
LENGTH_EXPANSION = {
    "en": 1.0, "de": 1.35, "fr": 1.25, "es": 1.25, "pt": 1.25, "it": 1.2, "ru": 1.3,
    "uk": 1.3, "pl": 1.3, "cs": 1.2, "nl": 1.25, "fi": 1.3, "sv": 1.15, "tr": 1.15,
    "zh": 1.0, "ja": 1.0, "ko": 1.0,
}
LENGTH_EXPANSION_DEFAULT = 1.2
LENGTH_UI_WORDS = frozenset({
    "ui", "menu", "menus", "button", "buttons", "btn", "label", "labels", "interface",
    "hud", "tab", "tabs", "option", "options", "setting", "settings", "title", "titles",
    "header", "headers", "control", "controls", "keybind", "keybinds",
})
LENGTH_PROSE_WORDS = frozenset({
    "dialog", "dialogs", "dialogue", "dialogues", "conversation", "conversations",
    "subtitle", "subtitles", "description", "descriptions", "desc", "journal", "forum",
    "keypost", "lore", "story", "quest", "quests", "tutorial", "tutorials", "book",
    "books", "letter", "letters", "note", "notes", "message", "messages", "codex",
    "narration",
})
ISSUE_LABELS = {
    "literal_line_structure_mismatch": "Translation must preserve one nonempty physical line",
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
    "length_ratio_review": "Çeviri, kategorisine göre kaynaktan çok uzun olabilir: inceleyin",
}


def literal_line_valid(text: str) -> bool:
    return bool(text.strip()) and not any(c in text for c in "\r\n\x00")


def plural_branches(text: str) -> dict[str, str]:
    """Parse verified I2 Plural/One/Zero branches; the model never selects tags."""
    matches = list(PLURAL_MARKER.finditer(text))
    if "[i2" in PLURAL_MARKER.sub("", text).lower():
        raise ValueError("Unverified I2 plural format.")
    branches = {"Plural": text[: matches[0].start()] if matches else text}
    for index, match in enumerate(matches):
        form = match.group(1)
        if form in branches:
            raise ValueError("Duplicate I2 plural branch.")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        branches[form] = text[match.end() : end]
    if any(not branch.strip() for branch in branches.values()):
        raise ValueError("Empty I2 plural or text branch.")
    return branches


def join_plural_branches(branches: dict[str, str]) -> str:
    if (
        not branches
        or next(iter(branches)) != "Plural"
        or not set(branches) <= {"Plural", "One", "Zero"}
    ):
        raise ValueError("Invalid plural branch set.")
    return branches["Plural"] + "".join(
        "[i2p_" + form + "]" + text for form, text in branches.items() if form != "Plural"
    )


def issue_label(code: str) -> str:
    if code.startswith("glossary_violation:"):
        return "Sözlük karşılığı bulunamadı: " + code.split(":", 1)[1]
    return ISSUE_LABELS.get(code, code)


def primary_language(language: str) -> str:
    return language.lower().split("-")[0]


def length_class(category: str | None) -> str | None:
    """Classify a category name as ``ui``, ``prose`` or ``default`` by its words."""
    if category is None:
        return None
    words = {
        word.lower()
        for word in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", category)
    }
    if words & LENGTH_UI_WORDS:
        return "ui"
    if words & LENGTH_PROSE_WORDS:
        return "prose"
    return "default"


def visible_length(text: str) -> int:
    """Grapheme-ish visible length with East Asian wide characters weighted."""
    total = 0
    space = False
    for character in text.strip():
        if character.isspace():
            total += 0 if space else 1
            space = True
            continue
        space = False
        if unicodedata.combining(character) or unicodedata.category(character) in (
            "Mn", "Me", "Cf",
        ):
            continue
        total += (
            LENGTH_WIDE_FACTOR if unicodedata.east_asian_width(character) in ("W", "F") else 1
        )
    return total


def length_ratio_exceeded(
    source: str, translated: str, category: str | None, source_language: str,
    target_language: str,
) -> bool:
    kind = length_class(category)
    if kind is None:
        return False
    source_length = visible_length(source)
    if source_length < LENGTH_MIN_SOURCE[kind]:
        return False
    expansion = LENGTH_EXPANSION.get(
        primary_language(target_language), LENGTH_EXPANSION_DEFAULT
    ) / LENGTH_EXPANSION.get(primary_language(source_language), LENGTH_EXPANSION_DEFAULT)
    allowed = source_length * LENGTH_RATIO_LIMITS[kind] * expansion + LENGTH_SLACK
    return visible_length(translated) > allowed


def cue_issues(original: str, result: str, source_language: str, target_language: str) -> list[str]:
    """Negation and condition hints for supported pairs; other pairs are skipped."""
    source, target = primary_language(source_language), primary_language(target_language)
    issues = []
    if source == "en" and target in CUE_TABLES:
        cues = CUE_TABLES[target]
        english = original.casefold()
        translated = letter_fold(language_fold(result, target_language), target_language)
        # Flag a missing negative cue or negation added to an explicit can statement.
        # Inflectional negation does not prove absence of implicit English negation.
        english_negative = bool(EN_NEGATION.search(english))
        target_negative = cues.negative(translated, english=english)
        if (english_negative and not target_negative) or (
            cues.added_negation and not english_negative
            and re.search(r"\bcan\b", english) and target_negative
        ):
            issues.append("negation_content_review")
        if any(
            re.search(EN_CONDITIONS[name], english) and not re.search(pattern, translated)
            for name, pattern in cues.conditions.items()
        ):
            issues.append("mechanical_condition_review")
    elif target == "en" and source in CUE_TABLES and CUE_TABLES[source].source_negation:
        # Reverse direction: only strict negation, where the cue is unambiguous, after
        # removing idioms and tag questions whose English needs no negation.
        if CUE_TABLES[source].negative(
            letter_fold(language_fold(original, source_language), source_language),
            strict=True,
        ) and not EN_TARGET_NEGATION.search(result.casefold()):
            issues.append("negation_content_review")
    return issues


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
        raise ValueError("Model response exceeds the size limit.")

    payload = strict_json(raw)
    envelope = Envelope.model_validate(payload)
    ids = [item.id for item in envelope.translations]
    if len(set(ids)) != len(ids) or set(ids) != expected:
        raise ValueError("Record IDs in the model response are not a complete and unique match.")
    if any(not item.text.strip() for item in envelope.translations):
        raise ValueError("Empty translations are not accepted.")
    return {item.id: item.text for item in envelope.translations}


def check_format(text: str) -> None:
    for branch in plural_branches(text).values():
        check_plain_format(branch)


def check_plain_format(text: str) -> None:
    if "__UT_" in text:
        raise ValueError("Conflict with the protected token prefix.")
    remainder = TOKEN.sub("", text)
    if any(character in remainder for character in "{}<>") or "[i2" in text.lower():
        raise ValueError("Unknown protected format; a reader rule is required.")
    stack: list[str] = []
    for match in TOKEN.finditer(text):
        token = match.group()
        if token in ("<", ">") or token.startswith("<sprite ") or not token.startswith("<"):
            continue
        attribute = re.sub(PARAMETER, "", token)
        if "{" in attribute or "}" in attribute:
            raise ValueError("Unknown variable format inside a tag.")
        name = re.split(r"[=>]", token.lstrip("</"))[0]
        if "=" in token and (token.startswith("</") or name in ("b", "i")):
            raise ValueError("Unsupported tag parameter.")
        if token.startswith("</"):
            if not stack or stack.pop() != name:
                raise ValueError("Unbalanced or misordered tags.")
        else:
            stack.append(name)
    if stack:
        raise ValueError("Unclosed tag.")


@dataclass(frozen=True)
class MaskedText:
    text: str
    replacements: dict[str, str]
    rules: str = PROTECTED_FORMAT_VERSION

    def restore(self, translated: str) -> str:
        if self.rules not in (PROTECTED_FORMAT_VERSION, LITERAL_LINE_FORMAT, *RENPY_FORMATS):
            raise ValueError("Unknown source format rules.")
        if self.rules in RENPY_FORMATS:
            printf = self.rules == RENPY_STRING_FORMAT
            if Counter(MARKER.findall(translated)) != Counter(self.replacements.keys()):
                raise ValueError("Missing, duplicate or damaged Ren'Py protection marker.")
            for marker, original in self.replacements.items():
                translated = translated.replace(marker, original)
            source = self.text
            for marker, original in self.replacements.items():
                source = source.replace(marker, original)
            if not renpy_format_matches(source, translated, printf=printf):
                raise ValueError("Ren'Py interpolation, tag, escape or format tokens changed.")
            return translated
        if self.rules == LITERAL_LINE_FORMAT:
            if not literal_line_valid(translated) or "__UT_" in translated:
                raise ValueError("Literal translation must remain one nonempty physical line.")
            return translated
        if len(plural_branches(translated)) != 1:
            raise ValueError("A new plural tag cannot be added to a single branch.")
        found = Counter(MARKER.findall(translated))
        if found != Counter(self.replacements.keys()):
            raise ValueError("Missing, extra or damaged protected token.")
        for marker, original in self.replacements.items():
            translated = translated.replace(marker, original)
        if "__UT_" in translated:
            raise ValueError("Unknown or damaged protection marker.")
        check_format(translated)
        if Counter(TOKEN.findall(translated)) != Counter(self.replacements.values()):
            raise ValueError("Restored variables or tags do not match the source.")
        return translated


def mask(text: str, *, rules: str = PROTECTED_FORMAT_VERSION) -> MaskedText:
    if rules in RENPY_FORMATS:
        prefix = uuid4().hex[:8]
        renpy_replacements: dict[str, str] = {}
        output: list[str] = []
        cursor = 0
        for token in renpy_tokens(text, printf=rules == RENPY_STRING_FORMAT):
            marker = f"__UT_{prefix}_{len(renpy_replacements)}__"
            renpy_replacements[marker] = token.text
            output.extend((text[cursor:token.start], marker))
            cursor = token.end
        output.append(text[cursor:])
        return MaskedText("".join(output), renpy_replacements, rules)
    if rules == LITERAL_LINE_FORMAT:
        if not literal_line_valid(text) or "__UT_" in text:
            raise ValueError("Unsupported literal source line.")
        return MaskedText(text, {}, rules)
    if rules != PROTECTED_FORMAT_VERSION:
        raise ValueError("Unknown source format rules.")
    check_format(text)
    if len(plural_branches(text)) != 1:
        raise ValueError("Plural text must be masked by branch.")
    if "__UT_" in text:
        raise ValueError("Source conflicts with the protected token prefix.")
    prefix = uuid4().hex[:8]
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        marker = f"__UT_{prefix}_{len(replacements)}__"
        replacements[marker] = match.group()
        return marker

    return MaskedText(TOKEN.sub(replace, text), replacements)


def unprotected_text(text: str, rules: str = PROTECTED_FORMAT_VERSION) -> str:
    """Text with protected tokens, tags and plural markers replaced by spaces.

    Uses the same token grammar as the review cues: I2 tokens for the protected
    format, Ren'Py tokens for Ren'Py rules, nothing for literal lines. Text that the
    Ren'Py grammar rejects, or unknown rules, are returned unchanged.
    """
    if rules == PROTECTED_FORMAT_VERSION:
        return TOKEN.sub(" ", PLURAL_MARKER.sub(" ", text))
    if rules in RENPY_FORMATS:
        try:
            return renpy_visible_text(text, printf=rules == RENPY_STRING_FORMAT)
        except ValueError:
            return text
    return text


def review_issues(
    source: str, translated: str, *, source_language: str = "en", target_language: str = "tr",
    rules: str = PROTECTED_FORMAT_VERSION, category: str | None = None,
) -> list[str]:
    """Numeric, cue and length hints (REVIEW_CHECKS_VERSION); not semantic or approval proof.

    Length ratios need the record's ``category``; without it they are skipped.
    """
    if rules not in (PROTECTED_FORMAT_VERSION, LITERAL_LINE_FORMAT, *RENPY_FORMATS):
        return ["unsupported_format"]
    try:
        if rules in (LITERAL_LINE_FORMAT, *RENPY_FORMATS):
            original_branches, target_branches = {"Plural": source}, {"Plural": translated}
        else:
            original_branches = plural_branches(source)
            target_branches = plural_branches(translated)
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
                        rules=rules,
                        category=category,
                    )
                )
        return sorted(branch_issues)
    issues = []
    if source.strip() == translated.strip():
        issues.append("unchanged_source")
    # Tag parameters and placeholder identifiers are not numeric content.
    original_text, result_text = (
        (source, translated) if rules == LITERAL_LINE_FORMAT
        else (TOKEN.sub(" ", source), TOKEN.sub(" ", translated))
    )
    if rules in RENPY_FORMATS:
        printf = rules == RENPY_STRING_FORMAT
        try:
            original_text, result_text = (
                renpy_visible_text(source, printf=printf),
                renpy_visible_text(translated, printf=printf),
            )
        except ValueError:
            return ["unsupported_or_unbalanced_format"]
    if numeric_mismatch(original_text, result_text, source_language, target_language):
        issues.append("numeric_content_review")
    if percentages(original_text.casefold(), source_language) != percentages(
        turkish_lower(result_text), target_language
    ):
        issues.append("percentage_content_review")
    issues.extend(cue_issues(original_text, result_text, source_language, target_language))
    if length_ratio_exceeded(
        original_text, result_text, category, source_language, target_language,
    ):
        issues.append("length_ratio_review")
    return issues


def format_issues(
    source: str, translated: str, *, rules: str = PROTECTED_FORMAT_VERSION
) -> list[str]:
    if rules in RENPY_FORMATS:
        try:
            return [] if renpy_format_matches(
                source, translated, printf=rules == RENPY_STRING_FORMAT
            ) else ["protected_content_mismatch"]
        except ValueError:
            return ["unsupported_or_unbalanced_format"]
    if rules == LITERAL_LINE_FORMAT:
        return [] if literal_line_valid(source) and literal_line_valid(translated) else [
            "literal_line_structure_mismatch"
        ]
    if rules != PROTECTED_FORMAT_VERSION:
        return ["unsupported_format"]
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
