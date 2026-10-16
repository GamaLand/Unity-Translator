import json
from pathlib import Path

import pytest

from unitytranslator.deployment import DeploymentService
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.game_process import GameProcessStatus
from unitytranslator.i2 import extract_i2
from unitytranslator.i2_trial import (
    prepare_i2_deployment_preview,
    prepare_i2_trial,
    validate_i2_trial,
)
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_configuration import bepinex_config_text, doorstop_config_bytes


@pytest.fixture
def trial(tmp_path: Path):
    game = tmp_path / "game"
    assembly_relative = "Synthetic_Data/Managed/Assembly-CSharp.dll"
    assembly = game / assembly_relative
    assembly.parent.mkdir(parents=True)
    assembly.write_bytes(b"synthetic assembly; never executed")
    paths = ProjectPaths(game, tmp_path / "project")
    runtime_relative = "artifacts/runtime/BepInEx"
    preloader = paths.output(runtime_relative + "/core/BepInEx.Preloader.dll")
    preloader.parent.mkdir(parents=True)
    preloader.write_bytes(b"synthetic loader; never executed")
    config = paths.output(runtime_relative + "/config/BepInEx.cfg")
    config.parent.mkdir(parents=True)
    config.write_bytes(bepinex_config_text().encode("utf-8"))
    ini = paths.output("artifacts/settings/doorstop_config.ini")
    ini.parent.mkdir(parents=True)
    ini.write_bytes(doorstop_config_bytes(preloader))
    paths.write_json(
        runtime_relative + "/runtime-base-manifest.json",
        {
            "purpose": "experimental-external-runtime-base",
            "status": "prepared",
            "files": [{"file": "core/BepInEx.Preloader.dll", "sha256": hash_file(preloader)}],
            "settings": {
                "loader_enabled": False,
                "runtime_config": str(config),
                "runtime_config_sha256": hash_file(config),
                "doorstop_ini": str(ini),
                "doorstop_ini_sha256": hash_file(ini),
            },
        },
    )
    plugin = tmp_path / "plugin.dll"
    plugin.write_bytes(b"synthetic plugin; never executed")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "status": "compiled",
                "output_sha256": hash_file(plugin),
                "references_sha256": {str(assembly): hash_file(assembly)},
            }
        )
    )
    winhttp = tmp_path / "winhttp.dll"
    winhttp.write_bytes(b"synthetic native dll; never executed")
    units = extract_i2(
        {
            "m_Name": "synthetic",
            "mLanguages": [{"Name": "English", "Code": "en"}],
            "mTerms": [{"Term": "UI/start", "TermType": 0, "Languages": ["Start {0}"]}],
        },
        "resources.assets",
        1,
    )
    with ProjectRepository(paths) as repo:
        repo.ingest(units, {})
        row = repo.page()[0]
        repo.edit(row["unit_id"], row["version"], "Başla {0}")
        repo.approve(row["unit_id"], repo.page()[0]["version"])
        args = dict(
            runtime_relative=runtime_relative,
            plugin=plugin,
            plugin_evidence=evidence,
            winhttp=winhttp,
            winhttp_sha256=hash_file(winhttp),
            source_set="synthetic",
            unity_version="2017.4.19f1",
            assembly_relative=assembly_relative,
            target_name="Türkçe",
            selected_unit_ids={row["unit_id"]},
        )
        yield repo, args


def prepared(repo, args):
    result = prepare_i2_trial(repo, **args)
    relative = Path(result["manifest"]).relative_to(repo.paths.project).as_posix()
    return relative, json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))


def test_preview_stays_outside_game_and_preserves_approval(trial):
    repo, args = trial
    before = {
        p.relative_to(repo.paths.game): hash_file(p)
        for p in repo.paths.game.rglob("*")
        if p.is_file()
    }
    relative, manifest = prepared(repo, args)
    result = validate_i2_trial(repo, relative)
    assert result["records"] == 1
    assert result["installation_authorized"] is False
    assert result["application_verified"] is False
    assert manifest["loader_enabled"] is False
    assert {p["target"] for p in manifest["proposed_game_files"]} == {
        "winhttp.dll",
        "doorstop_config.ini",
    }
    assert before == {
        p.relative_to(repo.paths.game): hash_file(p)
        for p in repo.paths.game.rglob("*")
        if p.is_file()
    }
    assert repo.page()[0]["status"] == "approved"
    with pytest.raises(ValueError, match="beklenmeyen|üzerine"):
        prepare_i2_trial(repo, **args)


