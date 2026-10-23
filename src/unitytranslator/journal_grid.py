"""Read one pinned journal literal grid as metadata; never execute CIL or assemblies.

The bounded Krypta worker uses this fixed component alongside its TextAsset reader.
Only the reviewed constructor's literal array-initializer shape is accepted.
"""

import struct
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dnfile

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.krypta_profile import load_profile

_ARRAY = b"\x14\x0e\x02\x00\x02\x00\x00"


@dataclass(frozen=True)
class JournalGrid:
    field_token: int
    rows: tuple[tuple[str, ...], ...]

    @property
    def payload(self) -> bytes:
        return "\n".join(value for row in self.rows for value in row).encode("utf-8")


def _instructions(code: bytes) -> list[tuple[int, int | None]]:
    if not code or len(code) > 65536:
        raise ValueError("Journal constructor size is unsupported.")
    result = []
    position = 0
    while position < len(code):
        opcode = code[position]
        position += 1
        operand = None
        if opcode in (0x28, 0x72, 0x73, 0x7D, 0x8D, 0x20):
            if position + 4 > len(code):
                raise ValueError("Truncated journal constructor operand.")
            operand = struct.unpack_from("<I", code, position)[0]
            position += 4
        elif opcode == 0x1F:
            if position == len(code):
                raise ValueError("Truncated journal integer operand.")
            operand = struct.unpack_from("<b", code, position)[0]
            position += 1
        elif opcode not in (0x02, 0x25, 0x2A, 0xA2) and not 0x15 <= opcode <= 0x1E:
            raise ValueError("Unexpected instruction in the reviewed journal constructor.")
        result.append((opcode, operand))
    return result


def _integer(instruction: tuple[int, int | None]) -> int:
    opcode, operand = instruction
    if 0x15 <= opcode <= 0x1E:
        return opcode - 0x16
    if opcode in (0x1F, 0x20) and operand is not None:
        return operand
    raise ValueError("Journal grid dimensions/indices must be literal integers.")


def literal_grid(
    code: bytes,
    field_token: int,
    resolve_string: Callable[[int], str],
    resolve_method: Callable[[int], tuple[bytes, bytes]],
) -> JournalGrid:
    """Parse one 4x3 initializer; callbacks resolve bounded metadata, never instructions."""
    instructions = _instructions(code)
    endings = [i for i, value in enumerate(instructions) if value == (0x7D, field_token)]
    if len(endings) != 1:
        raise ValueError("Journal English grid must have exactly one initializer.")
    end = endings[0]
    starts = [i for i in range(end) if instructions[i] == (0x02, None)]
    if not starts:
        raise ValueError("Journal English initializer receiver is missing.")
    block = instructions[starts[-1] + 1 : end]
    if len(block) != 3 + 12 * 5 or tuple(map(_integer, block[:2])) != (4, 3):
        raise ValueError("Journal English grid dimensions or initializer count changed.")
    if block[2][0] != 0x73 or block[2][1] is None:
        raise ValueError("Journal grid allocation is not a fixed array constructor.")
    if resolve_method(block[2][1]) != (_ARRAY, b"\x20\x02\x01\x08\x08"):
        raise ValueError("Journal grid constructor metadata changed.")
    cells = {}
    for start in range(3, len(block), 5):
        duplicate, row, column, value, setter = block[start : start + 5]
        index = (_integer(row), _integer(column))
        if duplicate != (0x25, None) or not (0 <= index[0] < 4 and 0 <= index[1] < 3):
            raise ValueError("Invalid journal grid literal cell.")
        if value[0] != 0x72 or value[1] is None or value[1] >> 24 != 0x70:
            raise ValueError("Journal grid text must come from the user-string heap.")
        if (
            setter[0] != 0x28
            or setter[1] is None
            or resolve_method(setter[1])
            != (
                _ARRAY,
                b"\x20\x03\x01\x08\x08\x0e",
            )
        ):
            raise ValueError("Journal grid setter metadata changed.")
        text = resolve_string(value[1])
        if index in cells or not isinstance(text, str) or any(c in text for c in "\r\n\x00"):
            raise ValueError("Duplicate or unsupported journal grid text cell.")
        if len(text.encode("utf-8", errors="strict")) > 4096:
            raise ValueError("Journal text cell size limit exceeded.")
        cells[index] = text
    return JournalGrid(
        field_token, tuple(tuple(cells[row, column] for column in range(3)) for row in range(4))
    )


