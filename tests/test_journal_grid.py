"""Synthetic literal metadata only; no CLR or game assembly execution."""

import struct
from hashlib import sha256

import pytest

from unitytranslator.journal_grid import _method_code, literal_grid
from unitytranslator.krypta_profile import declared_sources, load_profile, textasset_source_id
from unitytranslator.source_contracts import SourceDescriptor
from unitytranslator.textasset_layouts import parse_payload

FIELD = 0x04000123
CTOR = 0x0A000001
SET = 0x0A000002
ARRAY = b"\x14\x0e\x02\x00\x02\x00\x00"


def operand(opcode, token):
    return bytes([opcode]) + struct.pack("<I", token)


def initializer(indices=None):
    code = b"\x02\x1a\x19" + operand(0x73, CTOR)
    indices = indices or [(row, col) for row in range(4) for col in range(3)]
    for i, (row, col) in enumerate(indices):
        code += bytes([0x25, 0x16 + row, 0x16 + col])
        code += operand(0x72, 0x70000001 + i) + operand(0x28, SET)
    return code + operand(0x7D, FIELD) + b"\x02" + operand(0x28, 0x0A000003) + b"\x2a"


def method(token):
    return ARRAY, {CTOR: b"\x20\x02\x01\x08\x08", SET: b"\x20\x03\x01\x08\x08\x0e"}[token]


def text(token):
    return "" if token % 3 == 0 else "Synthetic çğıöşü " + str(token)


def test_reads_exact_literal_grid_with_empty_cells_and_unicode():
    result = literal_grid(initializer(), FIELD, text, method)
    assert result.field_token == FIELD
    assert len(result.rows) == 4 and all(len(row) == 3 for row in result.rows)
    assert result.rows[0][0] == text(0x70000001)
    assert len(result.payload.decode().split("\n")) == 12


def test_grid_round_trip_preserves_empty_objective_slots():
    raw = ("Objective" + "\n" * 11).encode()
    document = parse_payload(raw, "journal-lines-v1")
    source = SourceDescriptor(
        "synthetic-journal",
        "krypta-textassets",
        "synthetic",
        "journal-lines-v1",
        "Managed/Assembly-CSharp.dll",
        FIELD,
        "en",
        format_rules="literal-lines-v1",
        payload_fingerprint=sha256(raw).hexdigest(),
    )
    assert len(document.drafts(source)) == 1
    assert document.reconstruct({0: "Görev"}) == ("Görev" + "\n" * 11).encode()
    with pytest.raises(ValueError):
        document.reconstruct({1: "Injected objective"})
    for invalid in (raw + b"\n", b"\xef\xbb\xbf" + raw, raw[:-1]):
        with pytest.raises(ValueError):
            parse_payload(invalid, "journal-lines-v1")


def test_profile_expansion_preserves_all_legacy_textasset_namespaces():
    profile = load_profile()
    legacy = {**profile, "version": "1"}
    legacy.pop("textasset_identity_version")
    for source in profile["sources"]:
        arguments = source["container"], source["name"], "en"
        assert textasset_source_id(profile, *arguments) == textasset_source_id(legacy, *arguments)
    sources = declared_sources(profile)
    assert len([source for source in sources if not source.get("excluded_reason")]) == 35
    assert sources[-1]["schema"] == "journal-lines-v1"
    assert sources[-1]["object"] == profile["journal_grid"]["field_token"]


@pytest.mark.parametrize(
    "kind",
    ["branch", "truncated", "dimensions", "duplicate", "field", "heap", "setter", "allocation"],
)
def test_rejects_any_unreviewed_initializer_shape(kind):
    code = initializer()
    if kind == "branch":
        code = b"\x38" + code
    elif kind == "truncated":
        code = code[:-3]
    elif kind == "dimensions":
        code = code.replace(b"\x02\x1a\x19", b"\x02\x19\x19", 1)
    elif kind == "duplicate":
        code = initializer([(0, 0)] * 12)
    elif kind == "field":
        code += operand(0x7D, FIELD)
    elif kind == "heap":
        code = code.replace(operand(0x72, 0x70000001), operand(0x72, 0x01000001))
    elif kind == "setter":
        code = code.replace(operand(0x28, SET), operand(0x28, CTOR))
    else:
        code = code.replace(operand(0x73, CTOR), operand(0x73, SET))
    with pytest.raises(ValueError):
        literal_grid(code, FIELD, text, method)


@pytest.mark.parametrize("invalid", ["line\nbreak", "line\rbreak", "nul\0", "x" * 4097])
def test_rejects_unsupported_literal_text_cells(invalid):
    with pytest.raises(ValueError):
        literal_grid(initializer(), FIELD, lambda _: invalid, method)


def test_bounds_method_headers_and_ignores_adjacent_method_bytes():
    code = initializer()
    header = struct.pack("<HHII", 0x3013, 8, len(code), 0)
    assert _method_code(header + code + b"adjacent metadata") == code
    assert _method_code(b"\x06\x2a") == b"\x2a"
    for invalid in (b"", header + code[:-1], b"\x03" * 12, bytes([0x3B]) + header[1:] + code):
        with pytest.raises(ValueError):
            _method_code(invalid)
