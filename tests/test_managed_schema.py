import struct

import pytest

from unitytranslator.managed_schema import FieldType, SerializedCursor, Signature


def text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    data = struct.pack("<i", len(encoded)) + encoded
    return data + b"\0" * (-len(data) % 4)


def test_serialized_unicode_byte_arrays_and_alignment() -> None:
    schema = FieldType(
        "struct",
        fields=(
            ("Name", FieldType("string")),
            ("Enabled", FieldType("bool")),
            ("Flags", FieldType("array", element=FieldType("byte"))),
            ("Values", FieldType("array", element=FieldType("string"))),
        ),
    )
    payload = (
        text("Iıİi çğöşü")
        + b"\1\0\0\0"
        + struct.pack("<i", 3)
        + b"\0\1\2\0"
        + struct.pack("<i", 2)
        + text("English")
        + text("Türkçe")
    )
    cursor = SerializedCursor(payload, 0, "<")
    assert cursor.value(schema) == {
        "Name": "Iıİi çğöşü",
        "Enabled": True,
        "Flags": [0, 1, 2],
        "Values": ["English", "Türkçe"],
    }
    cursor.finish()


@pytest.mark.parametrize(
    "data,schema",
    [
        (struct.pack("<i", -1), FieldType("string")),
        (struct.pack("<i", 100001), FieldType("array", element=FieldType("byte"))),
        (b"\2\0\0\0", FieldType("bool")),
        (struct.pack("<i", 8) + b"x", FieldType("string")),
    ],
)
def test_malformed_serialized_data_rejected(data: bytes, schema: FieldType) -> None:
    with pytest.raises(ValueError):
        SerializedCursor(data, 0, "<").value(schema)


def test_trailing_bytes_are_schema_failure() -> None:
    cursor = SerializedCursor(text("value") + b"junk", 0, "<")
    cursor.value(FieldType("string"))
    with pytest.raises(ValueError):
        cursor.finish()


def test_compressed_signature_reference_and_invalid_forms() -> None:
    assert Signature(b"\xac\x10").number() == 0x2C10
    for value in (b"", b"\x80", b"\xe0", b"\xc0\x00"):
        with pytest.raises(ValueError):
            Signature(value).number()
