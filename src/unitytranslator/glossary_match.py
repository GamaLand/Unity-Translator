"""Language-aware glossary term patterns, compiled once and cached per term.

Source terms match their written form with word boundaries. Target terms of a
``preferred_translation`` additionally accept a fixed, per-language inflection
allowance: a closed list of endings after the written form or after a documented
stem change. Both edges are word boundaries after any allowed ending, so a term never
matches inside a longer word that merely starts or ends with it unless the remainder
is one of the listed endings. ``preserve_name`` targets are verbatim: the written
characters with their case and no stem change; only the language's endings may follow.

Inflection rules by target language (primary subtag; lowercase, language-folded text):

* ``tr``: Turkish inflection is agglutinative; only the last word of a term inflects.
  After an optional apostrophe the allowance is the chain plural (-lAr), possessive
  (-(I)m, -(I)n, -(s)I, -(I)mIz, -(I)nIz, -lArI), case (-(y)I, -(y)A, -(n)DA(n), -(n)In,
  -(y)lA, -nA, -nI), relative -ki and copula -DIr, each optional, where A is a/e, I is
  ı/i/u/ü and D is d/t. A final p, ç, t or k of a word of at least four letters may
  soften to b, c, d or ğ/g before a vowel-initial ending (kitap > kitabı, renk > rengi).
  A two-syllable word of at least four letters whose last vowel is a high vowel between
  consonants may drop it before a vowel-initial ending (şehir > şehre, isim > ismi,
  ağız > ağzı, oğul > oğlu, burun > burnu). The last word of a multi-word term that
  ends in a third-person possessive -(s)I/-yI (an izafet compound such as Ateş Topu,
  Can İksiri or Şifa Şişesi) may replace it with the plural possessive -lArI and any
  case ending (Ateş Topları'nı, Can İksirleri); an adjective compound ending in I
  (Demir Kapı) is therefore also accepted as Demir Kapları. Vowel harmony is not
  enforced; derivational suffixes such as -CI and -lIk form different words and do
  not match. Turkish casing (I/ı, İ/i) is applied by folding.
* ``fi``: each word may take an optional plural i/j, one case ending (-n, -t, -A, -tA,
  -ssA, -stA, -llA, -ltA, -lle, -nA, -ksi, -ttA, -ine, -hVn, -Vn, -seen, -siin), a
  possessive (-ni, -si, -mme, -nne, -nsA, -Vn) and a clitic (-kin, -kAAn, -kO, -pA,
  -han, -hän). Consonant gradation (kk > k) is not tolerated.
* ``de``: each word may take -e, -en, -n, -er, -ern, -es, -s, -ens or -nen. Umlaut
  plurals, a changed adjective ending (roter > roten) and compounds (Eisenschwert
  for Schwert) are not tolerated.
* ``ru``, ``uk``, ``be``: ё and е are the same letter in both the term and the text.
  Each word may take one listed case ending after the written form, after the word
  without a final adjective ending (-ый, -ий, -ой, -ая, -яя, -ое, -ее, -ые, -ие) when at
  least five letters long, or after the word without one final vowel, soft or short
  sign; both stems are tried, so nouns with adjective-like endings (заклинание >
  заклинанием, герой > героя, гений > гения) match. Endings include the soft-stem
  instrumental -ей/-ёй/-ею/-ью (земля > землёй, дверь > дверью). Fleeting vowels
  (отец > отца) are not tolerated.
* ``fr``: each word may take -s, -x, -e or -es (château > châteaux, jeu > jeux); a
  final -al may become -aux (cheval > chevaux).
* ``es``: each word may take -s or -es. A final stressed -ión, -ón, -án, -ín, -én,
  -ún or -és loses its accent before -es (poción > pociones, dragón > dragones,
  inglés > ingleses) and a final -z becomes -ces (luz > luces).
* ``pt``: each word may take -s or -es. A final -ão may become -ões, -ães or -ãos
  (poção > poções, pão > pães), -m becomes -ns (item > itens), -al and -ul take -is
  (animal > animais, azul > azuis), -el becomes -éis/-eis (papel > papéis, nível >
  níveis), -ol becomes -óis/-ois (farol > faróis), -il becomes -is/-eis (barril >
  barris, fóssil > fósseis) and -ês becomes -eses (mês > meses).
* ``ca``, ``gl``: each word may take -s or -es.
* ``it``: a final vowel of each word may change to a, e, i or o, or to -he/-hi.
* ``en``: each word may take -s, -es or 's; a final y may become -ies.
* ``zh``, ``ja``, ``ko``, ``th``, ``lo``, ``km``, ``my``: scripts without spaces between
  words (or with attached particles) match as substrings on both sides.
* Every other language matches the written form with word boundaries, as before.
"""

import re
import unicodedata
from functools import lru_cache

from unitytranslator.language import language_fold

UNSPACED_LANGUAGES = frozenset({"zh", "ja", "ko", "th", "lo", "km", "my"})
# Languages whose texts may write ё as е; both are folded to е before matching.
YO_LANGUAGES = frozenset({"ru", "uk", "be"})

