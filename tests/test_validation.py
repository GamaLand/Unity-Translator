import json
from pathlib import Path

import pytest

from unitytranslator.validation import (
    format_issues,
    issue_label,
    mask,
    numeric_value,
    parse_reply,
    plural_branches,
    review_issues,
)


@pytest.mark.parametrize(
    "case",
    json.loads(
        (Path(__file__).parent / "fixtures/protected-format-v4.json").read_text(encoding="utf-8")
    ),
)
def test_shared_python_and_csharp_protected_format_cases(case) -> None:
    assert (not format_issues(case["source"], case["target"])) == case["accepted"]
    if case["accepted"]:
        for branch in plural_branches(case["source"]).values():
            protected = mask(branch)
            assert protected.restore(protected.text) == branch


def test_plural_numbers_are_reviewed_per_branch_and_branch_injection_is_rejected():
    issues = review_issues("2 turns[i2p_One]1 turn", "1 tur[i2p_One]2 tur")
    assert "numeric_content_review" in issues
    assert "plural_content_review" in issues
    with pytest.raises(ValueError):
        mask("Many[i2p_One]One")
    protected = mask("Many")
    with pytest.raises(ValueError):
        protected.restore("Cok[i2p_One]Bir")


def test_mask_restore_unicode_and_reordering() -> None:
    source = "<color=red><b>{0}</b></color>\r\n{1}"
    protected = mask(source)
    assert source == protected.restore(protected.text)
    assert protected.restore(protected.text + " Türkçe Iıİi çğöşü").endswith("Türkçe Iıİi çğöşü")
    variables = mask("{0} and {1}")
    first, second = variables.replacements
    assert variables.restore(f"{second} ve {first}") == "{1} ve {0}"


def test_missing_added_and_broken_tokens_rejected() -> None:
    protected = mask("Value {0}")
    marker = next(iter(protected.replacements))
    for invalid in ("Değer", protected.text + marker, protected.text.replace(marker, "{7}")):
        with pytest.raises(ValueError):
            protected.restore(invalid)
    with pytest.raises(ValueError):
        protected.restore(protected.text + " __UT_broken__")


def test_review_controls_are_not_human_approval() -> None:
    assert review_issues("3 points {0}", "3 puan {0}") == []
    assert review_issues("3 points {0}", "4 puan {0}") == ["numeric_content_review"]
    assert review_issues("Same", "Same") == ["unchanged_source"]


def test_i2_runtime_parameters_and_nested_color_attribute_are_preserved() -> None:
    source = "<color=#{[COLOR]}>+{[DMG]} Damage</color>\r\nPress {[SUBMIT]}"
    protected = mask(source)
    assert len(protected.replacements) == 5
    assert "{[" not in protected.text
    translated = protected.text.replace("Damage", "Hasar").replace("Press", "Basın")
    assert protected.restore(translated) == source.replace("Damage", "Hasar").replace(
        "Press", "Basın"
    )
    with pytest.raises(ValueError):
        protected.restore(translated.replace(next(iter(protected.replacements)), "<color=red>"))
    assert review_issues("+{[DMG]} damage", "+{[DMG]} hasar") == []


def test_i2_parameters_can_reorder_but_cannot_change_or_duplicate() -> None:
    protected = mask("Use {[FIRST]} with {[SECOND]}")
    first, second = protected.replacements
    assert protected.restore(f"{second} ile {first} kullan") == "{[SECOND]} ile {[FIRST]} kullan"
    for text in (f"{first} kullan", f"{first} {first}", f"{first} {{[OTHER]}}"):
        with pytest.raises(ValueError):
            protected.restore(text)


def test_space_delimited_comparison_operator_is_protected_as_data() -> None:
    protected = mask("Lives < Knowledge")
    assert protected.restore(protected.text.replace("Lives", "Hayatlar")) == "Hayatlar < Knowledge"
    with pytest.raises(ValueError):
        protected.restore("Hayatlar > Bilgi")


@pytest.mark.parametrize(
    "source",
    [
        "{[SPACE NAME]}",
        "{[NAME:2]}",
        "{[NAME]",
        "<color=#{[BAD NAME]}>x</color>",
        "<script>x</script>",
        "x<y",
        "<size=bad>x</size>",
        "[i2p_One]x",
    ],
)
def test_unverified_parameter_and_tag_shapes_still_fail_closed(source: str) -> None:
    with pytest.raises(ValueError):
        mask(source)


