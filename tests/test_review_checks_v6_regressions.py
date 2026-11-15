"""review-multilingual-v6 regressions: inflection gaps, lexical negatives and idioms."""

import pytest

from unitytranslator.glossary_match import fold
from unitytranslator.policy import CompiledGlossary, GlossaryRule
from unitytranslator.validation import review_issues


def preferred(source: str, target: str, **values: object) -> GlossaryRule:
    return GlossaryRule(source=source, target=target, kind="preferred_translation", **values)


def matches(language: str, term: str, text: str) -> bool:
    return preferred("Term", term).matches(text, "UI", target=True, language=language)


def negation(source: str, target: str, **languages: str) -> bool:
    return "negation_content_review" in review_issues(source, target, **languages)


@pytest.mark.parametrize(
    "term,text",
    [
        ("заклинание", "Произнеси заклинания"),
        ("заклинание", "Удар заклинанием"),
        ("заклинание", "В заклинании"),
        ("оружие", "Без оружия"),
        ("оружие", "Владеет оружием"),
        ("задание", "Выполни задания"),
        ("задание", "О задании"),
        ("умение", "Новыми умениями"),
        ("герой", "Сила героя"),
        ("герой", "Стать героем"),
        ("герой", "Помоги героям"),
        ("гений", "Мысли гения"),
        ("гений", "Стать гением"),
        # Adjectives keep their adjective stem.
        ("железный меч", "с железным мечом"),
    ],
)
def test_russian_nouns_with_adjective_like_endings_inflect(term: str, text: str) -> None:
    assert matches("ru", term, text)


@pytest.mark.parametrize(
    "language,term,text",
    [
        ("ru", "ёлка", "Под елкой"),  # ё in the term, е in the text
        ("ru", "елка", "Под ёлкой"),  # е in the term, ё in the text
        ("ru", "Ёж", "Два ежа"),
        ("ru", "земля", "Под землёй"),
        ("ru", "земля", "Под землей"),
        ("ru", "дверь", "За дверью"),
        ("uk", "земля", "Під землею"),
    ],
)
def test_russian_yo_folding_and_soft_stem_instrumental(
    language: str, term: str, text: str,
) -> None:
    assert matches(language, term, text)
    assert fold("Ёлка", "ru", False) == "елка"
    assert fold("Ёлка", "ru", True) == "Елка"
    assert fold("Ёlka", "de", False) == "ёlka"


@pytest.mark.parametrize(
    "language,term,text",
    [
        ("es", "poción", "Dos pociones"),
        ("es", "misión", "Misiones diarias"),
        ("es", "dragón", "Los dragones"),
        ("es", "botón", "Pulsa los botones"),
        ("es", "capitán", "Los capitanes"),
        ("es", "jardín", "Los jardines"),
        ("es", "inglés", "Los ingleses"),
        ("es", "luz", "Las luces"),
        ("es", "poción", "Una poción"),
        ("pt", "poção", "Duas poções"),
        ("pt", "missão", "Missões diárias"),
        ("pt", "dragão", "Os dragões"),
        ("pt", "pão", "Os pães"),
        ("pt", "mão", "As mãos"),
        ("pt", "item", "Novos itens"),
        ("pt", "animal", "Os animais"),
        ("pt", "papel", "Os papéis"),
        ("pt", "nível", "Dois níveis"),
        ("pt", "farol", "Os faróis"),
        ("pt", "azul", "Olhos azuis"),
        ("pt", "barril", "Os barris"),
        ("pt", "mês", "Dois meses"),
        ("fr", "cheval", "Les chevaux"),
        ("fr", "animal", "Les animaux"),
        ("fr", "château", "Les châteaux"),
        ("fr", "bateau", "Deux bateaux"),
    ],
)
def test_iberian_and_french_stem_changing_plurals(language: str, term: str, text: str) -> None:
    assert matches(language, term, text)


@pytest.mark.parametrize(
    "language,term,text",
    [
        ("es", "luz", "Lucero"),
        ("es", "botón", "Botonera"),
        ("pt", "item", "Itensivo"),
        ("pt", "animal", "Animaizinhos"),
        ("fr", "cheval", "Chevauchée"),
    ],
)
def test_stem_changing_plurals_do_not_match_longer_words(
    language: str, term: str, text: str,
) -> None:
    assert not matches(language, term, text)


@pytest.mark.parametrize(
    "term,text",
    [
        ("şehir", "Şehre git"),
        ("şehir", "Şehrin kapısı"),
        ("şehir", "Şehir"),
        ("isim", "İsmini yaz"),
        ("nehir", "Nehri geç"),
        ("ağız", "Ağzını kapat"),
        ("oğul", "Oğlu geldi"),
        ("burun", "Burnu kanadı"),
        ("Ateş Topu", "Ateş Topları"),
        ("Ateş Topu", "Ateş Topları'nı fırlat"),
        ("Ateş Topu", "Ateş Topunu fırlat"),
        ("Can İksiri", "Can İksirleri"),
        ("Can İksiri", "Can İksirlerini iç"),
        ("Şifa Şişesi", "Şifa Şişeleri"),
    ],
)
def test_turkish_vowel_drop_and_compound_plurals(term: str, text: str) -> None:
    assert matches("tr", term, text)


