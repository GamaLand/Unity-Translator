"""Human editor drafts stored separately from model candidates and approvals."""

from typing import Any

from unitytranslator.repository import ProjectRepository, now

MAX_DRAFT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_DRAFT_BYTES = 64 * 1024 * 1024


class EditorDraftStore:
    def __init__(self, repo: ProjectRepository):
        self.repo = repo

    def get(self, unit_id: str) -> dict[str, Any] | None:
        row = self.repo.db.execute(
            "SELECT d.*,s.source_text FROM editor_drafts d "
            "JOIN source_revisions s ON s.id=d.source_revision WHERE d.unit_id=?",
            (unit_id,),
        ).fetchone()
        return dict(row) if row else None

    def put(
        self,
        unit_id: str,
        source_revision: str,
        base_version: int,
        text: str,
        expected_revision: int = 0,
    ) -> dict[str, Any]:
        if (
            type(base_version) is not int
            or base_version < 0
            or type(expected_revision) is not int
            or expected_revision < 0
            or not isinstance(text, str)
        ):
            raise ValueError("Geçersiz düzenleme taslağı.")
        size = len(text.encode("utf-8"))
        if size > MAX_DRAFT_BYTES:
            raise ValueError("Düzenleme taslağı boyut sınırını aşıyor.")
        with self.repo.transaction() as db:
            base = db.execute(
                "SELECT w.version FROM work_items w JOIN source_revisions s "
                "ON s.unit_id=w.unit_id WHERE w.unit_id=? AND s.id=?",
                (unit_id, source_revision),
            ).fetchone()
            if base is None or base_version > base["version"]:
                raise ValueError("Taslağın kaynak/sürüm kimliği geçersiz.")
            old = self.get(unit_id)
            if (old["revision"] if old else 0) != expected_revision:
                raise ValueError("Taslak değişti; güncel taslağı yeniden açın.")
            if old and (old["source_revision"], old["base_version"]) != (
                source_revision,
                base_version,
            ):
                raise ValueError("Eski taslağı açıkça kaldırmadan temel sürüm değiştirilemez.")
            total = db.execute(
                "SELECT COALESCE(sum(length(CAST(text AS BLOB))),0) FROM editor_drafts "
                "WHERE unit_id<>?",
                (unit_id,),
            ).fetchone()[0]
            if total + size > MAX_TOTAL_DRAFT_BYTES:
                raise ValueError("Projenin toplam taslak boyut sınırı aşıldı.")
            if old and old["text"] == text:
                return old
            # AUTOINCREMENT never reuses a removed draft token.
            # A stale window cannot overwrite or remove a replacement draft (ABA).
            db.execute("DELETE FROM editor_drafts WHERE unit_id=?", (unit_id,))
            db.execute(
                "INSERT INTO editor_drafts(unit_id,source_revision,base_version,text,updated_at) "
                "VALUES(?,?,?,?,?)",
                (unit_id, source_revision, base_version, text, now()),
            )
            result = self.get(unit_id)
            assert result is not None
            return result

    def discard(self, unit_id: str, expected_revision: int) -> None:
        if type(expected_revision) is not int or expected_revision <= 0:
            raise ValueError("Geçersiz taslak belirteci.")
        with self.repo.transaction() as db:
            row = self.get(unit_id)
            if row is None or row["revision"] != expected_revision:
                raise ValueError("Taslak değişti; kaldırma reddedildi.")
            db.execute("DELETE FROM editor_drafts WHERE unit_id=?", (unit_id,))

    def commit(self, unit_id: str, expected_revision: int) -> bool:
        if type(expected_revision) is not int or expected_revision <= 0:
            raise ValueError("Geçersiz taslak belirteci.")
        with self.repo.transaction() as db:
            row = self.get(unit_id)
            if row is None or row["revision"] != expected_revision:
                raise ValueError("Taslak değişti; kaydetme reddedildi.")
            current = db.execute(
                "SELECT u.source_revision,u.active,w.version FROM text_units u "
                "JOIN work_items w USING(unit_id) WHERE u.unit_id=?",
                (unit_id,),
            ).fetchone()
            if (
                current is None
                or not current["active"]
                or current["source_revision"] != row["source_revision"]
                or current["version"] != row["base_version"]
            ):
                raise ValueError("Kaynak veya çeviri değişti; taslak korundu, kaydedilmedi.")
            changed = self.repo.edit(unit_id, row["base_version"], row["text"])
            db.execute("DELETE FROM editor_drafts WHERE unit_id=?", (unit_id,))
            return changed
