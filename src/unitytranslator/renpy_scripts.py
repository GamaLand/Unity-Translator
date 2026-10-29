"""Static audited Ren'Py source subset. No engine imports, deserialization or eval.

Native say IDs follow the audited label/canonical-say/MD5 behavior contract. This
module deliberately excludes executable statements from output. UI keys come only
from explicit literal _() calls and menu choices, never arbitrary string literals.
"""

import ast
import base64
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from hashlib import md5, sha256
from typing import Any

from unitytranslator.renpy_format import tokens
from unitytranslator.renpy_python import (
    PYTHON_BLOCKS_V1,
    PYTHON_BLOCKS_V2,
    PythonSourceView,
    python_source_view,
    source_order,
)
from unitytranslator.renpy_say import SYNTAX_VERSION, SayShape, symbolic_prefix
from unitytranslator.renpy_templates import TemplateDocument, TemplateRecord, quoted_literal
from unitytranslator.source_contracts import SourceDescriptor, SourceSnapshot

ADAPTER_ID = "renpy-scripts"
PARSER_VERSION = "renpy-script-8.1.2-v1"
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_FILES = 2048
MAX_RECORDS = 100000
MAX_OCCURRENCES = 250000
MAX_LEXEMES = 200000
MAX_TOTAL_LEXEMES = 4_000_000
MAX_PHYSICAL_LINES = 100000
MAX_NATIVE_IDENTIFIER = 2000
SOURCE_NAMESPACE = "source_template"
_LABEL = re.compile(r"label ([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?|\.[A-Za-z_]\w*)"
                    r"(?:\([\s\S]*\))?( hide)?:\s*$", re.ASCII)
_LABEL_NAME = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?|\.[A-Za-z_]\w*"
_MENU = re.compile(r"menu(?: (" + _LABEL_NAME + r"))?(?: *\([\s\S]*\))?:\s*$", re.ASCII)
_CALL_FROM = re.compile(r"\bfrom (" + _LABEL_NAME + r")\s*$", re.ASCII)
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*", re.ASCII)
_SKIP_BLOCK = {
    "screen", "style", "transform", "image", "python", "init", "translate", "layeredimage",
    "testcase",
}
_NON_SAY = {
    "jump", "return", "scene", "show", "hide", "with", "play", "stop", "queue",
    "window", "pause", "camera", "define", "default", "menu", "if", "elif",
    "else", "while", "for", "pass", "extend",
}


@dataclass(frozen=True)
class Lexeme:
    kind: str
    raw: str
    start: int
    end: int
    line: int


@dataclass
class MenuContext:
    depth: int
    child: int | None = None
    choice_seen: bool = False
    caption_seen: bool = False
    say_seen: bool = False
    pending_group: bool = False


def lex(text: str) -> tuple[dict[int, list[Lexeme]], Counter[str]]:
    """Tokenize comments and quoted spans before interpreting any statement shape."""
    lines: dict[int, list[Lexeme]] = {}
    excluded: Counter[str] = Counter()
    i, line, count = 0, 1, 0
    logical_line: int | None = None
    brackets: list[str] = []
    while i < len(text):
        c = text[i]
        if c == "\t":
            raise ValueError("Tab characters outside comments or literals are unsupported.")
        if c in " \r\n":
            if c == "\n" and not brackets:
                logical_line = None
            line += c == "\n"
            i += 1
            continue
        if c == "\\" and text[i + 1:i + 2] in ("\n", "\r"):
            length = 3 if text[i + 1:i + 3] == "\r\n" else 2
            if text[i + 1:i + length] not in ("\n", "\r\n"):
                raise ValueError("Unsupported Ren'Py line continuation.")
            line += 1
            i += length
            continue
        if c == "#":
            end = text.find("\n", i)
            i = len(text) if end == -1 else end
            continue
        start, start_line = i, line
        if logical_line is None:
            logical_line = start_line
        if c in "\"'`":
            triple = text[i:i + 3] == c * 3
            width = 3 if triple else 1
            i += width
            closed = False
            while i < len(text):
                if text[i] == "\\":
                    line += text[i:i + 2].count("\n")
                    i += 2
                elif text[i:i + width] == c * width:
                    i += width
                    closed = True
                    break
                else:
                    line += text[i] == "\n"
                    i += 1
            if not closed:
                raise ValueError("Unterminated Ren'Py source literal.")
            kind = "string" if not triple and line == start_line and c != "`" else "opaque"
            if kind == "opaque":
                excluded["multiline_or_backtick_literal"] += 1
        elif match := _IDENTIFIER.match(text, i):
            i = match.end()
            kind = "identifier"
        else:
            if c in "([{":
                brackets.append({"(": ")", "[": "]", "{": "}"}[c])
                if len(brackets) > 64:
                    raise ValueError("Ren'Py source expression nesting limit exceeded.")
            elif c in ")]}" and (not brackets or brackets.pop() != c):
                raise ValueError("Unbalanced Ren'Py source expression delimiters.")
            i += 1
            kind = "punctuation"
        count += 1
        if count > MAX_LEXEMES:
            raise ValueError("Ren'Py source lexical token limit exceeded.")
        lines.setdefault(logical_line, []).append(Lexeme(kind, text[start:i], start, i, start_line))
    if brackets:
        raise ValueError("Unterminated Ren'Py source expression.")
    return lines, excluded


