"""Read-only metadata fallback selected by the I2 script identity."""

from pathlib import Path
from typing import Any

import UnityPy

from unitytranslator.filesystem import checked_path
from unitytranslator.managed_schema import FieldType, ManagedSchema, SerializedCursor


def read_managed_i2(
    obj: Any, source: Path, game: Path, cache: dict[str, Any]
) -> dict[str, Any] | None:
    head = obj.parse_monobehaviour_head()
    pointer = head.m_Script
    script_file = obj.assets_file
    if pointer.m_FileID:
        external = script_file.externals[pointer.m_FileID - 1]
        external_path = checked_path(source.parent / external.path)
        if not external_path.is_relative_to(game):
            raise ValueError("Script metaverisi oyun kökü dışına işaret ediyor.")
        key = str(external_path)
        if key not in cache:
            if external_path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("Script metaverisi dosyası boyut sınırını aşıyor.")
            with external_path.open("rb") as stream:
                cache[key] = UnityPy.load(stream.read())
        files = list(cache[key].files.values())
        if len(files) != 1:
            raise ValueError("Script metaverisi dosyası belirsiz.")
        script_file = files[0]
    script_object = script_file.objects.get(pointer.m_PathID)
    if script_object is None or script_object.type.name != "MonoScript":
        return None
    script = script_object.read()
    if (script.m_Namespace, script.m_ClassName) != ("I2.Loc", "LanguageSource"):
        return None
    if not str(obj.assets_file.unity_version).startswith("2017."):
        raise ValueError("Metaveri fallback yalnızca doğrulanmış Unity 2017 düzenini destekler.")
    if obj.assets_file.header.version < 14:
        raise ValueError("64 bit PathID düzeni gerekli.")
    name = script.m_AssemblyName
    if Path(name).name != name or not name.endswith(".dll"):
        raise ValueError("Assembly metaveri adı güvenli değil.")
    assembly = checked_path(source.parent / "Managed" / name)
    if not assembly.is_relative_to(game):
        raise ValueError("Assembly oyun kökü dışında.")
    key = "schema:" + str(assembly)
    if key not in cache:
        metadata = ManagedSchema(assembly)
        try:
            cache[key] = (metadata.language_source(), metadata.assembly_hash)
        finally:
            metadata.close()
    schema, assembly_hash = cache[key]
    cursor = SerializedCursor(obj.get_raw_data(), 0, obj.reader.endian)
    parsed_gameobject = cursor.value(FieldType("pptr"))
    enabled = cursor.value(FieldType("bool"))
    parsed_script = cursor.value(FieldType("pptr"))
    parsed_name = cursor.value(FieldType("string"))
    if (
        parsed_script != {"m_FileID": pointer.m_FileID, "m_PathID": pointer.m_PathID}
        or parsed_gameobject
        != {"m_FileID": head.m_GameObject.m_FileID, "m_PathID": head.m_GameObject.m_PathID}
        or enabled != bool(head.m_Enabled)
        or parsed_name != head.m_Name
    ):
        raise ValueError("Unity MonoBehaviour başlığı doğrulanamadı.")
    tree: dict[str, Any] = cursor.value(schema)
    cursor.finish()
    if head.m_GameObject.m_FileID != 0:
        raise ValueError("Haricî kaynak kümesi kimliği henüz desteklenmiyor.")
    gameobject = obj.assets_file.objects[head.m_GameObject.m_PathID].read()
    tree["m_Name"] = parsed_name or gameobject.m_Name
    tree["_schema_evidence"] = {
        "assembly_sha256": assembly_hash,
        "fields": [name for name, _ in schema.fields],
        "consumed_bytes": cursor.position,
        "schema_reader": "dnfile-unity2017-v1",
    }
    return tree
