"""Regenerate the synthetic Unity serialized-file and .NET metadata fixtures.

Everything is constructed here from literal values: no Unity editor, game file,
Unity/I2 assembly or downloaded template is read. UnityPy supplies only its bundled
Unity 2017.4 class layouts and its type-tree value writer. The .NET assembly is a
metadata-only PE image (no method bodies, no entry point) that is never executed.

Usage: python build_fixtures.py [--check] [--output DIR]
"""

import argparse
import hashlib
import struct
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from UnityPy.helpers.Tpk import get_typetree_node
from UnityPy.helpers.TypeTreeHelper import write_typetree
from UnityPy.helpers.TypeTreeNode import TypeTreeNode
from UnityPy.helpers.UnityVersion import UnityVersion
from UnityPy.streams import EndianBinaryWriter

UNITY_VERSION = "2017.4.40f1"
FORMAT_VERSION = 17
STANDALONE_WINDOWS64 = 19
ASSEMBLY_NAME = "Synthetic.I2.dll"
UI_ASSEMBLY_NAME = "Synthetic.Ui.dll"
SCRIPTS_FILE = "globalgamemanagers.assets"

# Committed fixture name -> name inside the synthetic game's <Game>_Data folder.
LAYOUT = {
    "typetree.bin": "sharedassets0.assets",
    "managed.bin": "resources.assets",
    "scripts.bin": SCRIPTS_FILE,
    "assembly.bin": "Managed/" + ASSEMBLY_NAME,
}

GAMEOBJECT, MONOBEHAVIOUR, MONOSCRIPT = 1, 114, 115
ALIGN = 0x4000

LANGUAGES = [
    {"Name": "English", "Code": "en", "Flags": 0},
    {"Name": "Turkish", "Code": "tr", "Flags": 0},
    {"Name": "Japanese", "Code": "ja", "Flags": 1},
]


def term(key: str, kind: int, description: str, texts: Sequence[str]) -> dict[str, Any]:
    return {
        "Term": key,
        "TermType": kind,
        "Description": description,
        "Languages": list(texts),
        "Flags": [0] * len(texts),
        "Languages_Touch": [],
    }


# I2 eTermType: Text = 0, Font = 1. Order is the extraction order.
TERMS = [
    term("Menu/Start", 0, "Main menu button", ["Start", "Başlat", "スタート"]),
    term("Dialog/Intro", 0, "", ["Hello, {[PLAYER]}!\nWelcome.", "Merhaba, {[PLAYER]}!", ""]),
    term("Fonts/Main", 1, "Font asset reference", ["Arial", "Arial", "Noto"]),
    term("Menu/Empty", 0, "Not written yet", ["", "Boş", ""]),
    term("Credits", 0, "", ["Thanks: Iıİi çğöşü", "Teşekkürler", "ありがとう"]),
]


def mono_behaviour_fields(
    name: str, script_file: int, script_path: int, game_object: int = 1
) -> dict[str, Any]:
    return {
        "m_GameObject": {"m_FileID": 0, "m_PathID": game_object},
        "m_Enabled": 1,
        "m_Script": {"m_FileID": script_file, "m_PathID": script_path},
        "m_Name": name,
    }


def language_source(name: str, script_file: int, script_path: int) -> dict[str, Any]:
    return {
        **mono_behaviour_fields(name, script_file, script_path),
        "mSource": {
            "CaseInsensitiveTerms": False,
            "mTerms": TERMS,
            "mLanguages": LANGUAGES,
            "Assets": [{"m_FileID": 0, "m_PathID": 0}],
            "mUpdateDelay": 0.5,
        },
    }


# ---------------------------------------------------------------- type trees


def _node(level: int, kind: str, name: str, size: int = -1, meta: int = 0) -> dict[str, Any]:
    return {
        "m_Level": level,
        "m_Type": kind,
        "m_Name": name,
        "m_ByteSize": size,
        "m_Version": 1,
        "m_TypeFlags": 1 if kind == "Array" else 0,
        "m_MetaFlag": meta,
    }


