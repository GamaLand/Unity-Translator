"""review-multilingual-v6: glossary inflection, multilingual cues and length ratios."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_jobs import profile
from test_repository import draft

from unitytranslator import policy as policy_module
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.policy import CompiledGlossary, GlossaryRule, PolicyStore
from unitytranslator.reports import save_current_quality_audit
from unitytranslator.repository import ProjectRepository
from unitytranslator.validation import (
    REVIEW_CHECKS_VERSION,
    issue_label,
    length_class,
    review_issues,
    visible_length,
)


def preferred(source: str, target: str, **values: object) -> GlossaryRule:
    return GlossaryRule(source=source, target=target, kind="preferred_translation", **values)


def violations(rule: GlossaryRule, source: str, target: str, language: str) -> list[str]:
    compiled = CompiledGlossary([rule], "en", language)
    return [r.source for r in compiled.violations(source, target, "UI")]


def test_version_is_v6() -> None:
    assert REVIEW_CHECKS_VERSION == "review-multilingual-v6"


@pytest.mark.parametrize(
    "language,term,text",
    [
        ("tr", "demir", "Demirden yapılmış kalkan"),
        ("tr", "demir", "DEMİRİ erit"),
        ("tr", "demir", "Demir'in gücü"),
        ("tr", "kılıç", "Kılıcını kuşan"),
        ("tr", "kitap", "Kitabı oku"),
        ("tr", "renk", "Rengi değiştir"),
        ("tr", "demir kalkan", "Demir kalkanlar kırıldı"),
        ("tr", "ışık", "IŞIKLARI kapat"),
        ("fi", "talo", "Olemme talossa"),
        ("fi", "miekka", "Miekalla"),  # gradation kk > k is not tolerated
        ("de", "Schwert", "Die Klinge des Schwertes"),
        ("de", "Schwert", "Zwei Schwerter"),
        ("de", "Drache", "Gegen den Drachen"),
        ("ru", "меч", "Удар мечом"),
        ("ru", "книга", "Прочитай книгу"),
        ("ru", "железный меч", "с железным мечом"),
        ("fr", "épée", "Deux épées"),
        ("fr", "château", "Les châteaux"),
        ("es", "espada larga", "Dos espadas largas"),
        ("pt", "flor", "As flores"),
        ("it", "spada", "Due spade"),
        ("it", "amica", "Le amiche"),
        ("en", "enemy", "Two enemies"),
        ("en", "sword", "The sword's edge"),
        ("zh", "长剑", "装备长剑后攻击"),
        ("ja", "剣", "剣を装備"),
        ("ko", "검", "검을 장착"),
    ],
)
def test_inflected_target_forms_are_accepted(language: str, term: str, text: str) -> None:
    rule = preferred("Sword", term)
    expected = language == "fi" and text == "Miekalla"
    assert rule.matches(text, "UI", target=True, language=language) is not expected


@pytest.mark.parametrize(
    "language,term,text",
    [
        ("tr", "ok", "Okul kapandı"),  # arrow is not school
        ("tr", "demir", "Demirci geldi"),  # derivation forms a different word
        ("tr", "demir", "Ademir"),
        ("de", "Rat", "Die Ratte"),
        ("de", "Schwert", "Eisenschwert"),  # compounds are not tolerated
        ("ru", "меч", "Мечта сбылась"),
        ("fr", "rat", "Le raton"),
        ("es", "sol", "Soldado"),
        ("it", "pane", "Panetteria"),
        ("en", "iron", "Ironic"),
    ],
)
def test_unrelated_longer_words_do_not_match(language: str, term: str, text: str) -> None:
    assert not preferred("Term", term).matches(text, "UI", target=True, language=language)


def test_source_terms_use_word_boundaries_and_unspaced_scripts_substrings() -> None:
    rule = preferred("Iron", "Demir")
    assert rule.matches("Iron shield", "UI")
    assert not rule.matches("Ironic shield", "UI")
    assert not rule.matches("Irons", "UI")  # source terms are not inflected
    assert preferred("开始", "Başla").matches("开始游戏", "UI", language="zh")
    assert preferred("Iron", "Demir", word_boundary=False).matches("Ironic", "UI")


def test_compiled_glossary_flags_missing_terms_with_existing_code() -> None:
    rule = preferred("Iron", "demir")
    assert violations(rule, "Iron shield", "Demirden kalkan", "tr") == []
    assert violations(rule, "Iron shield", "Çelik kalkan", "tr") == ["Iron"]
    assert violations(rule, "Wooden shield", "Tahta kalkan", "tr") == []
    scoped = preferred("Iron", "Demir", category="Items")
    assert CompiledGlossary([scoped], "en", "tr").violations("Iron", "Çelik", "UI") == []
    assert "Iron" in issue_label("glossary_violation:Iron")


def test_preserved_names_must_appear_verbatim() -> None:
    rule = GlossaryRule(source="Mars", target="Mars", kind="preserve_name")
    assert violations(rule, "Fly to Mars", "Mars'a uç", "tr") == []
    assert violations(rule, "Fly to Mars", "mars'a uç", "tr") == ["Mars"]
    assert violations(rule, "Fly to Mars", "Marsa uç", "tr") == []
    # An all-caps source spelling may be kept as written in the source.
    assert violations(rule, "FLY TO MARS", "MARS'A UÇ", "tr") == []
    assert violations(rule, "Fly to Mars", "Лететь на Марс", "ru") == ["Mars"]
    sensitive = preferred("Iron", "Demir", case_sensitive=True)
    assert violations(sensitive, "Iron", "demir", "tr") == ["Iron"]
    assert violations(sensitive, "Iron", "Demirden", "tr") == []


def test_glossary_versions_compile_once(tmp_path: Path, monkeypatch) -> None:
    game = tmp_path / "game"
    game.mkdir()
    built = []
    original = policy_module.CompiledGlossary.__init__

    def counting(self, *args, **kwargs):
        built.append(1)
        original(self, *args, **kwargs)

    monkeypatch.setattr(policy_module.CompiledGlossary, "__init__", counting)
    monkeypatch.setattr(policy_module, "_COMPILED", policy_module.OrderedDict())
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        store = PolicyStore(repo)
        version = store.set_glossary([preferred("Iron", "Demir")])
        first = store.compiled(version)
        assert store.compiled(version) is first and len(built) == 1
        other = store.set_glossary([preferred("Iron", "Çelik")])
        assert store.compiled(other) is not first and len(built) == 2
        assert store.compiled(None).rules == ()


def test_job_uses_inflection_tolerant_glossary(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()

    class Provider:
        async def translate_record(self, model, text, *args, **kwargs):
            return {
                "translation": "Demirden kalkan" if text == "Iron shield" else "Çelik kılıç",
                "issues": [],
            }

    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft("UI/a", "Iron shield"), draft("UI/b", "Iron sword")], {})
        PolicyStore(repo).set_glossary([preferred("Iron", "Demir")])
        job = JobStore(repo).create(["UI/a", "UI/b"], profile())
        asyncio.run(TranslationJobService(repo, lambda _: Provider()).run(job))
        issues = {row["unit_id"]: json.loads(row["issues_json"]) for row in repo.page()}
        assert issues["UI/a"] == []
        assert issues["UI/b"] == ["glossary_violation:Iron"]


@pytest.mark.parametrize(
    "language,source,target",
    [
        ("de", "Cannot move", "Kann sich nicht bewegen"),
        ("de", "No damage", "Kein Schaden"),
        ("de", "At least 3 points", "Mindestens 3 Punkte"),
        ("de", "Only if health is full", "Nur wenn die Gesundheit voll ist"),
        ("de", "Before attacking", "Vor dem Angriff"),
        ("fr", "Cannot move", "Ne peut pas bouger"),
        ("fr", "No longer moves", "Ne bouge plus"),
        ("fr", "Can attack only once", "Peut attaquer une seule fois"),
        ("fr", "At most 3 points", "Au plus 3 points"),
        ("fr", "If health is full, heal", "Si la santé est pleine, soigner"),
        ("es", "Never attack", "Nunca ataques"),
        ("es", "More than 3 points", "Más de 3 puntos"),
        ("es", "After the battle", "Después de la batalla"),
        ("pt", "Without armor", "Sem armadura"),
        ("pt", "Less than 3 points", "Menos de 3 pontos"),
        ("pt", "Until dawn", "Até o amanhecer"),
        ("ru", "Cannot move", "Не может двигаться"),
        ("ru", "Can deal at least 3 damage", "Может нанести не менее 3 урона"),
        ("ru", "Only if health is full", "Только если здоровье полное"),
        ("zh", "Cannot move", "无法移动"),
        ("zh", "Can be very strong", "可以非常强"),
        ("zh", "At least 3 points", "至少3点"),
        ("zh", "Only before the battle", "仅在战斗之前"),
        ("tr", "Cannot move", "Hareket edemez"),
    ],
)
def test_multilingual_cues_accept_faithful_translations(
    language: str, source: str, target: str,
) -> None:
    issues = review_issues(source, target, target_language=language)
    assert "negation_content_review" not in issues
    assert "mechanical_condition_review" not in issues


@pytest.mark.parametrize(
    "language,source,target,issue",
    [
        ("de", "Cannot move", "Kann sich bewegen", "negation_content_review"),
        ("de", "Can move", "Kann sich nicht bewegen", "negation_content_review"),
        ("de", "At least 3 points", "Genau 3 Punkte", "mechanical_condition_review"),
        ("de", "If health is full, heal", "Gesundheit voll, heilen",
         "mechanical_condition_review"),
        ("fr", "Never attack", "Attaquez toujours", "negation_content_review"),
        ("fr", "Can move", "Ne peut pas bouger", "negation_content_review"),
        ("fr", "At least 3 points", "Exactement 3 points", "mechanical_condition_review"),
        ("es", "Cannot move", "Puede moverse", "negation_content_review"),
        ("es", "Only once", "Una vez", "mechanical_condition_review"),
        ("pt", "No damage", "Dano total", "negation_content_review"),
        ("pt", "Before the battle", "Durante a batalha", "mechanical_condition_review"),
        ("ru", "Cannot move", "Может двигаться", "negation_content_review"),
        ("ru", "Can move", "Не может двигаться", "negation_content_review"),
        ("ru", "After the battle", "Во время битвы", "mechanical_condition_review"),
        ("zh", "Cannot move", "可以移动", "negation_content_review"),
        ("zh", "At least 3 points", "3点", "mechanical_condition_review"),
    ],
)
def test_multilingual_cues_flag_changed_meaning(
    language: str, source: str, target: str, issue: str,
) -> None:
    assert issue in review_issues(source, target, target_language=language)


def test_added_chinese_negation_is_not_flagged_and_unsupported_pairs_skip() -> None:
    assert review_issues("Can deal unlimited damage", "可造成无限伤害", target_language="zh") == []
    assert review_issues("Cannot move", "動ける", target_language="ja") == []
    assert review_issues("Cannot move", "Kan bewegen", target_language="nl") == []
    assert review_issues("Nicht bewegen", "Hareket et", source_language="de") == []


@pytest.mark.parametrize(
    "language,source,target,flagged",
    [
        ("de", "Kann sich nicht bewegen", "Cannot move", False),
        ("de", "Kann sich nicht bewegen", "Can move", True),
        ("fr", "Il ne bouge pas", "He does not move", False),
        ("fr", "Il ne bouge pas", "He moves", True),
        ("es", "No puede moverse", "It can move", True),
        ("pt", "Não pode mover", "It is impossible to move", False),
        ("ru", "Не менее 3 очков", "At least 3 points", False),
        ("ru", "Нельзя двигаться", "You may move", True),
        ("zh", "无法移动", "Can move", False),  # reverse direction is not reliable
        ("tr", "Hareket edemez", "Can move", False),
    ],
)
def test_reverse_direction_checks_only_strict_negation(
    language: str, source: str, target: str, flagged: bool,
) -> None:
    issues = review_issues(source, target, source_language=language, target_language="en")
    assert ("negation_content_review" in issues) is flagged
    assert "mechanical_condition_review" not in issues


def test_category_classes_and_visible_length() -> None:
    assert length_class("UI") == "ui"
    assert length_class("MainMenu") == "ui"
    assert length_class("menu") == "ui"
    assert length_class("interface") == "ui"
    assert length_class("dialogue") == "prose"
    assert length_class("ItemDescriptions") == "prose"
    assert length_class("subtitle") == "prose"
    assert length_class("Items") == "default"
    assert length_class(None) is None
    assert visible_length("  a   b  ") == 3
    assert visible_length("é") == 1
    assert visible_length("开始") == 4
    assert visible_length("ｓ") == 2


def test_length_ratio_is_stricter_for_short_ui_than_dialogue() -> None:
    source = "Open the map"
    long_target = "Haritayı açmak için buraya tıklayın ve bekleyin"
    assert "length_ratio_review" in review_issues(source, long_target, category="UI")
    assert "length_ratio_review" not in review_issues(source, "Haritayı aç", category="UI")
    assert "length_ratio_review" not in review_issues(source, long_target)
    dialogue = "I will meet you at the old bridge."
    assert "length_ratio_review" not in review_issues(
        dialogue, "Seninle eski köprüde, gün batımından hemen sonra buluşacağım.",
        category="dialogue",
    )
    assert "length_ratio_review" in review_issues(
        dialogue, "Seninle eski köprüde buluşacağım. " * 4, category="dialogue",
    )


def test_length_ratio_skips_short_sources_and_ignores_protected_tokens() -> None:
    assert review_issues("OK", "Tamam, anlaşıldı", category="UI") == []
    assert "length_ratio_review" not in review_issues(
        "Hit {0} for <color=red>{1}</color>",
        "{0} vur <color=red>{1}</color>",
        category="UI",
    )
    tokens = "<color=#{[COLOR]}>{[A]}</color><color=#{[COLOR]}>{[B]}</color>"
    assert "length_ratio_review" not in review_issues(
        "Damage " + tokens, "Hasar " + tokens, category="UI"
    )


def test_length_ratio_uses_language_expansion_and_wide_characters() -> None:
    source = "Settings menu"
    german = "Einstellungsmenü für Grafik"  # 27 <= 13 * 1.6 * 1.35 + 3
    assert "length_ratio_review" not in review_issues(
        source, german, target_language="de", category="UI"
    )
    assert "length_ratio_review" in review_issues(
        source, german + " und Ton", target_language="tr", category="UI"
    )
    assert "length_ratio_review" not in review_issues(
        source, "设置菜单", target_language="zh", category="UI"
    )
    assert "length_ratio_review" in review_issues(
        source, "设置菜单和图形设置和声音设置", target_language="zh", category="UI"
    )


def test_plural_branches_get_length_checks_per_branch() -> None:
    issues = review_issues(
        "{0} turns left[i2p_One]One turn left",
        "{0} tur kaldı[i2p_One]Yalnızca tek bir tur daha kaldı, acele et",
        category="UI",
    )
    assert "length_ratio_review" in issues and "plural_content_review" in issues


def test_new_candidates_record_v6_and_old_revisions_keep_their_version(
    tmp_path: Path,
) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft("UI/map", "Open the map")], {})
        repo.edit("UI/map", 0, "Haritayı açmak için buraya tıklayın ve bekleyin")
        row = repo.page()[0]
        assert row["status"] == "needs_review"
        assert json.loads(row["issues_json"]) == ["length_ratio_review"]
        repo.approve("UI/map", row["version"])
        # A revision stored by an earlier check version keeps its recorded issues.
        repo.db.execute(
            "UPDATE translation_revisions SET issues_json='[]',metadata_json=?",
            (json.dumps({"review_checks_version": "review-multilingual-v5"}),),
        )
        repo.db.commit()
        before = list(repo.db.iterdump())
        report = save_current_quality_audit(repo)
        assert report["review_checks_version"] == "review-multilingual-v6"
        assert report["issue_counts"] == {"length_ratio_review": 1}
        assert report["newly_flagged_records"] == 1
        assert list(repo.db.iterdump()) == before
        assert repo.page()[0]["status"] == "approved"
        html = Path(report["html_path"]).read_text(encoding="utf-8")
        assert "kategorisine göre" in html


def test_quality_audit_rechecks_the_active_glossary(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft("UI/a", "Iron shield"), draft("UI/b", "Iron sword")], {})
        repo.edit("UI/a", 0, "Demirden kalkan")
        repo.edit("UI/b", 0, "Çelik kılıç")
        version = PolicyStore(repo).set_glossary([preferred("Iron", "Demir")])
        report = save_current_quality_audit(repo)
        assert report["glossary_version"] == version
        assert report["issue_counts"] == {"glossary_violation:Iron": 1}
        content = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
        assert [row["unit_id"] for row in content["records"]] == ["UI/b"]


def test_history_candidate_records_category_length_issue(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([replace(draft("Talk/a", "I will meet you at the old bridge."),
                             category="dialogue")], {})
        current = repo.page()[0]
        revision = repo.add_history_candidate(
            "Talk/a", current["source_revision"], "Köprüde buluşalım. " * 6, "import", {},
        )
        stored = next(r for r in repo.history("Talk/a")["revisions"] if r["id"] == revision)
        assert json.loads(stored["issues_json"]) == ["length_ratio_review"]
        assert json.loads(stored["metadata_json"])["review_checks_version"] == (
            REVIEW_CHECKS_VERSION
        )
