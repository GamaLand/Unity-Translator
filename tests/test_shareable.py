import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from test_installation import install_project, original_hashes  # noqa: F401
from test_textasset_pipeline import approve, synthetic_runtime_profile
from test_textasset_pipeline import repo as synthetic_repo  # noqa: F401

from unitytranslator.filesystem import hash_file
from unitytranslator.krypta_runtime import KryptaRuntimeKit
from unitytranslator.runtime_kit import RUNTIME_NAMES, RuntimeKit
from unitytranslator.shareable import export_shareable_patch, supports_shareable_patch


@pytest.fixture
def krypta_project(synthetic_repo, monkeypatch):  # noqa: F811
    repo = synthetic_repo
    profile = synthetic_runtime_profile(repo, monkeypatch)
    relative = "Synthetic_Data/Managed/Assembly-CSharp.dll"
    profile["assembly"]["path"] = relative
    assembly = repo.paths.game / relative
    assembly.parent.mkdir(parents=True)
    assembly.write_bytes(b"synthetic assembly; never executed")
    (repo.paths.game / "UnityPlayer.dll").write_bytes(b"synthetic engine; never executed")
    (repo.paths.game / "Synthetic.exe").write_bytes(b"synthetic EXE; never executed")
    monkeypatch.setattr("unitytranslator.shareable.load_profile", lambda: profile)
    kit = KryptaRuntimeKit.__new__(KryptaRuntimeKit)
    kit.root = repo.paths.project.parent / "krypta-kit"
    names = kit.runtime_names | {"SOURCES/UnityTranslator-KryptaFM.zip", "README.txt"}
    for name in names:
        path = kit.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("synthetic component; never executed: " + name).encode())
    kit.catalog = {
        "files": {name: hash_file(kit.root / name) for name in names},
        "runtime_files": {name: hash_file(kit.root / name) for name in kit.runtime_names},
        "managed_references": {"Assembly-CSharp.dll": hash_file(assembly)},
        "unity_player_sha256": hash_file(repo.paths.game / "UnityPlayer.dll"),
        "ui_trial_evidence": {
            "format_version": 1, "scope": "limited-user-accepted",
            "plugin_sha256": hash_file(kit.root / ("plugin/" + kit.plugin_name)),
            "observed": ["startup", "menu", "options", "menu-to-game", "pause", "subtitles"],
        },
    }
    monkeypatch.setattr(kit, "check_game", lambda repository, relative: None)
    portable = RuntimeKit.__new__(RuntimeKit)
    portable.root = kit.root.parent / "portable-kit"
    names = RUNTIME_NAMES | {"SOURCES/protected-preloader.zip", "README.txt"}
    for name in names:
        path = portable.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name in kit.runtime_names and name != "core/BepInEx.Preloader.dll":
            path.write_bytes((kit.root / name).read_bytes())
        else:
            path.write_bytes(("synthetic portable component: " + name).encode())
    portable.catalog = {
        "files": {name: hash_file(portable.root / name) for name in names},
        "runtime_files": {name: hash_file(portable.root / name) for name in RUNTIME_NAMES},
    }
    monkeypatch.setattr("unitytranslator.shareable.KryptaRuntimeKit", lambda: kit)
    monkeypatch.setattr("unitytranslator.shareable.PortableRuntimeKit", lambda: portable)
    approve(repo)
    return repo, kit, portable


