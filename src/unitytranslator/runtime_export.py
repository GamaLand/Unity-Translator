"""Export a reviewed selection as experimental I2 runtime text data."""

from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.json_boundary import strict_json
from unitytranslator.language import language_name
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_payload import export_runtime_payload


def export_selected_runtime(
    repo: ProjectRepository, records: list[dict[str, Any]], *, record_limit: int = 10
) -> dict[str, Any]:
    if (
        type(record_limit) is not int
        or not 1 <= record_limit <= 100_000
        or not 1 <= len(records) <= record_limit
        or len({r["unit_id"] for r in records}) != len(records)
    ):
        raise ValueError(f"1–{record_limit} farklı onaylı kayıt seçin.")
    contexts = set()
    source_fingerprints: dict[str, str | None] = {}
    for frozen in records:
        row = repo.db.execute(
            "SELECT u.*,w.version,w.translation_revision,w.status,w.approved_source,"
            "w.approved_translation FROM text_units u JOIN work_items w USING(unit_id) "
            "WHERE unit_id=?",
            (frozen["unit_id"],),
        ).fetchone()
        if (
            row is None
            or not row["active"]
            or row["status"] != "approved"
            or any(
                row[key] != frozen[key]
                for key in ("source_revision", "translation_revision", "version")
            )
            or row["approved_source"] != row["source_revision"]
            or row["approved_translation"] != row["translation_revision"]
        ):
            raise ValueError(
                "Seçilen kayıt değişti veya güncel insan onayı yok; listeyi yenileyin."
            )
        snapshot = repo.db.execute(
            "SELECT s.metadata_json FROM source_snapshots s JOIN snapshot_units u "
            "ON u.snapshot_id=s.id WHERE u.unit_id=? AND u.source_revision=? "
            "ORDER BY s.created_at DESC,s.rowid DESC LIMIT 1",
            (row["unit_id"], row["source_revision"]),
        ).fetchone()
        if snapshot is None or len(snapshot[0].encode("utf-8")) > 4 * 1024 * 1024:
            raise ValueError("Kaynak çıkarma bilgisi eksik; metinleri yeniden çıkarın.")
        metadata = strict_json(snapshot[0])
        before, after = metadata.get("sha256_before"), metadata.get("sha256_after")
        fingerprint = after if isinstance(after, str) and before == after else None
        previous = source_fingerprints.get(row["source_file"], fingerprint)
        source_fingerprints[row["source_file"]] = fingerprint if previous == fingerprint else None
        versions = metadata.get("unity_versions", [])
        candidates = [
            item
            for item in metadata.get("i2_candidates", [])
            if item.get("object") == row["source_object"]
            and isinstance(item.get("source_set"), str)
            and sha256(
                "\0".join(("i2-v1", item["source_set"], row["original_key"])).encode()
            ).hexdigest()
            == row["unit_id"]
        ]
        source = Path(row["source_file"])
        if (
            len(candidates) != 1
            or len(versions) != 1
            or metadata.get("source") != row["source_file"]
            or len(source.parts) < 2
            or not source.parts[0].endswith("_Data")
        ):
            raise ValueError("Deneme kaynak bilgisi belirsiz veya eski; metinleri yeniden çıkarın.")
        contexts.add(
            (
                candidates[0]["source_set"],
                versions[0],
                source.parts[0] + "/Managed/Assembly-CSharp.dll",
            )
        )
    if len(contexts) != 1:
        raise ValueError("Bir denemede aynı I2 kaynak kümesindeki kayıtları seçin.")
    source_set, version, assembly_relative = contexts.pop()
    result = export_runtime_payload(
        repo,
        source_set=source_set,
        unity_version=version,
        assembly_relative=assembly_relative,
        target_name=language_name(repo.target_language),
        relative="artifacts/i2mono/selection-" + uuid4().hex + ".json",
        selected_unit_ids={item["unit_id"] for item in records},
        max_records=record_limit,
    )
    return {
        **result,
        "source_set": source_set,
        "unity_version": version,
        "assembly_relative": assembly_relative,
        "source_fingerprints": source_fingerprints,
    }