@pytest.mark.parametrize(
    "term,text",
    [
        ("ok", "Okul kapandı"),
        ("demir", "Demirci geldi"),
        ("şehir", "Şehr"),  # the dropped stem needs a vowel-initial ending
        ("şehir", "Şehrler"),
        ("isim", "İsmler"),
        ("kapı", "Kaplar"),  # a single word is not a possessive compound
        ("Ateş Topu", "Ateş Toplar"),
    ],
)
def test_turkish_inflection_refusals(term: str, text: str) -> None:
    assert not matches("tr", term, text)


@pytest.mark.parametrize(
    "language,source,target",
    [
        ("de", "Not enough gold", "Zu wenig Gold"),
        ("de", "Not available", "Nicht verfügbar"),
        ("de", "Unable to save", "Speichern fehlgeschlagen"),
        ("de", "Unable to save", "Speichern nicht möglich"),
        ("de", "Unable to save", "Speichern unmöglich"),
        ("de", "Not enough gold", "Unzureichendes Gold"),
        ("fr", "Not enough gold", "Or insuffisant"),
        ("fr", "Not available", "Indisponible"),
        ("fr", "Unable to save", "Impossible d'enregistrer"),
        ("fr", "No items", "Aucun objet"),
        ("es", "Not enough gold", "Oro insuficiente"),
        ("es", "Not available", "No disponible"),
        ("es", "Unable to save", "Imposible guardar"),
        ("pt", "Not enough gold", "Ouro insuficiente"),
        ("pt", "Not available", "Indisponível"),
        ("pt", "Unable to save", "Impossível salvar"),
        ("ru", "Not enough gold", "Недостаточно золота"),
        ("ru", "Not available", "Недоступно"),
        ("ru", "Not available", "Недоступен"),
        ("ru", "Unable to save", "Невозможно сохранить"),
        ("ru", "Unable to save", "Нельзя сохранить"),
        ("ru", "Unable to attack", "Неспособен атаковать"),
    ],
)
def test_lexical_negatives_count_as_negation(language: str, source: str, target: str) -> None:
    assert not negation(source, target, target_language=language)


@pytest.mark.parametrize(
    "language,target",
    [
        ("tr", "Kimse giremez"),
        ("de", "Niemand kann eintreten"),
        ("fr", "Personne ne peut entrer"),
        ("fr", "Personne n'entre"),
        ("es", "Nadie puede entrar"),
        ("pt", "Ninguém pode entrar"),
        ("ru", "Никто не может войти"),
        ("ru", "Никто"),
    ],
)
def test_nobody_is_negative_in_both_languages(language: str, target: str) -> None:
    assert not negation("Nobody can enter", target, target_language=language)
    assert not negation("No one can enter", target, target_language=language)


def test_nobody_still_flags_a_dropped_negation_and_reverse_personne() -> None:
    assert negation("Nobody can enter", "Tout le monde peut entrer", target_language="fr")
    assert negation("Nobody can enter", "Jeder kann eintreten", target_language="de")
    assert negation(
        "Personne ne bouge", "Everyone moves", source_language="fr", target_language="en",
    )
    assert not negation(
        "Personne ne bouge", "Nobody moves", source_language="fr", target_language="en",
    )


@pytest.mark.parametrize(
    "language,source,target",
    [
        ("fr", "C'est beau, n'est-ce pas ?", "It's beautiful, right?"),
        ("fr", "Ce n'est pas grave.", "It's fine."),
        ("fr", "Pas de problème.", "Sure."),
        ("fr", "De rien.", "You're welcome."),
        ("de", "Schön, nicht wahr?", "Nice, right?"),
        ("de", "Nicht schlecht!", "Pretty good!"),
        ("de", "Keine Ursache.", "You're welcome."),
        ("es", "Bonito, ¿no?", "Pretty, right?"),
        ("es", "No pasa nada.", "It's okay."),
        ("es", "No hay de qué.", "You're welcome."),
        ("pt", "Bonito, não é?", "Pretty, right?"),
        ("pt", "Não há de quê.", "You're welcome."),
        ("pt", "Não foi nada.", "It was nothing much."),
        ("ru", "Красиво, не правда ли?", "Beautiful, right?"),
        ("ru", "Не за что.", "You're welcome."),
        ("ru", "Ничего страшного.", "It's fine."),
        ("ru", "Не только огонь, но и лёд.", "Both fire and ice."),
    ],
)
def test_reverse_direction_ignores_idioms_and_tag_questions(
    language: str, source: str, target: str,
) -> None:
    assert not negation(source, target, source_language=language, target_language="en")


