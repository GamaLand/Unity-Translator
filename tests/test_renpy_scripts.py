"""Synthetic static scripts only; game code must never execute during extraction."""

import ast
import json
from dataclasses import replace
from hashlib import md5, sha256
from pathlib import Path

import pytest

from unitytranslator.discovery import extract_to_project, probe_source
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.portable import PortableService
from unitytranslator.renpy_export import export_native
from unitytranslator.renpy_scripts import native_identifier, parse_scripts, say_literal
from unitytranslator.renpy_templates import (
    parse_template,
    quoted_literal,
    read_literal,
    say_quoted_literal,
)
from unitytranslator.repository import ProjectRepository

SOURCE = '''
define e = Character(_("Example"))
screen preferences():
    label _("Display")
    text "This arbitrary literal is not a translation key."
    textbutton _("Window") action Preference("display", "window")
label start: # source comment is not part of the identifier
    e "Hello [name!q]."
    "Narration."
    menu:
        "Choose":
            e "Nested dialogue."
    python:
        raise RuntimeError("NEVER EXECUTE")
        ignored = '_("Not a key")'
    # _("Not a comment key")
    voice "audio.ogg"
    e "Voice group is excluded."
    e "Attributes are excluded." happy
    return "Not dialogue."
'''


def fixture(tmp_path, source=SOURCE):
    game = tmp_path / "game-root"
    (game / "game").mkdir(parents=True)
    (game / "renpy").mkdir()
    (game / "renpy/vc_version.py").write_text("version = '8.1.2.23090503'\n")
    path = game / "game/script.rpy"
    path.write_text(source, encoding="utf-8")
    return ProjectPaths(game, tmp_path / "project"), path


def approve(repo, source, target):
    row = next(r for r in repo.page() if r["source_text"] == source)
    assert repo.edit(row["unit_id"], row["version"], target)
    row = next(r for r in repo.page() if r["unit_id"] == row["unit_id"])
    repo.approve(row["unit_id"], row["version"])
    return next(r for r in repo.page() if r["unit_id"] == row["unit_id"])


def test_native_id_matches_published_plain_say_vector():
    assert native_identifier(
        "start", "e", "Thank you for taking a look at the Ren'Py translation framework.",
    ) == "start_636ae3f5"


@pytest.mark.parametrize(("attributes", "temporary", "nointeract", "explicit_id", "expected"), [
    (("happy",), (), False, "", "start_406ff91d"),
    (("-sad",), ("happy",), False, "", "start_18105eaa"),
    (("happy",), (), True, "", "start_81446bd8"),
    (("-sad",), ("happy",), True, "greeting", "start_45102671"),
])
def test_symbolic_say_native_vectors(attributes, temporary, nointeract, explicit_id, expected):
    # Fixed vectors from 8.1.2 Say.get_code / encode_say_string / Restructurer.
    # Reference: github.com/renpy/renpy/tree/8.1.2.23090503/renpy
    assert native_identifier(
        "start", "e", "Hello.", attributes=attributes, temporary_attributes=temporary,
        nointeract=nointeract, explicit_id=explicit_id,
    ) == expected


