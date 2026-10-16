"""Versioned data interchange; imported paths and profiles are never executed."""

import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from unitytranslator.domain import TextUnitDraft
from unitytranslator.filesystem import checked_path
from unitytranslator.json_boundary import strict_json
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.repository import ProjectRepository, canonical, now


class PortableTranslation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=1_000_000)
    origin: Literal["model", "manual", "import"]
    metadata: dict[str, Any]
    approved: bool


class PortableUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    unit_id: str = Field(min_length=1, max_length=256)
    original_key: str = Field(min_length=1, max_length=2048)
    source_revision: str = Field(min_length=1, max_length=256)
    source_hash: str
    source_text: str = Field(max_length=1_000_000)
    category: str
    context: str
    translation: PortableTranslation | None


class ArchivedSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=256)
    source_text: str = Field(max_length=1_000_000)
    source_hash: str
    category: str
    context: str
    created_at: str = Field(max_length=64)


class ArchivedTranslation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=256)
    source_revision: str
    text: str = Field(min_length=1, max_length=1_000_000)
    origin: Literal["model", "manual", "import"]
    metadata: dict[str, Any]
    issues: list[str] = Field(max_length=1000)
    created_at: str = Field(max_length=64)


class ArchivedUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    unit_id: str = Field(min_length=1, max_length=256)
    original_key: str = Field(min_length=1, max_length=2048)
    source_file: str = Field(min_length=1, max_length=2048)
    source_object: int
    active: bool
    current_source: str
    current_translation: str | None
    approved_source: str | None
    approved_translation: str | None
    sources: list[ArchivedSource] = Field(min_length=1, max_length=10000)
    translations: list[ArchivedTranslation] = Field(max_length=10000)
    imported_reviews: list[dict[str, str]] = Field(default_factory=list, max_length=10000)


class PortableProject(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format_version: Literal[1, 2]
    project_id: str
    source_language: str
    target_language: str
    units: list[PortableUnit] = Field(max_length=100_000)
    glossary: list[GlossaryRule] = Field(max_length=5000)
    styles: dict[str, str]
    history: list[ArchivedUnit] = Field(default_factory=list, max_length=100_000)


def portable_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: portable_metadata(item)
            for key, item in value.items()
            if key not in ("address", "endpoint", "game_path", "model_path", "server_path")
        }
    if isinstance(value, list):
        return [portable_metadata(item) for item in value]
    if isinstance(value, str) and (Path(value).is_absolute() or Path(value).drive):
        return "<local>"
    return value


