"""Native-ID serials for excluded say statements; synthetic static sources only."""

import sqlite3

import pytest
from test_renpy_scripts import approve, fixture

from unitytranslator.discovery import extract_to_project
from unitytranslator.renpy_scripts import (
    NATIVE_ID_ALLOCATION,
    native_identifier,
    parse_scripts,
)
from unitytranslator.repository import ProjectRepository

# Two different say codes whose truncated MD5 bases collide (synthetic vector).
EXTEND_LINE = 'extend "Line 120884."'
COLLIDING = 'e "Line 11374."'


def records(source: str):
    document = parse_scripts([("script.rpy", source.encode())], "a" * 64)
    return document, document.document.records


def test_collision_vector_precondition() -> None:
    assert native_identifier("start", "extend", "Line 120884.") == native_identifier(
        "start", "e", "Line 11374."
    )


def test_extend_is_counted_and_reserves_its_native_serial() -> None:
    document, found = records(
        f'label start:\n    e "Before."\n    {EXTEND_LINE}\n    {COLLIDING}\n'
    )
    base = native_identifier("start", "e", "Line 11374.")
    assert [r.block for r in found] == [native_identifier("start", "e", "Before."), base + "_1"]
    assert document.exclusions["extend_say"] == 1
    snapshot = document.snapshot("game/script.rpy", "en")
    assert snapshot.metadata["native_id_allocation"] == NATIVE_ID_ALLOCATION


def test_extend_explicit_id_is_preexisting() -> None:
    base = native_identifier("start", "e", "Repeated.")
    _, found = records(f'label start:\n    extend "x" id {base}\n    e "Repeated."\n')
    assert [r.block for r in found] == [base + "_1"]


@pytest.mark.parametrize(
    "excluded",
    [
        'e """Hello."""',
        "e `Hello.`",
        'e "Hel\\u006co."',
        'e"Hello."',
        'e "Hello.\n        "',
    ],
)
def test_possible_equal_code_exclusions_refuse_ambiguous_serials(excluded: str) -> None:
    with pytest.raises(ValueError, match="serials are ambiguous"):
        records(f'label start:\n    {excluded}\n    e "Hello."\n')


@pytest.mark.parametrize(
    "source",
    [
        'label start:\n    e "Hello."\n    e """Hello."""\n',  # excluded after the last copy
        'label start:\n    f """Hello."""\n    e "Hello."\n',  # different speaker
        'label other:\n    e """Hello."""\nlabel start:\n    e "Hello."\n',  # other label
        'label start:\n    e "Hello." with dissolve\n    e "Hello."\n',  # suffix differs
        'label start:\n    e "a__b"\n    e "Hello."\n',  # private name text
    ],
)
def test_exclusions_that_cannot_share_a_base_keep_ids(source: str) -> None:
    _, found = records(source)
    assert native_identifier("start", "e", "Hello.") in [r.block for r in found]


def test_changed_native_id_becomes_new_unit_with_history(tmp_path) -> None:
    paths, path = fixture(tmp_path, f'label start:\n    e "Before."\n    {COLLIDING}\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        approve(repo, "Before.", "Önce.")
        approve(repo, "Line 11374.", "Satır 11374.")
        old = {r["source_text"]: r for r in repo.page()}
    path.write_text(
        f'label start:\n    e "Before."\n    {EXTEND_LINE}\n    {COLLIDING}\n', encoding="utf-8"
    )
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        current = {r["source_text"]: r for r in repo.page()}
        kept = current["Before."]
        assert kept["unit_id"] == old["Before."]["unit_id"]
        assert kept["status"] == "approved" and kept["version"] == old["Before."]["version"]
        moved = current["Line 11374."]
        assert moved["unit_id"] != old["Line 11374."]["unit_id"]
        assert moved["status"] == "pending"
        assert moved["original_key"].endswith(
            native_identifier("start", "e", "Line 11374.") + "_1/0"
        )
        history = repo.db.execute(
            "SELECT u.active,w.status,w.approved_translation FROM text_units u "
            "JOIN work_items w USING(unit_id) WHERE unit_id=?",
            (old["Line 11374."]["unit_id"],),
        ).fetchone()
        assert history[0] == 0 and history[1] == "approved" and history[2] is not None


def test_ambiguous_serial_refusal_preserves_previous_snapshot(tmp_path) -> None:
    paths, path = fixture(tmp_path, f'label start:\n    {COLLIDING}\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        approve(repo, "Line 11374.", "Satır 11374.")
    database = paths.project / "project.sqlite3"
    with sqlite3.connect(database) as db:
        before = list(db.iterdump())
    path.write_text(
        'label start:\n    e """Line 11374."""\n    e "Line 11374."\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="serials are ambiguous"):
        extract_to_project(paths, "game/script.rpy")
    with sqlite3.connect(database) as db:
        assert list(db.iterdump()) == before


def test_voiced_line_repeated_unvoiced_keeps_the_plain_base() -> None:
    for group in ('voice "a.ogg"', "nvl clear"):
        _, found = records(f'label start:\n    {group}\n    e "Hello."\n    e "Hello."\n')
        assert [r.block for r in found] == [native_identifier("start", "e", "Hello.")]


@pytest.mark.parametrize(
    "source",
    [
        # Explicit nointeract outside a menu shares its code with a speaker's menu say.
        'label start:\n    e r"Hello." nointeract\n    menu:\n        e "Hello."\n'
        '        "Yes":\n            pass\n',
        'label start:\n    e """Hello.""" nointeract\n    e "Hello." nointeract\n',
    ],
)
def test_effective_nointeract_is_part_of_the_suspect_key(source: str) -> None:
    with pytest.raises(ValueError, match="serials are ambiguous"):
        records(source)


@pytest.mark.parametrize(
    "excluded,speaker",
    [('r"Hello."', ""), ('e r"Hello."', "e "), ('e"Hello."', "e ")],
)
def test_other_exclusions_inside_a_voice_group_do_not_refuse(excluded, speaker) -> None:
    lines = ["label start:", '    voice "a.ogg"', "    " + excluded,
             "    " + speaker + '"Hello."', "    " + speaker + '"Hello."']
    _, found = records("\n".join(lines) + "\n")
    assert len(found) == 2