@pytest.fixture(params=["i2", "krypta"])
def shareable(request, monkeypatch):
    if request.param == "i2":
        repo, kit = request.getfixturevalue("install_project")
        monkeypatch.setattr("unitytranslator.shareable.PortableRuntimeKit", lambda: RuntimeKit(kit))
        count = 23
    else:
        repo, kit, portable = request.getfixturevalue("krypta_project")
        count = 1
        assert supports_shareable_patch(repo)
    before = original_hashes(repo)
    approvals = repo.page()
    result = export_shareable_patch(repo)
    assert result["records"] == count and not result["requires_unitytranslator"]
    assert repo.page() == approvals
    assert original_hashes(repo) == before
    folder = Path(result["path"]).with_suffix("")
    with zipfile.ZipFile(result["path"]) as archive:
        assert archive.testzip() is None
        assert {"Install.cmd", "Uninstall.cmd", "Kur.cmd", "Kaldir.cmd"} <= set(archive.namelist())
        assert b"shareable translation patch" in archive.read("README.txt")
        assert not any(
            name.endswith((".sqlite3", ".gguf", ".assets")) for name in archive.namelist()
        )
        assert str(repo.paths.project).encode() not in archive.read("package.json")
        assert not any("doorstop_config.ini" in name for name in archive.namelist())
        if request.param == "krypta":
            prefix = "payload/UnityTranslatorPatch/"
            plugin = prefix + "BepInEx/plugins/UnityTranslator/UnityTranslator.KryptaFM.dll"
            assert archive.read(plugin) == (kit.root / ("plugin/" + kit.plugin_name)).read_bytes()
            assert archive.read(prefix + "BepInEx/core/BepInEx.Preloader.dll") == (
                portable.root / "core/BepInEx.Preloader.dll").read_bytes()
            assert (prefix + "support/krypta/SOURCES/UnityTranslator-KryptaFM.zip"
                    in archive.namelist())
            assert prefix + "support/portable/SOURCES/protected-preloader.zip" in archive.namelist()
            assert not any(name.endswith("UnityTranslator.I2Mono.dll")
                           for name in archive.namelist())
    return repo, folder, before


@pytest.mark.parametrize("change", ["core", "source", "draft", "evidence", "language"])
def test_krypta_shareable_rejects_stale_or_unapproved_inputs(krypta_project, change):
    repo, kit, portable = krypta_project
    before = original_hashes(repo)
    if change == "core":
        name = "core/0Harmony.dll"
        (portable.root / name).write_bytes(b"different shared component")
        portable.catalog["files"][name] = portable.catalog["runtime_files"][name] = hash_file(
            portable.root / name)
    elif change == "source":
        (repo.paths.game / "shared.assets").write_bytes(b"changed source")
        before = original_hashes(repo)
    elif change == "draft":
        from unitytranslator.editor_drafts import EditorDraftStore
        row = repo.page(status="approved")[0]
        EditorDraftStore(repo).put(
            row["unit_id"], row["source_revision"], row["version"], "unreviewed draft")
    elif change == "evidence":
        kit.catalog["ui_trial_evidence"]["plugin_sha256"] = "0" * 64
    else:
        repo.target_language = "de"
    with pytest.raises(ValueError):
        export_shareable_patch(repo)
    assert not list(repo.paths.project.glob("exports/shareable-*.zip"))
    assert original_hashes(repo) == before


def invoke(folder, game, action="Install", *, reviewed=True):
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               str(folder / "patch.ps1"), "-Action", action, "-GameFolder", str(game)]

    def run(extra):
        return subprocess.run(
            command + extra, capture_output=True, stdin=subprocess.DEVNULL, timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
        )

    if action == "Install" and reviewed:
        preview = run(["-ReviewOnly"])
        if preview.returncode:
            return preview
        plan = json.loads(preview.stdout.decode("utf-8-sig", errors="replace"))
        return run(["-ReviewedPlanSha256", plan["sha256"]])
    return run([])


@pytest.mark.skipif(os.name != "nt", reason="Windows recipient installer")
def test_recipient_requires_review_and_rejects_wrong_game(shareable):
    repo, folder, before = shareable
    assert invoke(folder, repo.paths.game, reviewed=False).returncode != 0
    assert original_hashes(repo) == before
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               str(folder / "patch.ps1"), "-GameFolder", str(repo.paths.game),
               "-ReviewedPlanSha256", "0" * 64]
    result = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL,
                            timeout=45, check=False)
    assert result.returncode != 0
    assert original_hashes(repo) == before
    (repo.paths.game / "UnityPlayer.dll").write_bytes(b"different synthetic engine")
    changed = original_hashes(repo)
    assert invoke(folder, repo.paths.game).returncode != 0
    assert original_hashes(repo) == changed