def say_literal(raw: str) -> str:
    """Pinned lexer.string subset: collapse spaces before expanding fixed escapes."""
    body = re.sub(r" +", " ", raw[1:-1])

    def escape(match: re.Match[str]) -> str:
        c = match[1]
        if c in "{[%":
            return c * 2
        if c == "n":
            return "\n"
        if c == "u":
            raise ValueError("Unsupported Unicode source escape.")
        return c

    result = re.sub(r"\\(.)", escape, body)
    tokens(result)
    return result


def native_identifier(
    label: str, speaker: str, text: str, *, attributes: tuple[str, ...] = (),
    temporary_attributes: tuple[str, ...] = (), nointeract: bool = False,
    explicit_id: str = "",
) -> str:
    """Reproduce canonical symbolic Say data, never executable AST nodes."""
    literal = quoted_literal(text)
    literal = re.sub(r"(?<= ) ", r"\\ ", literal)
    code = SayShape(speaker, attributes, temporary_attributes, nointeract).statement(literal)
    if explicit_id:
        code += " id " + explicit_id
    return label.replace(".", "_") + "_" + md5(
        (code + "\r\n").encode("utf-8"), usedforsecurity=False,
    ).hexdigest()[:8]


@dataclass(frozen=True)
class ScriptDocument:
    document: TemplateDocument
    fingerprint: str
    members: tuple[dict[str, Any], ...]
    locations: tuple[dict[str, Any], ...]
    exclusions: dict[str, int]

    def snapshot(self, relative: str, source_language: str) -> SourceSnapshot:
        base = self.document.snapshot(relative, source_language)
        logical = PARSER_VERSION + ":" + relative
        source = SourceDescriptor(
            logical, ADAPTER_ID, PARSER_VERSION, PARSER_VERSION, relative, -1,
            source_language, self.fingerprint, base.source.format_rules,
        )
        metadata = {
            **base.metadata, "logical_id": logical, "parser_version": PARSER_VERSION,
            "syntax_version": SYNTAX_VERSION,
            "input_kind": "original_source", "original_members": list(self.members),
            "locations": list(self.locations), "exclusions": self.exclusions,
        }
        return SourceSnapshot(source, tuple(
            replace(unit, context=unit.context + "; parser=" + PARSER_VERSION)
            for unit in base.units
        ), metadata)


