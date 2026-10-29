"""Synthetic Ren'Py inputs only; no installed game, engine or model is executed."""

import asyncio
import json

import httpx
import pytest

from unitytranslator.discovery import extract_to_project
from unitytranslator.domain import GenerationProfile
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.portable import PortableProject, PortableService
from unitytranslator.providers import LocalProvider, ProviderError
from unitytranslator.renpy_format import RENPY_FORMAT
from unitytranslator.renpy_templates import parse_template, quoted_literal, read_literal
from unitytranslator.repository import ProjectRepository
from unitytranslator.source_contracts import ReaderContext
from unitytranslator.validation import format_issues, mask, review_issues

TEMPLATE = '''# Synthetic fixture, not game data.
translate sample start_1234:

    # e "Hello [name!q]."
    e ""

translate sample strings:
    old "Start{#menu}"
    new "Existing{#menu}"
'''


@pytest.mark.parametrize("text", [
    "Hello [name]", "[player.names[0]!q]", "[mapping[']']!s:.2f]",
    "[[literal] {{braces} 100%%", "{b}Bold {i}italic{/i}{/b}",
    "{color=#ff00aa}Text{/color}{w=0.5}{nw}",
    "{a=jump:start}Link{/a}{image=heart.png}", "Start{#menu}", "A\r\nB",
    "[calculate({'key': values[2]})!q]",
])
def test_renpy_format_roundtrip_preserves_opaque_source_tokens(text):
    protected = mask(text, rules=RENPY_FORMAT)
    assert protected.restore(protected.text) == text
    assert not format_issues(text, text, rules=RENPY_FORMAT)


@pytest.mark.parametrize("text", [
    "[name", "[]", "{unknown}Text", "{b}open", "{b}{i}X{/b}{/i}",
    "{w=expression}", "{color=red}X{/color}", "{a=[url]}X{/a}",
    "{nw=1}", "{size=abc}X{/size}", "〖ruby〗", "\x00", "\t", "__UT_fake__",
])
def test_unsupported_text_has_no_i2_or_literal_fallback(text):
    with pytest.raises(ValueError):
        mask(text, rules=RENPY_FORMAT)
    assert format_issues(text, text, rules=RENPY_FORMAT)


@pytest.mark.parametrize("extra", ["[injected()]", "{a=jump:evil}Click{/a}", "{nw}"])
def test_model_and_manual_edits_cannot_introduce_executable_tokens(extra):
    protected = mask("Hello [name]", rules=RENPY_FORMAT)
    with pytest.raises(ValueError):
        protected.restore(protected.text + extra)
    assert format_issues("Hello [name]", "Merhaba [name]" + extra, rules=RENPY_FORMAT)


def test_exact_order_missing_tokens_and_numeric_review():
    source = "{b}Hello [values[99]]{/b}: 3"
    protected = mask(source, rules=RENPY_FORMAT)
    keys = list(protected.replacements)
    with pytest.raises(ValueError):
        protected.restore(protected.text.replace(keys[1], ""))
    with pytest.raises(ValueError):
        protected.restore(protected.text.replace(keys[1], keys[1] + keys[1]))
    assert format_issues("[a] [b]", "[b] [a]", rules=RENPY_FORMAT)
    assert not review_issues(source, "{b}Merhaba [values[99]]{/b}: 3", rules=RENPY_FORMAT)
    assert "numeric_content_review" in review_issues(
        source, "{b}Merhaba [values[99]]{/b}: 4", rules=RENPY_FORMAT
    )


def test_parser_preserves_raw_bytes_bom_comments_newlines_and_literal_spans():
    raw = b"\xef\xbb\xbf" + TEMPLATE.replace("\n", "\r\n").encode()
    document = parse_template(raw, "sample")
    assert document.raw == raw
    assert [record.source for record in document.records] == ["Hello [name!q].", "Start{#menu}"]
    text = raw.decode("utf-8-sig")
    for record in document.records:
        assert read_literal(text[record.literal_start:record.literal_end])[0] == record.candidate
    snapshot = document.snapshot("game/tl/sample/script.rpy", "en")
    assert snapshot.source.source_object == -1
    assert snapshot.source.format_rules == RENPY_FORMAT
    assert snapshot.units[0].source_text == "Hello [name!q]."
    assert snapshot.metadata["records"][1]["candidate"] == "Existing{#menu}"


