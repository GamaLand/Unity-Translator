import json
from hashlib import sha256
from pathlib import Path


def test_loader_catalog_keeps_exact_license_bytes_and_pinned_public_sources():
    root = Path(__file__).resolve().parents[1] / "adapters/i2mono"
    catalog = json.loads((root / "loader-components.json").read_text(encoding="utf-8"))
    licenses = {item["file"]: item for item in catalog["licenses"]}
    for name, item in licenses.items():
        path = root / name
        assert path.is_relative_to(root) and path.suffix == ".txt"
        assert sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert item["url"].startswith("https://raw.githubusercontent.com/")
    for source in catalog["sources"]:
        assert len(source["commit"]) == 40
        assert source["source_url"].endswith(source["commit"])
    assert not catalog["game_executed"]
    assert not catalog["application_verified"]
    assert not catalog["redistribution_package_verified"]


def test_pdb_mspl_and_original_harmony_notice_are_associated_with_their_binaries():
    root = Path(__file__).resolve().parents[1] / "adapters/i2mono"
    catalog = json.loads((root / "loader-components.json").read_text(encoding="utf-8"))
    components = {Path(item["path"]).name: item for item in catalog["components"]}
    licenses = {item["file"]: item for item in catalog["licenses"]}
    assert any(
        licenses[name]["license"] == "MS-PL"
        for name in components["Mono.Cecil.Pdb.dll"]["license_files"]
    )
    assert any("LICENSE.Harmony" in name for name in components["0Harmony.dll"]["license_files"])
    assert components["0Harmony20.dll"]["source_repository"] == "BepInEx/BepInEx.Harmony"
    assert any(
        licenses[name]["license"] == "LGPL-2.1"
        for name in components["winhttp.dll"]["license_files"]
    )
    assert all(name in licenses for item in components.values() for name in item["license_files"])
