"""Read bounded RPA-3.0 literal indexes without unpickling or importing game code.

The index grammar is deliberately smaller than pickle: only primitive values,
lists, tuples, dictionaries and memo references are accepted. Object/global/call
opcodes are rejected, never resolved. This is not a compiled-script reader.
"""

import pickletools
import re
import zlib
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from unitytranslator.filesystem import checked_path
from unitytranslator.source_contracts import validate_relative_source

MAX_COMPRESSED_INDEX = 4 * 1024 * 1024
MAX_INDEX = 8 * 1024 * 1024
MAX_OPERATIONS = 200000
MAX_MEMBERS = 20000
MAX_STACK = 4096
MAX_MEMBER = 8 * 1024 * 1024
_MARK = object()
_HEADER = re.compile(rb"RPA-3\.0 ([0-9a-fA-F]{16}) ([0-9a-fA-F]{8})\n")


def literal_index(raw: bytes) -> dict[str, Any]:
    """Interpret a fixed literal opcode grammar; never use pickle.load/loads."""
    if not raw or len(raw) > MAX_INDEX:
        raise ValueError("RPA literal index size limit exceeded.")
    stack: list[Any] = []
    memo: dict[int, Any] = {}
    stopped = False

    def marked() -> list[Any]:
        for i in range(len(stack) - 1, -1, -1):
            if stack[i] is _MARK:
                values = stack[i + 1:]
                del stack[i:]
                return values
        raise ValueError("Malformed RPA literal index stack.")

    try:
        for count, (operation, argument, position) in enumerate(pickletools.genops(raw), 1):
            if count > MAX_OPERATIONS or len(stack) > MAX_STACK or len(memo) > MAX_OPERATIONS:
                raise ValueError("RPA literal index operation limit exceeded.")
            name = operation.name
            if name == "PROTO":
                if count != 1 or argument not in (2, 3, 4, 5):
                    raise ValueError("Unsupported RPA literal index protocol.")
            elif name == "FRAME":
                if (
                    type(argument) is not int or position is None
                    or not 0 <= argument <= len(raw) - position - 9
                ):
                    raise ValueError("Invalid RPA literal index frame.")
            elif name == "EMPTY_DICT":
                stack.append({})
            elif name == "EMPTY_LIST":
                stack.append([])
            elif name == "EMPTY_TUPLE":
                stack.append(())
            elif name == "MARK":
                stack.append(_MARK)
            elif name in {"BININT", "BININT1", "BININT2", "LONG1", "LONG4"}:
                if type(argument) is not int or not -(1 << 63) <= argument < (1 << 63):
                    raise ValueError("RPA literal index integer out of bounds.")
                stack.append(argument)
            elif name in {"SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8"}:
                if not isinstance(argument, str) or len(argument) > 4096:
                    raise ValueError("RPA literal index string out of bounds.")
                stack.append(argument)
            elif name in {"SHORT_BINBYTES", "BINBYTES", "BINBYTES8"}:
                if not isinstance(argument, bytes) or len(argument) > 4096:
                    raise ValueError("RPA literal index prefix out of bounds.")
                stack.append(argument)
            elif name in {"TUPLE1", "TUPLE2", "TUPLE3"}:
                size = int(name[-1])
                if len(stack) < size or any(item is _MARK for item in stack[-size:]):
                    raise ValueError("Malformed RPA tuple.")
                tuple_values = tuple(stack[-size:])
                del stack[-size:]
                stack.append(tuple_values)
            elif name == "TUPLE":
                stack.append(tuple(marked()))
            elif name in {"APPEND", "APPENDS"}:
                values = [stack.pop()] if name == "APPEND" else marked()
                if not stack or type(stack[-1]) is not list or len(stack[-1]) + len(values) > 64:
                    raise ValueError("Invalid or oversized RPA fragment list.")
                stack[-1].extend(values)
            elif name in {"SETITEM", "SETITEMS"}:
                values = [stack.pop(), stack.pop()][::-1] if name == "SETITEM" else marked()
                if not stack or type(stack[-1]) is not dict or len(values) % 2:
                    raise ValueError("Malformed RPA member dictionary.")
                target = stack[-1]
                for i in range(0, len(values), 2):
                    key = values[i]
                    if type(key) is not str or key in target or len(target) >= MAX_MEMBERS:
                        raise ValueError("Duplicate, invalid or excessive RPA member names.")
                    target[key] = values[i + 1]
            elif name in {"MEMOIZE", "BINPUT", "LONG_BINPUT"}:
                key = len(memo) if name == "MEMOIZE" else argument
                if (
                    not stack or type(key) is not int
                    or not 0 <= key <= MAX_OPERATIONS or key in memo
                ):
                    raise ValueError("Invalid RPA literal memo assignment.")
                memo[key] = stack[-1]
            elif name in {"BINGET", "LONG_BINGET"}:
                if argument not in memo:
                    raise ValueError("Unknown RPA literal memo reference.")
                stack.append(memo[argument])
            elif name == "STOP":
                if position != len(raw) - 1 or len(stack) != 1 or type(stack[0]) is not dict:
                    raise ValueError("Ambiguous RPA literal index result.")
                stopped = True
            else:
                raise ValueError("Unsupported non-literal RPA index opcode: " + name)
    except (IndexError, OverflowError, UnicodeError) as exc:
        raise ValueError("Malformed RPA literal index.") from exc
    if not stopped:
        raise ValueError("Incomplete RPA literal index.")
    result: dict[str, Any] = stack[0]
    return result