def test_krypta_ui_enables_shareable_export(krypta_project):
    from PySide6.QtWidgets import QApplication
    from test_ui import wait_for

    from unitytranslator.ui.window import MainWindow

    repo, _, _ = krypta_project
    paths = repo.paths
    count = repo.count()
    repo.close()
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda *args: errors.append(args))
    window.game_path.setText(str(paths.game))
    window.project_path.setText(str(paths.project))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: window.review_model.rowCount() == count)
        assert window.shareable_export_button.isEnabled()
        assert window.shareable_note.isHidden()
        window.prepare_shareable_export()
        wait_for(app, lambda: bool(list(paths.project.glob("exports/shareable-*.zip"))))
        wait_for(app, lambda: window.shareable_export_button.isEnabled())
        assert not errors
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
        window.bridge.thread.join(timeout=5)
        assert not window.bridge.thread.is_alive()
        window.deleteLater()
        app.processEvents()


@pytest.mark.skipif(os.name != "nt", reason="Windows recipient installer")
def test_recipient_installs_removes_without_python_and_relocates_loader(shareable):
    repo, folder, before = shareable
    recipient = repo.paths.project.parent / "Alıcı Oyun çığı"
    shutil.copytree(repo.paths.game, recipient)
    installed = invoke(folder, recipient)
    assert installed.returncode == 0, installed.stderr.decode(errors="replace")
    ini = (recipient / "doorstop_config.ini").read_text(encoding="utf-16")
    assert str(recipient / "UnityTranslatorPatch/BepInEx/core/BepInEx.Preloader.dll") in ini
    assert str(repo.paths.game) not in ini
    assert str(repo.paths.project) not in ini
    payload = (recipient
               / "UnityTranslatorPatch/BepInEx/plugins/UnityTranslator/translation.json")
    assert payload.is_file()
    removed = invoke(folder, recipient, "Remove")
    assert removed.returncode == 0, removed.stderr.decode(errors="replace")
    assert not (recipient / "UnityTranslatorPatch").exists()
    assert {p.relative_to(recipient).as_posix(): hash_file(p)
            for p in recipient.rglob("*") if p.is_file()} == before
    assert original_hashes(repo) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows recipient installer")
@pytest.mark.parametrize("change", ["edited", "replaced", "hardlink"])
def test_recipient_refuses_conflicts_and_preserves_modified_owned_files(shareable, change):
    repo, folder, _ = shareable
    root = repo.paths.game
    (root / "winhttp.dll").write_bytes(b"existing third party mod")
    assert invoke(folder, root).returncode != 0
    assert (root / "winhttp.dll").read_bytes() == b"existing third party mod"
    assert not (root / "UnityTranslatorPatch").exists()
    (root / "winhttp.dll").unlink()  # Synthetic test-owned file only.
    assert invoke(folder, root).returncode == 0
    translation = root / "UnityTranslatorPatch/BepInEx/plugins/UnityTranslator/translation.json"
    original = translation.read_bytes()
    if change == "edited":
        translation.write_text("user edit", encoding="utf-8")
    elif change == "replaced":
        translation.rename(translation.with_suffix(".original"))
        translation.write_bytes(original)
    else:
        os.link(translation, repo.paths.project / "user-link.json")
    removed = invoke(folder, root, "Remove")
    assert removed.returncode != 0
    assert translation.read_bytes() == (b"user edit" if change == "edited" else original)
    assert (root / "UnityTranslatorPatch/install-receipt.json").exists()
    assert not (root / "winhttp.dll").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows recipient installer")
def test_recipient_rejects_tampered_package_before_game_write(shareable):
    repo, folder, before = shareable
    manifest = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    entry = manifest["files"][0]
    (folder / "payload" / entry["path"]).write_bytes(b"tamper")
    assert invoke(folder, repo.paths.game).returncode != 0
    assert original_hashes(repo) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows recipient installer")
@pytest.mark.parametrize("path", ["Synthetic.exe", "../outside", "UnityTranslatorPatch/../bad"])
def test_recipient_rejects_original_or_traversal_manifest_targets(shareable, path):
    repo, folder, before = shareable
    manifest_path = folder / "package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = path
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert invoke(folder, repo.paths.game).returncode != 0
    assert original_hashes(repo) == before