@pytest.mark.parametrize("raw", [
    'label start:\n    e "Hi"',
    'translate sample python:\n    import os',
    'translate sample id:\n    e "target with no source"',
    'translate sample id:\n    # e "Hello"\n    other ""',
    'translate sample id:\n    # e "Hello"\n    e happy ""',
    'translate sample id:\n    # e "Hello"\n    e "" with dissolve',
    'translate sample id:\n    # e "Hello"\n    e _("expression")',
    'translate sample strings:\n    old "A"\n    new "A"\n    old "A"\n    new "B"',
    'translate other id:\n    # e "Hello"\n    e ""',
    'translate sample id:\n    # e "Hello"\n    e ""\ntranslate sample id:\n    # e "Hi"\n    e ""',
    'translate sample strings:\n    old "Missing new"',
])
def test_unsupported_and_ambiguous_scripts_fail_as_whole_sources(raw):
    with pytest.raises(ValueError):
        parse_template(raw.encode(), "sample")


def test_literal_emission_keeps_quotes_backslashes_and_statement_injection_inside_literal():
    source = '\"\ninit python:\n    dangerous()\n\\tail'
    emitted = quoted_literal(source)
    assert "\n" not in emitted
    assert read_literal(emitted) == (source, len(emitted))


@pytest.mark.parametrize("statement", [
    'e happy @ -sad "" nointeract', 'e happy ""', 'e @ happy ""',
])
def test_template_say_shape_must_match_the_source_comment(statement):
    raw = f'translate sample block:\n    # e happy @ -sad "Hello" nointeract\n    {statement}\n'
    if statement == 'e happy @ -sad "" nointeract':
        record = parse_template(raw.encode(), "sample").records[0]
        assert record.attributes == ("happy",) and record.temporary_attributes == ("-sad",)
        assert record.nointeract
    else:
        with pytest.raises(ValueError, match="matching source comment"):
            parse_template(raw.encode(), "sample")


@pytest.mark.parametrize("prefix", [
    'e() happy', 'e happy; call', 'e @', 'e @ happy @ sad', 'python happy',
    'e happy:', 'e - happy', 'e happy.with',
])
def test_say_attributes_cannot_introduce_expressions_or_executable_statements(prefix):
    raw = f'translate sample block:\n    # {prefix} "Hello"\n    {prefix} ""\n'
    with pytest.raises(ValueError):
        parse_template(raw.encode(), "sample")


def make_game(tmp_path):
    game = tmp_path / "game-root"
    folder = game / "game/tl/sample"
    folder.mkdir(parents=True)
    source = folder / "script.rpy"
    source.write_bytes(TEMPLATE.encode())
    return ProjectPaths(game, tmp_path / "project"), source


def test_worker_and_shared_review_invalidate_ambiguous_structural_changes(tmp_path):
    paths, source = make_game(tmp_path)
    before = hash_file(source)
    extracted = extract_to_project(paths, "game/tl/sample/script.rpy")
    assert extracted["counts"]["records"] == 2
    assert extracted["capabilities"]["translation"]["status"] == "supported"
    assert extracted["capabilities"]["installation"]["status"] == "unknown"
    assert extracted["capabilities"]["installation"]["reason"] == "native_copy_plan_required"
    with ProjectRepository(paths) as repo:
        row = next(row for row in repo.page() if row["category"] == "dialogue")
        unit_id = row["unit_id"]
        repo.edit(row["unit_id"], row["version"], "Merhaba [name!q].")
        row = next(row for row in repo.page() if row["unit_id"] == unit_id)
        repo.approve(row["unit_id"], row["version"])
        assert repo.format_rules(row["unit_id"]) == RENPY_FORMAT
    assert hash_file(source) == before
    # Source insertion changes structural context, invalidating an ambiguous slot.
    source.write_text(TEMPLATE.replace('    e ""', '    e ""\n    # e "Another"\n    e ""'))
    extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        row = next(row for row in repo.page() if row["unit_id"] == unit_id)
        assert row["status"] != "approved"