def _primitive(level: int, kind: str, name: str, aligned: bool = True) -> list[dict[str, Any]]:
    size = {"int": 4, "float": 4, "bool": 1, "UInt8": 1}[kind]
    return [_node(level, kind, name, size, ALIGN if aligned and size == 1 else 0)]


def _string(level: int, name: str) -> list[dict[str, Any]]:
    return [
        _node(level, "string", name, meta=0x8000),
        _node(level + 1, "Array", "Array", meta=ALIGN | 1),
        _node(level + 2, "int", "size", 4, 1),
        _node(level + 2, "char", "data", 1, 1),
    ]


def _pptr(level: int, name: str, target: str) -> list[dict[str, Any]]:
    return [
        _node(level, f"PPtr<{target}>", name, 12),
        _node(level + 1, "int", "m_FileID", 4),
        _node(level + 1, "SInt64", "m_PathID", 8),
    ]


Element = Callable[[int], list[dict[str, Any]]]


def _vector(level: int, name: str, element: Element) -> list[dict[str, Any]]:
    """C# T[] and List<T>; the Array node aligns the end of the whole sequence."""
    return [
        _node(level, "vector", name),
        _node(level + 1, "Array", "Array", meta=ALIGN),
        _node(level + 2, "int", "size", 4),
        *element(level + 2),
    ]


def _struct(level: int, kind: str, name: str, fields: Sequence[Element]) -> list[dict[str, Any]]:
    return [_node(level, kind, name), *[node for field in fields for node in field(level + 1)]]


def language_source_nodes() -> list[dict[str, Any]]:
    """The type tree Unity would store for the synthetic LanguageSource MonoBehaviour."""

    def string(name: str) -> Element:
        return lambda level: _string(level, name)

    def primitive(kind: str, name: str, aligned: bool = True) -> Element:
        return lambda level: _primitive(level, kind, name, aligned)

    def vector(name: str, element: Element) -> Element:
        return lambda level: _vector(level, name, element)

    def term_data(level: int) -> list[dict[str, Any]]:
        return _struct(
            level,
            "TermData",
            "data",
            [
                string("Term"),
                primitive("int", "TermType"),
                string("Description"),
                vector("Languages", string("data")),
                vector("Flags", primitive("UInt8", "data", aligned=False)),
                vector("Languages_Touch", string("data")),
            ],
        )

    def language_data(level: int) -> list[dict[str, Any]]:
        return _struct(
            level,
            "LanguageData",
            "data",
            [
                string("Name"),
                string("Code"),
                primitive("UInt8", "Flags"),
            ],
        )

    return [
        _node(0, "MonoBehaviour", "Base", meta=0x8000),
        *_pptr(1, "m_GameObject", "GameObject"),
        *_primitive(1, "UInt8", "m_Enabled"),
        *_pptr(1, "m_Script", "MonoScript"),
        *_string(1, "m_Name"),
        *_struct(
            1,
            "LanguageSourceData",
            "mSource",
            [
                primitive("bool", "CaseInsensitiveTerms"),
                vector("mTerms", term_data),
                vector("mLanguages", language_data),
                vector("Assets", lambda level: _pptr(level, "data", "Object")),
                primitive("float", "mUpdateDelay"),
            ],
        ),
    ]


def build_node(nodes: list[dict[str, Any]]) -> TypeTreeNode:
    return TypeTreeNode.from_list([{**node, "m_Index": index} for index, node in enumerate(nodes)])


def builtin_node(class_id: int) -> TypeTreeNode:
    """UnityPy's bundled Unity 2017.4 class layout with explicit flags for blob storage."""
    source = get_typetree_node(class_id, UnityVersion.from_str(UNITY_VERSION))
    nodes = []
    for item in source.to_dict_list():
        node = {key: value for key, value in item.items() if key != "m_Children"}
        node["m_TypeFlags"] = 1 if node["m_Type"] == "Array" else 0
        nodes.append(node)
    return build_node(nodes)