def parse_scripts(
    members: Iterable[tuple[str, bytes]], fingerprint: str, *,
    cancelled: Callable[[], bool] = lambda: False,
    reserved_attributes: frozenset[str] = frozenset(),
    python_dialect: str | None = None,
) -> ScriptDocument:
    """Read a complete selected container's plain dialogue and explicit string keys."""
    records: list[TemplateRecord] = []
    originals = []
    locations: list[dict[str, Any]] = []
    exclusions: Counter[str] = Counter()
    ids: set[str] = set()
    strings: dict[str, int] = {}
    view: PythonSourceView | None = None

    def add(
        kind: str, block: str, speaker: str, value: str, token: Lexeme, member: str,
        shape: SayShape | None = None,
    ) -> None:
        shape = shape or SayShape()
        if not value.strip():
            exclusions["empty_text"] += 1
            return
        if "__" in value:
            exclusions["private_name_munging"] += 1
            return
        try:
            tokens(value)
        except ValueError:
            exclusions["unsupported_text_syntax"] += 1
            return
        start, end = (view.span(token.start, token.end, token.line) if view is not None
                      else (token.start, token.end))
        location = {"member": member, "line": token.line, "start": start,
                    "end": end, "kind": kind, "block": block}
        if len(locations) >= MAX_OCCURRENCES:
            raise ValueError("Ren'Py source occurrence limit exceeded.")
        if kind == "string" and value in strings:
            location["record"] = strings[value]
            locations.append(location)
            return
        if len(records) >= MAX_RECORDS:
            raise ValueError("Ren'Py source record limit exceeded.")
        location["record"] = len(records)
        locations.append(location)
        if kind == "string":
            strings[value] = len(records)
        records.append(TemplateRecord(
            kind, block, 0, speaker, value, "", start, end, token.line,
            shape.attributes, shape.temporary_attributes, shape.nointeract,
        ))

    # Lists retain the legacy sorting contract. A streaming reader supplies an
    # already sorted inventory; never materialize all original bytes to sort it.
    ordered = (sorted(members, key=lambda item: source_order(item[0]))
               if isinstance(members, Sequence) else members)
    count, total, lexical_total, previous = 0, 0, 0, ""
    for member, raw in ordered:
        if cancelled():
            raise ValueError("Source extraction was cancelled.")
        count += 1
        total += len(raw)
        if count > MAX_FILES or total > MAX_TOTAL_BYTES:
            raise ValueError("Ren'Py source container bounds exceeded.")
        order = source_order(member)
        if order <= previous:
            raise ValueError("Ren'Py source inventory is duplicate or out of order.")
        previous = order
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("Ren'Py source member size limit exceeded.")
        if b"register_statement" in raw:
            raise ValueError(
                "Custom Ren'Py statements require a separately verified source profile."
            )
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("NUL characters are outside the source subset.")
        if len(text.splitlines()) > MAX_PHYSICAL_LINES:
            raise ValueError("Ren'Py source physical line count limit exceeded.")
        if any(len(line) > 65536 for line in text.split("\n")):
            raise ValueError("Ren'Py source physical line limit exceeded.")
        originals.append({"name": member, "sha256": sha256(raw).hexdigest(),
                          "raw_base64": base64.b64encode(raw).decode("ascii")})
        view = None
        if member.endswith("_ren.py"):
            if python_dialect not in (PYTHON_BLOCKS_V1, PYTHON_BLOCKS_V2):
                raise ValueError("The _ren.py source conversion contract has not been verified.")
            if raw.startswith(b"\xef\xbb\xbf") and python_dialect == PYTHON_BLOCKS_V1:
                raise ValueError("A BOM in _ren.py requires the verified BOM-aware source dialect.")
            view = python_source_view(text)
            text = view.text
            exclusions["renpy_python_ignored_lines"] += view.ignored_lines
            originals[-1]["source_dialect"] = python_dialect
        statements, skipped = lex(text)
        lexical_total += sum(len(statement) for statement in statements.values())
        if lexical_total > MAX_TOTAL_LEXEMES:
            raise ValueError("Ren'Py source total lexical token limit exceeded.")
        exclusions.update(skipped)
        label, global_label, alternate = "", "", ""
        blocked_indent: int | None = None
        menus: list[MenuContext] = []
        pending_translatable = False
        physical_lines = text.split("\n")
        preexisting: set[str] = set()
        opaque_indent: int | None = None
        for number, statement in statements.items():
            if number % 1024 == 0 and cancelled():
                raise ValueError("Source extraction was cancelled.")
            physical = physical_lines[number - 1]
            indent = len(physical) - len(physical.lstrip(" "))
            if opaque_indent is not None:
                if indent > opaque_indent:
                    continue
                opaque_indent = None
            head = statement[0].raw
            if head in _SKIP_BLOCK:
                if statement[-1].raw == ":":
                    opaque_indent = indent
                continue
            if head in _NON_SAY or head in ("label", "call", "$"):
                continue
            if not any(item.kind == "string" for item in statement):
                continue
            for i, item in enumerate(statement[:-1]):
                if item.raw == "id" and statement[i + 1].kind == "identifier":
                    preexisting.add(statement[i + 1].raw)

        serials: dict[str, int] = {}

        def unique(
            base: str, reserved: set[str] = preexisting, allocated: dict[str, int] = serials,
        ) -> str:
            if len(base) > MAX_NATIVE_IDENTIFIER:
                raise ValueError("Ren'Py native identifier size limit exceeded.")
            serial = allocated.get(base, 0)
            candidate = base if serial == 0 else base + "_" + str(serial)
            while candidate in ids or candidate in reserved:
                serial += 1
                if serial % 1024 == 0 and cancelled():
                    raise ValueError("Source extraction was cancelled.")
                candidate = base + "_" + str(serial)
            allocated[base] = serial + 1
            return candidate

        for number, statement in statements.items():
            line = physical_lines[number - 1]
            if number % 1024 == 0 and cancelled():
                raise ValueError("Source extraction was cancelled.")
            statement_text = text[statement[0].start:statement[-1].end]
            indent = len(line) - len(line.lstrip(" "))
            menus = [menu for menu in menus if indent > menu.depth]
            if menus and menus[-1].child is None:
                menus[-1].child = indent
            direct_menu_item = bool(menus and indent == menus[-1].child)
            head = statement[0].raw
            for i, token in enumerate(statement):
                if token.raw != "_" or (i and statement[i - 1].raw == "."):
                    continue
                if [t.kind for t in statement[i + 1:i + 4]] != [
                    "punctuation", "string", "punctuation",
                ] or [statement[i + 1].raw, statement[i + 3].raw] != ["(", ")"]:
                    continue
                literal = statement[i + 2]
                try:
                    value = ast.literal_eval(literal.raw)
                    if not isinstance(value, str):
                        raise ValueError("Not a literal UI key.")
                except (ValueError, SyntaxError):
                    exclusions["unsupported_ui_literal"] += 1
                else:
                    # Resource/coverage failures must abort the complete source set,
                    # never masquerade as one unsupported literal and activate a prefix.
                    add("string", "strings", "", value, literal, member)
            if blocked_indent is not None:
                if indent > blocked_indent:
                    continue
                blocked_indent = None
            if head in _SKIP_BLOCK or (head == "$" and len(statement) > 1):
                if statement[-1].raw == ":":
                    blocked_indent = indent
                pending_translatable = False
                continue
            if head == "label":
                match = _LABEL.fullmatch(statement_text)
                if match is None:
                    label, global_label, alternate = "", "", ""
                    exclusions["unsupported_label"] += 1
                else:
                    name = match[1]
                    if "__" in name:
                        label, global_label, alternate = "", "", ""
                        exclusions["private_name_munging"] += 1
                        continue
                    if name.startswith("."):
                        name = global_label + name if global_label else ""
                    else:
                        global_label = name.split(".")[0]
                    # Underscore labels create alternate IDs under the preceding normal label.
                    if not match[2]:
                        if name.startswith("_"):
                            alternate = name
                        else:
                            label = name
                            alternate = ""
                pending_translatable = False
                continue
            if head == "call":
                match = _CALL_FROM.search(statement_text)
                if match:
                    if "__" in match[1]:
                        label, alternate = "", ""
                        exclusions["private_name_munging"] += 1
                        continue
                    name = match[1]
                    if name.startswith("."):
                        name = global_label + name if global_label else ""
                    if name.startswith("_"):
                        alternate = name
                    else:
                        label, alternate = name, ""
                elif any(item.kind == "identifier" and item.raw == "from" for item in statement):
                    label, alternate = "", ""
                    exclusions["unsupported_call_from_label"] += 1
                pending_translatable = False
                continue
            if head in ("voice", "nvl"):
                pending_translatable = True
                exclusions["voice_or_nvl_group"] += 1
                continue
            if head in _NON_SAY:
                if head == "menu":
                    header = _MENU.fullmatch(statement_text)
                    if header is None:
                        raise ValueError("Unsupported or multiline Ren'Py menu header.")
                    name = header[1]
                    menus.append(MenuContext(
                        indent, pending_group=pending_translatable and not name,
                    ))
                    if name:
                        if name.startswith("."):
                            name = global_label + name if global_label else ""
                        else:
                            global_label = name.split(".")[0]
                        if "__" in name:
                            label, global_label, alternate = "", "", ""
                            exclusions["private_name_munging"] += 1
                        elif name.startswith("_"):
                            alternate = name
                        else:
                            label, alternate = name, ""
                pending_translatable = False
                continue
            literal_index = next((
                i for i, item in enumerate(statement) if item.kind in ("string", "opaque")
            ), -1)
            if literal_index < 0:
                pending_translatable = False
                continue
            try:
                if literal_index and text[statement[literal_index].start - 1] != " ":
                    raise ValueError("Missing say separator.")
                prefix = "" if literal_index == 0 else text[
                    statement[0].start:statement[literal_index].start
                ].strip()
                shape = symbolic_prefix(re.sub(r"\s+", " ", prefix))
                if any(name.lstrip("-") in reserved_attributes for name in (
                    *shape.attributes, *shape.temporary_attributes,
                )):
                    raise ValueError("Reserved image attribute for the source dialect.")
                if "__" in prefix:
                    exclusions["private_name_munging"] += 1
                    pending_translatable = False
                    continue
            except ValueError:
                exclusions["unsupported_say_prefix"] += 1
                pending_translatable = False
                continue
            speaker = shape.speaker
            literal = statement[literal_index]
            if literal.kind != "string":
                # Plain non-translatable statements terminate voice/nvl groups.
                pending_translatable = False
                continue
            if speaker == "r" and statement[0].end == literal.start:
                exclusions["raw_say_literal"] += 1
                continue
            tail = statement[literal_index + 1:]
            nointeract = bool(tail and tail[0].raw == "nointeract")
            if nointeract:
                tail = tail[1:]
            shape = replace(shape, nointeract=nointeract or (direct_menu_item and bool(speaker)))
            explicit_id = ""
            if len(tail) == 2 and tail[0].raw == "id" and tail[1].kind == "identifier":
                explicit_id = tail[1].raw
                if "__" in explicit_id:
                    exclusions["private_name_munging"] += 1
                    pending_translatable = False
                    continue
                if explicit_id in {"strings", "python", "style", "default", "None"}:
                    exclusions["unsupported_explicit_identifier"] += 1
                    continue
                tail = []
            try:
                value = say_literal(literal.raw)
            except ValueError:
                exclusions["unsupported_say_literal"] += 1
                pending_translatable = False
                continue
            if "__" in value:
                exclusions["private_name_munging"] += 1
                pending_translatable = False
                continue
            if not speaker and not nointeract and not explicit_id and direct_menu_item and (
                not tail or (tail[0].raw in (":", "if") and tail[-1].raw == ":")
            ):
                if tail:
                    menus[-1].choice_seen = True
                else:
                    if menus[-1].say_seen:
                        raise ValueError("Menu captions and say statements cannot be mixed.")
                    menus[-1].caption_seen = True
                add("string", "strings", "", value, literal, member)
            elif direct_menu_item and not speaker:
                exclusions["unsupported_menu_item"] += 1
            elif direct_menu_item and (
                menus[-1].choice_seen or menus[-1].caption_seen or menus[-1].say_seen
            ):
                # The engine moves a menu's say before its choices. Defer lexical
                # layouts requiring reordered serial allocation rather than guess IDs.
                raise ValueError(
                    "Menu say ordering requires separately verified native-ID mapping."
                )
            elif tail or not label or pending_translatable or (
                direct_menu_item and menus[-1].pending_group
            ):
                exclusions["unsupported_say_suffix" if tail else (
                    "say_without_label" if not label else "say_in_voice_or_nvl_group"
                )] += 1
            else:
                if direct_menu_item:
                    menus[-1].say_seen = True
                base = native_identifier(
                    label, speaker, value, attributes=shape.attributes,
                    temporary_attributes=shape.temporary_attributes,
                    nointeract=shape.nointeract, explicit_id=explicit_id,
                )
                digest = base.rsplit("_", 1)[-1]
                base = unique(base)
                alternate_id = ""
                if alternate:
                    alternate_id = unique(alternate.replace(".", "_") + "_" + digest)
                elif explicit_id:
                    alternate_id = base
                block = explicit_id or base
                if len(block) > MAX_NATIVE_IDENTIFIER:
                    raise ValueError("Ren'Py native identifier size limit exceeded.")
                if block in ids:
                    raise ValueError("Ambiguous native Ren'Py dialogue identifier.")
                ids.add(block)
                if alternate_id:
                    ids.add(alternate_id)
                add("dialogue", block, speaker, value, literal, member, shape)
            pending_translatable = False
    if not records:
        raise ValueError("No supported translatable source statements were found.")
    # A data-only normalized intermediate; retained originals are the source authority.
    document = TemplateDocument(b"", SOURCE_NAMESPACE, tuple(records))
    return ScriptDocument(
        document, fingerprint, tuple(originals), tuple(locations), dict(exclusions),
    )
