"""Değişmez sözlük/üslup sürümleri ve ilgili kuralların seçimi."""

import json
import re
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from unitytranslator.language import turkish_lower
from unitytranslator.repository import ProjectRepository, canonical, now


class GlossaryRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)
    kind: Literal["preserve_name", "preferred_translation"]
    category: str | None = None
    case_sensitive: bool = False
    word_boundary: bool = True

    def matches(self, text: str, category: str, target: bool = False) -> bool:
        if self.category is not None and self.category != category:
            return False
        term = self.target if target else self.source
        if not self.case_sensitive:
            text = turkish_lower(text) if target else text.casefold()
            term = turkish_lower(term) if target else term.casefold()
        expression = re.escape(term)
        if self.word_boundary:
            expression = r"(?<!\w)" + expression + r"(?!\w)"
        return re.search(expression, text) is not None


class PolicyStore:
    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    def set_glossary(self, rules: list[GlossaryRule]) -> str:
        if len(rules) > 5000:
            raise ValueError("Sözlük boyut sınırı aşıldı.")
        if any(rule.kind == "preserve_name" and rule.source != rule.target for rule in rules):
            raise ValueError("Korunacak adın kaynak ve hedef değeri aynı olmalı.")
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
                if any(rule.matches(row["source_text"], row["category"]) for rule in changed):
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
            raise ValueError("Üslup boyut sınırı aşıldı.")
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
                "ORDER BY u.original_key,u.unit_id"
            )
        ]

    def active_version(self, kind: str) -> str | None:
        row = self.repository.db.execute(
            "SELECT value FROM project_settings WHERE key=?", (kind,)
        ).fetchone()
        return str(row[0]) if row is not None else None

    def rules(self, version: str | None) -> list[GlossaryRule]:
        if version is None:
            return []
        row = self.repository.db.execute(
            "SELECT rules_json FROM glossary_versions WHERE id=?", (version,)
        ).fetchone()
        if row is None:
            raise ValueError("Sabitlenen sözlük sürümü bulunamadı.")
        return [GlossaryRule.model_validate(value) for value in json.loads(row[0])]

    def style(self, version: str | None, category: str) -> str:
        if version is None:
            return "Preserve the original tone and meaning."
        row = self.repository.db.execute(
            "SELECT styles_json FROM style_versions WHERE id=?", (version,)
        ).fetchone()
        if row is None:
            raise ValueError("Sabitlenen üslup sürümü bulunamadı.")
        styles = json.loads(row[0])
        return str(styles.get(category, styles.get("default", "Preserve the original tone.")))
