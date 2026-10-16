"""Deneysel I2 Mono adaptörüne yalnızca güncel, elle onaylı metin verisi."""

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.language import normalize_language
from unitytranslator.repository import ProjectRepository
from unitytranslator.validation import format_issues

MAX_PAYLOAD_BYTES = 64 * 1024 * 1024


def export_runtime_payload(
    repository: ProjectRepository,
    *,
    source_set: str,
    unity_version: str,
    assembly_relative: str,
    target_name: str,
    relative: str = "artifacts/i2mono/translation.json",
    selected_unit_ids: set[str] | None = None,
    max_records: int | None = None,
) -> dict[str, Any]:
    if selected_unit_ids is not None and not selected_unit_ids:
        raise ValueError("Deneme kayıt seçimi boş olamaz.")
    if max_records is not None and (type(max_records) is not int or max_records < 1):
        raise ValueError("Geçersiz deneme kayıt sınırı.")
    source_language = normalize_language(repository.source_language)
    target_language = normalize_language(repository.target_language)
    if source_language == target_language:
        raise ValueError("Source and target languages must differ.")
    if (
        not source_set
        or not target_name
        or not re.fullmatch(r"2017\.\d+\.\d+[abfp]\d+", unity_version)
    ):
        raise ValueError("Doğrulanmış I2 kaynak kümesi, hedef adı ve Unity 2017 sürümü gerekli.")
    part = Path(assembly_relative)
    if part.is_absolute() or part.drive or ".." in part.parts or part.name != "Assembly-CSharp.dll":
        raise ValueError("Assembly konumu oyun köküne göreli Assembly-CSharp.dll olmalı.")
    assembly = checked_path(repository.paths.game / part)
    if not assembly.is_relative_to(repository.paths.game) or not assembly.is_file():
        raise ValueError("Oyun assembly'si bulunamadı.")
    entries = []
    reviewed = []
    payload_bytes = 4096
    for row in repository.db.execute(
        "SELECT u.unit_id,u.original_key,u.source_revision,s.source_text,s.source_hash,"
        "w.version,w.translation_revision,t.text "
        "FROM text_units u JOIN source_revisions s ON s.id=u.source_revision "
        "JOIN work_items w USING(unit_id) JOIN translation_revisions t "
        "ON t.id=w.translation_revision WHERE u.active=1 AND w.status='approved' "
        "AND w.approved_source=u.source_revision AND w.approved_translation=w.translation_revision "
        "ORDER BY u.original_key"
    ):
        identity = sha256(
            "\0".join(("i2-v1", source_set, row["original_key"])).encode()
        ).hexdigest()
        if identity != row["unit_id"]:
            continue  # Başka okuyucu/kaynak kümesi uygulanmaz.
        if selected_unit_ids is not None and row["unit_id"] not in selected_unit_ids:
            continue
        if format_issues(row["source_text"], row["text"]):
            raise ValueError("Onaylı metin korumalı biçim kontrolünü geçmedi; paket oluşturulmadı.")
        entries.append(
            {
                "source_set": source_set,
                "key": row["original_key"],
                "source_sha256": row["source_hash"],
                "text": row["text"],
            }
        )
        encoded = json.dumps(entries[-1], ensure_ascii=False, indent=2)
        payload_bytes += len(encoded.encode("utf-8")) + 4 * (encoded.count("\n") + 1) + 2
        if payload_bytes > MAX_PAYLOAD_BYTES:
            raise ValueError(
                "Çeviri paketi 64 MiB veri sınırını aşıyor; daha küçük bir seçim yapın."
            )
        reviewed.append(
            {
                key: row[key]
                for key in ("unit_id", "source_revision", "translation_revision", "version")
            }
        )
    if not entries:
        raise ValueError("Bu I2 kaynak kümesinde güncel elle onaylı çeviri bulunmuyor.")
    if selected_unit_ids is not None and {row["unit_id"] for row in reviewed} != selected_unit_ids:
        raise ValueError("Seçilen kayıtların tamamı güncel insan onaylı I2 metni değil.")
    if max_records is not None and len(entries) > max_records:
        raise ValueError("Deneme kayıt sınırı aşıldı; daha küçük bir seçim gerekli.")
    value = {
        "format_version": 2,
        "source_language": source_language,
        "unity_version": unity_version,
        "assembly_sha256": hash_file(assembly),
        "target_language": target_language,
        "target_name": target_name,
        "entries": entries,
    }
    path = repository.paths.write_json(relative, value)
    return {
        "path": str(path),
        "records": len(entries),
        "sha256": hash_file(path),
        "application": "unknown",
        "experimental": True,
        "game_written": False,
        "reviewed_records": reviewed,
    }