_TR_A = "[ae]"
_TR_I = "[ıiuü]"
TURKISH_ENDINGS = (
    r"(?:['’])?"
    rf"(?:l{_TR_A}r)?"
    rf"(?:{_TR_I}?m(?:{_TR_I}z)?|{_TR_I}?n(?:{_TR_I}z)?|s?{_TR_I}|l{_TR_A}r{_TR_I})?"
    rf"(?:y?{_TR_I}|y?{_TR_A}|n?[dt]{_TR_A}n?|n?{_TR_I}n|y?l{_TR_A}|n{_TR_A}|n{_TR_I})?"
    rf"(?:ki(?:n{_TR_I}|n{_TR_A}|nd{_TR_A}n?|l{_TR_A}r)?)?"
    rf"(?:[dt]{_TR_I}r)?"
)
TURKISH_SOFTENING = {"p": "b", "ç": "c", "t": "d", "k": "[ğg]"}
TURKISH_VOWELS = "aeıioöuüâîû"
TURKISH_HIGH_VOWELS = "ıiuü"
TURKISH_VOWEL = "[aeıioöuü]"
_FI_V = "[aeiouyäö]"
FINNISH_ENDINGS = (
    r"(?:[ij])?"
    r"(?:n|t|[aä]|t[aä]|ss[aä]|st[aä]|ll[aä]|lt[aä]|lle|n[aä]|ksi|tt[aä]|ine|"
    rf"h{_FI_V}n|{_FI_V}n|seen|siin)?"
    rf"(?:ni|si|mme|nne|ns[aä]|{_FI_V}n)?"
    r"(?:kin|k[aä][aä]n|k[oö]|p[aä]|han|hän)?"
)
GERMAN_ENDINGS = r"(?:e|en|n|er|ern|es|s|ens|nen)?"
SLAVIC_ENDINGS = (
    r"(?:а|я|о|е|ё|и|ы|у|ю|ь|й|і|ї|ой|ей|ёй|ою|ею|ёю|ью|ом|ем|ём|ам|ям|ами|ями|ах|ях|"
    r"ов|ев|ёв|ів|ові|еві|ий|ый|ая|яя|ое|ее|ые|ие|ую|юю|ого|его|ому|ему|ым|им|ых|их|"
    r"ыми|ими)?"
)
SLAVIC_ADJECTIVE = ("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие")
SLAVIC_FINAL = "аяоеёьйыиіїу"
FRENCH_ENDINGS = r"(?:s|x|e|es)?"
IBERIAN_ENDINGS = r"(?:s|es)?"
# Spanish final stressed vowels that lose their accent before the plural -es.
SPANISH_ACCENT_PLURAL = "áéíóú"
# Portuguese plurals that replace a word's last letters, in order of precedence:
# (written ending, letters of it kept, replacement endings).
PORTUGUESE_PLURALS = (
    ("ão", 0, r"(?:ões|ães|ãos)"),
    ("ês", 0, r"eses"),
    ("al", 1, r"is"),
    ("ul", 1, r"is"),
    ("el", 0, r"(?:éis|eis)"),
    ("ol", 0, r"(?:óis|ois)"),
    ("il", 0, r"(?:is|eis)"),
    ("m", 0, r"ns"),
)
ENGLISH_ENDINGS = r"(?:s|es|['’]s)?"
# Languages whose multi-word terms inflect only in their last word.
LAST_WORD_ONLY = frozenset({"tr", "az"})


def primary(language: str) -> str:
    return language.split("-")[0].lower()


def _unaccented(character: str) -> str:
    return unicodedata.normalize("NFD", character)[0]


def _turkish_dropped(word: str) -> str | None:
    """The stem of a two-syllable word that drops its last high vowel (şehir > şehr)."""
    lower = word.lower()
    if (
        len(word) >= 4
        and sum(character in TURKISH_VOWELS for character in lower) == 2
        and lower[-1].isalpha() and lower[-1] not in TURKISH_VOWELS
        and lower[-2] in TURKISH_HIGH_VOWELS
        and lower[-3].isalpha() and lower[-3] not in TURKISH_VOWELS
    ):
        return word[:-2] + word[-1]
    return None


def _turkish_possessive_stem(word: str) -> str | None:
    """A compound's last word without its possessive -(s)I/-yI (topu > top)."""
    lower = word.lower()
    if len(word) < 3 or lower[-1] not in TURKISH_HIGH_VOWELS:
        return None
    if lower[-2] in "sy" and lower[-3] in TURKISH_VOWELS:
        return word[:-2]
    if lower[-2].isalpha() and lower[-2] not in TURKISH_VOWELS:
        return word[:-1]
    return None