def _method_code(data: bytes) -> bytes:
    if not data:
        raise ValueError("Missing journal method body.")
    if data[0] & 3 == 2:
        offset, size = 1, data[0] >> 2
    elif data[0] & 3 == 3 and len(data) >= 12:
        flags = struct.unpack_from("<H", data)[0]
        offset, size = (flags >> 12) * 4, struct.unpack_from("<I", data, 4)[0]
        if offset != 12 or flags & 8:
            raise ValueError("Unsupported journal method header or exception sections.")
    else:
        raise ValueError("Unsupported journal method header.")
    if not 0 < size <= 65536 or offset + size > len(data):
        raise ValueError("Journal method body is truncated or oversized.")
    return data[offset : offset + size]


def read_journal_grid(game: Path) -> JournalGrid:
    profile = load_profile()
    assembly = checked_path(game / profile["assembly"]["path"])
    expected = profile["assembly"]["sha256"]
    if not assembly.is_relative_to(game) or hash_file(assembly) != expected:
        raise ValueError("Journal extraction is pinned to the reviewed game assembly.")
    pe = dnfile.dnPE(str(assembly))  # type: ignore[no-untyped-call]
    try:
        net = pe.net
        if net is None or net.mdtables is None or net.user_strings is None:
            raise ValueError("Journal managed metadata or user-string heap is missing.")
        tables: Any = net.mdtables
        if tables.TypeDef is None or tables.Field is None or tables.MemberRef is None:
            raise ValueError("Journal metadata tables are missing.")
        strings = net.user_strings
        types = [row for row in tables.TypeDef if str(row.TypeName) == "Journal"]
        if len(types) != 1:
            raise ValueError("Journal type identity is ambiguous.")
        fields = [
            item.row
            for item in types[0].FieldList
            if str(item.row.Name) == "objectivesDescriptionsENG"
        ]
        methods = [item.row for item in types[0].MethodList if str(item.row.Name) == ".ctor"]
        if len(fields) != 1 or fields[0].Signature.value != b"\x06" + _ARRAY or len(methods) != 1:
            raise ValueError("Journal field or constructor metadata changed.")
        field_token = 0x04000000 + next(
            i for i, row in enumerate(tables.Field, 1) if row is fields[0]
        )

        def string(token: int) -> str:
            value = strings.get(token & 0xFFFFFF)
            if value is None:
                raise ValueError("Journal user-string reference is missing.")
            return str(value)

        def method(token: int) -> tuple[bytes, bytes]:
            index = (token & 0xFFFFFF) - 1
            if token >> 24 != 0x0A or not 0 <= index < len(tables.MemberRef.rows):
                raise ValueError("Unsupported journal initializer method token.")
            member: Any = tables.MemberRef.rows[index]
            if str(member.Name) not in (".ctor", "Set"):
                raise ValueError("Unexpected journal initializer method.")
            owner = member.Class.row
            if owner.__class__.__name__ != "TypeSpecRow":
                raise ValueError("Journal initializer does not target a literal array.")
            return bytes(owner.Signature.value), bytes(member.Signature.value)

        data = pe.get_data(methods[0].Rva, 65552)
        return literal_grid(_method_code(data), field_token, string, method)
    finally:
        pe.close()
        if hash_file(assembly) != expected:
            raise ValueError("Journal assembly changed during static reading.")
