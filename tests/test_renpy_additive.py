"""Synthetic additive recipient plans and ownership checks. Never launch a game."""

import json
import os
import zipfile
from pathlib import Path

import pytest
from test_renpy_package import package as legacy_package  # noqa: F401
from test_renpy_package import run_ps

from unitytranslator.filesystem import hash_file
from unitytranslator.renpy_package import export_install_package
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def patch(legacy_package, tmp_path):  # noqa: F811
    paths, originals = legacy_package[:2]
    with ProjectRepository(paths) as repo:
        result = export_install_package(repo, "turkish")
    root = tmp_path / "additive recipient's & package"
    with zipfile.ZipFile(result["path"]) as archive:
        archive.extractall(root)  # Fixed exporter-generated synthetic ZIP only.
        assert not any(name.endswith(".exe") for name in archive.namelist())
        for name in archive.namelist():
            data = archive.read(name)
            assert b"PRIVATE RUNTIME DATA" not in data
            assert str(paths.game).encode() not in data
            assert str(paths.project).encode() not in data
    manifest = json.loads((root / "package.json").read_bytes())
    return paths, originals, result, root, manifest


def install(patch):
    paths, _, _, root, _ = patch
    review = run_ps(root, "-GameFolder", paths.game, "-ReviewOnly")
    assert review.returncode == 0, review.stderr
    plan = json.loads(review.stdout)
    applied = run_ps(root, "-GameFolder", paths.game, "-ReviewedPlanSha256", plan["sha256"])
    assert applied.returncode == 0, applied.stderr
    return plan, json.loads(applied.stdout)


def unchanged(patch):
    paths, originals = patch[:2]
    assert all(hash_file(paths.game / name) == digest for name, digest in originals.items())


def test_additive_zip_and_readme_describe_one_folder_and_no_game_copy(patch):
    paths, originals, result, root, manifest = patch
    assert result["installation_mode"] == "original-additions"
    assert result["copy_files"] == result["copy_bytes"] == 0
    assert manifest["format_version"] == 3 and "copy_folder" not in manifest
    readme = (root / "README.txt").read_text()
    assert "folder once" in readme and "game is NOT copied" in readme
    assert "not replaced" in readme and "normal saves" in readme.lower()
    assert "automatic removal stops BEFORE" in readme
    assert len(originals) == len([p for p in paths.game.rglob("*") if p.is_file()])
    unchanged(patch)


def test_review_install_launch_review_and_remove_only_add_patch_files(patch):
    paths, originals, _, root, manifest = patch
    plan, result = install(patch)
    assert Path(result["target"]) == paths.game
    assert result["game_files_copied"] == 0 and result["game_started"] is False
    assert plan["plan"]["original_files_overwritten"] is False
    allowed = {item["path"] for item in plan["plan"]["files"]} | set(
        plan["plan"]["generated_files"],
    )
    added = {p.relative_to(paths.game).as_posix() for p in paths.game.rglob("*")
             if p.is_file()} - set(originals)
    assert added == allowed
    installed = paths.game / manifest["metadata_folder"]
    launch = run_ps(installed, "-Action", "Launch", "-ReviewOnly")
    assert launch.returncode == 0, launch.stderr
    assert json.loads(launch.stdout)["save_policy"] == "game-default"
    assert json.loads(launch.stdout)["game_started"] is False
    review = run_ps(root, "-Action", "Remove", "-InstallFolder", paths.game, "-ReviewOnly")
    assert review.returncode == 0, review.stderr
    removal = run_ps(root, "-Action", "Remove", "-InstallFolder", paths.game,
                     "-ReviewedPlanSha256", json.loads(review.stdout)["sha256"])
    assert removal.returncode == 0, removal.stderr
    assert all(not (paths.game / item["path"]).exists() for item in manifest["payloads"])
    assert not (paths.game / "Play-Translated.cmd").exists()
    assert not (paths.game / "game/tl/turkish").exists()
    assert (installed / "receipt.json").exists()
    unchanged(patch)
    # Retained receipt history does not prevent exporting a new package after removal.
    with ProjectRepository(paths) as repo:
        assert Path(export_install_package(repo, "turkish")["path"]).exists()


@pytest.mark.parametrize("conflict", ["language", "launcher", "script", "archive", "wrong_build"])
def test_conflicts_and_new_inputs_are_refused_without_overwriting(patch, conflict):
    paths, _, _, root, manifest = patch
    if conflict == "language":
        path = paths.game / "game/tl/turkish/user.rpy"
    elif conflict == "launcher":
        path = paths.game / "Play-Translated.cmd"
    elif conflict == "script":
        path = paths.game / "game/new_script.rpy"
    elif conflict == "archive":
        path = paths.game / "game/new_archive.rpa"
    else:
        path = paths.game / "Synthetic.exe"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"User file; must never change")
    before = hash_file(path)
    result = run_ps(root, "-GameFolder", paths.game, "-ReviewOnly")
    assert result.returncode != 0
    assert hash_file(path) == before
    assert not (paths.game / manifest["metadata_folder"]).exists()


