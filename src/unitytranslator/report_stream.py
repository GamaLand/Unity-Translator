"""Bounded framed JSON reports; no object deserialization or worker-selected paths."""

import json
import math
from collections.abc import Callable, Iterator
from hashlib import sha256
from typing import Any, Protocol, TextIO

from unitytranslator.json_boundary import strict_json

PROTOCOL = "reader-report-v1"
MAX_FRAME_BYTES = 256 * 1024
MAX_VALUE_BYTES = 128 * 1024
MAX_REPORT_BYTES = 256 * 1024 * 1024
MAX_FRAMES = 1_000_000
MAX_NODES = 4_000_000
MAX_DEPTH = 32
MAX_STRING_BYTES = 4 * 1024 * 1024
_ENCODER = json.JSONEncoder(ensure_ascii=True, separators=(",", ":"), allow_nan=False)


class ReportInput(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...

    def readline(self, size: int = -1, /) -> bytes: ...


def report_digest(value: dict[str, Any]) -> str:
    """Hash canonical data without allocating another complete encoded report."""
    digest = sha256()
    encoder = json.JSONEncoder(
        ensure_ascii=True, separators=(",", ":"), sort_keys=True, allow_nan=False,
    )
    for piece in encoder.iterencode(value):
        digest.update(piece.encode("ascii"))
    return digest.hexdigest()


def _small_json(value: Any) -> str | None:
    pieces = []
    size = 0
    for piece in _ENCODER.iterencode(value):
        size += len(piece)
        if size > MAX_VALUE_BYTES:
            return None
        pieces.append(piece)
    return "".join(pieces)


def _events(value: Any, path: list[str | int]) -> Iterator[dict[str, Any]]:
    if len(path) > MAX_DEPTH:
        raise ValueError("Reader report nesting limit exceeded.")
    small = _small_json(value)
    if small is not None:
        yield {"event": "value", "path": path, "value": value}
    elif isinstance(value, dict):
        yield {"event": "dict", "path": path}
        for key, child in value.items():
            yield from _events(child, [*path, key])
    elif isinstance(value, list):
        yield {"event": "list", "path": path}
        for index, child in enumerate(value):
            yield from _events(child, [*path, index])
    elif isinstance(value, str):
        yield {"event": "string", "path": path}
        for start in range(0, len(value), 8192):
            yield {"event": "append", "path": path, "value": value[start:start + 8192]}
        yield {"event": "string_end", "path": path}
    else:
        raise ValueError("Unsupported reader report value.")


def write_report(value: dict[str, Any], stream: TextIO) -> None:
    """Write bounded frames rather than one report-sized JSON string."""
    digest = sha256()
    count, size = 0, 0
    raw = _ENCODER.encode({"event": "begin", "protocol": PROTOCOL}) + "\n"
    stream.write(raw)
    digest.update(raw.encode("ascii"))
    size += len(raw)
    for event in _events(value, []):
        raw = _ENCODER.encode(event) + "\n"
        count += 1
        size += len(raw)
        if len(raw) > MAX_FRAME_BYTES or size > MAX_REPORT_BYTES or count > MAX_FRAMES:
            raise ValueError("Reader report frame or total-size limit exceeded.")
        stream.write(raw)
        digest.update(raw.encode("ascii"))
    raw = _ENCODER.encode({"event": "end", "frames": count,
                           "sha256": digest.hexdigest()}) + "\n"
    if size + len(raw) > MAX_REPORT_BYTES:
        raise ValueError("Reader report total-size limit exceeded.")
    stream.write(raw)


def read_report(
    stream: ReportInput, *, cancelled: Callable[[], bool], max_bytes: int = MAX_REPORT_BYTES,
) -> dict[str, Any]:
    """Assemble verified frames with strict ordering, size, depth and node budgets."""
    digest = sha256()
    count, size, nodes = 0, 0, 0
    root: list[Any] = []
    string_path: list[str | int] | None = None
    string_parts: list[str] = []
    string_bytes = 0

    def line() -> tuple[bytes, dict[str, Any]]:
        nonlocal size
        if cancelled():
            raise ValueError("Source extraction was cancelled.")
        raw = stream.readline(MAX_FRAME_BYTES + 1)
        size += len(raw)
        if not raw or not raw.endswith(b"\n") or len(raw) > MAX_FRAME_BYTES or size > max_bytes:
            raise ValueError("Incomplete or oversized reader report frame.")
        try:
            event = strict_json(raw)
        except (ValueError, RecursionError) as exc:
            raise ValueError("Invalid reader report frame.") from exc
        if not isinstance(event, dict):
            raise ValueError("Reader report frame must be an object.")
        # Windows text stdout may encode LF as CRLF. Hash the protocol's LF
        # terminator while retaining the actual-byte transport budget above.
        return raw[:-2] + b"\n" if raw.endswith(b"\r\n") else raw, event

    def check_value(value: Any, depth: int) -> None:
        nonlocal nodes
        pending = [(value, depth)]
        while pending:
            child, level = pending.pop()
            nodes += 1
            if nodes > MAX_NODES or level > MAX_DEPTH:
                raise ValueError("Reader report node or nesting limit exceeded.")
            if isinstance(child, dict):
                if any(not isinstance(key, str) or len(key) > 4096 for key in child):
                    raise ValueError("Invalid reader report key.")
                pending.extend((item, level + 1) for item in child.values())
            elif isinstance(child, list):
                pending.extend((item, level + 1) for item in child)
            elif isinstance(child, str):
                if len(child.encode("utf-8")) > MAX_STRING_BYTES:
                    raise ValueError("Reader report string limit exceeded.")
            elif child is not None and type(child) not in (bool, int, float):
                raise ValueError("Invalid reader report value.")
            elif type(child) is float and not math.isfinite(child):
                raise ValueError("Invalid reader report number.")

    def put(path: list[str | int], value: Any) -> None:
        if not path:
            if root:
                raise ValueError("Duplicate reader report root.")
            root.append(value)
            return
        if not root:
            raise ValueError("Reader report root is missing.")
        parent = root[0]
        for key in path[:-1]:
            if isinstance(parent, dict) and type(key) is str and key in parent:
                parent = parent[key]
            elif isinstance(parent, list) and type(key) is int and 0 <= key < len(parent):
                parent = parent[key]
            else:
                raise ValueError("Invalid reader report parent.")
        last = path[-1]
        if isinstance(parent, dict) and type(last) is str and last not in parent:
            parent[last] = value
        elif isinstance(parent, list) and type(last) is int and last == len(parent):
            parent.append(value)
        else:
            raise ValueError("Duplicate or out-of-order reader report path.")

    raw, start = line()
    if start != {"event": "begin", "protocol": PROTOCOL}:
        raise ValueError("Unknown reader report protocol.")
    digest.update(raw)
    while True:
        raw, event = line()
        kind = event.get("event")
        if kind == "end":
            if (
                event != {"event": "end", "frames": count, "sha256": digest.hexdigest()}
                or type(event.get("frames")) is not int
                or string_path is not None or len(root) != 1 or not isinstance(root[0], dict)
                or stream.read(1)
            ):
                raise ValueError("Incomplete, altered or trailing reader report.")
            result: dict[str, Any] = root[0]
            return result
        count += 1
        digest.update(raw)
        if count > MAX_FRAMES:
            raise ValueError("Reader report frame count limit exceeded.")
        path = event.get("path")
        if not isinstance(path, list) or len(path) > MAX_DEPTH or any(
            not ((type(key) is str and len(key) <= 4096) or (type(key) is int and key >= 0))
            for key in path
        ):
            raise ValueError("Invalid reader report path.")
        fields = {"event", "path", "value"} if kind in ("value", "append") else {"event", "path"}
        if set(event) != fields:
            raise ValueError("Invalid reader report frame fields.")
        if string_path is not None:
            if path != string_path or kind not in ("append", "string_end"):
                raise ValueError("Interrupted reader report string.")
            if kind == "append":
                part = event["value"]
                if not isinstance(part, str):
                    raise ValueError("Invalid reader report string chunk.")
                string_bytes += len(part.encode("utf-8"))
                if string_bytes > MAX_STRING_BYTES:
                    raise ValueError("Reader report string limit exceeded.")
                string_parts.append(part)
            else:
                value = "".join(string_parts)
                check_value(value, len(path))
                put(path, value)
                string_path, string_parts = None, []
            continue
        if kind == "string":
            string_path, string_parts, string_bytes = path, [], 0
        elif kind in ("dict", "list", "value"):
            value = {} if kind == "dict" else [] if kind == "list" else event["value"]
            check_value(value, len(path))
            put(path, value)
        else:
            raise ValueError("Unknown reader report event.")