def payload(value: dict[str, Any], node: TypeTreeNode) -> bytes:
    writer = EndianBinaryWriter(endian="<")
    write_typetree(value, node, writer)
    return bytes(writer.bytes)


def game_object(name: str, component: int) -> bytes:
    return payload(
        {
            "m_Component": [{"component": {"m_FileID": 0, "m_PathID": component}}],
            "m_Layer": 0,
            "m_Name": name,
            "m_Tag": 0,
            "m_IsActive": True,
        },
        builtin_node(GAMEOBJECT),
    )


def mono_script(class_name: str, namespace: str, assembly: str) -> bytes:
    return payload(
        {
            "m_Name": class_name,
            "m_ExecutionOrder": 0,
            "m_PropertiesHash": {
                f"bytes[{index}]": value
                for index, value in enumerate(digest("properties", namespace, class_name))
            },
            "m_ClassName": class_name,
            "m_Namespace": namespace,
            "m_AssemblyName": assembly,
            "m_IsEditorScript": False,
        },
        builtin_node(MONOSCRIPT),
    )


# ---------------------------------------------------------- serialized file


def digest(*parts: str) -> bytes:
    return hashlib.md5("\0".join(parts).encode("utf-8"), usedforsecurity=False).digest()


@dataclass(frozen=True)
class SerializedType:
    class_id: int
    label: str
    node: TypeTreeNode | None = None
    script_index: int = -1


@dataclass(frozen=True)
class SerializedObject:
    path_id: int
    type_index: int
    data: bytes


def _align(writer: EndianBinaryWriter, size: int = 4) -> None:
    writer.write(b"\0" * (-writer.Position % size))


def serialized_file(
    types: Sequence[SerializedType],
    objects: Sequence[SerializedObject],
    *,
    type_tree: bool,
    scripts: Sequence[tuple[int, int]] = (),
    externals: Sequence[str] = (),
) -> bytes:
    """A Unity 2017.4 (format 17) little-endian serialized file."""
    meta = EndianBinaryWriter(endian="<")
    # Alignment in the metadata is relative to the file start, after the 20-byte header.
    meta.write(b"\0" * 20)
    meta.write_string_to_null(UNITY_VERSION)
    meta.write_int(STANDALONE_WINDOWS64)
    meta.write_boolean(type_tree)
    meta.write_int(len(types))
    for item in types:
        meta.write_int(item.class_id)
        meta.write_boolean(False)
        meta.write_short(item.script_index)
        if item.class_id == MONOBEHAVIOUR:
            meta.write_bytes(digest("script", item.label))
        meta.write_bytes(digest("type", item.label))
        if type_tree:
            if item.node is None:
                raise ValueError("A type tree is required for every type.")
            item.node.dump_blob(meta, FORMAT_VERSION)
    meta.write_int(len(objects))
    data = bytearray()
    for obj in objects:
        data.extend(b"\0" * (-len(data) % 8))
        _align(meta)
        meta.write_long(obj.path_id)
        meta.write_u_int(len(data))
        meta.write_u_int(len(obj.data))
        meta.write_int(obj.type_index)
        data.extend(obj.data)
    meta.write_int(len(scripts))
    for file_index, path_id in scripts:
        meta.write_int(file_index)
        _align(meta)
        meta.write_long(path_id)
    meta.write_int(len(externals))
    for path in externals:
        meta.write_string_to_null("")
        meta.write_bytes(digest("external", path))
        meta.write_int(2)  # kSerializedAssetType
        meta.write_string_to_null(path)
    meta.write_string_to_null("")
    metadata = bytes(meta.bytes)[20:]
    data_offset = 20 + len(metadata)
    data_offset += -data_offset % 16
    file_size = data_offset + len(data)
    header = struct.pack(">IIII", len(metadata), file_size, FORMAT_VERSION, data_offset)
    header += b"\0\0\0\0"  # little-endian flag and reserved bytes
    result = header + metadata
    return result + b"\0" * (data_offset - len(result)) + bytes(data)


