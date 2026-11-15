"""Narrow Unity 2017 Mono serialization schema from static .NET metadata.

Game assemblies are never loaded into the CLR. Unknown types, cycles and
unsupported inheritance are rejected. This fallback handles I2 sources without a type tree."""

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dnfile

from unitytranslator.diagnostics import Diagnostic
from unitytranslator.filesystem import checked_path, hash_file


@dataclass(frozen=True)
class FieldType:
    kind: str
    name: str = ""
    fields: tuple[tuple[str, "FieldType"], ...] = ()
    element: "FieldType | None" = None


class Signature:
    def __init__(self, data: bytes):
        self.data = data
        self.position = 0

    def number(self) -> int:
        if self.position >= len(self.data):
            raise ValueError("Truncated .NET field signature.")
        first = self.data[self.position]
        self.position += 1
        if first < 0x80:
            return first
        count = 1 if first < 0xC0 else 3 if first < 0xE0 else -1
        if count < 0 or self.position + count > len(self.data):
            raise ValueError("Invalid .NET compressed integer.")
        value = first & (0x3F if count == 1 else 0x1F)
        for _ in range(count):
            value = (value << 8) | self.data[self.position]
            self.position += 1
        return value


class ManagedSchema:
    def __init__(self, assembly: Path):
        assembly = checked_path(assembly)
        self.assembly = assembly
        if assembly.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Assembly metadata size limit exceeded.")
        self.assembly_hash = hash_file(assembly)
        self.pe = dnfile.dnPE(str(assembly))  # type: ignore[no-untyped-call]
        if self.pe.net is None or self.pe.net.mdtables is None:
            raise ValueError("Managed assembly metadata was not found.")
        self.tables: Any = self.pe.net.mdtables
        self.explicit_fields: set[int] = set()
        for attribute in self.tables.CustomAttribute or []:
            constructor = attribute.Type.row
            owner = getattr(getattr(constructor, "Class", None), "row", None)
            if owner is not None and str(getattr(owner, "TypeNamespace", "")) == "UnityEngine":
                if str(getattr(owner, "TypeName", "")) == "SerializeField":
                    self.explicit_fields.add(id(attribute.Parent.row))
        self.cache: dict[int, FieldType] = {}
        self.visiting: set[int] = set()

    def close(self) -> None:
        self.pe.close()
        if hash_file(self.assembly) != self.assembly_hash:
            raise ValueError("The assembly changed during inspection; the schema was not accepted.")

    def reference(self, coded: int) -> Any:
        index, tag = coded >> 2, coded & 3
        table = {0: self.tables.TypeDef, 1: self.tables.TypeRef}.get(tag)
        if table is None or index < 1 or index > len(table.rows):
            raise ValueError("Unsupported .NET type reference.")
        return table.rows[index - 1]

    def signature_type(self, signature: Signature) -> FieldType:
        code = signature.number()
        primitive = {2: "bool", 5: "byte", 8: "int", 12: "float", 14: "string"}
        if code in primitive:
            return FieldType(primitive[code])
        if code == 0x1D:
            return FieldType("array", element=self.signature_type(signature))
        if code == 0x15:
            if signature.number() != 0x12:
                raise ValueError("Unsupported generic value type.")
            generic = self.reference(signature.number())
            if (str(generic.TypeNamespace), str(generic.TypeName)) != (
                "System.Collections.Generic",
                "List`1",
            ) or signature.number() != 1:
                raise ValueError("Only single-dimensional List<T> is supported.")
            return FieldType("array", element=self.signature_type(signature))
        if code in (0x11, 0x12):
            row = self.reference(signature.number())
            if (str(row.TypeNamespace), str(row.TypeName)) == ("UnityEngine", "Object"):
                return FieldType("pptr")
            if row.__class__.__name__ != "TypeDefRow":
                raise ValueError("A custom type outside the assembly could not be resolved.")
            return self.class_type(row)
        raise Diagnostic(".NET field type {p0} is not supported.", p0=code)

    def class_type(self, row: Any, root: bool = False) -> FieldType:
        identity = id(row)
        if identity in self.cache:
            return self.cache[identity]
        if identity in self.visiting:
            raise ValueError("A cyclic serialized type was rejected.")
        parent = row.Extends.row
        base = (str(parent.TypeNamespace), str(parent.TypeName))
        if base == ("System", "Enum"):
            underlying = next((f.row for f in row.FieldList if str(f.row.Name) == "value__"), None)
            if underlying is None or underlying.Signature.value != b"\x06\x08":
                raise ValueError("Only int32 enums are supported.")
            return FieldType("int", str(row.TypeName))
        if (root and base != ("UnityEngine", "MonoBehaviour")) or (
            not root and (base != ("System", "Object") or not row.Flags.tdSerializable)
        ):
            raise ValueError("Unsupported serialized inheritance.")
        self.visiting.add(identity)
        fields = []
        try:
            for index in row.FieldList:
                field = index.row
                flags = field.Flags
                if flags.fdStatic or flags.fdLiteral or flags.fdInitOnly or flags.fdNotSerialized:
                    continue
                if not flags.fdPublic and id(field) not in self.explicit_fields:
                    continue
                signature = Signature(field.Signature.value)
                if signature.number() != 6:
                    raise ValueError("Invalid .NET field signature.")
                field_type = self.signature_type(signature)
                if signature.position != len(signature.data):
                    raise ValueError("The field signature was not read completely.")
                fields.append((str(field.Name), field_type))
            result = FieldType("struct", f"{row.TypeNamespace}.{row.TypeName}", tuple(fields))
            self.cache[identity] = result
            return result
        finally:
            self.visiting.remove(identity)

    def language_source(self) -> FieldType:
        matches = [
            row
            for row in self.tables.TypeDef
            if (str(row.TypeNamespace), str(row.TypeName)) == ("I2.Loc", "LanguageSource")
        ]
        if len(matches) != 1:
            raise ValueError("A unique I2 LanguageSource type was not found.")
        return self.class_type(matches[0], root=True)


