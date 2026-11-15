"""Single-writer local SQLite store with immutable source/translation revisions."""

import json
import sqlite3
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.domain import OperationCancelled, TextUnitDraft
from unitytranslator.filesystem import ProjectPaths, checked_path
from unitytranslator.language import normalize_language, turkish_lower
from unitytranslator.renpy_format import (
    RENPY_FORMAT,
    RENPY_FORMATS,
    RENPY_STRING_FORMAT,
    unit_rules,
)
from unitytranslator.source_contracts import ReaderResult, SourceDescriptor
from unitytranslator.validation import (
    PROTECTED_FORMAT_VERSION,
    REVIEW_CHECKS_VERSION,
    format_issues,
    review_issues,
)

LATEST_SCHEMA = 7
# Records per review page; the interface, session and repository share it.
REVIEW_PAGE_SIZE = 200
SUPPORTED_SCHEMAS = frozenset(range(1, LATEST_SCHEMA + 1))
# Each step applies resources/schema-v<new>.sql after a consistent backup, in order.
MIGRATIONS = tuple((version, version + 1) for version in range(1, LATEST_SCHEMA))


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
            raise ValueError("The project is open for writing in another application.") from exc

    def close(self) -> None:
        self.stream.close()  # The operating-system file lock is released as well.


class ProjectRepository:
    @staticmethod
    def existing_paths(project: Path) -> ProjectPaths:
        """Read the stored game binding without creating a missing project."""
        root = checked_path(project)
        database = checked_path(root / "project.sqlite3")
        if not database.is_file():
            raise ValueError(
                "No saved project was found in this folder. Select the folder that contains "
                "project.sqlite3."
            )
        try:
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as reader:
                version = reader.execute("PRAGMA user_version").fetchone()[0]
                if version not in SUPPORTED_SCHEMAS:
                    raise ValueError(
                        "This project version is not supported; use a newer version of the "
                        "application."
                    )
                rows = reader.execute("SELECT game_path FROM project LIMIT 2").fetchall()
                if len(rows) != 1 or not isinstance(rows[0][0], str):
                    raise ValueError("The project's game link could not be read.")
                game = Path(rows[0][0])
        except sqlite3.DatabaseError as exc:
            raise ValueError(
                "The project database could not be read. Use an intact backup."
            ) from exc
        return ProjectPaths(game, root)

    def __init__(
        self, paths: ProjectPaths, source_language: str = "en", target_language: str = "tr"
    ):
        self.paths = paths
        self.operation_cancelled: Callable[[], bool] = lambda: False
        self.lock = ProjectLock(paths)
        self.connection: sqlite3.Connection | None = None
        try:
            database = paths.output("project.sqlite3")
            if not database.exists():
                source_language = normalize_language(source_language)
                target_language = normalize_language(target_language)
                if source_language == target_language:
                    raise ValueError("Source and target languages must differ.")
            if database.exists():
                with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as preflight:
                    version = preflight.execute("PRAGMA user_version").fetchone()[0]
                    if version not in SUPPORTED_SCHEMAS:
                        raise ValueError("Unknown or newer project schema; writing was refused.")
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
            for old_version, new_version in MIGRATIONS:
                if self.connection.execute("PRAGMA user_version").fetchone()[0] == old_version:
                    self.migrate(old_version, new_version)
            project = self.db.execute("SELECT * FROM project").fetchone()
            if project is None or project["game_path"] != str(paths.game):
                raise ValueError("The project's linked game folder does not match.")
            self.project_id = str(project["id"])
            self.source_language = str(project["source_language"])
            self.target_language = str(project["target_language"])
            manifest = paths.output("project.json")
            if manifest.exists():
                value = json.loads(manifest.read_text(encoding="utf-8"))
                if value != self.manifest():
                    raise ValueError("The project manifest does not match the database.")
            else:
                paths.write_json("project.json", self.manifest())
            self.recover_interrupted()
        except Exception:
            self.close()
            raise

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise ValueError("The project store is closed.")
        return self.connection

    def check_cancelled(self) -> None:
        if self.operation_cancelled():
            raise OperationCancelled("Local preparation was cancelled.")

    def manifest(self) -> dict[str, Any]:
        return {
            "format_version": 1,
            "project_id": self.project_id,
            "database": "project.sqlite3",
            "source_language": self.source_language,
            "target_language": self.target_language,
        }

    def migrate(self, old_version: int, new_version: int) -> None:
        if (old_version, new_version) not in MIGRATIONS:
            raise ValueError("The migration path is not supported.")
        if self.db.execute("PRAGMA user_version").fetchone()[0] != old_version:
            raise ValueError("Migration source schema version changed; no writes performed.")
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

    def ingest_reader_result(
        self, result: ReaderResult, *, format_rules: str | None = None,
    ) -> tuple[str, ...]:
        """Activate only a complete, validated built-in reader result, atomically.

        Ren'Py sources keep the project's persisted text rule; new projects start with
        renpy-text-v2. Only an explicit format_rules='renpy-text-v2' upgrades v1 sources.
        """
        if not result.complete or not result.snapshots:
            raise ValueError("Incomplete source discovery cannot replace active sources.")
        renpy = {s.source.adapter_id for s in result.snapshots} <= {
            "renpy-templates", "renpy-scripts",
        }
        if format_rules is not None and (not renpy or format_rules not in RENPY_FORMATS):
            raise ValueError("Text rules can only be selected for Ren'Py sources.")
        upgrade = False
        if renpy:
            persisted = self.renpy_format_rules()
            if persisted is not None and persisted not in RENPY_FORMATS:
                raise ValueError("Stored Ren'Py sources use an unknown text rule.")
            target = format_rules or persisted or RENPY_STRING_FORMAT
            if persisted == RENPY_STRING_FORMAT and target == RENPY_FORMAT:
                raise ValueError("Ren'Py text rules cannot be downgraded.")
            upgrade = persisted == RENPY_FORMAT and target == RENPY_STRING_FORMAT
            result = replace(result, snapshots=tuple(
                replace(snapshot, source=replace(snapshot.source, format_rules=target))
                for snapshot in result.snapshots
            ))
        descriptors = [snapshot.source for snapshot in result.snapshots]
        identities = [source.logical_id for source in descriptors]
        units = [unit.unit_id for snapshot in result.snapshots for unit in snapshot.units]
        if len(set(identities)) != len(identities) or len(set(units)) != len(units):
            raise ValueError("Ambiguous source or record identities in reader result.")
        groups = {(s.adapter_id, s.profile_id, s.source_language) for s in descriptors}
        if len(groups) != 1:
            raise ValueError("A complete source set must belong to one adapter/profile/language.")
        with self.transaction() as db:
            if upgrade:
                self._begin_renpy_rule_upgrade(db)
            snapshots = tuple(
                self.ingest(
                    snapshot.units, {**result.metadata, **snapshot.metadata}, source=snapshot.source
                ) for snapshot in result.snapshots
            )
            # Retire absent sources only after every member succeeded. Their history stays.
            retired = db.execute(
                "SELECT id FROM source_descriptors WHERE adapter_id=? AND profile_id=? "
                "AND source_language=? AND active=1", next(iter(groups))
            ).fetchall() if result.replace_source_set else ()
            for row in retired:
                if row["id"] not in identities:
                    db.execute(
                        "UPDATE text_units SET active=0 WHERE logical_source_id=?", (row[0],)
                    )
                    db.execute("UPDATE source_descriptors SET active=0 WHERE id=?", (row[0],))
            if upgrade:
                self._finish_renpy_rule_upgrade(db, identities)
        return snapshots

    def _begin_renpy_rule_upgrade(self, db: sqlite3.Connection) -> None:
        if db.execute(
            "SELECT 1 FROM jobs WHERE status IN ('queued','running','pausing','paused')"
        ).fetchone():
            raise ValueError(
                "Finish or cancel unfinished jobs before upgrading Ren'Py text rules."
            )
        # Every Ren'Py descriptor, retired ones included, moves to the new rule together.
        for identifier, encoded in db.execute(
            "SELECT id,descriptor_json FROM source_descriptors "
            "WHERE adapter_id IN ('renpy-templates','renpy-scripts')"
        ).fetchall():
            value = json.loads(encoded)
            value["format_rules"] = RENPY_STRING_FORMAT
            db.execute(
                "UPDATE source_descriptors SET descriptor_json=? WHERE id=?",
                (canonical(value), identifier),
            )

    def _finish_renpy_rule_upgrade(
        self, db: sqlite3.Connection, identities: Sequence[str],
    ) -> None:
        """Invalidate only string translations that fail the new printf rule."""
        invalidated = []
        checked = 0
        for row in db.execute(
            "SELECT u.unit_id,s.source_text,t.text,w.approved_translation FROM text_units u "
            "JOIN source_revisions s ON s.id=u.source_revision JOIN work_items w USING(unit_id) "
            "JOIN translation_revisions t ON t.id=w.translation_revision "
            # Without any '%', printf mode cannot change the result of an earlier check.
            "WHERE u.original_key LIKE 'string/%' "
            "AND (instr(s.source_text,'%')>0 OR instr(t.text,'%')>0) AND u.logical_source_id IN "
            "(SELECT id FROM source_descriptors "
            "WHERE adapter_id IN ('renpy-templates','renpy-scripts'))"
        ).fetchall():
            checked += 1
            if format_issues(row[1], row[2], rules=RENPY_STRING_FORMAT):
                invalidated.append((row[0], row[3] is not None))
                db.execute(
                    "UPDATE work_items SET status='needs_review',approved_source=NULL,"
                    "approved_translation=NULL,version=version+1 WHERE unit_id=?", (row[0],),
                )
        db.execute(
            "INSERT INTO source_snapshots VALUES(?,?,?)",
            (uuid4().hex, now(), canonical({
                "kind": "format_rules_upgrade", "from": RENPY_FORMAT,
                "to": RENPY_STRING_FORMAT, "logical_ids": sorted(identities),
                "checked_string_translations": checked,
                "invalidated_units": sorted(unit for unit, _ in invalidated),
                "invalidated_approvals": sum(approved for _, approved in invalidated),
            })),
        )

    def ingest(
        self, units: Sequence[TextUnitDraft], metadata: dict[str, Any], *,
        source: SourceDescriptor | None = None,
    ) -> str:
        if len({unit.unit_id for unit in units}) != len(units):
            raise ValueError("The source snapshot contains a duplicate identity.")
        for unit in units:
            if source is not None and (
                unit.source_file != source.source_file
                or (source.source_object != -1 and unit.source_object != source.source_object)
            ):
                raise ValueError("Record does not belong to the declared logical source.")
            if unit.source_language != self.source_language:
                raise ValueError(
                    "The snapshot source language does not match the project language."
                )
            if sha256(unit.source_text.encode("utf-8")).hexdigest() != unit.source_hash:
                raise ValueError("Source hash verification failed.")
            relative = Path(unit.source_file)
            if relative.is_absolute() or relative.drive or ".." in relative.parts:
                raise ValueError("The source location must be a safe, relative path.")
        snapshot = uuid4().hex
        scope = {unit.source_file for unit in units}
        descriptors = (
            [source] if source is not None
            else [SourceDescriptor.legacy(path, self.source_language) for path in sorted(scope)]
        )
        with self.transaction() as db:
            db.execute(
                "INSERT INTO source_snapshots VALUES(?,?,?)", (snapshot, now(), canonical(metadata))
            )
            for descriptor in descriptors:
                if descriptor.source_language != self.source_language:
                    raise ValueError("Source descriptor language differs from the project.")
                encoded = canonical(asdict(descriptor))
                previous = db.execute(
                    "SELECT * FROM source_descriptors WHERE id=?", (descriptor.logical_id,)
                ).fetchone()
                if previous is not None and (
                    previous["adapter_id"], previous["profile_id"], previous["schema_version"],
                    previous["source_file"], previous["source_language"],
                ) != (
                    descriptor.adapter_id, descriptor.profile_id, descriptor.schema_version,
                    descriptor.source_file, descriptor.source_language,
                ):
                    raise ValueError("Logical source identity cannot be reassigned.")
                if previous is not None and json.loads(previous["descriptor_json"]).get(
                    "format_rules", PROTECTED_FORMAT_VERSION
                ) != descriptor.format_rules:
                    raise ValueError("Source format changes require a new schema identity.")
                db.execute(
                    "INSERT INTO source_descriptors VALUES(?,?,?,?,?,?,?,?,1) "
                    "ON CONFLICT(id) DO UPDATE SET descriptor_json=excluded.descriptor_json,"
                    "source_object=excluded.source_object,active=1",
                    (descriptor.logical_id, descriptor.adapter_id, descriptor.profile_id,
                     descriptor.schema_version, descriptor.source_file, descriptor.source_object,
                     descriptor.source_language, encoded),
                )
                db.execute(
                    "INSERT INTO snapshot_sources VALUES(?,?,?)",
                    (snapshot, descriptor.logical_id, encoded),
                )
                db.execute(
                    "UPDATE text_units SET active=0 WHERE logical_source_id=?",
                    (descriptor.logical_id,),
                )
                if descriptor.profile_id == "legacy-i2":
                    db.execute(
                        "UPDATE text_units SET active=0 WHERE logical_source_id IS NULL "
                        "AND source_file=?", (descriptor.source_file,),
                    )
            for unit in units:
                logical_id = (
                    source.logical_id if source is not None
                    else "legacy-file-v1:" + unit.source_file
                )
                meaning = {
                    key: value
                    for key, value in asdict(unit).items()
                    if key not in ("source_file", "source_object", "original_key")
                }
                revision = sha256(canonical(meaning).encode("utf-8")).hexdigest()
                old = db.execute(
                    "SELECT source_revision,source_file,logical_source_id "
                    "FROM text_units WHERE unit_id=?",
                    (unit.unit_id,),
                ).fetchone()
                if old is not None and old["logical_source_id"] not in (None, logical_id):
                    legacy_move = (
                        str(old["logical_source_id"]).startswith("legacy-file-v1:")
                        and (source is None or source.profile_id == "legacy-i2")
                    )
                    if not legacy_move:
                        raise ValueError("A record identity cannot move between logical sources.")
                if old is not None and old["source_file"] != unit.source_file:
                    previous = checked_path(self.paths.game / old["source_file"])
                    incoming = checked_path(self.paths.game / unit.source_file)
                    if not previous.is_relative_to(self.paths.game) or not incoming.is_relative_to(
                        self.paths.game
                    ):
                        raise ValueError("The source location is outside the game root.")
                    if previous != incoming and previous.exists():
                        raise ValueError(
                            "The logical source identity is ambiguous between two existing files; "
                            "previous records were preserved."
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
                    "UPDATE text_units SET logical_source_id=? WHERE unit_id=?",
                    (logical_id, unit.unit_id),
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
                raise ValueError("Unknown record status.")
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
        limit: int = REVIEW_PAGE_SIZE,
        *,
        search: str = "",
        status: str | None = None,
        category: str | None = None,
        affected: bool = False,
        source_order: bool = False,
    ) -> list[dict[str, Any]]:
        if offset < 0 or not 1 <= limit <= REVIEW_PAGE_SIZE:
            raise ValueError("Invalid page limit.")
        where, parameters = self.filters(search, status, category, affected)
        # The review-order index serves unfiltered/status/category pages. Selective search
        # and impact filters keep the schema-6 scan-and-sort plan; walking the index in key
        # order for few matches would visit every row through random lookups.
        ordering = (
            "+u.original_key,u.unit_id" if search or affected else "u.original_key,u.unit_id"
        )
        order_join = ""
        if source_order:
            from unitytranslator.dialogue_context import DialogueContextStore

            DialogueContextStore(self).prepare_review_order()
            order_join = "LEFT JOIN temp.dialogue_order o USING(unit_id) "
            ordering = "o.position IS NULL,o.position,u.original_key,u.unit_id"
        rows = self.db.execute(
            "SELECT u.*,s.source_text,s.source_hash,s.category,s.context,w.status,w.version,"
            "w.translation_revision,t.text AS translation,t.issues_json FROM text_units u "
            "JOIN source_revisions s ON s.id=u.source_revision JOIN work_items w USING(unit_id) "
            "LEFT JOIN translation_revisions t ON t.id=w.translation_revision "
            f"{order_join}WHERE {where} ORDER BY {ordering} LIMIT ? OFFSET ?",
            (*parameters, limit, offset),
        )
        return [{**dict(row), "format_rules": self.format_rules(row["unit_id"])} for row in rows]

    def format_rules(self, unit_id: str) -> str:
        """Effective rule of one record; renpy-text-v2 applies only to string keys."""
        row = self.db.execute(
            "SELECT d.descriptor_json,u.original_key FROM text_units u "
            "LEFT JOIN source_descriptors d ON d.id=u.logical_source_id WHERE u.unit_id=?",
            (unit_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return PROTECTED_FORMAT_VERSION
        rules = json.loads(row[0]).get("format_rules", PROTECTED_FORMAT_VERSION)
        if rules not in (PROTECTED_FORMAT_VERSION, "literal-lines-v1", *RENPY_FORMATS):
            raise ValueError("Unknown built-in source format rules.")
        return unit_rules(str(rules), str(row[1]))

    def renpy_format_rules(self) -> str | None:
        """The single text rule of this project's Ren'Py sources, if any exist."""
        found = {
            json.loads(row[0]).get("format_rules") for row in self.db.execute(
                "SELECT descriptor_json FROM source_descriptors "
                "WHERE adapter_id IN ('renpy-templates','renpy-scripts')"
            )
        }
        if len(found) > 1:
            raise ValueError("Ren'Py sources use more than one text rule.")
        return str(next(iter(found))) if found else None

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
                "SELECT u.source_revision,u.active,w.version,t.text FROM text_units u "
                "JOIN work_items w USING(unit_id) LEFT JOIN translation_revisions t "
                "ON t.id=w.translation_revision WHERE u.unit_id=?",
                (unit_id,),
            ).fetchone()
            if row is None or row["version"] != version:
                raise ValueError("The record changed; reopen the current text.")
            if not row["active"]:
                # Reject before any state change: an inactive record keeps its approval.
                raise ValueError("Inactive records are history only and cannot be edited.")
            if row["text"] == text:
                return False
            source = db.execute(
                "SELECT source_text FROM source_revisions WHERE id=?", (row["source_revision"],)
            ).fetchone()[0]
            if not text.strip() or format_issues(source, text, rules=self.format_rules(unit_id)):
                raise ValueError(
                    "The edit failed the protected format check; the existing translation was "
                    "preserved."
                )
            db.execute(
                "UPDATE work_items SET status='pending',approved_source=NULL,"
                "approved_translation=NULL WHERE unit_id=?",
                (unit_id,),
            )
            return self.candidate(unit_id, row["source_revision"], version, text, "manual", {}, [])

    def candidate_identity(
        self, unit_id: str, source_revision: str, text: str, origin: str,
        metadata: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Return the content-addressed translation revision ID and its stored metadata."""
        metadata = {
            **metadata,
            "review_checks_version": REVIEW_CHECKS_VERSION,
            "protected_format_version": self.format_rules(unit_id),
        }
        identity = {
            "source_revision": source_revision,
            "language": self.target_language,
            "text": text,
            "origin": origin,
            "metadata": metadata,
        }
        return sha256(canonical(identity).encode("utf-8")).hexdigest(), metadata

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
            raise ValueError("Invalid translation candidate.")
        revision, metadata = self.candidate_identity(
            unit_id, source_revision, text, origin, metadata
        )
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
            hard_issues = format_issues(
                current["source_text"], text, rules=self.format_rules(unit_id)
            )
            issues = sorted(
                set(
                    issues
                    + hard_issues
                    + review_issues(
                        current["source_text"],
                        text,
                        source_language=current["source_language"],
                        target_language=self.target_language,
                        rules=self.format_rules(unit_id),
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
                raise ValueError("Approval requires a current, validated translation candidate.")
            texts = db.execute(
                "SELECT s.source_text,t.text FROM source_revisions s,translation_revisions t "
                "WHERE s.id=? AND t.id=?", (row["source_revision"], row["translation_revision"]),
            ).fetchone()
            # A rule upgrade can make an older candidate invalid; never approve it.
            if format_issues(texts[0], texts[1], rules=self.format_rules(unit_id)):
                raise ValueError("The current translation fails its protected format rules.")
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
            raise ValueError("Record not found.")
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
                raise ValueError("The candidate or source changed; reopen the current history.")
            if current["translation_revision"] == revision:
                return False
            if current["status"] == "approved" and not replace_approved:
                raise ValueError(
                    "Replacing approved text requires an explicit candidate selection."
                )
            if not candidate["text"].strip() or format_issues(
                candidate["source_text"], candidate["text"], rules=self.format_rules(unit_id)
            ):
                raise ValueError(
                    "The candidate failed the protected format check; the existing text was "
                    "preserved."
                )
            issues = json.loads(candidate["issues_json"])
            status = "needs_review" if issues else "translated"
            db.execute(
                "UPDATE work_items SET translation_revision=?,status=?,approved_source=NULL,"
                "approved_translation=NULL,version=version+1 WHERE unit_id=?",
                (revision, status, unit_id),
            )
            return True