def typetree_source(name: str = "SyntheticLanguages") -> bytes:
    """Type trees present: the ordinary I2 worker path; the MonoScript is local."""
    source = build_node(language_source_nodes())
    return serialized_file(
        [
            SerializedType(GAMEOBJECT, "GameObject", builtin_node(GAMEOBJECT)),
            SerializedType(MONOSCRIPT, "MonoScript", builtin_node(MONOSCRIPT)),
            SerializedType(MONOBEHAVIOUR, "I2.Loc.LanguageSource", source, 0),
        ],
        [
            SerializedObject(1, 0, game_object("SyntheticLanguages", 3)),
            SerializedObject(2, 1, mono_script("LanguageSource", "I2.Loc", ASSEMBLY_NAME)),
            SerializedObject(3, 2, payload(language_source(name, 0, 2), source)),
        ],
        type_tree=True,
        scripts=[(0, 2)],
    )


def managed_source(source_suffix: bytes = b"", source_trim: int = 0) -> bytes:
    """No type trees: the I2 object needs the managed-metadata fallback.

    Component names are empty as in built games, so the source-set name comes from the
    GameObject. A second MonoBehaviour uses a non-I2 script and must be skipped."""
    source = payload(language_source("", 1, 1), build_node(language_source_nodes()))
    source = source[: len(source) - source_trim] + source_suffix
    label = payload(
        {**mono_behaviour_fields("", 1, 2, game_object=3), "text": "never read"},
        build_node(
            [
                _node(0, "MonoBehaviour", "Base"),
                *_pptr(1, "m_GameObject", "GameObject"),
                *_primitive(1, "UInt8", "m_Enabled"),
                *_pptr(1, "m_Script", "MonoScript"),
                *_string(1, "m_Name"),
                *_string(1, "text"),
            ]
        ),
    )
    return serialized_file(
        [
            SerializedType(GAMEOBJECT, "GameObject"),
            SerializedType(MONOBEHAVIOUR, "I2.Loc.LanguageSource", script_index=0),
            SerializedType(MONOBEHAVIOUR, "Synthetic.Ui.MenuLabel", script_index=1),
        ],
        [
            SerializedObject(1, 0, game_object("SyntheticLanguages", 2)),
            SerializedObject(2, 1, source),
            SerializedObject(3, 0, game_object("MenuLabel", 4)),
            SerializedObject(4, 2, label),
        ],
        type_tree=False,
        scripts=[(1, 1), (1, 2)],
        externals=[SCRIPTS_FILE],
    )


def scripts_file() -> bytes:
    return serialized_file(
        [SerializedType(MONOSCRIPT, "MonoScript")],
        [
            SerializedObject(1, 0, mono_script("LanguageSource", "I2.Loc", ASSEMBLY_NAME)),
            SerializedObject(2, 0, mono_script("MenuLabel", "Synthetic.Ui", UI_ASSEMBLY_NAME)),
        ],
        type_tree=False,
    )


# ------------------------------------------------------------ .NET metadata


def _compressed(value: int) -> bytes:
    if value < 0x80:
        return bytes([value])
    if value < 0x4000:
        return struct.pack(">H", value | 0x8000)
    return struct.pack(">I", value | 0xC0000000)


