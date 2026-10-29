"""The _ren.py format is converted as data; embedded Python must never execute."""

import ast
from hashlib import sha256

import pytest

from unitytranslator.renpy_python import PYTHON_BLOCKS_V1, PYTHON_BLOCKS_V2, python_source_view
from unitytranslator.renpy_scripts import native_identifier, parse_scripts

SOURCE = '''ignored = _("Not an engine input")
"""renpy
init python:
"""
display = _("Display")
raise RuntimeError("NEVER EXECUTE")
"""renpy
label start:
    e happy "Hello [name!q]."
"""
'''


def test_python_view_reads_only_supported_keys_and_retains_original_spans():
    raw = SOURCE.replace("\n", "\r\n").encode()
    parsed = parse_scripts([("script_ren.py", raw)], sha256(raw).hexdigest(),
                           python_dialect=PYTHON_BLOCKS_V2)
    records = parsed.document.records
    assert [record.source for record in records] == ["Display", "Hello [name!q]."]
    assert records[1].attributes == ("happy",)
    assert records[1].block == native_identifier("start", "e", "Hello [name!q].",
                                                 attributes=("happy",))
    original = raw.decode()
    for record, location in zip(records, parsed.locations, strict=True):
        literal = original[location["start"]:location["end"]]
        assert ast.literal_eval(literal) == record.source
        assert original[record.literal_start:record.literal_end] == literal
    assert records[0].line == 5 and records[1].line == 9
    assert parsed.exclusions["renpy_python_ignored_lines"] == 1
    assert parsed.members[0]["sha256"] == sha256(raw).hexdigest()
    assert parsed.members[0]["source_dialect"] == PYTHON_BLOCKS_V2


def test_bom_requires_the_bom_aware_conversion_contract():
    raw = b"\xef\xbb\xbf" + SOURCE.encode()
    with pytest.raises(ValueError, match="BOM-aware"):
        parse_scripts([("script_ren.py", raw)], "a" * 64, python_dialect=PYTHON_BLOCKS_V1)
    records = parse_scripts([("script_ren.py", raw)], "a" * 64,
                            python_dialect=PYTHON_BLOCKS_V2).document.records
    assert records[0].source == "Display"


@pytest.mark.parametrize("text", [
    'ordinary_python = _("Not a native source")\n',
    '"""renpy\nlabel start:\n    "Never closed"\n',
])
def test_missing_or_unclosed_renpy_blocks_refuse_the_complete_source(text):
    with pytest.raises(ValueError, match="block"):
        python_source_view(text)


def test_generic_python_cannot_be_selected_as_the_renpy_dialect():
    with pytest.raises(ValueError, match="filename"):
        parse_scripts([("ordinary.py", SOURCE.encode())], "a" * 64,
                      python_dialect=PYTHON_BLOCKS_V2)
    with pytest.raises(ValueError, match="not been verified"):
        parse_scripts([("script_ren.py", SOURCE.encode())], "a" * 64)


def test_source_basename_order_and_conflicts_match_the_verified_loader_rule():
    parsed = parse_scripts([
        ("a0.rpy", b'label second:\n    "Second."\n'),
        ("a_ren.py", b'"""renpy\nlabel first:\n    "First."\n"""\n'),
        ("a.extra.rpy", b'label middle:\n    "Middle."\n'),
    ], "a" * 64, python_dialect=PYTHON_BLOCKS_V2)
    assert [record.source for record in parsed.document.records] == ["First.", "Middle.", "Second."]
    with pytest.raises(ValueError, match="duplicate or out of order"):
        parse_scripts([
            ("a.rpy", b'label first:\n    "First."\n'),
            ("a_ren.py", SOURCE.encode()),
        ], "a" * 64, python_dialect=PYTHON_BLOCKS_V2)


def test_modern_attribute_keywords_do_not_inherit_older_attribute_grammar():
    raw = b'label start:\n    e at "Legacy attribute."\n    e "Shared syntax."\n'
    old = parse_scripts([("script.rpy", raw)], "a" * 64)
    modern = parse_scripts([("script.rpy", raw)], "a" * 64,
                           reserved_attributes=frozenset({"at"}))
    assert len(old.document.records) == 2
    assert [record.source for record in modern.document.records] == ["Shared syntax."]
    assert modern.exclusions["unsupported_say_prefix"] == 1


def test_unverified_private_name_munging_is_visible_and_cannot_guess_native_ids():
    raw = b'''label start:
    e "Private [__name]."
    $ key = _("Private__key")
label __private:
    e "Unverified private label."
label safe:
    e "Supported."
'''
    parsed = parse_scripts([("script.rpy", raw)], "a" * 64)
    assert [record.source for record in parsed.document.records] == ["Supported."]
    assert parsed.exclusions["private_name_munging"] == 3
    assert parsed.exclusions["say_without_label"] == 1