def test_partial_read_duplicate_ids_and_missing_files_preserve_existing_state(tmp_path):
    paths, source = make_game(tmp_path)
    sibling = source.with_name("other.rpy")
    sibling.write_text('translate sample second:\n    # "Other"\n    ""\n')
    extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        before = list(repo.db.iterdump())
    for content in ("init python:\n    dangerous()", TEMPLATE):
        sibling.write_text(content)
        with pytest.raises(ValueError):
            extract_to_project(paths, "game/tl/sample/script.rpy")
        with ProjectRepository(paths) as repo:
            assert list(repo.db.iterdump()) == before
    sibling.unlink()  # Synthetic temporary fixture only.
    with pytest.raises(ValueError, match="missing"):
        extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        assert list(repo.db.iterdump()) == before


def test_renpy_reader_cancels_before_worker_launch(tmp_path):
    from unitytranslator.reader_adapters import RenpyTemplateReader

    paths, _ = make_game(tmp_path)
    with pytest.raises(ValueError, match="cancelled"):
        RenpyTemplateReader().probe(
            ReaderContext(paths.game, paths.project, "en", cancelled=lambda: True),
            "game/tl/sample/script.rpy",
        )


def test_native_context_ids_and_source_revisions_do_not_inherit_unrelated_approvals(tmp_path):
    paths, source = make_game(tmp_path)
    extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        row = next(row for row in repo.page() if row["category"] == "dialogue")
        unit_id = row["unit_id"]
        repo.edit(unit_id, row["version"], "Merhaba [name!q].")
        row = next(row for row in repo.page() if row["unit_id"] == unit_id)
        repo.approve(unit_id, row["version"])
    # Target candidates and location comments do not replace local reviewed work.
    source.write_text(TEMPLATE.replace('e ""', 'e "Preexisting [name!q]."'))
    extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        row = next(row for row in repo.page() if row["unit_id"] == unit_id)
        assert row["status"] == "approved"
        assert row["translation"] == "Merhaba [name!q]."
    source.write_text(TEMPLATE.replace("start_1234", "different_1234"))
    extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        assert not any(row["status"] == "approved" for row in repo.page())
        assert repo.db.execute(
            "SELECT active FROM text_units WHERE unit_id=?", (unit_id,)
        ).fetchone()[0] == 0


def test_portable_roundtrip_preserves_renpy_ownership_without_local_approval(tmp_path):
    paths, _ = make_game(tmp_path)
    extract_to_project(paths, "game/tl/sample/script.rpy")
    with ProjectRepository(paths) as repo:
        row = next(row for row in repo.page() if row["category"] == "dialogue")
        unit_id = row["unit_id"]
        repo.edit(unit_id, row["version"], "Merhaba [name!q].")
        row = next(row for row in repo.page() if row["unit_id"] == unit_id)
        repo.approve(unit_id, row["version"])
        exported = PortableService(repo).export()
        value = PortableService(repo).read(exported)
        assert value.format_version == 3
    restored_paths = ProjectPaths(paths.game, tmp_path / "restored")
    with ProjectRepository(restored_paths) as repo:
        result = PortableService(repo).restore(value)
        assert result["local_approvals"] == 0
        assert repo.format_rules(unit_id) == RENPY_FORMAT
        assert repo.page()[0]["status"] != "approved"
        assert repo.db.execute("SELECT count(*) FROM snapshot_sources").fetchone()[0] == 0
        row = next(row for row in repo.page() if row["unit_id"] == unit_id)
        with pytest.raises(ValueError):
            repo.edit(unit_id, row["version"], "[inject()]")
        assert repo.format_rules(unit_id) == RENPY_FORMAT
        damaged = value.model_dump()
        damaged["source_descriptors"][0]["format_rules"] = "literal-lines-v1"
        with pytest.raises(ValueError, match="ownership or format"):
            PortableService(repo).validate_history(PortableProject.model_validate(damaged))
        damaged = value.model_dump()
        damaged["format_version"] = 2
        damaged.pop("source_descriptors")
        with pytest.raises(ValueError, match="format 3"):
            PortableService(repo).validate_history(PortableProject.model_validate(damaged))