def test_attribute_export_preserves_structure_and_existing_plain_approval(tmp_path):
    paths, source = fixture(tmp_path, 'label start:\n    e "Plain."\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        old = approve(repo, "Plain.", "Sade.")
    source.write_text('''label start:
    e "Plain."
    e -sad @ happy "Hello [name!q]." nointeract
    menu:
        e happy "Choose."
        "Choice":
            pass
''', encoding="utf-8")
    before = hash_file(source)
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        plain = next(r for r in repo.page() if r["source_text"] == "Plain.")
        for key in ("unit_id", "source_revision", "translation_revision", "version", "status"):
            assert plain[key] == old[key]
        approve(repo, "Hello [name!q].", "Merhaba [name!q].")
        approve(repo, "Choose.", "Seç.")
        result = export_native(repo, "turkish")
    records = parse_template(next(Path(result["folder"]).rglob("*.rpy")).read_bytes(),
                             "turkish").records
    attributed = next(r for r in records if r.source == "Hello [name!q].")
    assert attributed.attributes == ("-sad",)
    assert attributed.temporary_attributes == ("happy",)
    assert attributed.nointeract
    menu_say = next(r for r in records if r.source == "Choose.")
    assert menu_say.attributes == ("happy",) and menu_say.nointeract
    assert hash_file(source) == before


def test_late_menu_say_is_refused_instead_of_guessing_reordered_native_ids():
    with pytest.raises(ValueError, match="Menu say ordering"):
        parse_scripts([("script.rpy", b'''label start:
    menu:
        "Choice":
            e "Repeated."
        e "Repeated."
''')], "a" * 64)


def test_mixed_python_dialect_cannot_retire_approved_source_state(tmp_path):
    paths, _ = fixture(tmp_path)
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        old = approve(repo, "Display", "Ekran")
    (paths.game / "game/extra_ren.py").write_text('raise RuntimeError("NEVER EXECUTE")')
    with pytest.raises(ValueError, match="_ren.py"):
        extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        current = next(r for r in repo.page() if r["unit_id"] == old["unit_id"])
        assert current == old


def test_archived_python_dialect_refuses_partial_original_reading(tmp_path):
    from test_renpy_archive import archive

    paths, _ = fixture(tmp_path)
    path = archive(paths.game / "game/archive.rpa", {
        "extra_ren.py": b'raise RuntimeError("NEVER EXECUTE")',
        "script.rpy": b'label start:\n    "Hello."\n',
    })
    before = hash_file(path)
    with pytest.raises(ValueError, match="Archived _ren.py"):
        probe_source(paths, "game/archive.rpa")
    assert hash_file(path) == before


def test_static_source_uses_native_dialogue_and_explicit_keys_only():
    raw = SOURCE.encode()
    document = parse_scripts([("script.rpy", raw)], sha256(raw).hexdigest())
    actual = [(r.kind, r.source) for r in document.document.records]
    assert actual == [
        ("string", "Example"), ("string", "Display"), ("string", "Window"),
        ("dialogue", "Hello [name!q]."), ("dialogue", "Narration."),
        ("string", "Choose"), ("dialogue", "Nested dialogue."),
    ]
    assert document.exclusions["voice_or_nvl_group"] == 1
    snapshot = document.snapshot("game/script.rpy", "en")
    assert snapshot.source.adapter_id == "renpy-scripts"
    assert snapshot.metadata["original_members"][0]["sha256"] == sha256(raw).hexdigest()
    assert snapshot.metadata["locations"][0]["member"] == "script.rpy"


def test_repeated_native_ids_and_string_locations_are_deterministic():
    document = parse_scripts([("script.rpy", b'''label start:
    e "Repeated."
    e "Repeated."
    $ label1 = _("Same")
    $ label2 = _("Same")
''')], "a" * 64)
    records = document.document.records
    assert len(records) == 3
    assert records[1].block == records[0].block + "_1"
    assert len(document.locations) == 4
    assert document.locations[-1]["record"] == document.locations[-2]["record"]


def test_symbolic_attributes_are_extracted_without_counting_screen_code():
    document = parse_scripts([("script.rpy", b'''screen example():
    text size "Not dialogue."
label start:
    e happy "Attribute dialogue."
    e -sad @ happy "Temporary attribute dialogue."
    e "Supported dialogue."
''')], "a" * 64)
    assert not document.exclusions.get("unsupported_say_prefix")
    records = document.document.records
    assert [r.source for r in records] == [
        "Attribute dialogue.", "Temporary attribute dialogue.", "Supported dialogue.",
    ]
    assert records[0].attributes == ("happy",)
    assert records[1].attributes == ("-sad",)
    assert records[1].temporary_attributes == ("happy",)


def test_menu_captions_are_string_keys_and_menu_say_preserves_nointeract():
    document = parse_scripts([("script.rpy", b'''label start:
    menu:
        "Caption"
        "Choice":
            e "Inside choice."
    menu:
        e "Noninteractive menu say."
        "Other choice":
            pass
''')], "a" * 64)
    assert [(r.kind, r.source) for r in document.document.records] == [
        ("string", "Caption"), ("string", "Choice"),
        ("dialogue", "Inside choice."),
        ("dialogue", "Noninteractive menu say."), ("string", "Other choice"),
    ]
    assert document.document.records[3].nointeract


def test_anonymous_menu_say_does_not_lose_a_preceding_voice_group():
    parsed = parse_scripts([("script.rpy", b'''label start:
    voice "audio.ogg"
    menu:
        e "Grouped menu say is excluded."
        "Choice":
            e "Inside choice."
''')], "a" * 64)
    assert [record.source for record in parsed.document.records] == ["Choice", "Inside choice."]
    assert parsed.exclusions["say_in_voice_or_nvl_group"] == 1


def test_hidden_labels_and_local_call_from_labels_use_parser_global_scope():
    parsed = parse_scripts([("script.rpy", b'''label start:
    e "Before."
label hidden hide:
    e "Inside hidden."
label .local:
    e "After local."
    call target from .resumed
    e "After call."
''')], "a" * 64)
    assert [record.block for record in parsed.document.records] == [
        native_identifier("start", "e", "Before."),
        native_identifier("start", "e", "Inside hidden."),
        native_identifier("hidden.local", "e", "After local."),
        native_identifier("hidden.resumed", "e", "After call."),
    ]


def test_named_menu_arguments_do_not_hide_its_native_label():
    parsed = parse_scripts([("script.rpy", b'''label start:
    menu options (screen="choice"):
        e "Menu say."
        "Choice":
            e "Inside."
''')], "a" * 64)
    records = parsed.document.records
    assert records[0].block == native_identifier("options", "e", "Menu say.", nointeract=True)
    assert records[2].block == native_identifier("options", "e", "Inside.")


def test_alternate_labels_and_explicit_ids_preserve_native_identity_allocation():
    base = native_identifier("start", "e", "Repeated.")
    raw = f'''label start:
    e "Repeated."
label _alternate:
    e "Repeated."
    e "Other." id {base}
'''.encode()
    document = parse_scripts([("script.rpy", raw)], "a" * 64)
    assert [r.block for r in document.document.records] == [base + "_1", base + "_2", base]


def test_screen_ids_do_not_reserve_native_dialogue_identifiers():
    base = native_identifier("start", "e", "Repeated.")
    raw = f'''screen example():
    text "Ignored"
    id {base}
label start:
    e "Repeated."
    e "Repeated."
'''.encode()
    records = parse_scripts([("script.rpy", raw)], "a" * 64).document.records
    assert [record.block for record in records] == [base, base + "_1"]


def test_opaque_multiline_literals_and_nonliteral_calls_do_not_leak_code():
    raw = b'''define e = Character(_("Known"))
init python:
    example = """_("Hidden")
label fake:
    e "Not a statement."
"""
    member._("Not the translator")
    _(variable)
    _("Not complete" + variable)
label start:
    e "Visible."
'''
    document = parse_scripts([("script.rpy", raw)], "a" * 64)
    assert [r.source for r in document.document.records] == ["Known", "Visible."]


def test_custom_translatable_statements_and_broken_literals_fail_closed():
    for raw in (b'register_statement("custom")', b'label start:\n    e "broken'):
        with pytest.raises(ValueError):
            parse_scripts([("script.rpy", raw)], "a" * 64)


def test_tabs_in_comments_are_opaque_but_indentation_and_text_tabs_are_not_supported():
    raw = b'label start: # A\tcomment\n    # Another\tcomment\n    e "Visible."\n'
    parsed = parse_scripts([("script.rpy", raw)], "a" * 64)
    assert [record.source for record in parsed.document.records] == ["Visible."]
    with pytest.raises(ValueError, match="outside comments or literals"):
        parse_scripts([("script.rpy", b'label start:\n\te "Indentation."\n')], "a" * 64)
    raw += b'    e "Unsupported\ttext."\n'
    parsed = parse_scripts([("script.rpy", raw)], "a" * 64)
    assert parsed.exclusions["unsupported_say_literal"] == 1
    assert [record.source for record in parsed.document.records] == ["Visible."]


def test_commented_headers_cannot_turn_screen_or_python_properties_into_say_statements():
    raw = b'''label start:
    e "Visible."
screen controls(): # The comment does not change the block boundary.
    tooltip "Not dialogue."
    text_style "Not dialogue either."
    textbutton _("Explicit key")
init python: # This Python is never executed.
    example = "Not dialogue."
    "Not narration."
'''
    parsed = parse_scripts([("script.rpy", raw)], "a" * 64)
    assert [record.source for record in parsed.document.records] == ["Visible.", "Explicit key"]


def test_multiline_expression_arguments_are_not_independent_narration():
    raw = b'''label start:
    if person.action(messages=[
        "Not narration.",
        "Still not narration."
    ]):
        e "Actual dialogue."
    $ keys = [
        _(
            "Explicit multiline key"
        )
    ]
'''
    parsed = parse_scripts([("script.rpy", raw)], "a" * 64)
    assert [record.source for record in parsed.document.records] == [
        "Actual dialogue.", "Explicit multiline key",
    ]
    assert parsed.locations[-1]["line"] == 9


def test_delimiter_and_continuation_bounds_do_not_activate_an_incomplete_statement():
    for raw in (b'label start:\n    if call([):\n        "Invalid"\n',
                b'label start:\n    if call(\n        "Invalid"\n'):
        with pytest.raises(ValueError, match="expression"):
            parse_scripts([("script.rpy", raw)], "a" * 64)


def test_static_lexical_and_line_bounds_fail_without_partial_results(monkeypatch):
    monkeypatch.setattr("unitytranslator.renpy_scripts.MAX_LEXEMES", 4)
    with pytest.raises(ValueError, match="lexical token"):
        parse_scripts([("script.rpy", b'label start:\n    e "Hello"\n')], "a" * 64)
    with pytest.raises(ValueError, match="physical line"):
        parse_scripts([("script.rpy", b"x" * 65537)], "a" * 64)


def test_loose_source_shared_review_export_and_portable_ownership(tmp_path):
    paths, source = fixture(tmp_path)
    before = hash_file(source)
    report = extract_to_project(paths, "game/script.rpy")
    assert report["capabilities"]["extraction"]["reason"] == "native_scripts_extracted"
    with ProjectRepository(paths) as repo:
        approve(repo, "Hello [name!q].", "Merhaba [name!q].")
        approve(repo, "Display", "Ekran")
        result = export_native(repo, "turkish")
        archive = json.loads(PortableService(repo).export().read_bytes())
    assert archive["format_version"] == 3
    assert archive["source_descriptors"][0]["adapter_id"] == "renpy-scripts"
    output = list(Path(result["folder"]).glob("game/tl/turkish/*.rpy"))
    assert len(output) == 1
    records = parse_template(output[0].read_bytes(), "turkish").records
    assert [(r.kind, r.source, r.candidate) for r in records] == [
        ("dialogue", "Hello [name!q].", "Merhaba [name!q]."),
        ("string", "Display", "Ekran"),
    ]
    assert hash_file(source) == before
    manifest = json.loads(Path(result["manifest"]).read_bytes())
    assert manifest["adapter_id"] == "renpy-scripts"
    assert manifest["input_kind"] == "original_source"
    assert manifest["installation"] == "unsupported"


def test_unknown_version_and_partial_source_selection_cannot_activate(tmp_path):
    paths, source = fixture(tmp_path)
    version = paths.game / "renpy/vc_version.py"
    version.write_text("version = '9.0.0.00000000'\n")
    with pytest.raises(ValueError, match="pinned"):
        probe_source(paths, "game/script.rpy")
    assert source.is_file()


def test_worker_cannot_supply_different_source_records(tmp_path, monkeypatch):
    from unitytranslator.reader_adapters import RenpyScriptReader
    from unitytranslator.source_contracts import ReaderContext
    from unitytranslator.workers.renpy_script_probe import probe

    paths, _ = fixture(tmp_path)
    report = probe(paths.game, "game/script.rpy", "en")
    report["units"][0]["source_text"] = "Injected"
    monkeypatch.setattr("unitytranslator.worker_process.run_json_worker", lambda *a, **k: report)
    reader = RenpyScriptReader()
    context = ReaderContext(paths.game, paths.project, "en")
    with pytest.raises(ValueError, match="differs"):
        reader.probe(context, "game/script.rpy")
    with pytest.raises(ValueError, match="cancelled"):
        reader.probe(replace(context, cancelled=lambda: True), "game/script.rpy")


def test_current_source_changes_block_original_native_export(tmp_path):
    paths, source = fixture(tmp_path)
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        approve(repo, "Display", "Ekran")
        source.write_text(SOURCE + '\nlabel later:\n    "Added."\n', encoding="utf-8")
        with pytest.raises(ValueError, match="changed"):
            export_native(repo, "turkish")


def test_native_say_and_python_string_keys_use_distinct_whitespace_rules(tmp_path):
    value = "Two  spaces."
    assert ast.literal_eval(quoted_literal(value)) == value
    assert say_literal(say_quoted_literal(value)) == value
    assert read_literal(say_quoted_literal(value), say=True)[0] == value
    assert read_literal(quoted_literal(value), say=True)[0] == "Two spaces."
    paths, _ = fixture(tmp_path, r'''label start:
    e "Two \ spaces."
screen preferences():
    label _("Double  spaces")
''')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        approve(repo, "Two  spaces.", "İki  boşluk.")
        approve(repo, "Double  spaces", "Çift  boşluk")
        output = export_native(repo, "turkish")
    raw = next(Path(output["folder"]).rglob("*.rpy")).read_text(encoding="utf-8")
    assert 'e "İki \\ boşluk."' in raw
    assert 'old "Double  spaces"' in raw
    assert 'new "Çift  boşluk"' in raw
    assert [(record.source, record.candidate) for record in parse_template(
        raw.encode(), "turkish",
    ).records] == [("Two  spaces.", "İki  boşluk."), ("Double  spaces", "Çift  boşluk")]


def test_archive_source_pair_is_required_and_shared_export_rechecks_bytes(tmp_path):
    from test_renpy_archive import archive

    paths, source = fixture(tmp_path)
    raw = source.read_bytes()
    source.unlink()  # Synthetic fixture only; no real input is modified.
    compiled = b"RENPY RPC2" + b"\x00" * 36 + md5(raw, usedforsecurity=False).digest()
    path = archive(paths.game / "game/archive.rpa", {
        "script.rpy": raw, "script.rpyc": compiled,
    })
    before = hash_file(path)
    extract_to_project(paths, "game/archive.rpa")
    report = probe_source(paths, "game/archive.rpa")
    assert report["paired_source_evidence"][0]["source_footer_matches"]
    with ProjectRepository(paths) as repo:
        approve(repo, "Display", "Ekran")
        result = export_native(repo, "turkish")
        assert result["approved_translations"] == 1
    assert hash_file(path) == before
    archive(path, {"script.rpy": raw, "script.rpyc": compiled[:-16] + b"x" * 16})
    with pytest.raises(ValueError, match="compiled-source evidence"):
        probe_source(paths, "game/archive.rpa")


def test_missing_loose_member_does_not_retire_previous_records(tmp_path):
    paths, _ = fixture(tmp_path)
    extra = paths.game / "game/z_extra.rpy"
    extra.write_text('label extra:\n    "Extra text."\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        approved = approve(repo, "Extra text.", "Ek metin.")
    extra.unlink()
    with pytest.raises(ValueError, match="members are missing"):
        extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        archived = repo.db.execute(
            "SELECT active FROM text_units WHERE unit_id=?", (approved["unit_id"],),
        ).fetchone()
        assert archived[0] == 1
        assert repo.db.execute(
            "SELECT approved_translation FROM work_items WHERE unit_id=?", (approved["unit_id"],),
        ).fetchone()[0] == approved["translation_revision"]