class _Heaps:
    def __init__(self) -> None:
        self.strings = bytearray(b"\0")
        self.blobs = bytearray(b"\0")
        self.guids = bytearray()
        self._strings: dict[str, int] = {"": 0}
        self._blobs: dict[bytes, int] = {b"": 0}

    def string(self, value: str) -> int:
        if value not in self._strings:
            self._strings[value] = len(self.strings)
            self.strings.extend(value.encode("utf-8") + b"\0")
        return self._strings[value]

    def blob(self, value: bytes) -> int:
        if value not in self._blobs:
            self._blobs[value] = len(self.blobs)
            self.blobs.extend(_compressed(len(value)) + value)
        return self._blobs[value]

    def guid(self, value: bytes) -> int:
        self.guids.extend(value)
        return len(self.guids) // 16


# Field flags (ECMA-335 II.23.1.5) and type flags (II.23.1.15).
PUBLIC, PRIVATE, STATIC, LITERAL, NOT_SERIALIZED = 0x0006, 0x0001, 0x0010, 0x0040, 0x0080
SPECIAL_NAME = 0x0600
TYPE_PUBLIC, TYPE_SEALED, TYPE_SERIALIZABLE, BEFORE_FIELD_INIT = 0x1, 0x100, 0x2000, 0x100000

# TypeRef rows (1-based): (scope AssemblyRef row, namespace, name).
TYPE_REFS = [
    (1, "UnityEngine", "MonoBehaviour"),
    (1, "UnityEngine", "Object"),
    (1, "UnityEngine", "SerializeField"),
    (2, "System", "Object"),
    (2, "System", "Enum"),
    (2, "System.Collections.Generic", "List`1"),
]
REF = {f"{namespace}.{name}": index + 1 for index, (_, namespace, name) in enumerate(TYPE_REFS)}
DEF = {
    "LanguageSource": 2,
    "LanguageSourceData": 3,
    "TermData": 4,
    "eTermType": 5,
    "LanguageData": 6,
}


def _type_ref(row: int) -> bytes:
    return _compressed(row << 2 | 1)


def _type_def(row: int) -> bytes:
    return _compressed(row << 2)


def _list(element: bytes) -> bytes:
    return b"\x15\x12" + _type_ref(REF["System.Collections.Generic.List`1"]) + b"\x01" + element


STRING, BOOL, BYTE, INT, FLOAT = b"\x0e", b"\x02", b"\x05", b"\x08", b"\x0c"

# (namespace, name, flags, base TypeRef or None, fields as (name, flags, type signature)).
TYPE_DEFS: list[tuple[str, str, int, int | None, list[tuple[str, int, bytes]]]] = [
    ("", "<Module>", 0, None, []),
    (
        "I2.Loc",
        "LanguageSource",
        TYPE_PUBLIC | BEFORE_FIELD_INIT,
        REF["UnityEngine.MonoBehaviour"],
        [
            ("mSource", PUBLIC, b"\x12" + _type_def(DEF["LanguageSourceData"])),
            ("EmptyCategory", PUBLIC | STATIC, STRING),
            ("mIsGlobalSource", PUBLIC | NOT_SERIALIZED, BOOL),
            ("mLoadedFrame", PRIVATE, INT),
        ],
    ),
    (
        "I2.Loc",
        "LanguageSourceData",
        TYPE_PUBLIC | TYPE_SERIALIZABLE | BEFORE_FIELD_INIT,
        REF["System.Object"],
        [
            ("CaseInsensitiveTerms", PUBLIC, BOOL),
            ("mTerms", PUBLIC, _list(b"\x12" + _type_def(DEF["TermData"]))),
            ("mLanguages", PUBLIC, _list(b"\x12" + _type_def(DEF["LanguageData"]))),
            ("Assets", PUBLIC, _list(b"\x12" + _type_ref(REF["UnityEngine.Object"]))),
            ("mUpdateDelay", PRIVATE, FLOAT),  # [SerializeField]
            ("mOwner", PRIVATE, b"\x12" + _type_def(DEF["LanguageSource"])),
        ],
    ),
    (
        "I2.Loc",
        "TermData",
        TYPE_PUBLIC | TYPE_SERIALIZABLE | BEFORE_FIELD_INIT,
        REF["System.Object"],
        [
            ("Term", PUBLIC, STRING),
            ("TermType", PUBLIC, b"\x11" + _type_def(DEF["eTermType"])),
            ("Description", PUBLIC, STRING),
            ("Languages", PUBLIC, b"\x1d" + STRING),
            ("Flags", PUBLIC, b"\x1d" + BYTE),
            ("Languages_Touch", PUBLIC, b"\x1d" + STRING),
        ],
    ),
    (
        "I2.Loc",
        "eTermType",
        TYPE_PUBLIC | TYPE_SEALED | TYPE_SERIALIZABLE,
        REF["System.Enum"],
        [
            ("value__", PUBLIC | SPECIAL_NAME, INT),
            ("Text", PUBLIC | STATIC | LITERAL, b"\x11" + _type_def(DEF["eTermType"])),
            ("Font", PUBLIC | STATIC | LITERAL, b"\x11" + _type_def(DEF["eTermType"])),
        ],
    ),
    (
        "I2.Loc",
        "LanguageData",
        TYPE_PUBLIC | TYPE_SERIALIZABLE | BEFORE_FIELD_INIT,
        REF["System.Object"],
        [
            ("Name", PUBLIC, STRING),
            ("Code", PUBLIC, STRING),
            ("Flags", PUBLIC, BYTE),
        ],
    ),
]
SERIALIZE_FIELD = ("LanguageSourceData", "mUpdateDelay")