def test_existing_pilot_queue_translates_renpy_sources_without_granting_approval(tmp_path):
    paths, _ = make_game(tmp_path)
    extract_to_project(paths, "game/tl/sample/script.rpy")
    seen = []

    def handler(request):
        value = json.loads(json.loads(request.content)["messages"][1]["content"])
        seen.append(value)
        target = value["source"].replace("Hello", "Merhaba").replace("Start", "Başla")
        return httpx.Response(200, json={"choices": [{"message": {
            "content": json.dumps({"translations": [{"id": value["id"], "text": target}]})
        }}]})

    provider = LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))
    with ProjectRepository(paths) as repo:
        profile = GenerationProfile("lm-studio", "http://localhost:1234", "synthetic", 8192)
        job = JobStore(repo).create([r["unit_id"] for r in repo.page()], profile, kind="pilot")
        result = asyncio.run(TranslationJobService(repo, lambda _: provider).run(job))
        assert result["counts"] == {"completed": 2}
        assert len(seen) == 2
        assert all("Ren'Py" in value["context"] for value in seen)
        assert all(row["translation"] and row["status"] != "approved" for row in repo.page())
        for row in repo.db.execute("SELECT metadata_json FROM translation_revisions"):
            assert json.loads(row[0])["protected_format_version"] == RENPY_FORMAT


def test_desktop_scans_selects_and_extracts_native_templates(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QPushButton
    from test_ui import wait_for

    from unitytranslator.ui.i18n import tr
    from unitytranslator.ui.window import MainWindow

    paths, _ = make_game(tmp_path)
    app = QApplication.instance()
    window = MainWindow()
    results, errors = {}, []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.bridge.completed.connect(lambda command, result: results.update({command: result}))
    window.game_path.setText(str(paths.game))
    window.project_path.setText(str(paths.project))
    window.open_project()
    window.show()
    try:
        wait_for(app, lambda: window.project_open and "deployment_status" in results)
        assert results["deployment_status"]["kit_available"] is False
        window.inspection_engine.setCurrentIndex(window.inspection_engine.findData("renpy"))
        next(button for button in window.findChildren(QPushButton)
             if button.text() == tr("Read-only compatibility scan")).click()
        wait_for(app, lambda: "scan" in results)
        assert results["scan"]["result"]["engine_report"]["selection"] == "renpy"
        assert window.source_file.currentText() == "game/tl/sample/script.rpy"
        assert "Ren'Py" in window.discovery.toPlainText()
        next(button for button in window.findChildren(QPushButton)
             if button.text() == tr("Read the source and extract text")).click()
        wait_for(app, lambda: window.review_model.rowCount() == 2)
        assert all(row["format_rules"] == RENPY_FORMAT for row in window.review_model.rows)
        assert not errors
        window.tabs.setCurrentIndex(1)
        assert window.grab().save(str(tmp_path / "native-template-discovery.png"))
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)


@pytest.mark.parametrize("injection", [False, True])
def test_shared_provider_uses_renpy_tokens_without_i2_plural_interpretation(injection):
    def handler(request):
        value = json.loads(json.loads(request.content)["messages"][1]["content"])
        translation = value["source"].replace("Hello", "Merhaba")
        if injection:
            translation += "[execute()]"
        return httpx.Response(200, json={"choices": [{"message": {
            "content": json.dumps({"translations": [{"id": value["id"], "text": translation}]})
        }}]})

    provider = LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))
    call = provider.translate_record(
        "synthetic", "Hello [name!q]", "record", "en", "tr",
        context_tokens=8192, format_rules=RENPY_FORMAT,
    )
    if injection:
        with pytest.raises(ProviderError) as error:
            asyncio.run(call)
        assert error.value.code == "protected_content_error"
    else:
        assert asyncio.run(call)["translation"] == "Merhaba [name!q]"
