"""Only synthetic payloads: real game content must never become public fixtures."""

from dataclasses import replace
from hashlib import sha256

import pytest

from unitytranslator.source_contracts import SourceDescriptor
from unitytranslator.textasset_layouts import MENU_SECTIONS, parse_payload


def forum(newline="\r\n", *, keypost=False):
    header = ["02", "123", "01.02.2006 9:12", "Synthetic title", "Synthetic body"]
    return newline.join(
        header
        + ([] if keypost else ["p00"])
        + [
            "03",
            "Synthetic reply",
            "p01",
        ]
    ).encode("utf-8")


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
@pytest.mark.parametrize("keypost", [True, False])
def test_forum_round_trip_protects_metadata_and_reply_slots(newline, bom, keypost):
    raw = bom + forum(newline, keypost=keypost)
    schema = "keypost-lines-v1" if keypost else "forum-lines-v1"
    doc = parse_payload(raw, schema)
    assert doc.reconstruct({}) == raw
    translated = doc.reconstruct(
        {
            3: "Başlık",
            4: "Unicode body < back",
            doc.text_fields[-1]: "Yanıt",
        }
    )
    result = parse_payload(translated, schema)
    assert result.lines[3][0] == "Başlık"
    for i in (0, 1, 2, len(doc.lines) - 1):
        assert result.lines[i] == doc.lines[i]
    assert translated.startswith(bom)


def test_menu_offsets_and_markers_are_protected():
    lines = ["Synthetic text"] * 90
    for index, marker in MENU_SECTIONS.items():
        lines[index] = marker
    raw = "\n".join(lines).encode()
    doc = parse_payload(raw, "menu-lines-v1")
    assert doc.reconstruct({1: "Başla"}).split(b"\n")[0] == b"//MAIN_MENU"
    with pytest.raises(ValueError):
        doc.reconstruct({0: "Do not translate controls"})
    with pytest.raises(ValueError):
        parse_payload(b"extra\n" + raw, "menu-lines-v1")


def test_subtitle_empty_lines_and_trailing_newline_are_retained():
    raw = b"One\r\n\r\nTwo\n"
    doc = parse_payload(raw, "subtitle-lines-v1")
    assert doc.text_fields == (0, 2)
    assert doc.reconstruct({0: "Bir", 2: "İki"}) == "Bir\r\n\r\nİki\n".encode()


@pytest.mark.parametrize("value", ["injected\nline", "injected\rline", "", "\x00"])
def test_translations_cannot_change_physical_line_structure(value):
    doc = parse_payload(forum(), "forum-lines-v1")
    with pytest.raises(ValueError):
        doc.reconstruct({4: value})


@pytest.mark.parametrize(
    "raw",
    [
        b"01\n2\nwrong-date\ntitle\nbody\np00",
        b"01\n2\n01.01.2006 1:00\ntitle\nbody\nnot-photo",
        forum() + b"\nextra",
        forum().replace(b"03\r\n", b"user-code\r\n"),
        b"\xff",
        b"NUL\x00",
        b"bare\rcarriage",
    ],
)
def test_malformed_payloads_are_rejected(raw):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        parse_payload(raw, "forum-lines-v1")


def test_positional_ids_invalidate_the_whole_source_on_insertion_or_reordering():
    raw = b"First\nSecond"
    doc = parse_payload(raw, "subtitle-lines-v1")
    descriptor = SourceDescriptor(
        "synthetic-subtitles",
        "textasset",
        "synthetic",
        "subtitle-lines-v1",
        "shared.assets",
        10,
        "en",
        format_rules="literal-lines-v1",
        payload_fingerprint=sha256(raw).hexdigest(),
    )
    original_ids = {unit.unit_id for unit in doc.drafts(descriptor)}
    assert original_ids == {unit.unit_id for unit in doc.drafts(descriptor)}
    for changed in (b"Second\nFirst", b"Inserted\nFirst\nSecond", b"Changed\nSecond"):
        new_doc = parse_payload(changed, "subtitle-lines-v1")
        new_source = replace(descriptor, payload_fingerprint=sha256(changed).hexdigest())
        assert not original_ids & {unit.unit_id for unit in new_doc.drafts(new_source)}
    with pytest.raises(ValueError):
        doc.drafts(replace(descriptor, payload_fingerprint="b" * 64))