@pytest.mark.parametrize(
    "language,source,target",
    [
        ("fr", "Il ne bouge pas, n'est-ce pas ?", "He moves, right?"),
        ("fr", "Ce n'est pas grave, mais il ne bouge pas.", "It's fine, he moves."),
        ("de", "Er bewegt sich nicht, nicht wahr?", "He moves, right?"),
        ("es", "No se mueve, ¿no?", "It moves, right?"),
        ("es", "¿No puedes moverte?", "Can you move?"),
        ("pt", "Não se move, não é?", "It moves, right?"),
        ("ru", "Он не двигается, не правда ли?", "He moves, right?"),
        ("ru", "Ничего не вышло.", "It worked."),
    ],
)
def test_reverse_direction_still_flags_a_dropped_negation(
    language: str, source: str, target: str,
) -> None:
    assert negation(source, target, source_language=language, target_language="en")


@pytest.mark.parametrize(
    "language,source,target",
    [
        ("ru", "Not only fire", "Не только огонь"),
        ("ru", "No more than 3 points", "Не более 3 очков"),
        ("ru", "Not less than 3 points", "Не менее 3 очков"),
        ("zh", "Not only fire", "不仅是火"),
        ("zh", "No matter what, attack", "无论如何都要攻击"),
    ],
)
def test_neutral_look_alikes_stay_negative_for_matching_english_idioms(
    language: str, source: str, target: str,
) -> None:
    assert not negation(source, target, target_language=language)


def test_neutral_look_alikes_are_still_removed_otherwise() -> None:
    # Affirmative English: the look-alike is not an added negation.
    assert not negation("Can deal at least 3 damage", "Может нанести не менее 3 урона",
                        target_language="ru")
    assert not negation("Can be very strong", "可以非常强", target_language="zh")
    # A negative English sentence still needs a real negation besides the look-alike.
    assert negation("Cannot deal at least 3 damage", "Может нанести не менее 3 урона",
                    target_language="ru")
    assert negation("Not fire, only ice", "Не только огонь", target_language="ru")
    assert negation("Not fire, only ice", "不仅是火", target_language="zh")


@pytest.mark.parametrize(
    "language,target",
    [
        ("de", "Der einzige Weg"),
        ("es", "El único camino"),
        ("es", "La única salida"),
        ("pt", "O único caminho"),
        ("pt", "A única saída"),
    ],
)
def test_adjectival_only_is_a_condition_cue(language: str, target: str) -> None:
    issues = review_issues("The only way", target, target_language=language)
    assert "mechanical_condition_review" not in issues


def test_adjectival_only_still_flags_a_missing_cue() -> None:
    assert "mechanical_condition_review" in review_issues(
        "The only way", "El camino", target_language="es"
    )


def test_glossary_ignores_terms_inside_protected_tokens() -> None:
    iron = CompiledGlossary([preferred("Iron", "Demir")], "en", "tr")
    red = CompiledGlossary([preferred("red", "kırmızı")], "en", "tr")
    # A term only inside a tag or placeholder is not relevant.
    assert red.relevant("<color=red>Hit</color>", "UI") == []
    assert red.violations("<color=red>Hit</color>", "<color=red>Vur</color>", "UI") == []
    assert iron.relevant("Hit {Iron}", "UI") == []
    assert iron.relevant("Iron[i2p_One]One Iron", "UI") != []
    # A target term only inside a placeholder does not satisfy the rule.
    assert [r.source for r in iron.violations(
        "Iron shield {demir}", "Çelik kalkan {demir}", "UI",
    )] == ["Iron"]
    assert iron.violations("Iron shield {demir}", "Demir kalkan {demir}", "UI") == []
    # Preserved names are checked on the masked texts too.
    mars = CompiledGlossary(
        [GlossaryRule(source="Mars", target="Mars", kind="preserve_name")], "en", "tr",
    )
    assert [r.source for r in mars.violations(
        "Fly to Mars {Mars}", "Uç {Mars}", "UI",
    )] == ["Mars"]


def test_glossary_masking_follows_format_rules() -> None:
    sword = CompiledGlossary([preferred("sword", "kılıç")], "en", "tr")
    color = CompiledGlossary([preferred("color", "renk")], "en", "tr")
    # Ren'Py interpolation and tags are protected under Ren'Py rules only.
    assert sword.relevant("Take [sword] now", "UI", format_rules="renpy-text-v1") == []
    assert sword.relevant("Take [sword] now", "UI") != []
    assert color.relevant("{color=#f00}Hi{/color}", "UI", format_rules="renpy-text-v2") == []
    # Literal lines have no protected tokens: everything is visible text.
    assert color.relevant("<color=red>", "UI", format_rules="literal-lines-v1") != []
    assert color.relevant("<color=red>", "UI") == []
    assert [r.source for r in sword.violations(
        "Take [sword] and a sword", "[sword] ve bir balta al", "UI",
        format_rules="renpy-text-v1",
    )] == ["sword"]
