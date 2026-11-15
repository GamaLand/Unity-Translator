"""Immutable glossary/style versions and selection of applicable rules."""

import json
import re
from collections import OrderedDict
from collections.abc import Callable, Iterable
from hashlib import sha256
from threading import Lock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from unitytranslator.glossary_match import fold, term_pattern
from unitytranslator.repository import ProjectRepository, canonical, now
from unitytranslator.validation import PROTECTED_FORMAT_VERSION, unprotected_text


class GlossaryRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)
    kind: Literal["preserve_name", "preferred_translation"]
    category: str | None = None
    case_sensitive: bool = False
    word_boundary: bool = True

    def applies(self, category: str) -> bool:
        return self.category is None or self.category == category

    def pattern(self, language: str, *, target: bool) -> re.Pattern[str]:
        """The cached term pattern; search it in ``self.prepare(text, language, ...)``."""
        verbatim = target and self.kind == "preserve_name"
        exact_case = self.case_sensitive or verbatim
        term = self.target if target else self.source
        return term_pattern(
            fold(term, language, exact_case), language,
            # Inflection applies to translated terms only; names keep their spelling.
            inflect=target, word_boundary=self.word_boundary, verbatim=verbatim,
            exact_case=exact_case,
        )

    def prepare(self, text: str, language: str, *, target: bool) -> str:
        return fold(text, language, self.case_sensitive or (
            target and self.kind == "preserve_name"
        ))

    def matches(
        self, text: str, category: str, target: bool = False, *, language: str | None = None
    ) -> bool:
        if not self.applies(category):
            return False
        language = language or ("tr" if target else "en")
        return self.pattern(language, target=target).search(
            self.prepare(text, language, target=target)
        ) is not None


class CompiledGlossary:
    """One glossary version's rules with their source and target patterns compiled.

    Source terms match with word boundaries; target terms are inflection-tolerant per
    ``glossary_match``. A preserved name must appear verbatim: as the rule writes it
    or exactly as it occurs in the source text (for example in an all-caps title).
    Relevance and violations ignore protected tokens and tags of the record's format
    rules (``format_rules``; the I2 protected format unless a caller passes another).
    """

    def __init__(
        self, rules: Iterable[GlossaryRule], source_language: str, target_language: str,
    ) -> None:
        self.rules = tuple(rules)
        self.source_language = source_language
        self.target_language = target_language
        self._compiled = {
            id(rule): (
                rule.pattern(source_language, target=False),
                rule.pattern(target_language, target=True),
            )
            for rule in self.rules
        }

    def _patterns(self, rule: GlossaryRule) -> tuple[re.Pattern[str], re.Pattern[str]]:
        compiled = self._compiled.get(id(rule))
        if compiled is None:
            compiled = (
                rule.pattern(self.source_language, target=False),
                rule.pattern(self.target_language, target=True),
            )
        return compiled

    def relevant(
        self, text: str, category: str, *, format_rules: str = PROTECTED_FORMAT_VERSION,
    ) -> list[GlossaryRule]:
        """Rules of this category whose source term occurs in ``text``.

        Protected tokens and tags of ``format_rules`` are masked first, so a term that
        occurs only inside a placeholder or tag is not relevant.
        """
        text = unprotected_text(text, format_rules)
        folded: dict[bool, str] = {}
        result = []
        for rule in self.rules:
            if not rule.applies(category):
                continue
            if rule.case_sensitive not in folded:
                folded[rule.case_sensitive] = fold(
                    text, self.source_language, rule.case_sensitive
                )
            if self._patterns(rule)[0].search(folded[rule.case_sensitive]):
                result.append(rule)
        return result

    def violations(
        self, source_text: str, translation: str, category: str,
        rules: Iterable[GlossaryRule] | None = None, *,
        format_rules: str = PROTECTED_FORMAT_VERSION,
    ) -> list[GlossaryRule]:
        """Relevant rules none of whose allowed target forms occur in ``translation``.

        Both texts are masked by ``format_rules`` as in ``relevant``: a target term
        inside a protected token does not satisfy a rule.
        """
        selected = (
            self.relevant(source_text, category, format_rules=format_rules)
            if rules is None else list(rules)
        )
        source_text = unprotected_text(source_text, format_rules)
        translation = unprotected_text(translation, format_rules)
        missing = []
        for rule in selected:
            source, target = self._patterns(rule)
            if target.search(rule.prepare(translation, self.target_language, target=True)):
                continue
            if rule.kind == "preserve_name" and any(
                term_pattern(
                    occurrence, self.target_language, inflect=True,
                    word_boundary=rule.word_boundary, verbatim=True, exact_case=True,
                ).search(translation)
                for occurrence in self._occurrences(rule, source, source_text)
            ):
                continue
            missing.append(rule)
        return missing

    def _occurrences(
        self, rule: GlossaryRule, source: re.Pattern[str], text: str,
    ) -> set[str]:
        """The source spellings of a matched name, when folding kept positions."""
        folded = fold(text, self.source_language, rule.case_sensitive)
        if len(folded) != len(text):
            return set()
        return {text[m.start():m.end()] for m in source.finditer(folded)} - {rule.target}