def _word(
    word: str, language: str, *, inflect: bool, verbatim: bool, exact_case: bool,
    compound: bool = False,
) -> str:
    """Pattern for one word of a term: its written form plus the allowed endings."""
    written = re.escape(word)
    if not inflect or not word or not word[-1].isalpha():
        return written

    def _endings(endings: str) -> str:
        # A case-sensitive or verbatim term keeps its own case; endings follow the text.
        return "(?i:" + endings + ")" if exact_case else endings

    def _any(forms: list[str]) -> str:
        return forms[0] if len(forms) == 1 else "(?:" + "|".join(forms) + ")"

    if language in ("tr", "az"):
        stems = [written]
        vowel_initial = _endings(f"(?={TURKISH_VOWEL})")
        if not verbatim and len(word) >= 4 and word[-1] in TURKISH_SOFTENING:
            stems.append(re.escape(word[:-1]) + TURKISH_SOFTENING[word[-1]] + vowel_initial)
        dropped = None if verbatim else _turkish_dropped(word)
        if dropped is not None:
            stems.append(re.escape(dropped) + vowel_initial)
        forms = ["(?:" + "|".join(stems) + ")" + _endings(TURKISH_ENDINGS)]
        possessive = _turkish_possessive_stem(word) if compound and not verbatim else None
        if possessive is not None:
            forms.append(
                re.escape(possessive) + _endings(f"l{_TR_A}r{_TR_I}" + TURKISH_ENDINGS)
            )
        return _any(forms)
    if language == "fi":
        return written + _endings(FINNISH_ENDINGS)
    if language == "de":
        return written + _endings(GERMAN_ENDINGS)
    if language in ("ru", "uk", "be"):
        if verbatim:
            return written + _endings(SLAVIC_ENDINGS)
        stems = [written]
        # Both stems: nouns such as заклинание or герой end like adjectives.
        if len(word) >= 5 and word.lower().endswith(SLAVIC_ADJECTIVE):
            stems.append(re.escape(word[:-2]))
        if len(word) >= 3 and word[-1].lower() in SLAVIC_FINAL:
            stems.append(re.escape(word[:-1]))
        return "(?:" + "|".join(stems) + ")" + _endings(SLAVIC_ENDINGS)
    if language == "fr":
        forms = [written + _endings(FRENCH_ENDINGS)]
        if not verbatim and len(word) >= 4 and word[-2:].lower() == "al":
            forms.append(re.escape(word[:-2]) + _endings("aux"))
        return _any(forms)
    if language == "es":
        forms = [written + _endings(IBERIAN_ENDINGS)]
        if not verbatim and len(word) >= 3:
            last, vowel = word[-1].lower(), word[-2].lower()
            if last in "ns" and vowel in SPANISH_ACCENT_PLURAL:
                forms.append(
                    re.escape(word[:-2] + _unaccented(word[-2]) + word[-1]) + _endings("es")
                )
            if last == "z":
                forms.append(re.escape(word[:-1]) + _endings("ces"))
        return _any(forms)
    if language == "pt":
        forms = [written + _endings(IBERIAN_ENDINGS)]
        if not verbatim and len(word) >= 3:
            for ending, kept, plural in PORTUGUESE_PLURALS:
                if word.lower().endswith(ending):
                    stem = word[: len(word) - len(ending) + kept]
                    forms.append(re.escape(stem) + _endings(plural))
                    break
        return _any(forms)
    if language in ("ca", "gl"):
        return written + _endings(IBERIAN_ENDINGS)
    if language == "it":
        if verbatim or len(word) < 3 or word[-1] not in "aeio":
            return written
        return "(?:" + written + "|" + re.escape(word[:-1]) + _endings("(?:[aeio]|h[ei])") + ")"
    if language == "en":
        stems_pattern = written
        if not verbatim and len(word) >= 3 and word[-1] == "y":
            stems_pattern = "(?:" + written + "|" + re.escape(word[:-1]) + "ies)"
        return stems_pattern + _endings(ENGLISH_ENDINGS)
    return written


@lru_cache(maxsize=16384)
def term_pattern(
    term: str, language: str, *, inflect: bool, word_boundary: bool, verbatim: bool = False,
    exact_case: bool = False,
) -> re.Pattern[str]:
    """Compile one term; the text searched must be folded the same way as ``term``."""
    language = primary(language)
    unspaced = language in UNSPACED_LANGUAGES
    if not word_boundary or unspaced:
        return re.compile(re.escape(term))
    parts = re.split(r"(\s+)", term.strip())
    words = parts[::2]
    last = len(words) - 1
    pieces = []
    for index, word in enumerate(words):
        allowed = inflect and (language not in LAST_WORD_ONLY or index == last)
        pieces.append(_word(
            word, language, inflect=allowed, verbatim=verbatim, exact_case=exact_case,
            compound=index == last and last > 0,
        ))
    return re.compile(r"(?<!\w)" + r"\s+".join(pieces) + r"(?!\w)")


def letter_fold(text: str, language: str) -> str:
    """Length-preserving spelling equivalences of a language (Russian ё is е)."""
    if primary(language) in YO_LANGUAGES:
        return text.replace("ё", "е").replace("Ё", "Е")
    return text


def fold(text: str, language: str, case_sensitive: bool) -> str:
    """Fold for matching: language casing unless case-sensitive, then ``letter_fold``."""
    return letter_fold(text if case_sensitive else language_fold(text, language), language)