def metadata() -> bytes:
    heaps = _Heaps()
    u16 = struct.Struct("<H").pack
    tables: dict[int, list[bytes]] = {}
    tables[0x00] = [
        u16(0)
        + u16(heaps.string(ASSEMBLY_NAME))
        + u16(heaps.guid(uuid.uuid5(uuid.NAMESPACE_URL, "synthetic:i2").bytes_le))
        + u16(0)
        + u16(0)
    ]
    tables[0x01] = [
        u16(scope << 2 | 2) + u16(heaps.string(name)) + u16(heaps.string(namespace))
        for scope, namespace, name in TYPE_REFS
    ]
    tables[0x02], tables[0x04] = [], []
    serialize_field = 0
    for namespace, name, flags, base, fields in TYPE_DEFS:
        extends = 0 if base is None else base << 2 | 1
        tables[0x02].append(
            struct.pack("<I", flags)
            + u16(heaps.string(name))
            + u16(heaps.string(namespace))
            + u16(extends)
            + u16(len(tables[0x04]) + 1)
            + u16(1)
        )
        for field, field_flags, signature in fields:
            tables[0x04].append(
                u16(field_flags) + u16(heaps.string(field)) + u16(heaps.blob(b"\x06" + signature))
            )
            if (name, field) == SERIALIZE_FIELD:
                serialize_field = len(tables[0x04])
    # MemberRef: SerializeField::.ctor() (HASTHIS, no parameters, void).
    tables[0x0A] = [
        u16(REF["UnityEngine.SerializeField"] << 3 | 1)
        + u16(heaps.string(".ctor"))
        + u16(heaps.blob(b"\x20\x00\x01"))
    ]
    # CustomAttribute: [SerializeField] on the private field (Field tag 1, MemberRef tag 3).
    tables[0x0C] = [
        u16(serialize_field << 5 | 1) + u16(1 << 3 | 3) + u16(heaps.blob(b"\x01\x00\x00\x00"))
    ]
    tables[0x20] = [
        struct.pack("<IHHHHI", 0x8004, 1, 0, 0, 0, 0)
        + u16(0)
        + u16(heaps.string("Synthetic.I2"))
        + u16(0)
    ]
    tables[0x23] = [
        struct.pack("<HHHHI", major, 0, 0, 0, 0)
        + u16(0)
        + u16(heaps.string(name))
        + u16(0)
        + u16(0)
        for name, major in (("UnityEngine", 0), ("mscorlib", 2))
    ]
    valid = sum(1 << table for table in tables)
    stream = bytearray(struct.pack("<IBBBBQQ", 0, 2, 0, 0, 1, valid, 0x000016003301FA00))
    for table in sorted(tables):
        stream.extend(struct.pack("<I", len(tables[table])))
    for table in sorted(tables):
        for row in tables[table]:
            stream.extend(row)
    streams = [
        ("#~", bytes(stream)),
        ("#Strings", bytes(heaps.strings)),
        ("#US", b"\0"),
        ("#GUID", bytes(heaps.guids)),
        ("#Blob", bytes(heaps.blobs)),
    ]
    version = b"v2.0.50727\0\0"
    headers = bytearray()
    for name, _ in streams:
        encoded = name.encode("ascii") + b"\0"
        headers.extend(b"\0" * 8 + encoded + b"\0" * (-len(encoded) % 4))
    offset = 16 + len(version) + 4 + len(headers)
    root = bytearray(struct.pack("<IHHII", 0x424A5342, 1, 1, 0, len(version)) + version)
    root.extend(struct.pack("<HH", 0, len(streams)))
    body = bytearray()
    for name, data in streams:
        padded = data + b"\0" * (-len(data) % 4)
        encoded = name.encode("ascii") + b"\0"
        root.extend(struct.pack("<II", offset + len(body), len(padded)))
        root.extend(encoded + b"\0" * (-len(encoded) % 4))
        body.extend(padded)
    return bytes(root + body)


