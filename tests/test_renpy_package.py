"""Synthetic Windows recipient-copy checks. No synthetic or real game is launched."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest
from test_renpy_scripts import approve, fixture

from unitytranslator.application import ApplicationSession
from unitytranslator.discovery import extract_to_project
from unitytranslator.filesystem import hash_file
from unitytranslator.renpy_package import export_copy_package
from unitytranslator.renpy_templates import quoted_literal, say_quoted_literal
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def package(tmp_path):
    paths, source = fixture(tmp_path)
    (paths.game / "Synthetic.exe").write_bytes(b"Synthetic EXE; must never execute")
    (paths.game / "renpy/vendor_module.pyc").write_bytes(b"Sourceless module; never executed")
    for relative in ("game/saves/private-secret.save", "game/cache/test.rpyb",
                     "renpy/__pycache__/vc_version.cpython-39.pyc", "log.txt"):
        path = paths.game / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"PRIVATE RUNTIME DATA; MUST NOT APPEAR IN PACKAGE")
    extract_to_project(paths, "game/script.rpy")
    originals = {p.relative_to(paths.game).as_posix(): hash_file(p)
                 for p in paths.game.rglob("*") if p.is_file()}
    with ProjectRepository(paths) as repo:
        approve(repo, "Display", "Ekran")
        before = repo.page()
        result = export_copy_package(repo, "turkish")
        assert repo.page() == before
    root = tmp_path / "recipient-package"
    with zipfile.ZipFile(result["path"]) as archive:
        assert archive.testzip() is None
        archive.extractall(root)  # Our fixed exporter-generated synthetic ZIP only.
    manifest = json.loads((root / "package.json").read_bytes())
    return paths, originals, result, root, manifest


def run_ps(root, *args):
    powershell = shutil.which("powershell.exe")
    if sys.platform != "win32" or powershell is None:
        pytest.skip("Windows PowerShell required for native recipient checks")
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(root / "renpy-copy.ps1"), *map(str, args)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        input="CANCEL\n", timeout=90, check=False,
    )


def reviewed_install(package, tmp_path):
    paths, originals, result, root, manifest = package
    output = tmp_path / "translated copy's & parent"
    output.mkdir()
    review = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output, "-ReviewOnly")
    assert review.returncode == 0, review.stderr
    plan = json.loads(review.stdout)
    assert list(output.iterdir()) == []
    installed = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output,
                       "-ReviewedPlanSha256", plan["sha256"])
    assert installed.returncode == 0, installed.stderr
    target = Path(json.loads(installed.stdout)["target"])
    assert target == output / manifest["copy_folder"]
    return target, plan


def test_package_contains_only_reviewed_text_and_fixed_installer(package):
    paths, originals, result, root, manifest = package
    assert result["installation_mode"] == "new-translated-copy"
    assert not result["requires_unitytranslator"]
    assert result["records"] == 1
    assert len(manifest["copy_omissions"]) == 4
    assert any(entry["path"] == "renpy/vendor_module.pyc" for entry in manifest["copy_files"])
    with zipfile.ZipFile(result["path"]) as archive:
        for name in archive.namelist():
            raw = archive.read(name)
            assert b"PRIVATE RUNTIME DATA" not in raw
            assert b"private-secret.save" not in raw
            assert str(paths.project).encode() not in raw
            assert str(paths.game).encode() not in raw
            assert b"Voice group is excluded." not in raw
        assert not any(name.endswith(".exe") for name in archive.namelist())
    assert json.loads((root / "native-manifest.json").read_bytes())["selection"]
    assert originals == {p.relative_to(paths.game).as_posix(): hash_file(p)
                         for p in paths.game.rglob("*") if p.is_file()}


@pytest.mark.parametrize("relative", [".git/config", ".aider.tags.cache.v4/private", ".env.local"])
def test_export_refuses_private_development_metadata_instead_of_silently_omitting_it(
    tmp_path, relative,
):
    paths, _ = fixture(tmp_path)
    (paths.game / "Synthetic.exe").write_bytes(b"Never execute")
    private = paths.game / relative
    private.parent.mkdir(parents=True, exist_ok=True)
    private.write_bytes(b"PRIVATE; NOT A DISTRIBUTION INPUT")
    extract_to_project(paths, "game/script.rpy")
    before = hash_file(private)
    with ProjectRepository(paths) as repo:
        approve(repo, "Display", "Ekran")
        with pytest.raises(ValueError, match="reviewed clean game build"):
            export_copy_package(repo, "turkish")
    assert hash_file(private) == before
    assert not list(paths.project.glob("exports/*renpy-copy*.zip"))


def test_recipient_refuses_a_private_copy_scope_even_with_matching_build_hash(package, tmp_path):
    paths, _, _, root, manifest = package
    private = paths.game / ".env.private"
    private.write_bytes(b"PRIVATE; NEVER COPY")
    manifest["copy_files"].append({"path": ".env.private", "bytes": private.stat().st_size,
                                   "sha256": hash_file(private)})
    (root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    checked = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output, "-ReviewOnly")
    assert checked.returncode != 0
    assert list(output.iterdir()) == []


def test_recipient_plan_install_and_launch_review_do_not_change_originals(package, tmp_path):
    paths, originals, result, root, manifest = package
    target, plan = reviewed_install(package, tmp_path)
    assert (target / "Synthetic.exe").read_bytes() == (paths.game / "Synthetic.exe").read_bytes()
    assert not (target / "game/saves").exists()
    assert not (target / "game/cache").exists()
    receipt = json.loads((target / ".unitytranslator/renpy-copy/receipt.json").read_bytes())
    assert receipt["status"] == "installed"
    assert receipt["reviewed_plan_sha256"] == plan["sha256"]
    assert all(entry["identity"] for entry in receipt["files"])
    launch = run_ps(target / ".unitytranslator/renpy-copy", "-Action", "Launch", "-ReviewOnly")
    assert launch.returncode == 0, launch.stderr
    assert not json.loads(launch.stdout)["game_started"]
    assert not (target / ".unitytranslator/renpy-copy/saves").exists()
    assert originals == {p.relative_to(paths.game).as_posix(): hash_file(p)
                         for p in paths.game.rglob("*") if p.is_file()}


def test_wrong_review_existing_output_and_changed_source_are_rejected(package, tmp_path):
    paths, originals, result, root, manifest = package
    output = tmp_path / "output"
    output.mkdir()
    bad = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output,
                 "-ReviewedPlanSha256", "0" * 64)
    assert bad.returncode != 0
    assert list(output.iterdir()) == []
    target = output / manifest["copy_folder"]
    target.mkdir()
    sentinel = target / "user.txt"
    sentinel.write_text("Preserve")
    existing = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output, "-ReviewOnly")
    assert existing.returncode != 0
    assert sentinel.read_text() == "Preserve"
    other_output = tmp_path / "other-output"
    other_output.mkdir()
    (paths.game / "Synthetic.exe").write_bytes(b"Different synthetic build")
    changed = run_ps(root, "-GameFolder", paths.game, "-OutputParent", other_output, "-ReviewOnly")
    assert changed.returncode != 0
    assert list(other_output.iterdir()) == []


def test_drive_root_output_parent_keeps_absolute_review_target(package):
    paths, _, _, root, manifest = package
    drive = Path(paths.game.anchor)
    reviewed = run_ps(root, "-GameFolder", paths.game, "-OutputParent", drive, "-ReviewOnly")
    assert reviewed.returncode == 0, reviewed.stderr
    target = Path(json.loads(reviewed.stdout)["plan"]["target"])
    assert target == drive / manifest["copy_folder"]
    assert not target.exists()


def test_removal_preserves_modified_owned_and_unknown_runtime_files(package, tmp_path):
    paths, originals, result, root, manifest = package
    target, _ = reviewed_install(package, tmp_path)
    modified = target / "game/script.rpy"
    modified.write_bytes(b"User modified copy; preserve")
    unknown = target / (manifest["payloads"][0]["path"] + "c")
    unknown.write_bytes(b"Unknown compiled sidecar; preserve")
    review = run_ps(root, "-Action", "Remove", "-InstallFolder", target, "-ReviewOnly")
    assert review.returncode == 0, review.stderr
    plan = json.loads(review.stdout)
    removed = run_ps(root, "-Action", "Remove", "-InstallFolder", target,
                     "-ReviewedPlanSha256", plan["sha256"])
    assert removed.returncode == 0, removed.stderr
    report = json.loads(removed.stdout)
    assert report["status"] == "owned_files_removed_runtime_data_retained"
    assert "game/script.rpy" in report["changed_files_preserved"]
    audit = json.loads((target / report["removal_receipt"]).read_bytes())
    assert audit["reviewed_plan_sha256"] == plan["sha256"]
    assert modified.read_bytes() == b"User modified copy; preserve"
    assert unknown.read_bytes() == b"Unknown compiled sidecar; preserve"
    assert not (target / manifest["payloads"][0]["path"]).exists()
    assert (paths.game / "Synthetic.exe").exists()
    assert originals == {p.relative_to(paths.game).as_posix(): hash_file(p)
                         for p in paths.game.rglob("*") if p.is_file()}


def test_hardlinked_owned_payload_is_preserved_on_removal(package, tmp_path):
    target, _ = reviewed_install(package, tmp_path)
    root, manifest = package[3:]
    path = target / manifest["payloads"][0]["path"]
    alias = tmp_path / "linked-user-file"
    try:
        os.link(path, alias)
    except OSError:
        pytest.skip("Hardlinks unavailable")
    review = run_ps(root, "-Action", "Remove", "-InstallFolder", target, "-ReviewOnly")
    assert review.returncode == 0, review.stderr
    removed = run_ps(root, "-Action", "Remove", "-InstallFolder", target,
                     "-ReviewedPlanSha256", json.loads(review.stdout)["sha256"])
    assert removed.returncode == 0, removed.stderr
    assert path.exists() and alias.read_bytes() == path.read_bytes()


def test_shared_session_and_cli_package_use_current_project_binding(package, monkeypatch, capsys):
    from unitytranslator.__main__ import main

    paths = package[0]

    async def run():
        session = ApplicationSession()
        try:
            await session.dispatch("open", {"project": str(paths.project), "existing_only": True})
            with pytest.raises(ValueError, match="Project changed"):
                await session.dispatch("renpy_package", {
                    "project_id": "stale", "language": "turkish",
                })
        finally:
            await session.close()

    asyncio.run(run())
    monkeypatch.setattr(sys, "argv", [
        "unitytranslator", "export-renpy-zip", "--game", str(paths.game),
        "--project", str(paths.project), "--language", "turkish",
    ])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["installation_mode"] == "original-additions"
    assert Path(result["path"]).is_file()


@pytest.mark.parametrize("unsaved_draft", [False, True])
def test_desktop_copy_zip_uses_shared_draft_checks(package, tmp_path, unsaved_draft):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from test_ui import wait_for

    from unitytranslator.ui.window import MainWindow

    paths = package[0]
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
        wait_for(app, lambda: window.renpy_available and window.review_model.rowCount() > 0)
        row = next(index for index, item in enumerate(window.review_model.rows)
                   if item["source_text"] == "Hello [name!q].")
        window.table.selectRow(row)
        window.renpy_language.setText("turkish")
        assert window.renpy_package_button.isEnabled()
        if unsaved_draft:
            window.translation_editor.setPlainText("Merhaba [name!q].")
        window.renpy_package_button.click()
        if unsaved_draft:
            wait_for(app, lambda: bool(errors))
            assert errors[-1][0] == "renpy_package" and "drafts" in errors[-1][1]
        else:
            wait_for(app, lambda: "renpy_package" in results)
            assert Path(results["renpy_package"]["path"]).is_file()
            assert "Install.cmd" in window.export_status.toPlainText()
            assert not errors
        for index in range(window.tabs.count()):
            if window.tabs.widget(index).isAncestorOf(window.renpy_export_group):
                window.tabs.setCurrentIndex(index)
                break
        app.processEvents()
        assert window.grab().save(str(tmp_path / "native-copy-package.png"))
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)


def test_approval_change_during_zip_staging_prevents_publication(package, monkeypatch):
    paths = package[0]
    existing = set(paths.project.glob("exports/renpy-copy-*.zip"))
    with ProjectRepository(paths) as repo:
        original_write = zipfile.ZipFile.writestr

        def write(archive, name, data, *args, **kwargs):
            result = original_write(archive, name, data, *args, **kwargs)
            if name == "package.json":
                repo.db.execute(
                    "UPDATE work_items SET approved_source=NULL WHERE status='approved'"
                )
            return result

        monkeypatch.setattr(zipfile.ZipFile, "writestr", write)
        with pytest.raises(ValueError, match="approval or draft changed"):
            export_copy_package(repo, "turkish")
    assert set(paths.project.glob("exports/renpy-copy-*.zip")) == existing
    assert list(paths.project.glob("exports/.pending-renpy-copy-*.zip"))


@pytest.mark.parametrize(("source", "target", "accepted"), [
    ("Hello [name!q]", "Merhaba [name!q]", True),
    ("Hello [items['name'][0]!q]", "Merhaba [items['name'][0]!q]", True),
    ("{b}3{/b}\n[[literal", "{b}3{/b}\n[[metin", True),
    ("{#context}One", "{#context}Bir", True),
    ("Emoji \U0001f600", "Emoji \U0001f600", True),
    ("Two  spaces", "İki  boşluk", True),
    ("One\r\nTwo", "Bir\r\nİki", True),
    ("Hi", "Hi [execute()]", False),
    ("Hi [name]", "Hi [name!q]", False),
    ("{b}One{/b}", "{b}Bir{/i}", False),
    ("{unknown}One{/unknown}", "{unknown}Bir{/unknown}", False),
])
def test_recipient_revalidates_fixed_grammar_and_opaque_tokens(
    package, tmp_path, source, target, accepted,
):
    paths, _, _, root, manifest = package
    entry = manifest["payloads"][0]
    raw = (
        "translate turkish strings:\n    old " + quoted_literal(source)
        + "\n    new " + quoted_literal(target) + "\n"
    ).encode("utf-8")
    (root / "payload" / entry["path"]).write_bytes(raw)
    entry.update(sha256=sha256(raw).hexdigest(), bytes=len(raw))
    (root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    result = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output, "-ReviewOnly")
    assert (result.returncode == 0) == accepted, result.stderr
    assert list(output.iterdir()) == []


def test_recipient_refuses_executable_script_even_with_matching_payload_hash(package, tmp_path):
    paths, _, _, root, manifest = package
    entry = manifest["payloads"][0]
    raw = b'init python:\n    raise RuntimeError("MUST NEVER EXECUTE")\n'
    (root / "payload" / entry["path"]).write_bytes(raw)
    entry.update(sha256=sha256(raw).hexdigest(), bytes=len(raw))
    (root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    result = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output, "-ReviewOnly")
    assert result.returncode != 0
    assert list(output.iterdir()) == []


def test_recipient_say_grammar_preserves_escaped_spaces(package, tmp_path):
    paths, _, _, root, manifest = package
    entry = manifest["payloads"][0]
    source, target = "Hello  [name!q].", "Merhaba  [name!q]."
    raw = (
        "translate turkish start_fixture:\n    # e " + say_quoted_literal(source)
        + "\n    e " + say_quoted_literal(target) + "\n"
    ).encode("utf-8")
    (root / "payload" / entry["path"]).write_bytes(raw)
    entry.update(sha256=sha256(raw).hexdigest(), bytes=len(raw))
    (root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    checked = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output, "-ReviewOnly")
    assert checked.returncode == 0, checked.stderr
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(("target_shape", "accepted"), [
    ('e -sad @ happy "Merhaba [name!q]." nointeract', True),
    ('e sad @ happy "Merhaba [name!q]." nointeract', False),
    ('e -sad @ happy "Merhaba [name!q]."', False),
    ('e -sad @ happy "Merhaba [name!q]." nointeract; jump evil', False),
    ('e() -sad @ happy "Merhaba [name!q]." nointeract', False),
])
def test_recipient_checks_attribute_and_interaction_structure(
    package, tmp_path, target_shape, accepted,
):
    paths, _, _, root, manifest = package
    entry = manifest["payloads"][0]
    raw = (
        'translate turkish start_fixture:\n'
        '    # e -sad @ happy "Hello [name!q]." nointeract\n'
        f'    {target_shape}\n'
    ).encode()
    (root / "payload" / entry["path"]).write_bytes(raw)
    entry.update(sha256=sha256(raw).hexdigest(), bytes=len(raw))
    (root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    checked = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output, "-ReviewOnly")
    assert (checked.returncode == 0) == accepted, checked.stderr
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("kind", ["dialogue", "string"])
def test_recipient_rejects_duplicate_native_identity_across_shards(package, tmp_path, kind):
    paths, _, _, root, manifest = package
    prefix = manifest["payloads"][0]["path"].removesuffix(".rpy")
    raw = (
        b'translate turkish repeated:\n    # e "Hello"\n    e "Merhaba"\n'
        if kind == "dialogue" else
        b'translate turkish strings:\n    old "Hi"\n    new "Merhaba"\n'
    )
    payloads = []
    for index in (1, 2):
        name = prefix + f"_{index:04d}.rpy"
        (root / "payload" / name).write_bytes(raw)
        payloads.append({"path": name, "bytes": len(raw), "sha256": sha256(raw).hexdigest()})
    manifest["payloads"] = payloads
    (root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    checked = run_ps(root, "-GameFolder", paths.game, "-OutputParent", output, "-ReviewOnly")
    assert checked.returncode != 0
    assert list(output.iterdir()) == []


def test_sharded_package_installs_only_reviewed_new_files_and_preserves_originals(
    tmp_path, monkeypatch,
):
    paths, _ = fixture(tmp_path, 'label start:\n    e "One."\n    e "Two."\n')
    (paths.game / "Synthetic.exe").write_bytes(b"Synthetic executable; NEVER LAUNCH")
    extract_to_project(paths, "game/script.rpy")
    monkeypatch.setattr("unitytranslator.renpy_export.SHARD_RECORDS", 1)
    originals = {p.relative_to(paths.game).as_posix(): hash_file(p)
                 for p in paths.game.rglob("*") if p.is_file()}
    with ProjectRepository(paths) as repo:
        approve(repo, "One.", "Bir.")
        approve(repo, "Two.", "İki.")
        result = export_copy_package(repo, "turkish")
    root = tmp_path / "recipient-package"
    with zipfile.ZipFile(result["path"]) as archive:
        archive.extractall(root)
    manifest = json.loads((root / "package.json").read_bytes())
    assert len(manifest["payloads"]) == 2
    assert manifest["format_version"] == 2
    target, _ = reviewed_install((paths, originals, result, root, manifest), tmp_path)
    assert all((target / item["path"]).is_file() for item in manifest["payloads"])
    review = run_ps(root, "-Action", "Remove", "-InstallFolder", target, "-ReviewOnly")
    assert review.returncode == 0, review.stderr
    removal = run_ps(root, "-Action", "Remove", "-InstallFolder", target,
                     "-ReviewedPlanSha256", json.loads(review.stdout)["sha256"])
    assert removal.returncode == 0, removal.stderr
    assert all(not (target / item["path"]).exists() for item in manifest["payloads"])
    assert originals == {p.relative_to(paths.game).as_posix(): hash_file(p)
                         for p in paths.game.rglob("*") if p.is_file()}
