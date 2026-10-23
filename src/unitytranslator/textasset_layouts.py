"""Explicit line layouts; reconstruction preserves every non-text byte and line slot."""

import re
from dataclasses import dataclass
from hashlib import sha256

from unitytranslator.domain import TextUnitDraft
from unitytranslator.source_contracts import SourceDescriptor

MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
MAX_LINES = 20000
MENU_SECTIONS = {
    0: "//MAIN_MENU",
    5: "//OPTIONS",
    13: "//PAUSE",
    21: "//CONTROLS",
    38: "//DAYS",
    44: "//PC",
    56: "//PLAYER THOUGHTS",
    70: "//BOOTLEG",
    73: "//INTRO",
}
SCHEMAS = frozenset(
    {"menu-lines-v1", "forum-lines-v1", "keypost-lines-v1", "subtitle-lines-v1", "journal-lines-v1"}
)


@dataclass(frozen=True)
class PayloadDocument:
    schema: str
    original: bytes
    bom: bytes
    lines: tuple[tuple[str, str], ...]
    text_fields: tuple[int, ...]

    @property
    def fingerprint(self) -> str:
        return sha256(self.original).hexdigest()

    def drafts(self, source: SourceDescriptor) -> tuple[TextUnitDraft, ...]:
        if source.payload_fingerprint != self.fingerprint or source.schema_version != self.schema:
            raise ValueError("Payload does not match its verified source descriptor.")
        return tuple(
            TextUnitDraft(
                unit_id=self.record_id(source, index),
                original_key=f"line/{index}",
                source_file=source.source_file,
                source_object=source.source_object,
                source_language=source.source_language,
                source_text=self.lines[index][0],
                source_hash=sha256(self.lines[index][0].encode("utf-8")).hexdigest(),
                category=self.schema.removesuffix("-lines-v1"),
                context=f"{source.asset_name}; {self.schema}; line {index}; literal single line",
            )
            for index in self.text_fields
        )

    def record_id(self, source: SourceDescriptor, index: int) -> str:
        # The entire positional snapshot participates: edits/insertion/reordering
        # create new IDs rather than silently moving approvals to different slots.
        return sha256(
            "\0".join(
                (
                    "textasset-position-v1",
                    source.logical_id,
                    self.fingerprint,
                    str(index),
                )
            ).encode("utf-8")
        ).hexdigest()

    def reconstruct(self, translations: dict[int, str]) -> bytes:
        if not set(translations) <= set(self.text_fields):
            raise ValueError("Only declared text slots may be translated.")
        for value in translations.values():
            if (
                not isinstance(value, str)
                or not value.strip()
                or any(c in value for c in "\r\n\x00")
            ):
                raise ValueError("A line translation must be nonempty and preserve line structure.")
        text = "".join(
            translations.get(i, line) + ending for i, (line, ending) in enumerate(self.lines)
        )
        output = self.bom + text.encode("utf-8")
        verified = parse_payload(output, self.schema)
        if len(verified.lines) != len(self.lines) or verified.text_fields != self.text_fields:
            raise ValueError("Translated payload changed its structural layout.")
        for index, line in enumerate(self.lines):
            if index not in translations and verified.lines[index] != line:
                raise ValueError("Translated payload changed a protected control field.")
            if verified.lines[index][1] != line[1]:
                raise ValueError("Translated payload changed a newline sequence.")
        return output


def parse_payload(raw: bytes, schema: str) -> PayloadDocument:
    if schema not in SCHEMAS:
        raise ValueError("Unknown built-in TextAsset schema.")
    if not raw or len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError("TextAsset payload exceeds the supported size bounds.")
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    text = raw[len(bom) :].decode("utf-8", errors="strict")
    if "\x00" in text:
        raise ValueError("TextAsset payload contains NUL characters.")
    parts = text.split("\n")
    if len(parts) > MAX_LINES:
        raise ValueError("TextAsset line count exceeds the supported bounds.")
    lines = []
    for index, part in enumerate(parts):
        ending = "\n" if index < len(parts) - 1 else ""
        if ending and part.endswith("\r"):
            part, ending = part[:-1], "\r\n"
        if "\r" in part:
            raise ValueError("Bare carriage returns are not supported by this line schema.")
        lines.append((part, ending))
    values = [line for line, _ in lines]
    if schema == "menu-lines-v1":
        if len(values) != 90 or any(values[i] != marker for i, marker in MENU_SECTIONS.items()):
            raise ValueError("Menu offsets or record count differ from the reviewed schema.")
        fields = [i for i in range(len(values)) if i not in MENU_SECTIONS and values[i].strip()]
    elif schema in ("subtitle-lines-v1", "journal-lines-v1"):
        if schema == "journal-lines-v1" and (bom or len(values) != 12):
            raise ValueError("Journal literal grids require exactly twelve UTF-8 cell slots.")
        fields = [i for i, value in enumerate(values) if value.strip()]
    else:
        header = 6 if schema == "forum-lines-v1" else 5
        if len(values) < header or (len(values) - header) % 3:
            raise ValueError("Forum/message reply triplets do not match the reviewed schema.")
        if (
            not re.fullmatch(r"\s*\d{1,6}\s*", values[0])
            or not re.fullmatch(r"\s*\d{1,12}\s*", values[1])
            or not re.fullmatch(r"\s*\d{2}\.\d{2}\.\d{4} \d{1,2}:\d{2}\s*", values[2])
        ):
            raise ValueError("Forum/message author, view count or date control is malformed.")
        if header == 6 and not re.fullmatch(r"\s*p\d{2}\s*", values[5]):
            raise ValueError("Forum/message photo control is malformed.")
        fields = [3, 4]
        for start in range(header, len(values), 3):
            if not re.fullmatch(r"\s*\d{1,6}\s*", values[start]) or not re.fullmatch(
                r"\s*p\d{2}\s*", values[start + 2]
            ):
                raise ValueError("Forum/message reply author or photo control is malformed.")
            fields.append(start + 1)
        if any(not values[index].strip() for index in fields):
            raise ValueError("Declared forum/message text fields cannot be empty.")
    return PayloadDocument(schema, raw, bom, tuple(lines), tuple(fields))