def test_unknown_compiled_sidecars_stop_removal_before_any_patch_deletion(patch):
    install(patch)
    paths, _, _, root, manifest = patch
    source = paths.game / manifest["payloads"][0]["path"]
    compiled = Path(str(source) + "c")
    compiled.write_bytes(b"Runtime-generated; ownership not established")
    review = run_ps(root, "-Action", "Remove", "-InstallFolder", paths.game, "-ReviewOnly")
    assert review.returncode == 0, review.stderr
    plan = json.loads(review.stdout)
    assert plan["plan"]["can_remove"] is False
    result = run_ps(root, "-Action", "Remove", "-InstallFolder", paths.game,
                    "-ReviewedPlanSha256", plan["sha256"])
    assert result.returncode != 0 and "sidecars" in result.stderr
    assert source.exists() and compiled.exists() and (paths.game / "Play-Translated.cmd").exists()
    unchanged(patch)


@pytest.mark.parametrize("change", ["modified", "hardlink", "receipt", "proof"])
def test_removal_preserves_modified_linked_and_unowned_files(patch, tmp_path, change):
    install(patch)
    paths, _, _, root, manifest = patch
    payload = paths.game / manifest["payloads"][0]["path"]
    if change == "modified":
        payload.write_bytes(b"User-edited translation")
    elif change == "hardlink":
        try:
            os.link(payload, tmp_path / "user-link")
        except OSError:
            pytest.skip("Hardlinks unavailable")
    elif change == "receipt":
        file = paths.game / manifest["metadata_folder"] / "receipt.json"
        receipt = json.loads(file.read_bytes())
        receipt["files"][0]["path"] = "game/script.rpy"
        file.write_text(json.dumps(receipt), encoding="utf-8")
    else:
        (paths.game / manifest["metadata_folder"] / "install-start.json").write_bytes(b"Changed")
    review = run_ps(root, "-Action", "Remove", "-InstallFolder", paths.game, "-ReviewOnly")
    if review.returncode == 0:
        result = run_ps(root, "-Action", "Remove", "-InstallFolder", paths.game,
                        "-ReviewedPlanSha256", json.loads(review.stdout)["sha256"])
        assert result.returncode != 0
    assert payload.exists()
    unchanged(patch)


def test_wrong_plan_reinstall_and_incomplete_install_are_not_adopted(patch):
    paths, _, _, root, manifest = patch
    refused = run_ps(root, "-GameFolder", paths.game, "-ReviewedPlanSha256", "0" * 64)
    assert refused.returncode != 0
    assert not (paths.game / manifest["metadata_folder"]).exists()
    install(patch)
    refused = run_ps(root, "-GameFolder", paths.game, "-ReviewOnly")
    assert refused.returncode != 0
    unchanged(patch)


def test_remove_from_missing_or_unowned_game_never_creates_directories(patch, tmp_path):
    root = patch[3]
    target = tmp_path / "missing-game"
    result = run_ps(root, "-Action", "Remove", "-InstallFolder", target, "-ReviewOnly")
    assert result.returncode != 0 and not target.exists()
    unchanged(patch)


@pytest.mark.parametrize("kind", ["script", "token", "duplicate"])
def test_additive_recipient_rejects_untrusted_payloads_even_with_updated_hash(patch, kind):
    paths, _, _, root, manifest = patch
    from hashlib import sha256

    raw = {
        "script": b'init python:\n    raise RuntimeError("NEVER EXECUTE")\n',
        "token": b'translate turkish strings:\n    old "Hello"\n    new "[execute()]"\n',
        "duplicate": (
            b'translate turkish strings:\n    old "Hello"\n    new "Merhaba"\n'
            b'translate turkish strings:\n    old "Hello"\n    new "Merhaba"\n'
        ),
    }[kind]
    entry = manifest["payloads"][0]
    (root / "payload" / entry["path"]).write_bytes(raw)
    entry.update(sha256=sha256(raw).hexdigest(), bytes=len(raw))
    (root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = run_ps(root, "-GameFolder", paths.game, "-ReviewOnly")
    assert result.returncode != 0
    assert not (paths.game / manifest["metadata_folder"]).exists()
    unchanged(patch)


def test_changed_native_file_plan_and_unknown_language_files_are_preserved(patch):
    paths, _, _, root, manifest = patch
    review = run_ps(root, "-GameFolder", paths.game, "-ReviewOnly")
    assert review.returncode == 0, review.stderr
    launcher = paths.game / "Play-Translated.cmd"
    launcher.write_bytes(b"User file appeared after review")
    result = run_ps(root, "-GameFolder", paths.game,
                    "-ReviewedPlanSha256", json.loads(review.stdout)["sha256"])
    assert result.returncode != 0 and launcher.read_bytes() == b"User file appeared after review"
    launcher.unlink()  # Synthetic fixture file only.
    install(patch)
    unknown = paths.game / "game/tl/turkish/user.txt"
    unknown.write_bytes(b"Preserve user file")
    review = run_ps(root, "-Action", "Remove", "-InstallFolder", paths.game, "-ReviewOnly")
    result = run_ps(root, "-Action", "Remove", "-InstallFolder", paths.game,
                    "-ReviewedPlanSha256", json.loads(review.stdout)["sha256"])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["language_directory_retained"] is True
    assert unknown.read_bytes() == b"Preserve user file"
    unchanged(patch)