@dataclass(frozen=True)
class ArchiveMember:
    name: str
    offset: int
    length: int
    prefix: bytes


@dataclass(frozen=True)
class ArchiveIndex:
    path: Path
    index_offset: int
    size: int
    index_sha256: str
    members: tuple[ArchiveMember, ...]

    def read_member(self, name: str, *, limit: int = MAX_MEMBER) -> bytes:
        """Return one bounded member as bytes, never write an archive-selected path."""
        if not 0 < limit <= MAX_MEMBER:
            raise ValueError("Invalid RPA member read limit.")
        candidates = [member for member in self.members if member.name == name]
        if len(candidates) != 1 or candidates[0].length > limit:
            raise ValueError("RPA member missing, ambiguous or oversized.")
        if read_index(self.path).index_sha256 != self.index_sha256:
            raise ValueError("RPA index changed before member reading.")
        member = candidates[0]
        with checked_path(self.path).open("rb") as stream:
            stream.seek(member.offset)
            payload = stream.read(member.length - len(member.prefix))
        result = member.prefix + payload
        if len(result) != member.length or self.path.stat().st_size != self.size:
            raise ValueError("RPA member truncated or archive size changed.")
        return result


def read_index(path: Path) -> ArchiveIndex:
    path = checked_path(path)
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.readline(128)
        match = _HEADER.fullmatch(header)
        if match is None:
            raise ValueError("Only the bounded RPA-3.0 archive subset is supported.")
        offset, key = int(match[1], 16), int(match[2], 16)
        if not len(header) <= offset < size or size - offset > MAX_COMPRESSED_INDEX:
            raise ValueError("RPA index offset or compressed-size limit is invalid.")
        stream.seek(offset)
        compressed = stream.read(MAX_COMPRESSED_INDEX + 1)
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(compressed, MAX_INDEX + 1)
    except zlib.error as exc:
        raise ValueError("Invalid compressed RPA index.") from exc
    if len(raw) > MAX_INDEX or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("RPA index exceeds its bounds or contains trailing data.")
    members = []
    names: set[str] = set()
    for name, chunks in literal_index(raw).items():
        validate_relative_source(name)
        if (
            "\\" in name or any(part in ("", ".", "..") for part in name.split("/"))
            or name.casefold() in names
        ):
            raise ValueError("Ambiguous RPA member path.")
        names.add(name.casefold())
        if type(chunks) is not list or len(chunks) != 1:
            raise ValueError("Multi-fragment RPA members are outside the supported subset.")
        chunk = chunks[0]
        if type(chunk) is not tuple or len(chunk) not in (2, 3):
            raise ValueError("Invalid RPA member descriptor.")
        if type(chunk[0]) is not int or type(chunk[1]) is not int:
            raise ValueError("Invalid RPA member offset/length types.")
        start, length = chunk[0] ^ key, chunk[1] ^ key
        prefix = chunk[2] if len(chunk) == 3 else b""
        if (
            type(prefix) is not bytes or len(prefix) > length or length < 0
            or start < len(header) or start + length - len(prefix) > offset
        ):
            raise ValueError("RPA member points outside its data region.")
        members.append(ArchiveMember(name, start, length, prefix))
    if path.stat().st_size != size:
        raise ValueError("RPA archive changed during index reading.")
    return ArchiveIndex(path, offset, size, sha256(header + compressed).hexdigest(), tuple(members))


def inspect_archive(path: Path) -> dict[str, Any]:
    """Report verified container evidence, without implying text extraction support."""
    index = read_index(path)
    counts: dict[str, int] = {}
    for member in index.members:
        extension = Path(member.name).suffix.lower()
        counts[extension] = counts.get(extension, 0) + 1
    return {
        "status": "verified_literal_index", "format": "RPA-3.0-literal-v1",
        "index_sha256": index.index_sha256, "members": len(index.members),
        "extensions": dict(sorted(counts.items())),
        "translation_templates": sum(
            member.name.startswith("tl/") and member.name.endswith(".rpy")
            for member in index.members
        ),
        "renpy_python_sources": sum(
            member.name.lower().endswith("_ren.py") for member in index.members
        ),
        "extraction": "unsupported", "installation": "unsupported",
    }