class SerializedCursor:
    def __init__(self, data: bytes, offset: int, endian: str):
        self.data = data
        self.position = offset
        if endian not in ("<", ">"):
            raise ValueError("Unknown Unity byte order.")
        self.endian = endian

    def read(self, length: int) -> bytes:
        if length < 0 or self.position + length > len(self.data):
            raise ValueError("Truncated Unity serialized object.")
        result = self.data[self.position : self.position + length]
        self.position += length
        return result

    def number(self, fmt: str) -> Any:
        return struct.unpack(self.endian + fmt, self.read(struct.calcsize(fmt)))[0]

    def align(self) -> None:
        self.read((-self.position) % 4)

    def value(self, schema: FieldType, depth: int = 0) -> Any:
        if depth > 16:
            raise ValueError("Serialized depth limit exceeded.")
        if schema.kind == "struct":
            return {name: self.value(field, depth + 1) for name, field in schema.fields}
        if schema.kind == "pptr":
            return {"m_FileID": self.number("i"), "m_PathID": self.number("q")}
        if schema.kind in ("bool", "byte"):
            value = self.number("B")
            if schema.kind == "bool" and value not in (0, 1):
                raise ValueError("Invalid serialized bool.")
            self.align()
            return bool(value) if schema.kind == "bool" else value
        if schema.kind in ("int", "float"):
            return self.number("i" if schema.kind == "int" else "f")
        if schema.kind == "string":
            length = self.number("i")
            if not 0 <= length <= 4 * 1024 * 1024:
                raise ValueError("Serialized text size limit exceeded.")
            result = self.read(length).decode("utf-8", errors="strict")
            self.align()
            return result
        if schema.kind == "array" and schema.element is not None:
            length = self.number("i")
            if not 0 <= length <= 100_000:
                raise ValueError("Serialized array size limit exceeded.")
            if schema.element.kind == "byte":
                byte_values = list(self.read(length))
                self.align()
                return byte_values
            return [self.value(schema.element, depth + 1) for _ in range(length)]
        raise ValueError("Unknown serialized field schema.")

    def finish(self) -> None:
        if self.position != len(self.data):
            raise ValueError(
                "The serialized object was not fully consumed; the schema was not accepted."
            )
