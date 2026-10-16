"""Yerel tek yazarlı SQLite proje deposu ve değişmez kaynak/çeviri revizyonları."""

import json
import sqlite3
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.domain import TextUnitDraft
from unitytranslator.filesystem import ProjectPaths, checked_path
from unitytranslator.language import turkish_lower
from unitytranslator.validation import (
    PROTECTED_FORMAT_VERSION,
    REVIEW_CHECKS_VERSION,
    format_issues,
    review_issues,
)


def canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def now() -> str:
    return datetime.now(UTC).isoformat()


class ProjectLock:
    def __init__(self, paths: ProjectPaths):
        path = paths.output(".project.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("a+b")
        try:
            if path.stat().st_size == 0:
                self.stream.write(b"\0")
                self.stream.flush()
            self.stream.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise ValueError("Proje başka bir uygulama tarafından yazmaya açık.") from exc

    def close(self) -> None:
        self.stream.close()  # İşletim sistemi kilidini de serbest bırakır.


class ProjectRepository:
    @staticmethod
    def existing_paths(project: Path) -> ProjectPaths:
        """Kayıtlı oyun bağlantısını salt okunur bulur; eksik proje oluşturmaz."""
        root = checked_path(project)
        database = checked_path(root / "project.sqlite3")
        if not database.is_file():
            raise ValueError(
                "Bu klasörde kayıtlı proje bulunamadı. project.sqlite3 içeren klasörü seçin."
            )
        try:
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as reader:
                version = reader.execute("PRAGMA user_version").fetchone()[0]
                if version not in (1, 2, 3, 4):
                    raise ValueError(
                        "Bu proje sürümü desteklenmiyor; daha güncel uygulamayı kullanın."
                    )
                rows = reader.execute("SELECT game_path FROM project LIMIT 2").fetchall()
                if len(rows) != 1 or not isinstance(rows[0][0], str):
                    raise ValueError("Projenin oyun bağlantısı okunamadı.")
                game = Path(rows[0][0])
        except sqlite3.DatabaseError as exc:
            raise ValueError("Proje veritabanı okunamadı. Sağlam bir yedeği kullanın.") from exc
        return ProjectPaths(game, root)

    def __init__(
        self, paths: ProjectPaths, source_language: str = "en", target_language: str = "tr"
    ):
        self.paths = paths
        self.lock = ProjectLock(paths)
        self.connection: sqlite3.Connection | None = None
        try:
            database = paths.output("project.sqlite3")
            if database.exists():
                with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as preflight:
                    version = preflight.execute("PRAGMA user_version").fetchone()[0]
                    if version not in (1, 2, 3, 4):
                        raise ValueError(
                            "Bilinmeyen veya daha yeni proje şeması; yazma reddedildi."
                        )
            self.connection = sqlite3.connect(database, isolation_level=None)
            self.connection.row_factory = sqlite3.Row
            self.connection.create_function("tr_lower", 1, turkish_lower, deterministic=True)
            self.connection.create_function("unicode_fold", 1, str.casefold, deterministic=True)
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA busy_timeout=5000")
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
            if self.connection.execute("PRAGMA user_version").fetchone()[0] == 0:
                sql = files("unitytranslator.resources").joinpath("schema-v1.sql").read_text()
                self.connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version=1;"
                )
                self.connection.execute("INSERT INTO schema_migrations VALUES(1,?)", (now(),))
                self.connection.execute(
                    "INSERT INTO project VALUES(?,?,?,?,?)",
                    (uuid4().hex, source_language, target_language, str(paths.game), now()),
                )
                self.connection.commit()
            if self.connection.execute("PRAGMA user_version").fetchone()[0] == 1:
                self.migrate(1, 2)
            if self.connection.execute("PRAGMA user_version").fetchone()[0] == 2:
                self.migrate(2, 3)
            if self.connection.execute("PRAGMA user_version").fetchone()[0] == 3:
                self.migrate(3, 4)
            project = self.db.execute("SELECT * FROM project").fetchone()
            if project is None or project["game_path"] != str(paths.game):
                raise ValueError("Projenin bağlı olduğu oyun klasörü eşleşmiyor.")
            self.project_id = str(project["id"])
            self.source_language = str(project["source_language"])
            self.target_language = str(project["target_language"])
            manifest = paths.output("project.json")
            if manifest.exists():
                value = json.loads(manifest.read_text(encoding="utf-8"))
                if value != self.manifest():
                    raise ValueError("Proje manifesti veritabanıyla eşleşmiyor.")
            else:
                paths.write_json("project.json", self.manifest())
            self.recover_interrupted()
        except Exception:
            self.close()
            raise

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise ValueError("Proje deposu kapalı.")
        return self.connection

    def manifest(self) -> dict[str, Any]:
        return {
            "format_version": 1,
            "project_id": self.project_id,
            "database": "project.sqlite3",
            "source_language": self.source_language,
            "target_language": self.target_language,
        }

    def migrate(self, old_version: int, new_version: int) -> None:
        if (old_version, new_version) not in ((1, 2), (2, 3), (3, 4)):
            raise ValueError("Migration yolu desteklenmiyor.")
        backup = self.paths.output(f"backups/schema-{old_version}-{uuid4().hex}.sqlite3")
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as destination:
            self.db.backup(destination)
        sql = files("unitytranslator.resources").joinpath(f"schema-v{new_version}.sql").read_text()
        try:
            self.db.executescript(
                "BEGIN IMMEDIATE;\n" + sql + f"\nPRAGMA user_version={new_version};"
            )
            self.db.execute("INSERT INTO schema_migrations VALUES(?,?)", (new_version, now()))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def recover_interrupted(self) -> None:
        with self.transaction() as db:
            db.execute(
                "UPDATE job_items SET work_version=work_version+1 WHERE status='processing' "
                "AND EXISTS(SELECT 1 FROM work_items w WHERE w.unit_id=job_items.unit_id "
                "AND w.status='processing' AND w.version=job_items.work_version)"
            )
            db.execute(
                "UPDATE work_items SET status='pending',version=version+1 WHERE status='processing'"
            )
            db.execute(
                "UPDATE job_items SET status='queued',claim_id=NULL "
                "WHERE status='processing' AND job_id IN "
                "(SELECT id FROM jobs WHERE cancel_requested=0)"
            )
            db.execute(
                "UPDATE job_items SET status='cancelled',claim_id=NULL "
                "WHERE status IN ('queued','processing') AND job_id IN "
                "(SELECT id FROM jobs WHERE cancel_requested=1)"
            )
            db.execute(
                "UPDATE jobs SET status=CASE WHEN cancel_requested=1 THEN 'cancelled' "
                "ELSE 'paused' END WHERE status IN ('running','pausing')"
            )
            db.execute("UPDATE translation_runs SET status='interrupted' WHERE status='processing'")

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        self.lock.close()

    def __enter__(self) -> "ProjectRepository":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        nested = self.db.in_transaction
        savepoint = "sp_" + uuid4().hex
        self.db.execute(f"SAVEPOINT {savepoint}" if nested else "BEGIN IMMEDIATE")
        try:
            yield self.db
            if nested:
                self.db.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                self.db.commit()
        except BaseException:
            if nested:
                self.db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self.db.execute(f"RELEASE SAVEPOINT {savepoint}")
            else:
                self.db.rollback()
            raise

    def ingest(self, units: Sequence[TextUnitDraft], metadata: dict[str, Any]) -> str:
        if len({unit.unit_id for unit in units}) != len(units):
            raise ValueError("Kaynak snapshot'ında yinelenen kimlik var.")
        for unit in units:
            if unit.source_language != self.source_language:
                raise ValueError("Snapshot kaynak dili proje diliyle eşleşmiyor.")
            if sha256(unit.source_text.encode("utf-8")).hexdigest() != unit.source_hash:
                raise ValueError("Kaynak hash doğrulaması başarısız.")
            relative = Path(unit.source_file)
            if relative.is_absolute() or relative.drive or ".." in relative.parts:
                raise ValueError("Kaynak konumu güvenli, göreli bir yol olmalı.")
        snapshot = uuid4().hex
        scope = {unit.source_file for unit in units}
        with self.transaction() as db:
            db.execute(
                "INSERT INTO source_snapshots VALUES(?,?,?)", (snapshot, now(), canonical(metadata))
            )
            for source in scope:
                db.execute("UPDATE text_units SET active=0 WHERE source_file=?", (source,))
            for unit in units:
                meaning = {
                    key: value
                    for key, value in asdict(unit).items()
                    if key not in ("source_file", "source_object", "original_key")
                }
                revision = sha256(canonical(meaning).encode("utf-8")).hexdigest()
                old = db.execute(
                    "SELECT source_revision,source_file FROM text_units WHERE unit_id=?",
                    (unit.unit_id,),
                ).fetchone()
                if old is not None and old["source_file"] != unit.source_file:
                    previous = checked_path(self.paths.game / old["source_file"])
                    incoming = checked_path(self.paths.game / unit.source_file)
                    if not previous.is_relative_to(self.paths.game) or not incoming.is_relative_to(
                        self.paths.game
                    ):
                        raise ValueError("Kaynak konumu oyun kökü dışında.")
                    if previous != incoming and previous.exists():
                        raise ValueError(
                            "Mantıksal kaynak kimliği iki mevcut dosyada belirsiz; "
                            "önceki kayıtlar korundu."
                        )
                db.execute(
                    "INSERT INTO text_units(unit_id,original_key,source_file,source_object) "
                    "VALUES(?,?,?,?) ON CONFLICT(unit_id) DO UPDATE SET "
                    "original_key=excluded.original_key,source_file=excluded.source_file,"
                    "source_object=excluded.source_object,active=1",
                    (unit.unit_id, unit.original_key, unit.source_file, unit.source_object),
                )
                db.execute(
                    "INSERT OR IGNORE INTO source_revisions VALUES(?,?,?,?,?,?,?,?)",
                    (
                        revision,
                        unit.unit_id,
                        unit.source_language,
                        unit.source_text,
                        unit.source_hash,
                        unit.category,
                        unit.context,
                        now(),
                    ),
                )
                db.execute(
                    "UPDATE text_units SET source_revision=?,active=1 WHERE unit_id=?",
                    (revision, unit.unit_id),
                )
                db.execute(
                    "INSERT OR IGNORE INTO work_items(unit_id,status) VALUES(?,'pending')",
                    (unit.unit_id,),
                )
                if old is not None and old["source_revision"] != revision:
                    db.execute(
                        "UPDATE work_items SET status='needs_review',translation_revision=NULL,"
                        "approved_source=NULL,approved_translation=NULL,version=version+1 "
                        "WHERE unit_id=?",
                        (unit.unit_id,),
                    )
                db.execute(
                    "INSERT INTO snapshot_units VALUES(?,?,?)", (snapshot, unit.unit_id, revision)
                )
        return snapshot

    def filters(
        self,
        search: str = "",
        status: str | None = None,
        category: str | None = None,
        affected: bool = False,
    ) -> tuple[str, list[Any]]:
        conditions = ["u.active=1"]
        parameters: list[Any] = []
        if affected:
            conditions.append("EXISTS(SELECT 1 FROM policy_impacts p WHERE p.unit_id=u.unit_id)")
        if status is not None:
            if status not in (
                "pending",
                "processing",
                "translated",
                "validation_error",
                "needs_review",
                "approved",
            ):
                raise ValueError("Bilinmeyen kayıt durumu.")
            conditions.append("w.status=?")
            parameters.append(status)
        if category is not None:
            conditions.append("s.category=?")
            parameters.append(category)
        if search:
            source_func = "tr_lower" if self.source_language == "tr" else "unicode_fold"
            target_func = "tr_lower" if self.target_language == "tr" else "unicode_fold"
            conditions.append(
                f"({source_func}(s.source_text) LIKE ? ESCAPE '\\' OR "
                f"{target_func}(COALESCE(t.text,'')) LIKE ? ESCAPE '\\' OR "
                "unicode_fold(u.original_key) LIKE ? ESCAPE '\\')"
            )
            for normalized in (
                turkish_lower(search) if source_func == "tr_lower" else search.casefold(),
                turkish_lower(search) if target_func == "tr_lower" else search.casefold(),
                search.casefold(),
            ):
                parameters.append(
                    "%"
                    + normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    + "%"
                )
        return " AND ".join(conditions), parameters

    def page(
        self,
        offset: int = 0,
        limit: int = 200,
        *,
        search: str = "",
        status: str | None = None,
        category: str | None = None,
        affected: bool = False,
    ) -> list[dict[str, Any]]:
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Sayfa sınırı geçersiz.")
        where, parameters = self.filters(search, status, category, affected)
        rows = self.db.execute(
            "SELECT u.*,s.source_text,s.source_hash,s.category,s.context,w.status,w.version,"
            "w.translation_revision,t.text AS translation,t.issues_json FROM text_units u "
            "JOIN source_revisions s ON s.id=u.source_revision JOIN work_items w USING(unit_id) "
            "LEFT JOIN translation_revisions t ON t.id=w.translation_revision "
            f"WHERE {where} ORDER BY u.original_key,u.unit_id LIMIT ? OFFSET ?",
            (*parameters, limit, offset),
        )
        return [dict(row) for row in rows]

    def count(
        self,
        *,
        search: str = "",
        status: str | None = None,
        category: str | None = None,
        affected: bool = False,
    ) -> int:
        where, parameters = self.filters(search, status, category, affected)
        row = self.db.execute(
            "SELECT count(*) FROM text_units u "
            "JOIN source_revisions s ON s.id=u.source_revision "
            "JOIN work_items w ON w.unit_id=u.unit_id "
            "LEFT JOIN translation_revisions t ON t.id=w.translation_revision "
            f"WHERE {where}",
            parameters,
        ).fetchone()
        return int(row[0])

    def edit(self, unit_id: str, version: int, text: str) -> bool:
        with self.transaction() as db:
            row = db.execute(
                "SELECT u.source_revision,w.version,t.text FROM text_units u "
                "JOIN work_items w USING(unit_id) LEFT JOIN translation_revisions t "
                "ON t.id=w.translation_revision WHERE u.unit_id=?",
                (unit_id,),
            ).fetchone()
            if row is None or row["version"] != version:
                raise ValueError("Kayıt değişti; güncel metni yeniden açın.")
            if row["text"] == text:
                return False
            source = db.execute(
                "SELECT source_text FROM source_revisions WHERE id=?", (row["source_revision"],)
            ).fetchone()[0]
            if not text.strip() or format_issues(source, text):
                raise ValueError(
                    "Düzenleme korumalı biçim kontrolünü geçmedi; mevcut çeviri korundu."
                )
            db.execute(
                "UPDATE work_items SET status='pending',approved_source=NULL,"
                "approved_translation=NULL WHERE unit_id=?",
                (unit_id,),
            )
            return self.candidate(unit_id, row["source_revision"], version, text, "manual", {}, [])

    def candidate(
        self,
        unit_id: str,
        source_revision: str,
        version: int,
        text: str,
        origin: str,
        metadata: dict[str, Any],
        issues: list[str],
    ) -> bool:
        if origin not in ("model", "manual", "import") or not text.strip():
            raise ValueError("Geçersiz çeviri adayı.")
        metadata = {
            **metadata,
            "review_checks_version": REVIEW_CHECKS_VERSION,
            "protected_format_version": PROTECTED_FORMAT_VERSION,
        }
        identity = {
            "source_revision": source_revision,
            "language": self.target_language,
            "text": text,
            "origin": origin,
            "metadata": metadata,
        }
        revision = sha256(canonical(identity).encode("utf-8")).hexdigest()
        with self.transaction() as db:
            current = db.execute(
                "SELECT u.source_revision,u.active,s.source_text,s.source_language,w.* "
                "FROM text_units u "
                "JOIN source_revisions s ON s.id=u.source_revision "
                "JOIN work_items w ON w.unit_id=u.unit_id WHERE u.unit_id=?",
                (unit_id,),
            ).fetchone()
            if current is None or source_revision != current["source_revision"]:
                return False
            hard_issues = format_issues(current["source_text"], text)
            issues = sorted(
                set(
                    issues
                    + hard_issues
                    + review_issues(
                        current["source_text"],
                        text,
                        source_language=current["source_language"],
                        target_language=self.target_language,
                    )
                )
            )
            db.execute(
                "INSERT OR IGNORE INTO translation_revisions VALUES(?,?,?,?,?,?,?,?)",
                (
                    revision,
                    source_revision,
                    self.target_language,
                    text,
                    origin,
                    canonical(metadata),
                    canonical(issues),
                    now(),
                ),
            )
            if (
                not current["active"]
                or hard_issues
                or current["version"] != version
                or current["status"] == "approved"
            ):
                return False
            if current["translation_revision"] == revision:
                return True
            status = "needs_review" if issues else "translated"
            db.execute(
                "UPDATE work_items SET translation_revision=?,status=?,version=version+1 "
                "WHERE unit_id=?",
                (revision, status, unit_id),
            )
        return True

    def approve(self, unit_id: str, version: int) -> None:
        with self.transaction() as db:
            row = db.execute(
                "SELECT u.source_revision,u.active,w.* FROM text_units u "
                "JOIN work_items w USING(unit_id) WHERE unit_id=?",
                (unit_id,),
            ).fetchone()
            if (
                row is None
                or not row["active"]
                or row["version"] != version
                or row["translation_revision"] is None
                or row["status"] not in ("translated", "needs_review", "approved")
            ):
                raise ValueError("Onay için güncel ve doğrulanmış çeviri adayı gerekli.")
            impact = db.execute(
                "SELECT 1 FROM policy_impacts WHERE unit_id=?", (unit_id,)
            ).fetchone()
            if row["status"] == "approved" and not impact:
                return
            if impact:
                policies = dict(db.execute("SELECT key,value FROM project_settings"))
                db.execute(
                    "INSERT INTO source_snapshots VALUES(?,?,?)",
                    (
                        uuid4().hex,
                        now(),
                        canonical(
                            {
                                "kind": "human_policy_review",
                                "unit_id": unit_id,
                                "source_revision": row["source_revision"],
                                "translation_revision": row["translation_revision"],
                                "glossary_version": policies.get("glossary"),
                                "style_version": policies.get("style"),
                            }
                        ),
                    ),
                )
            db.execute(
                "UPDATE work_items SET status='approved',approved_source=?,"
                "approved_translation=translation_revision,version=version+1 WHERE unit_id=?",
                (row["source_revision"], unit_id),
            )
            db.execute("DELETE FROM policy_impacts WHERE unit_id=?", (unit_id,))

    def history(self, unit_id: str) -> dict[str, Any]:
        current = self.db.execute(
            "SELECT u.source_revision,u.active,w.version,w.status,w.translation_revision "
            "FROM text_units u JOIN work_items w USING(unit_id) WHERE unit_id=?",
            (unit_id,),
        ).fetchone()
        if current is None:
            raise ValueError("Kayıt bulunamadı.")
        rows = [
            dict(row)
            for row in self.db.execute(
                "SELECT t.*,s.source_text,s.context FROM translation_revisions t "
                "JOIN source_revisions s ON s.id=t.source_revision WHERE s.unit_id=? "
                "ORDER BY t.created_at DESC,t.rowid DESC LIMIT 200",
                (unit_id,),
            )
        ]
        return {"unit_id": unit_id, "current": dict(current), "revisions": rows}

    def select_candidate(
        self,
        unit_id: str,
        version: int,
        revision: str,
        *,
        replace_approved: bool = False,
    ) -> bool:
        with self.transaction() as db:
            current = db.execute(
                "SELECT u.source_revision,u.active,w.* FROM text_units u "
                "JOIN work_items w USING(unit_id) WHERE unit_id=?",
                (unit_id,),
            ).fetchone()
            candidate = db.execute(
                "SELECT t.*,s.unit_id,s.source_text FROM translation_revisions t "
                "JOIN source_revisions s ON s.id=t.source_revision WHERE t.id=?",
                (revision,),
            ).fetchone()
            if (
                current is None
                or candidate is None
                or not current["active"]
                or current["version"] != version
                or candidate["unit_id"] != unit_id
                or candidate["source_revision"] != current["source_revision"]
                or candidate["target_language"] != self.target_language
            ):
                raise ValueError("Aday/kaynak değişti; güncel geçmişi yeniden açın.")
            if current["translation_revision"] == revision:
                return False
            if current["status"] == "approved" and not replace_approved:
                raise ValueError("Onaylı metni değiştirmek için açık aday seçimi gerekli.")
            if not candidate["text"].strip() or format_issues(
                candidate["source_text"], candidate["text"]
            ):
                raise ValueError("Aday korumalı biçim kontrolünü geçmedi; mevcut metin korundu.")
            issues = json.loads(candidate["issues_json"])
            status = "needs_review" if issues else "translated"
            db.execute(
                "UPDATE work_items SET translation_revision=?,status=?,approved_source=NULL,"
                "approved_translation=NULL,version=version+1 WHERE unit_id=?",
                (revision, status, unit_id),
            )
            return True