def assembly() -> bytes:
    """A 32-bit IL-only DLL image that carries metadata and nothing executable."""
    section_rva, file_alignment, section_alignment = 0x2000, 0x200, 0x2000
    meta = metadata()
    cli = struct.pack("<IHHIIII", 72, 2, 5, section_rva + 72, len(meta), 1, 0) + b"\0" * 48
    text = cli + meta
    raw_size = len(text) + (-len(text) % file_alignment)
    dos = b"MZ" + b"\0" * 58 + struct.pack("<I", 0x80)
    dos += b"\0" * (0x80 - len(dos))
    coff = struct.pack("<HHIIIHH", 0x14C, 1, 0, 0, 0, 0xE0, 0x2102)
    directories = [(0, 0)] * 16
    directories[14] = (section_rva, 72)
    optional = struct.pack(
        "<HBBIIIIIIIIIHHHHHHIIIIHHIIIIII",
        0x10B,
        8,
        0,
        raw_size,
        0,
        0,
        0,
        section_rva,
        0,
        0x10000000,
        section_alignment,
        file_alignment,
        4,
        0,
        0,
        0,
        4,
        0,
        0,
        section_rva + section_alignment,
        file_alignment,
        0,
        3,
        0x8540,
        0x100000,
        0x1000,
        0x100000,
        0x1000,
        0,
        16,
    ) + b"".join(struct.pack("<II", *item) for item in directories)
    section = struct.pack(
        "<8sIIIIIIHHI",
        b".text",
        len(text),
        section_rva,
        raw_size,
        file_alignment,
        0,
        0,
        0,
        0,
        0x60000020,
    )
    headers = dos + b"PE\0\0" + coff + optional + section
    headers += b"\0" * (file_alignment - len(headers))
    return headers + text + b"\0" * (raw_size - len(text))


# --------------------------------------------------------------------- entry


def fixtures() -> dict[str, bytes]:
    return {
        "typetree.bin": typetree_source(),
        "managed.bin": managed_source(),
        "scripts.bin": scripts_file(),
        "assembly.bin": assembly(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="Compare without writing")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args(argv)
    stale = []
    for name, data in fixtures().items():
        target = args.output / name
        if args.check:
            if not target.is_file() or target.read_bytes() != data:
                stale.append(name)
        else:
            target.write_bytes(data)
            print(f"{name}: {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}")
    if stale:
        print("Stale fixtures: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
