import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from test_installation import install_project, original_hashes  # noqa: F401

from unitytranslator.filesystem import hash_file
from unitytranslator.runtime_kit import RuntimeKit
from unitytranslator.shareable import export_shareable_patch


@pytest.fixture
def shareable(install_project, monkeypatch):  # noqa: F811
    repo, kit = install_project
    monkeypatch.setattr("unitytranslator.shareable.PortableRuntimeKit", lambda: RuntimeKit(kit))
    before = original_hashes(repo)
    result = export_shareable_patch(repo)
    assert result["records"] == 23 and not result["requires_unitytranslator"]
    assert original_hashes(repo) == before
    folder = Path(result["path"]).with_suffix("")
    with zipfile.ZipFile(result["path"]) as archive:
        assert archive.testzip() is None
        assert "Kur.cmd" in archive.namelist() and "Kaldir.cmd" in archive.namelist()
        assert not any(
            name.endswith((".sqlite3", ".gguf", ".assets")) for name in archive.namelist()
        )
        assert str(repo.paths.project).encode() not in archive.read("package.json")
        assert not any("doorstop_config.ini" in name for name in archive.namelist())
    return repo, folder, before


def invoke(folder, game, action="Install"):
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(folder / "patch.ps1"), "-Action", action, "-GameFolder", str(game)],
        capture_output=True, stdin=subprocess.DEVNULL, timeout=45,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )


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
