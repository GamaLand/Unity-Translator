"""Large synthetic source sets, incremental bounds and complete-block sharding."""

import json
from hashlib import sha256
from pathlib import Path

import pytest
from test_renpy_scripts import approve, fixture

from unitytranslator.discovery import extract_to_project
from unitytranslator.filesystem import hash_file
from unitytranslator.renpy_export import _emit, export_native
from unitytranslator.renpy_scripts import parse_scripts
from unitytranslator.renpy_templates import MAX_FILE_BYTES, parse_template
from unitytranslator.repository import ProjectRepository


def test_reader_activates_a_large_complete_set_beyond_the_pilot_bounds(tmp_path):
    paths, first = fixture(tmp_path, 'label chapter_0000:\n    e "Existing."\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        old = approve(repo, "Existing.", "Mevcut.")
    original = hash_file(first)
    total = first.stat().st_size
    for index in range(1, 589):
        body = f"label chapter_{index:04d}:\n" + "".join(
            f'    e "Synthetic {index:04d}/{line:02d}: ' + "text " * 95 + '."\n'
            for line in range(20)
        )
        # Untranslated comments exercise retained originals without harvesting text.
        raw = body.encode() + b"#" + b"x" * (33000 - len(body.encode()) - 2) + b"\n"
        path = first.parent / f"z_chapter_{index:04d}.rpy"
        path.write_bytes(raw)
        total += len(raw)
    assert total > 18 * 1024 * 1024
    result = extract_to_project(paths, "game/script.rpy")
    assert result["counts"]["records"] == 1 + 588 * 20
    assert Path(result["report"]).stat().st_size > 32 * 1024 * 1024
    with ProjectRepository(paths) as repo:
        assert repo.db.execute("SELECT count(*) FROM text_units WHERE active=1").fetchone()[0] == (
            1 + 588 * 20
        )
        current = next(r for r in repo.page() if r["unit_id"] == old["unit_id"])
        assert current == old
        assert repo.db.execute("SELECT count(*) FROM source_descriptors").fetchone()[0] == 1
    assert hash_file(first) == original
    assert len(list(first.parent.glob("*.rpy"))) == 589


def test_generator_is_parsed_before_the_next_original_member_is_read(monkeypatch):
    from unitytranslator.renpy_scripts import lex

    operations = []

    def members():
        for index in range(3):
            operations.append(("read", index))
            yield f"{index}.rpy", f'label chapter_{index}:\n    "Hello {index}."\n'.encode()

    def tracked(text):
        operations.append(("parse", len(operations) // 2))
        return lex(text)

    monkeypatch.setattr("unitytranslator.renpy_scripts.lex", tracked)
    document = parse_scripts(members(), "a" * 64)
    assert len(document.members) == 3
    assert operations == [(kind, index) for index in range(3) for kind in ("read", "parse")]


def test_failure_at_the_end_of_an_expanded_inventory_preserves_prior_work(tmp_path):
    paths, _ = fixture(tmp_path, 'label start:\n    e "Existing."\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        old = approve(repo, "Existing.", "Mevcut.")
        snapshots = repo.db.execute("SELECT count(*) FROM source_snapshots").fetchone()[0]
    for index in range(130):
        (paths.game / f"game/z_{index:04d}.rpy").write_bytes(
            f'label chapter_{index}:\n    "New {index}."\n'.encode()
        )
    (paths.game / "game/zz_broken.rpy").write_bytes(b'"Unterminated')
    with pytest.raises(ValueError, match="Unterminated"):
        extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        assert repo.page() == [old]
        assert repo.db.execute("SELECT count(*) FROM source_snapshots").fetchone()[0] == snapshots


def test_new_earlier_filename_keeps_the_original_logical_source_and_approval(tmp_path):
    paths, _ = fixture(tmp_path, 'label start:\n    e "Existing."\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        old = approve(repo, "Existing.", "Mevcut.")
        descriptor = repo.db.execute("SELECT id FROM source_descriptors").fetchone()[0]
    (paths.game / "game/a_earlier.rpy").write_text('label earlier:\n    e "New."\n')
    extract_to_project(paths, "game/a_earlier.rpy")
    with ProjectRepository(paths) as repo:
        current = next(row for row in repo.page() if row["unit_id"] == old["unit_id"])
        assert current == old
        assert repo.db.execute("SELECT id FROM source_descriptors").fetchall()[0][0] == descriptor
        assert repo.db.execute("SELECT count(*) FROM source_descriptors").fetchone()[0] == 1
        assert len(repo.page()) == 2


@pytest.mark.parametrize("limit", ["MAX_FILES", "MAX_TOTAL_BYTES", "MAX_RECORDS", "MAX_OCCURRENCES",
                                   "MAX_TOTAL_LEXEMES"])
def test_incremental_limits_refuse_the_whole_set_including_literal_ui_keys(monkeypatch, limit):
    monkeypatch.setattr("unitytranslator.renpy_scripts." + limit, 1)
    with pytest.raises(ValueError, match="bound|limit"):
        parse_scripts(iter([
            ("a.rpy", b'$ first = _("One")\n$ second = _("Two")\n'),
            ("b.rpy", b'$ third = _("Three")\n'),
        ]), "a" * 64)


def test_streamed_inventory_must_be_unique_sorted_and_cancellable():
    raw = b'label chapter:\n    "Hello."\n'
    for names in (("b.rpy", "a.rpy"), ("a.rpy", "a.rpy")):
        with pytest.raises(ValueError, match="duplicate or out of order"):
            parse_scripts(iter((name, raw) for name in names), "a" * 64)
    with pytest.raises(ValueError, match="cancelled"):
        parse_scripts(iter([("a.rpy", raw)]), "a" * 64, cancelled=lambda: True)


def test_more_than_ten_thousand_native_records_are_sharded_and_reparse():
    raw = b'label chapter:\n' + b''.join(
        f'    e "Synthetic dialogue {index}."\n'.encode() for index in range(10005)
    )
    parsed = parse_scripts([("script.rpy", raw)], sha256(raw).hexdigest())
    snapshot = parsed.snapshot("game/script.rpy", "en")
    selection = {unit.unit_id: {"translation": unit.source_text.replace("Synthetic", "Translated")}
                 for unit in snapshot.units}
    payloads, counts = _emit(parsed.document, snapshot, "turkish", selection, {}, set())
    assert len(payloads) == 3
    assert counts["dialogue_statements"] == 10005
    records = [record for payload in payloads
               for record in parse_template(payload, "turkish").records]
    assert [record.block for record in records] == [r.block for r in parsed.document.records]
    assert len({record.block for record in records}) == 10005
    assert all(len(payload) <= MAX_FILE_BYTES for payload in payloads)


def test_repeated_dialogue_serials_preserve_allocation_across_member_boundaries():
    from unitytranslator.renpy_scripts import native_identifier

    raw = b'label chapter:\n' + b'    "Repeated."\n' * 4096
    document = parse_scripts([("a.rpy", raw), ("b.rpy", raw)], "a" * 64)
    base = native_identifier("chapter", "", "Repeated.")
    assert [record.block for record in document.document.records] == [
        base, *(base + "_" + str(index) for index in range(1, 8192))
    ]


def test_native_identifiers_and_snapshot_context_have_independent_bounds(monkeypatch):
    monkeypatch.setattr("unitytranslator.renpy_scripts.MAX_NATIVE_IDENTIFIER", 16)
    with pytest.raises(ValueError, match="identifier size limit"):
        parse_scripts([("a.rpy", b'label chapter_long:\n    "Hello."\n')], "a" * 64)
    monkeypatch.setattr("unitytranslator.renpy_scripts.MAX_NATIVE_IDENTIFIER", 2000)
    document = parse_scripts([("a.rpy", b'label chapter:\n    "Hello."\n')], "a" * 64)
    monkeypatch.setattr("unitytranslator.renpy_templates.MAX_CONTEXT_BYTES", 10)
    with pytest.raises(ValueError, match="context size limit"):
        document.snapshot("game/a.rpy", "en")


def test_shard_boundaries_preserve_complete_blocks_and_unique_strings(tmp_path, monkeypatch):
    from test_renpy_export import fixture_paths

    paths = fixture_paths(tmp_path)
    monkeypatch.setattr("unitytranslator.renpy_export.SHARD_RECORDS", 1)
    with ProjectRepository(paths) as repo:
        approve(repo, "Hello [name!q].", "Merhaba [name!q].")
        approve(repo, "Start{#menu}", "Başla{#menu}")
        result = export_native(repo, "turkish")
        assert result["files"] == 2
    manifest = json.loads(Path(result["manifest"]).read_bytes())
    assert manifest["format_version"] == 2
    outputs = manifest["coverage"][0]["files"]
    assert len(outputs) == 2
    groups = [parse_template((Path(result["folder"]) / output["file"]).read_bytes(),
                             "turkish").records for output in outputs]
    dialogue = next(group for group in groups if group[0].kind == "dialogue")
    assert len(dialogue) == 2  # Approved first statement plus its original fallback.
    assert len({record.block for record in dialogue}) == 1
    assert sum(record.kind == "string" for group in groups for record in group) == 1
    assert manifest["coverage"][0]["fallback_dialogue"] == 1