class PortableService:
    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    def export(self, relative: str = "exports/project.json") -> Path:
        units = []
        for offset in range(0, self.repository.count(), 200):
            for item in self.repository.page(offset):
                translation = None
                if item["translation_revision"] is not None:
                    revision = self.repository.db.execute(
                        "SELECT * FROM translation_revisions WHERE id=?",
                        (item["translation_revision"],),
                    ).fetchone()
                    translation = {
                        "text": revision["text"],
                        "origin": revision["origin"],
                        "metadata": portable_metadata(json.loads(revision["metadata_json"])),
                        "approved": item["status"] == "approved",
                    }
                units.append(
                    {
                        key: item[key]
                        for key in (
                            "unit_id",
                            "original_key",
                            "source_revision",
                            "source_hash",
                            "source_text",
                            "category",
                            "context",
                        )
                    }
                    | {"translation": translation}
                )
        policies = PolicyStore(self.repository)
        style_version = policies.active_version("style")
        styles: dict[str, str] = {}
        if style_version is not None:
            styles = json.loads(
                self.repository.db.execute(
                    "SELECT styles_json FROM style_versions WHERE id=?", (style_version,)
                ).fetchone()[0]
            )
        value = {
            "format_version": 2,
            "project_id": self.repository.project_id,
            "source_language": self.repository.source_language,
            "target_language": self.repository.target_language,
            "units": units,
            "glossary": [
                rule.model_dump() for rule in policies.rules(policies.active_version("glossary"))
            ],
            "styles": styles,
            "history": self.export_history(),
        }
        PortableProject.model_validate(value)
        if len(canonical(value).encode("utf-8")) > 64 * 1024 * 1024:
            raise ValueError("Taşınabilir proje boyut sınırı aşıldı.")
        return self.repository.paths.write_json(relative, value)

    def export_history(self) -> list[dict[str, Any]]:
        result = []
        reviews: dict[str, list[dict[str, str]]] = {}
        for row in self.repository.db.execute("SELECT metadata_json FROM source_snapshots"):
            metadata = json.loads(row[0])
            if metadata.get("kind") == "portable_review_archive":
                for review in metadata["reviews"]:
                    reviews.setdefault(review["unit_id"], []).append(review)
        for unit in self.repository.db.execute(
            "SELECT u.*,w.translation_revision,w.approved_source,w.approved_translation "
            "FROM text_units u JOIN work_items w USING(unit_id) ORDER BY u.unit_id"
        ):
            sources = [
                {
                    key: row[key]
                    for key in (
                        "id",
                        "source_text",
                        "source_hash",
                        "category",
                        "context",
                        "created_at",
                    )
                }
                for row in self.repository.db.execute(
                    "SELECT * FROM source_revisions WHERE unit_id=? ORDER BY created_at,id",
                    (unit["unit_id"],),
                )
            ]
            translations = [
                {
                    **{
                        key: row[key]
                        for key in ("id", "source_revision", "text", "origin", "created_at")
                    },
                    "metadata": portable_metadata(json.loads(row["metadata_json"])),
                    "issues": json.loads(row["issues_json"]),
                }
                for row in self.repository.db.execute(
                    "SELECT t.* FROM translation_revisions t JOIN source_revisions s "
                    "ON s.id=t.source_revision WHERE s.unit_id=? ORDER BY t.created_at,t.id",
                    (unit["unit_id"],),
                )
            ]
            result.append(
                {
                    **{
                        key: unit[key]
                        for key in (
                            "unit_id",
                            "original_key",
                            "source_file",
                            "source_object",
                            "approved_source",
                            "approved_translation",
                        )
                    },
                    "active": bool(unit["active"]),
                    "current_source": unit["source_revision"],
                    "current_translation": unit["translation_revision"],
                    "sources": sources,
                    "translations": translations,
                    "imported_reviews": reviews.get(unit["unit_id"], []),
                }
            )
        return result

    def read(self, path: Path) -> PortableProject:
        path = checked_path(path)
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("İçe aktarma boyut sınırı aşıldı.")
        value = PortableProject.model_validate(strict_json(path.read_bytes()))
        if (value.source_language, value.target_language) != (
            self.repository.source_language,
            self.repository.target_language,
        ):
            raise ValueError("İçe aktarma dil çifti projeyle eşleşmiyor.")
        if len({unit.unit_id for unit in value.units}) != len(value.units):
            raise ValueError("İçe aktarmada yinelenen kayıt kimliği.")
        self.validate_history(value)
        return value

    def validate_history(self, value: PortableProject) -> None:
        if (value.source_language, value.target_language) != (
            self.repository.source_language,
            self.repository.target_language,
        ):
            raise ValueError("İçe aktarma dil çifti projeyle eşleşmiyor.")
        if value.format_version == 1 and value.history:
            raise ValueError("Eski JSON sürümü revizyon arşivi içeremez.")
        seen_units: set[str] = set()
        seen_sources: set[str] = set()
        seen_translations: set[str] = set()
        archived = {unit.unit_id: unit for unit in value.history}
        for unit in value.history:
            if unit.unit_id in seen_units:
                raise ValueError("Arşivde yinelenen kayıt kimliği.")
            seen_units.add(unit.unit_id)
            location = Path(unit.source_file)
            if location.is_absolute() or location.drive or ".." in location.parts:
                raise ValueError("Arşiv kaynak yolu güvenli ve göreli olmalı.")
            # The path is location data only; importing never opens that file.
            self.repository.paths.output("tmp/location-check/" + unit.source_file)
            sources = {source.id: source for source in unit.sources}
            translations = {translation.id: translation for translation in unit.translations}
            if len(sources) != len(unit.sources) or len(translations) != len(unit.translations):
                raise ValueError("Arşivde yinelenen revizyon kimliği.")
            for source in unit.sources:
                draft = TextUnitDraft(
                    unit.unit_id,
                    unit.original_key,
                    unit.source_file,
                    unit.source_object,
                    value.source_language,
                    source.source_text,
                    source.source_hash,
                    source.category,
                    source.context,
                )
                meaning = {
                    key: item
                    for key, item in asdict(draft).items()
                    if key not in ("source_file", "source_object", "original_key")
                }
                if (
                    sha256(source.source_text.encode()).hexdigest() != source.source_hash
                    or sha256(canonical(meaning).encode()).hexdigest() != source.id
                    or source.id in seen_sources
                ):
                    raise ValueError("Arşiv kaynak revizyonu/hash geçersiz.")
                seen_sources.add(source.id)
            for translation in unit.translations:
                if (
                    translation.source_revision not in sources
                    or translation.id in seen_translations
                ):
                    raise ValueError("Arşiv çeviri revizyonu ilişkisi geçersiz.")
                seen_translations.add(translation.id)
            if unit.current_source not in sources or (
                unit.current_translation is not None
                and (
                    unit.current_translation not in translations
                    or translations[unit.current_translation].source_revision != unit.current_source
                )
            ):
                raise ValueError("Arşiv etkin revizyon ilişkisi geçersiz.")
            if (unit.approved_source is None) != (unit.approved_translation is None) or (
                unit.approved_source is not None
                and (
                    unit.approved_source != unit.current_source
                    or unit.approved_translation != unit.current_translation
                )
            ):
                raise ValueError("Arşiv onay ilişkisi geçersiz.")
            for review in unit.imported_reviews:
                if set(review) != {
                    "unit_id",
                    "project_id",
                    "source_revision",
                    "translation_revision",
                } or (
                    review["unit_id"] != unit.unit_id
                    or review["source_revision"] not in sources
                    or review["translation_revision"] not in translations
                    or translations[review["translation_revision"]].source_revision
                    != review["source_revision"]
                ):
                    raise ValueError("İçe aktarılmış arşiv onay ilişkisi geçersiz.")
        if value.format_version == 2:
            if {unit.unit_id for unit in value.units} != {
                unit.unit_id for unit in value.history if unit.active
            }:
                raise ValueError("Etkin kayıtlar revizyon arşiviyle eşleşmiyor.")
            for current in value.units:
                history = archived[current.unit_id]
                source = next(s for s in history.sources if s.id == history.current_source)
                if (
                    current.source_revision != source.id
                    or current.original_key != history.original_key
                    or any(
                        getattr(current, key) != getattr(source, key)
                        for key in ("source_text", "source_hash", "category", "context")
                    )
                ):
                    raise ValueError("Etkin kaynak revizyon arşiviyle eşleşmiyor.")

    def preview(self, value: PortableProject) -> dict[str, Any]:
        self.validate_history(value)
        result: dict[str, list[str]] = {
            "applicable": [],
            "approved_conflicts": [],
            "source_conflicts": [],
            "unknown": [],
            "archive_applicable": [],
            "archive_conflicts": [],
            "archive_unknown": [],
        }
        for unit in value.history:
            row = self.repository.db.execute(
                "SELECT original_key FROM text_units WHERE unit_id=?", (unit.unit_id,)
            ).fetchone()
            kind = (
                "archive_unknown"
                if row is None
                else ("archive_applicable" if row[0] == unit.original_key else "archive_conflicts")
            )
            result[kind].append(unit.unit_id)
        for item in value.units:
            if item.translation is None:
                continue
            row = self.repository.db.execute(
                "SELECT u.original_key,u.source_revision,u.active,w.status "
                "FROM text_units u JOIN work_items w USING(unit_id) "
                "WHERE u.unit_id=?",
                (item.unit_id,),
            ).fetchone()
            source = self.repository.db.execute(
                "SELECT * FROM source_revisions WHERE id=?", (item.source_revision,)
            ).fetchone()
            if row is None or not row["active"]:
                result["unknown"].append(item.unit_id)
            elif (
                row["source_revision"] != item.source_revision
                or source is None
                or row["original_key"] != item.original_key
                or any(
                    source[key] != getattr(item, key)
                    for key in ("source_text", "source_hash", "category", "context")
                )
            ):
                result["source_conflicts"].append(item.unit_id)
            elif row["status"] == "approved":
                result["approved_conflicts"].append(item.unit_id)
            else:
                result["applicable"].append(item.unit_id)
        return {
            **result,
            "restore_available": bool(value.history)
            and not self.repository.db.execute("SELECT count(*) FROM text_units").fetchone()[0],
        }

    def apply(self, value: PortableProject) -> dict[str, Any]:
        preview = self.preview(value)
        applicable = set(preview["applicable"])
        applied = 0
        rejected = []
        with self.repository.transaction():
            self.import_history(value, set(preview["archive_applicable"]))
            for item in value.units:
                if item.unit_id not in applicable or item.translation is None:
                    continue
                row = self.repository.db.execute(
                    "SELECT version FROM work_items WHERE unit_id=?", (item.unit_id,)
                ).fetchone()
                metadata = {
                    "imported_project": value.project_id,
                    "original_origin": item.translation.origin,
                    "original_metadata": portable_metadata(item.translation.metadata),
                    "imported_approval": item.translation.approved,
                }
                if self.repository.candidate(
                    item.unit_id,
                    item.source_revision,
                    row[0],
                    item.translation.text,
                    "import",
                    metadata,
                    [],
                ):
                    applied += 1
                else:
                    rejected.append(item.unit_id)
        # Preview policies without automatically replacing the active glossary/style.
        return {
            **preview,
            "applied": applied,
            "format_rejected": rejected,
            "policy_import_available": bool(value.glossary or value.styles),
        }

    def import_history(self, value: PortableProject, units: set[str]) -> None:
        """Append history without changing active source, translation or approval fields."""
        db = self.repository.db
        reviews = []
        for unit in value.history:
            if unit.unit_id not in units:
                continue
            for source in unit.sources:
                existing = db.execute(
                    "SELECT * FROM source_revisions WHERE id=?", (source.id,)
                ).fetchone()
                if existing is not None:
                    if existing["unit_id"] != unit.unit_id or any(
                        existing[key] != getattr(source, key)
                        for key in ("source_text", "source_hash", "category", "context")
                    ):
                        raise ValueError("Arşiv kaynak kimliği mevcut revizyonla çakışıyor.")
                    continue
                db.execute(
                    "INSERT INTO source_revisions VALUES(?,?,?,?,?,?,?,?)",
                    (
                        source.id,
                        unit.unit_id,
                        value.source_language,
                        source.source_text,
                        source.source_hash,
                        source.category,
                        source.context,
                        source.created_at,
                    ),
                )
            for translation in unit.translations:
                metadata = portable_metadata(translation.metadata)
                existing = db.execute(
                    "SELECT * FROM translation_revisions WHERE id=?", (translation.id,)
                ).fetchone()
                if existing is not None:
                    if any(
                        existing[key] != getattr(translation, key)
                        for key in ("source_revision", "text", "origin")
                    ) or (
                        portable_metadata(json.loads(existing["metadata_json"])) != metadata
                        or json.loads(existing["issues_json"]) != translation.issues
                    ):
                        raise ValueError("Arşiv çeviri kimliği mevcut revizyonla çakışıyor.")
                    continue
                db.execute(
                    "INSERT INTO translation_revisions VALUES(?,?,?,?,?,?,?,?)",
                    (
                        translation.id,
                        translation.source_revision,
                        value.target_language,
                        translation.text,
                        translation.origin,
                        canonical(metadata),
                        canonical(translation.issues),
                        translation.created_at,
                    ),
                )
            reviews.extend(unit.imported_reviews)
            if unit.approved_translation is not None:
                assert unit.approved_source is not None
                reviews.append(
                    {
                        "unit_id": unit.unit_id,
                        "project_id": value.project_id,
                        "source_revision": unit.approved_source,
                        "translation_revision": unit.approved_translation,
                    }
                )
        if reviews:
            unique = {canonical(review): review for review in reviews}
            metadata = {
                "kind": "portable_review_archive",
                "reviews": [unique[k] for k in sorted(unique)],
            }
            encoded = canonical(metadata)
            db.execute(
                "INSERT OR IGNORE INTO source_snapshots VALUES(?,?,?)",
                (
                    "reviews-" + sha256(encoded.encode()).hexdigest(),
                    now(),
                    encoded,
                ),
            )

    def restore(self, value: PortableProject) -> dict[str, Any]:
        """Restore into an empty project; imported approvals remain archive history."""
        self.validate_history(value)
        if value.format_version != 2 or not value.history:
            raise ValueError("Geri yükleme revizyon arşivli JSON sürüm 2 gerektirir.")
        if self.repository.db.execute("SELECT count(*) FROM text_units").fetchone()[0]:
            raise ValueError("Geri yükleme yalnızca boş projede yapılabilir.")
        with self.repository.transaction():
            for unit in value.history:
                self.repository.db.execute(
                    "INSERT INTO text_units VALUES(?,?,?,?,?,?)",
                    (
                        unit.unit_id,
                        unit.original_key,
                        unit.source_file,
                        unit.source_object,
                        int(unit.active),
                        unit.current_source,
                    ),
                )
                self.repository.db.execute(
                    "INSERT INTO work_items(unit_id,status) VALUES(?,'pending')", (unit.unit_id,)
                )
            self.import_history(value, {unit.unit_id for unit in value.history})
            result = self.apply(value)
            for unit in value.history:
                if not unit.active:
                    self.repository.db.execute(
                        "UPDATE text_units SET active=0 WHERE unit_id=?", (unit.unit_id,)
                    )
            policy = PolicyStore(self.repository)
            policy.set_glossary(value.glossary)
            policy.set_styles(value.styles)
            # Imported approvals are archive history, not local human approvals.
        return {**result, "restored_units": len(value.history), "local_approvals": 0}
