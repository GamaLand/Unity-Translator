"""Static parser for a strict subset of generated native translation templates.

Only paired-comment say statements and old/new string pairs are accepted. There
is no Python parser, engine import, archive reader or compiled-object deserializer.
Offsets refer to decoded UTF-8 characters; the complete original bytes are retained.
"""

import base64
import keyword
import re
from dataclasses import asdict, dataclass
from hashlib import sha256

from unitytranslator.domain import TextUnitDraft
from unitytranslator.renpy_format import RENPY_FORMAT, tokens
from unitytranslator.renpy_say import SYNTAX_VERSION, SayShape, symbolic_prefix
from unitytranslator.source_contracts import (
    SourceDescriptor,
    SourceSnapshot,
    validate_relative_source,
)

PARSER_VERSION = "renpy-template-v1"
ADAPTER_ID = "renpy-templates"
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 10000
MAX_CONTEXT_BYTES = 64 * 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_HEADER = re.compile(r"translate ([A-Za-z_][A-Za-z_0-9]*) ([A-Za-z_][A-Za-z_0-9]*):")
_RESERVED = {
    "None", "python", "style", "strings", "default", "init", "old", "new", "translate",
    "label", "jump", "call", "return", "scene", "show", "hide", "with", "image",
    "menu", "screen", "define", "transform", "pause", "play", "stop", "voice", "nvl",
    "window", "camera", "layeredimage", "rpy", "pass", "extend",
}


def language_identifier(value: str) -> str:
    if (
        not _IDENTIFIER.fullmatch(value) or value in _RESERVED
        or keyword.iskeyword(value) or len(value) > 128
    ):
        raise ValueError("Select an explicit non-default Ren'Py language identifier.")
    return value


def quoted_literal(value: str) -> str:
    """Emit a single fixed-grammar literal; text never supplies script syntax."""
    if "\x00" in value or len(value) > 1_000_000:
        raise ValueError("Invalid Ren'Py string literal.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace(
        "\r", "\\u000d"
    ).replace("\n", "\\n") + '"'


def say_quoted_literal(value: str) -> str:
    """Ren'Py say literals collapse raw spaces; Python string-table literals do not."""
    return re.sub(r"(?<= ) ", r"\\ ", quoted_literal(value))


def read_literal(value: str, start: int = 0, *, say: bool = False) -> tuple[str, int]:
    if start >= len(value) or value[start] not in "\"'" or value[start:start + 3] in (
        '"""', "'''"
    ):
        raise ValueError("Only single-line quoted Ren'Py literals are supported.")
    quote, index = value[start], start + 1
    output: list[str] = []
    escapes = {"n": "\n", "r": "r" if say else "\r", "\\": "\\", '"': '"', "'": "'"}
    if say:
        escapes[" "] = " "
    while index < len(value):
        character = value[index]
        if character == quote:
            return "".join(output), index + 1
        if character in "\r\n\x00\t":
            raise ValueError("Unsupported control character in Ren'Py literal.")
        if say and character == " " and value[index - 1] == " ":
            index += 1
            continue
        if character == "\\":
            index += 1
            if value[index:index + 5] == "u000d":
                output.append("\r")
                index += 5
                continue
            if index >= len(value) or value[index] not in escapes:
                raise ValueError("Unsupported Ren'Py literal escape.")
            character = escapes[value[index]]
        output.append(character)
        index += 1
    raise ValueError("Unterminated Ren'Py literal.")


def _say(value: str) -> tuple[SayShape, str, int, int]:
    start = next((i for i, char in enumerate(value) if char in "\"'"), -1)
    if start < 0 or (start and value[start - 1] != " "):
        raise ValueError("Unsupported Ren'Py say structure.")
    shape = symbolic_prefix(value[:start - 1] if start else "")
    text, end = read_literal(value, start, say=True)
    suffix = value[end:]
    if suffix not in ("", " nointeract"):
        raise ValueError("Unsupported Ren'Py say suffix.")
    shape = SayShape(shape.speaker, shape.attributes, shape.temporary_attributes,
                     suffix == " nointeract")
    return shape, text, start, end


@dataclass(frozen=True)
class TemplateRecord:
    kind: str
    block: str
    slot: int
    speaker: str
    source: str
    candidate: str
    literal_start: int
    literal_end: int
    line: int
    attributes: tuple[str, ...] = ()
    temporary_attributes: tuple[str, ...] = ()
    nointeract: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", tuple(self.attributes))
        object.__setattr__(self, "temporary_attributes", tuple(self.temporary_attributes))

    def say_shape(self) -> SayShape:
        return SayShape(self.speaker, self.attributes, self.temporary_attributes, self.nointeract)