@pytest.mark.parametrize(
    "source,target",
    [
        ("1,000 points and 1.5 damage", "1.000 puan ve 1,5 hasar"),
        ("+3 points", "3 puan"),
        ("50% damage", "%50 hasar"),
        ("50 percent damage", "yüzde 50 hasar"),
        ("At least 3 points", "En az 3 puan"),
        ("At most 3 points", "En fazla 3 puan"),
        ("More than 3 points", "3 puandan fazla"),
        ("Less than 3 points", "3 puandan az"),
        ("Only if health is full", "Yalnızca can doluysa"),
        ("Cannot move", "Hareket edemez"),
        ("Doesn’t heal", "İyileşmez"),
        ("Does not move", "Hareket etmiyor"),
        ("Never attack", "Asla saldır"),
        ("No damage", "Hasar yok"),
        ("Surprise = no", "Sürpriz = hayır"),
        ("Find nowhere to hide", "Saklanacak hiçbir yer bulamayacak"),
        ("The steel shall endure", "Ancak çelik dayanacaktır"),
        ("Chance to attack before engaging", "Çatışmaya girmeden önce saldırma şansı"),
        ("Raw energy to destroy the tomb", "Mezarı yok edecek kadar ham enerji"),
        ("Ignore Armor", "Zırhı Yok Say"),
        ("Game 40,000 trophies", "Game 40,000 başarımları"),
        ("Can destroy the tomb", "Mezarı yok edebilir"),
        ("Cannot destroy the tomb", "Mezarı yok edemez"),
    ],
)
def test_recognized_equivalent_quality_cues(source: str, target: str) -> None:
    assert review_issues(source, target) == []


@pytest.mark.parametrize(
    "source,target,issue",
    [
        ("-3 points", "3 puan", "numeric_content_review"),
        ("50% damage", "50 hasar", "percentage_content_review"),
        ("50 damage", "%50 hasar", "percentage_content_review"),
        ("Cannot move", "Hareket eder", "negation_content_review"),
        ("Can move", "Hareket edemez", "negation_content_review"),
        ("If health is full, heal", "Can dolar, iyileş", "mechanical_condition_review"),
        ("At least 3 points", "En fazla 3 puan", "mechanical_condition_review"),
        ("Before attacking", "Saldırdıktan sonra", "mechanical_condition_review"),
        ("More than 3 points", "3 puan", "mechanical_condition_review"),
    ],
)
def test_changed_quality_cues_require_review(source: str, target: str, issue: str) -> None:
    assert issue in review_issues(source, target)


def test_quality_checks_ignore_protected_content_and_other_language_pairs() -> None:
    assert (
        review_issues("Value {not} <color=50>No</color>", "Değer {not} <color=50>Yok</color>") == []
    )
    assert review_issues("No damage", "Kein Schaden", target_language="de") == []
    assert review_issues("Nicht bewegen", "Hareket et", source_language="de") == []
    assert "negation_content_review" in review_issues(
        "NOT movable", "Hareket eder", source_language="en-US", target_language="tr-TR"
    )


def test_number_normalization_is_exact_and_ambiguous_formats_remain_distinct() -> None:
    huge = "123456789012345678901234567890.1234567890123456789"
    assert numeric_value(huge, "en") == huge
    assert numeric_value("1.5,000", "en") == "1.5,000"
    assert numeric_value("1,00", "en") == "1,00"
    assert numeric_value("−0.00", "en") == "0"
    assert "numeric_content_review" in review_issues("1,000 damage", "1,0 hasar")


def test_issue_labels_are_readable_and_preserve_unknown_codes() -> None:
    assert "Olumsuzluk" in issue_label("negation_content_review")
    assert "Mars" in issue_label("glossary_violation:Mars")
    assert issue_label("future_code") == "future_code"


@pytest.mark.parametrize("source", ["<b><i>x</b></i>", "{0:N2}", "[i2p_One]x", "__UT_x"])
def test_unknown_format_fails_closed(source: str) -> None:
    with pytest.raises(ValueError):
        mask(source)


@pytest.mark.parametrize(
    "raw",
    [
        '{"translations":[]}',
        '{"translations":[{"id":"other","text":"x"}]}',
        '{"translations":[{"id":"one","text":"x"},{"id":"one","text":"y"}]}',
        '{"translations":[{"id":"one","text":7}]}',
        '{"translations":[{"id":"one","text":"x","command":"execute"}]}',
        '{"translations":[],"translations":[{"id":"one","text":"x"}]}',
        '```json\n{"translations":[]}\n```',
        '{"translations":',
        '{"translations":[{"id":"one","text":"x"}],"extra":NaN}',
    ],
)
def test_malformed_model_output_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_reply(raw, {"one"})
