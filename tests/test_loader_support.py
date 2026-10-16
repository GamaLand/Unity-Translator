import json
from hashlib import sha256
from pathlib import Path

import pytest

from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.loader_support import (
    STOCK_SHIM_HASHES,
    assess_loader_write_safety,
    classify_loader_write_safety,
    stage_loader_support,
)


@pytest.fixture
def inputs(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "original.bin").write_bytes(b"original synthetic data")
    roots = {name: tmp_path / name for name in ("loader", "source_cache", "catalog_root")}
    for path in roots.values():
        path.mkdir()
    binary = roots["loader"] / "module.dll"
    binary.write_bytes(b"synthetic DLL bytes; never execute")
    notice = roots["catalog_root"] / "license.txt"
    notice.write_bytes(b"synthetic license")
    source = roots["source_cache"] / ("owner-project-" + "a" * 40 + ".zip")
    source.write_bytes(b"synthetic source archive; only copy")
    catalog = {
        "format_version": 1,
        "components": [
            {"path": "module.dll", "sha256": hash_file(binary), "license_files": ["license.txt"]}
        ],
        "licenses": [{"file": "license.txt", "sha256": hash_file(notice)}],
        "sources": [
            {
                "repository": "owner/project",
                "commit": "a" * 40,
                "source_archive_sha256": hash_file(source),
            }
        ],
    }
    (roots["catalog_root"] / "loader-components.json").write_text(json.dumps(catalog))
    return ProjectPaths(game, tmp_path / "project"), roots, catalog


def stage(inputs):
    paths, roots, _ = inputs
    return stage_loader_support(paths, **roots)


def save_catalog(inputs):
    _, roots, catalog = inputs
    (roots["catalog_root"] / "loader-components.json").write_text(json.dumps(catalog))


def test_support_bundle_has_all_hashes_and_never_grants_installation(inputs):
    paths, roots, _ = inputs
    before = {
        str(p): hash_file(p) for root in roots.values() for p in root.rglob("*") if p.is_file()
    }
    original = hash_file(paths.game / "original.bin")
    result = stage(inputs)
    output = Path(result["directory"])
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["status"] == "prepared" and result["files"] == 5
    assert not manifest["installation_authorized"] and not manifest["application_verified"]
    assert not manifest["includes_plugin"] and not manifest["includes_translation"]
    assert manifest["loader_write_safety"]["status"] == "unknown"
    for item in manifest["files"]:
        assert hash_file(output / item["path"]) == item["sha256"]
    assert (
        sha256((output / "component-catalog.json").read_bytes()).hexdigest()
        == manifest["catalog_sha256"]
    )
    assert all(hash_file(Path(name)) == expected for name, expected in before.items())
    assert hash_file(paths.game / "original.bin") == original
    assert list(paths.game.iterdir()) == [paths.game / "original.bin"]


@pytest.mark.parametrize(
    "root,name",
    [
        ("loader", "module.dll"),
        ("catalog_root", "license.txt"),
        ("source_cache", "owner-project-" + "a" * 40 + ".zip"),
    ],
)
def test_changed_support_input_is_rejected_before_output_creation(inputs, root, name):
    inputs[1][root].joinpath(name).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="katalogdan sonra"):
        stage(inputs)
    assert not inputs[0].output("artifacts").exists()


def test_catalog_cannot_escape_picked_source_roots(inputs):
    inputs[2]["licenses"][0]["file"] = "../private.txt"
    inputs[2]["components"][0]["license_files"] = ["../private.txt"]
    save_catalog(inputs)
    with pytest.raises(ValueError, match="göreli"):
        stage(inputs)


def test_binary_without_notice_cannot_be_staged(inputs):
    inputs[2]["components"][0]["license_files"] = []
    save_catalog(inputs)
    with pytest.raises(ValueError, match="lisans bildirimi"):
        stage(inputs)


def test_copy_failure_keeps_failed_manifest_and_preserves_all_source_files(inputs, monkeypatch):
    original_open = Path.open

    def fail(path, *args, **kwargs):
        if path.name == "license.txt" and args and args[0] == "xb":
            raise OSError("synthetic copy failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(OSError, match="copy failure"):
        stage(inputs)
    manifests = list(inputs[0].project.glob("artifacts/*/support-manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text())
    assert manifest["status"] == "failed"
    assert len(manifest["files"]) == 1
    assert inputs[1]["catalog_root"].joinpath("license.txt").read_bytes() == b"synthetic license"


def test_known_stock_loader_is_ineligible_for_original_file_preservation():
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "adapters/i2mono/loader-components.json").read_text())
    result = classify_loader_write_safety(
        {item["path"]: item["sha256"] for item in catalog["components"]}
    )
    assert result["status"] == "unsupported"
    assert result["reason"] == "persistent_assembly_shim"
    assert not result["game_executed"]


def test_modified_or_partial_loader_cannot_inherit_a_safety_claim(inputs):
    assert assess_loader_write_safety(inputs[1]["loader"])["status"] == "unknown"
    partial = dict(STOCK_SHIM_HASHES)
    partial.pop("BepInEx/core/HarmonyXInterop.dll")
    assert classify_loader_write_safety(partial)["status"] == "unknown"
    partial["BepInEx/core/HarmonyXInterop.dll"] = "0" * 64
    assert classify_loader_write_safety(partial)["status"] == "unknown"