@dataclass(frozen=True)
class TemplateDocument:
    raw: bytes
    language: str
    records: tuple[TemplateRecord, ...]

    def snapshot(self, relative: str, source_language: str) -> SourceSnapshot:
        validate_relative_source(relative)
        if "\\" in relative:
            raise ValueError("Ren'Py logical source paths must use forward slashes.")
        logical = PARSER_VERSION + ":" + relative
        descriptor = SourceDescriptor(
            logical, ADAPTER_ID, "native-template-v1:" + self.language,
            PARSER_VERSION, relative, -1, source_language,
            sha256(self.raw).hexdigest(), RENPY_FORMAT,
        )
        shapes: dict[str, list[tuple[object, ...]]] = {}
        for record in self.records:
            if record.kind == "dialogue":
                # Keep the historical shape for unchanged plain statements.
                shape: tuple[object, ...] = (record.speaker, record.source)
                if record.attributes or record.temporary_attributes or record.nointeract:
                    shape += (record.attributes, record.temporary_attributes, record.nointeract)
                shapes.setdefault(record.block, []).append(shape)
        structures = {
            block: sha256(repr(shape).encode()).hexdigest() for block, shape in shapes.items()
        }
        units = []
        entries = []
        context_bytes = 0
        for record in self.records:
            key = record.source if record.kind == "string" else f"{record.block}:{record.slot}"
            identity = "\x00".join((PARSER_VERSION, relative, record.kind, key))
            unit_id = "renpy-v1:" + sha256(identity.encode()).hexdigest()
            structure = structures[record.block] if record.kind == "dialogue" else sha256(
                key.encode()
            ).hexdigest()
            context = (
                f"Ren'Py {record.kind}; block={record.block}; slot={record.slot}; "
                f"speaker={record.speaker or 'narrator'}; "
                f"structure={structure}"
            )
            context_bytes += len(context.encode("utf-8"))
            if context_bytes > MAX_CONTEXT_BYTES:
                raise ValueError("Ren'Py aggregate review context size limit exceeded.")
            units.append(TextUnitDraft(
                unit_id, f"{record.kind}/{record.block}/{record.slot}", relative, -1,
                source_language, record.source, sha256(record.source.encode()).hexdigest(),
                "dialogue" if record.kind == "dialogue" else "interface", context,
            ))
            entries.append({"unit_id": unit_id, **asdict(record),
                            "attributes": list(record.attributes),
                            "temporary_attributes": list(record.temporary_attributes)})
        return SourceSnapshot(descriptor, tuple(units), {
            "logical_id": logical,
            "raw_base64": base64.b64encode(self.raw).decode("ascii"),
            "encoding": "utf-8-sig" if self.raw.startswith(b"\xef\xbb\xbf") else "utf-8",
            "span_units": "decoded_unicode_characters",
            "template_language": self.language,
            "parser_version": PARSER_VERSION,
            "syntax_version": SYNTAX_VERSION,
            "records": entries,
        })


def parse_template(raw: bytes, language: str) -> TemplateDocument:
    language_identifier(language)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Ren'Py template file size limit exceeded.")
    text = raw.decode("utf-8-sig")
    if "\x00" in text or "\t" in text:
        raise ValueError("NUL and tab indentation are unsupported in Ren'Py templates.")
    records: list[TemplateRecord] = []
    native_ids: set[str] = set()
    string_keys: set[str] = set()
    block, offset, slot = "", 0, 0
    pending: tuple[SayShape, str] | None = None
    block_count = 0
    for number, physical in enumerate(text.splitlines(keepends=True), 1):
        line = physical.rstrip("\r\n")
        stripped = line.strip()
        line_offset = offset
        offset += len(physical)
        if len(line) > 65536:
            raise ValueError("Ren'Py template physical line limit exceeded.")
        if not stripped:
            continue
        if not line.startswith(" ") and stripped.startswith("translate "):
            if pending is not None or (block and not block_count):
                raise ValueError("Incomplete Ren'Py translation block.")
            header = _HEADER.fullmatch(line)
            if header is None or header[1] != language:
                raise ValueError("Unsupported Ren'Py header or template language mismatch.")
            block, slot, block_count = header[2], 0, 0
            if block in {"python", "style", "default", "None"}:
                raise ValueError("Executable Ren'Py translation blocks are unsupported.")
            if block != "strings":
                if block in native_ids:
                    raise ValueError("Duplicate native Ren'Py translation identifier.")
                native_ids.add(block)
            continue
        if stripped.startswith("#"):
            if block and block != "strings" and line.startswith("    # "):
                comment = line[6:]
                if comment.startswith(('"', "'")) or re.match(
                    r"[A-Za-z_]\w* .*?[\"']", comment
                ):
                    if pending is not None:
                        raise ValueError("Ambiguous paired Ren'Py source comments.")
                    pending = _say(comment)[:2]
            continue
        if not block or not line.startswith("    ") or line.startswith("     "):
            raise ValueError("Only generated Ren'Py translation statements are supported.")
        statement = line[4:]
        if block == "strings":
            if statement.startswith("old ") and pending is None:
                source, end = read_literal(statement, 4)
                if statement[end:].strip() or not source.strip():
                    raise ValueError("Invalid Ren'Py old string key.")
                pending = (SayShape(), source)
                continue
            if not statement.startswith("new ") or pending is None:
                raise ValueError("Ren'Py string tables require paired old/new literals.")
            target, end = read_literal(statement, 4)
            if statement[end:].strip():
                raise ValueError("Unsupported Ren'Py new string suffix.")
            shape, source = pending
            if source in string_keys:
                raise ValueError("Duplicate Ren'Py old key in a template file.")
            string_keys.add(source)
            start, kind = 4, "string"
        else:
            shape, target, start, end = _say(statement)
            if pending is None or shape != pending[0] or not pending[1].strip():
                raise ValueError("Ren'Py dialogue needs an unambiguous matching source comment.")
            source, kind = pending[1], "dialogue"
        tokens(source)
        if target:
            tokens(target)
        records.append(TemplateRecord(
            kind, block, slot, shape.speaker, source, target,
            line_offset + 4 + start, line_offset + 4 + end, number,
            shape.attributes, shape.temporary_attributes, shape.nointeract,
        ))
        if len(records) > MAX_RECORDS:
            raise ValueError("Ren'Py template record limit exceeded.")
        pending, slot, block_count = None, slot + 1, block_count + 1
    if pending is not None or not records or (block and not block_count):
        raise ValueError("Missing or incomplete native Ren'Py template statements.")
    return TemplateDocument(raw, language, tuple(records))