@pytest.mark.parametrize("change", ["approval", "extra", "config", "assembly", "target"])
def test_changed_preconditions_invalidate_preview(trial, change):
    repo, args = trial
    relative, _ = prepared(repo, args)
    if change == "approval":
        row = repo.page()[0]
        repo.edit(row["unit_id"], row["version"], "Başlat {0}")
    elif change == "extra":
        repo.paths.output(args["runtime_relative"] + "/patchers/extra.dll").parent.mkdir()
        repo.paths.output(args["runtime_relative"] + "/patchers/extra.dll").write_bytes(b"extra")
    elif change == "config":
        repo.paths.output(args["runtime_relative"] + "/config/BepInEx.cfg").write_bytes(b"changed")
    elif change == "assembly":
        (repo.paths.game / args["assembly_relative"]).write_bytes(b"changed")
    else:
        (repo.paths.game / "winhttp.dll").write_bytes(b"user file")
    with pytest.raises(ValueError):
        validate_i2_trial(repo, relative)


def test_unapproved_selection_fails_without_game_files(trial):
    repo, args = trial
    args["selected_unit_ids"].add("not-approved")
    with pytest.raises(ValueError, match="insan onaylı"):
        prepare_i2_trial(repo, **args)
    manifests = list(repo.paths.project.glob("artifacts/i2-trial-*/trial-preview.json"))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text(encoding="utf-8"))["status"] == "failed"
    assert not (repo.paths.game / "winhttp.dll").exists()
    assert not repo.paths.output(args["runtime_relative"] + "/plugins/UnityTranslator").exists()


def test_preexisting_patcher_is_refused_before_preparation(trial):
    repo, args = trial
    path = repo.paths.output(args["runtime_relative"] + "/patchers/extra.dll")
    path.parent.mkdir()
    path.write_bytes(b"unreviewed executable")
    with pytest.raises(ValueError, match="beklenmeyen"):
        prepare_i2_trial(repo, **args)
    assert not list(repo.paths.project.glob("artifacts/i2-trial-*"))


def test_inventory_bound_plan_requires_baseline_and_stays_disabled(trial):
    repo, args = trial
    relative, _ = prepared(repo, args)
    service = DeploymentService(repo, process_probe=lambda _: GameProcessStatus("closed"))
    with pytest.raises(ValueError, match="envanteri"):
        prepare_i2_deployment_preview(repo, relative, service)
    baseline = service.baseline()
    result = prepare_i2_deployment_preview(repo, relative, service)
    assert result["plan"]["fingerprint"] == baseline["fingerprint"]
    assert result["loader_enabled"] is False and result["installation_authorized"] is False
    assert len(result["plan"]["files"]) == 2
    assert service.inventory() == baseline["files"]
    assert not repo.paths.output("artifacts/deployment.json").exists()


def test_game_update_blocks_inventory_bound_preview(trial):
    repo, args = trial
    relative, _ = prepared(repo, args)
    service = DeploymentService(repo, process_probe=lambda _: GameProcessStatus("closed"))
    service.baseline()
    (repo.paths.game / "new-update.bin").write_bytes(b"update")
    with pytest.raises(ValueError, match="envanteri değişti"):
        prepare_i2_deployment_preview(repo, relative, service)
    assert not list(repo.paths.project.glob("artifacts/plans/*-trial-review.json"))


def test_metadata_cannot_disguise_enabled_loader_settings(trial):
    repo, args = trial
    base_relative = args["runtime_relative"] + "/runtime-base-manifest.json"
    base = json.loads(repo.paths.output(base_relative).read_text(encoding="utf-8"))
    ini = Path(base["settings"]["doorstop_ini"])
    ini.write_bytes(
        doorstop_config_bytes(
            repo.paths.output(args["runtime_relative"] + "/core/BepInEx.Preloader.dll"),
            enabled=True,
        )
    )
    base["settings"]["doorstop_ini_sha256"] = hash_file(ini)
    repo.paths.write_json(base_relative, base)
    with pytest.raises(ValueError, match="ayar içeriği"):
        prepare_i2_trial(repo, **args)


def test_changed_payload_cannot_borrow_original_human_approval(trial):
    repo, args = trial
    relative, manifest = prepared(repo, args)
    path = Path(manifest["payload"]["path"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["text"] = "İnsan tarafından onaylanmayan değişiklik {0}"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    digest = hash_file(path)
    manifest["payload"]["sha256"] = digest
    for item in manifest["immutable_files"]:
        if item["relative"] == path.relative_to(repo.paths.project).as_posix():
            item["sha256"] = digest
    repo.paths.write_json(relative, manifest)
    with pytest.raises(ValueError, match="incelenmiş kayıt değişti"):
        validate_i2_trial(repo, relative)