COMPILED_GLOSSARY_CACHE = 8
_COMPILED: OrderedDict[tuple[str, str, str], CompiledGlossary] = OrderedDict()
_COMPILED_LOCK = Lock()


def compiled_glossary(
    version: str | None, load: Callable[[], Iterable[GlossaryRule]], source_language: str,
    target_language: str,
) -> CompiledGlossary:
    """Return a compiled glossary version, loading and compiling it on first use.

    Versions are content-addressed and immutable, so the cache key is the version ID
    with the language pair; ``None`` (no glossary) is never cached.
    """
    if version is None:
        return CompiledGlossary(load(), source_language, target_language)
    key = (version, source_language, target_language)
    with _COMPILED_LOCK:
        cached = _COMPILED.get(key)
        if cached is not None:
            _COMPILED.move_to_end(key)
            return cached
    compiled = CompiledGlossary(load(), source_language, target_language)
    with _COMPILED_LOCK:
        _COMPILED[key] = compiled
        while len(_COMPILED) > COMPILED_GLOSSARY_CACHE:
            _COMPILED.popitem(last=False)
    return compiled


class PolicyStore:
    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    def set_glossary(self, rules: list[GlossaryRule]) -> str:
        if len(rules) > 5000:
            raise ValueError("The glossary size limit was exceeded.")
        if any(rule.kind == "preserve_name" and rule.source != rule.target for rule in rules):
            raise ValueError("A preserved name must have the same source and target value.")
        encoded = canonical([rule.model_dump() for rule in rules])
        identifier = sha256(encoded.encode("utf-8")).hexdigest()
        old = self.rules(self.active_version("glossary"))
        old_rules = {canonical(rule.model_dump()): rule for rule in old}
        new_rules = {canonical(rule.model_dump()): rule for rule in rules}
        changed = [
            rule
            for key, rule in (old_rules | new_rules).items()
            if key not in old_rules or key not in new_rules
        ]
        with self.repository.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO glossary_versions VALUES(?,?,?)",
                (identifier, encoded, now()),
            )
            db.execute(
                "INSERT INTO project_settings VALUES('glossary',?) ON CONFLICT(key) "
                "DO UPDATE SET value=excluded.value",
                (identifier,),
            )
            for row in db.execute(
                "SELECT u.unit_id,s.source_text,s.category FROM text_units u "
                "JOIN source_revisions s ON s.id=u.source_revision WHERE u.active=1"
            ):
                if any(
                    rule.matches(
                        row["source_text"],
                        row["category"],
                        language=self.repository.source_language,
                    )
                    for rule in changed
                ):
                    db.execute(
                        "INSERT INTO policy_impacts(unit_id,glossary_version,reason,created_at) "
                        "VALUES(?,?,'glossary_changed',?) ON CONFLICT(unit_id) DO UPDATE SET "
                        "glossary_version=excluded.glossary_version,reason=excluded.reason,"
                        "created_at=excluded.created_at",
                        (row["unit_id"], identifier, now()),
                    )
        return identifier

    def set_styles(self, styles: dict[str, str]) -> str:
        if len(styles) > 100 or any(len(v) > 2000 for v in styles.values()):
            raise ValueError("The style size limit was exceeded.")
        encoded = canonical(styles)
        identifier = sha256(encoded.encode("utf-8")).hexdigest()
        old_version = self.active_version("style")
        old = {}
        if old_version is not None:
            old = json.loads(
                self.repository.db.execute(
                    "SELECT styles_json FROM style_versions WHERE id=?", (old_version,)
                ).fetchone()[0]
            )
        with self.repository.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO style_versions VALUES(?,?,?)", (identifier, encoded, now())
            )
            db.execute(
                "INSERT INTO project_settings VALUES('style',?) ON CONFLICT(key) "
                "DO UPDATE SET value=excluded.value",
                (identifier,),
            )
            for row in db.execute(
                "SELECT u.unit_id,s.category FROM text_units u "
                "JOIN source_revisions s ON s.id=u.source_revision WHERE u.active=1"
            ):
                category = row["category"]
                if old.get(category, old.get("default")) != styles.get(
                    category, styles.get("default")
                ):
                    db.execute(
                        "INSERT INTO policy_impacts(unit_id,style_version,reason,created_at) "
                        "VALUES(?,?,'style_changed',?) ON CONFLICT(unit_id) DO UPDATE SET "
                        "style_version=excluded.style_version,reason=excluded.reason,"
                        "created_at=excluded.created_at",
                        (row["unit_id"], identifier, now()),
                    )
        return identifier

    def impacted(self) -> list[dict[str, str]]:
        return [
            dict(row)
            for row in self.repository.db.execute(
                "SELECT p.unit_id,p.reason,w.status FROM policy_impacts p "
                "JOIN work_items w USING(unit_id) JOIN text_units u USING(unit_id) "
                "WHERE u.active=1 "
                "ORDER BY +u.original_key,u.unit_id"
            )
        ]

    def active_version(self, kind: str) -> str | None:
        row = self.repository.db.execute(
            "SELECT value FROM project_settings WHERE key=?", (kind,)
        ).fetchone()
        return str(row[0]) if row is not None else None

    def select_pinned_versions(self, glossary: str | None, style: str | None) -> None:
        """Select existing settings for future jobs; retain policy and review history."""
        self.rules(glossary)
        self.style(style, "unknown")
        with self.repository.transaction() as db:
            for kind, version in (("glossary", glossary), ("style", style)):
                if version is None:
                    db.execute("DELETE FROM project_settings WHERE key=?", (kind,))
                else:
                    db.execute(
                        "INSERT INTO project_settings VALUES(?,?) ON CONFLICT(key) "
                        "DO UPDATE SET value=excluded.value", (kind, version),
                    )

    def compiled(self, version: str | None) -> CompiledGlossary:
        """The version's rules, compiled once per version and project language pair."""
        return compiled_glossary(
            version, lambda: self.rules(version), self.repository.source_language,
            self.repository.target_language,
        )

    def rules(self, version: str | None) -> list[GlossaryRule]:
        if version is None:
            return []
        row = self.repository.db.execute(
            "SELECT rules_json FROM glossary_versions WHERE id=?", (version,)
        ).fetchone()
        if row is None:
            raise ValueError("The pinned glossary version was not found.")
        return [GlossaryRule.model_validate(value) for value in json.loads(row[0])]

    def style(self, version: str | None, category: str) -> str:
        if version is None:
            return "Preserve the original tone and meaning."
        row = self.repository.db.execute(
            "SELECT styles_json FROM style_versions WHERE id=?", (version,)
        ).fetchone()
        if row is None:
            raise ValueError("The pinned style version was not found.")
        styles = json.loads(row[0])
        return str(styles.get(category, styles.get("default", "Preserve the original tone.")))
