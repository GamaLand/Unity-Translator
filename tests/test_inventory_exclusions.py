import json
from dataclasses import replace

import pytest
from test_deployment import service as service_fixture  # noqa: F401
from test_repository import draft

from unitytranslator.deployment import DeploymentService, VolatileFile
from unitytranslator.filesystem import hash_file
from unitytranslator.game_process import GameProcessStatus


@pytest.fixture
def service(service_fixture):  # noqa: F811 — pytest fixture injection
    return service_fixture


def rule(path="Logs/session.log", kind="log"):
    return VolatileFile(path=path, kind=kind, reason="Synthetic selected variable data")


def selected(service, *rules):
    return DeploymentService(
        service.repository,
        process_probe=lambda _: GameProcessStatus("closed"),
        exclusions=tuple(rules),
        exclusions_reviewed=True,
    )


def prepare(service, target="mod/a.txt"):
    return service.prepare("synthetic", "1", [("artifacts/payload/a.txt", target)])


def test_default_inventory_includes_logs_and_selection_is_required(service):
    path = service.target("Logs/session.log")
    path.parent.mkdir()
    path.write_text("private log")
    assert "Logs/session.log" in service.inventory()
    with pytest.raises(ValueError, match="açık kullanıcı"):
        DeploymentService(service.repository, exclusions=(rule(),))


@pytest.mark.parametrize(
    "path,kind",
    [
        ("Game_Data/resources.assets", "cache"),
        ("Logs/module.dll", "log"),
        ("Logs/config.json", "log"),
        ("Saves/scene.unity3d", "save"),
        ("Cache/asset.bundle", "cache"),
        ("Logs/*.log", "log"),
        ("Logs/deep/session.log", "log"),
        ("BepInEx/LogOutput.log", "log"),
        ("Game_Data/log.txt", "log"),
        ("Saves/slot.txt", "save"),
        ("Cache/data.txt", "cache"),
    ],
)
def test_assets_loader_wildcards_and_directory_scopes_are_rejected(service, path, kind):
    with pytest.raises(ValueError):
        selected(service, rule(path, kind))


def test_rotated_log_and_save_cache_changes_are_separate_and_preserved(service):
    rules = [rule(), rule("Saves/slot.sav", "save"), rule("Cache/shader.cache", "cache")]
    for item in rules:
        path = service.target(item.path)
        path.parent.mkdir(exist_ok=True)
        path.write_text("private variable data")
    protected = selected(service, *rules)
    plan = prepare(protected)
    baseline = protected.baseline()
    assert baseline["format_version"] == 2 and set(baseline["files"]) == {"original.bin"}
    protected.target(rules[0].path).unlink()  # Yalnızca sentetik log rotasyonu.
    protected.target(rules[1].path).write_text("new save")
    protected.target(rules[2].path).write_text("new cache")
    result = protected.activate(plan, user_action=True, adapter_verified=True)
    assert result["status"] == "installed"
    assert result["excluded_observations"][0]["state"] == "missing"
    assert protected.original_changes() == []
    protected.uninstall(user_action=True)
    assert protected.baseline() == baseline
    assert protected.target(rules[1].path).read_text() == "new save"
    report = json.loads(
        protected.paths.output("artifacts/volatile-data-observations.json").read_text()
    )
    assert len(report) == 3 and all("sha256" not in item for item in report)
    assert "private variable data" not in json.dumps(report)


def test_unselected_new_file_still_invalidates_plan(service):
    protected = selected(service, rule())
    plan = prepare(protected)
    path = protected.target("Logs/new.log")
    path.parent.mkdir()
    path.write_text("unselected log")
    with pytest.raises(ValueError, match="Oyun hazırlamadan"):
        protected.activate(plan, user_action=True, adapter_verified=True)
    assert not protected.target("mod/a.txt").exists()


def test_missing_excluded_path_cannot_be_payload_target(service):
    protected = selected(service, rule())
    with pytest.raises(ValueError, match="kullanıcı verisi"):
        prepare(protected, "Logs/session.log")
    assert not protected.target("Logs/session.log").exists()


def test_baseline_policy_is_immutable_and_reused_on_reopen(service):
    protected = selected(service, rule())
    baseline = protected.baseline()
    reopened = DeploymentService(
        service.repository, process_probe=lambda _: GameProcessStatus("closed")
    )
    assert reopened.baseline() == baseline
    with pytest.raises(ValueError, match="dışlama bağlantısı"):
        selected(service, rule(), rule("Logs/new.log")).baseline()
    assert protected.baseline() == baseline


def test_tampered_policy_is_rejected(service):
    protected = selected(service, rule())
    value = protected.baseline()
    value["exclusions"][0]["path"] = "Logs/new.log"
    protected.paths.write_json("artifacts/original-inventory.json", value)
    with pytest.raises(ValueError, match="dışlama bağlantısı"):
        protected.inventory()


def test_known_reader_source_cannot_be_excluded(service):
    service.repository.ingest([replace(draft(), source_file="Logs/session.log")], {})
    with pytest.raises(ValueError, match="oyun kaynağı"):
        selected(service, rule())


def test_legacy_inventory_still_reads_without_changing_its_fingerprint(service):
    value = service.baseline()
    value.pop("exclusions")
    service.paths.write_json("artifacts/original-inventory.json", value)
    assert service.baseline()["format_version"] == 1
    assert service.baseline()["exclusions"] == []
    assert prepare(service).fingerprint == value["fingerprint"]


def test_corrupted_owned_receipt_cannot_delete_excluded_existing_user_data(service):
    path = service.target("Logs/session.log")
    path.parent.mkdir()
    path.write_bytes(b"synthetic private log")
    protected = selected(service, rule())
    plan = prepare(protected)
    protected.activate(plan, user_action=True, adapter_verified=True)
    manifest = protected.read_manifest()
    info = path.stat()
    manifest["files"][0].update(
        target="Logs/session.log", sha256=hash_file(path), device=info.st_dev, inode=info.st_ino
    )
    with pytest.raises(ValueError, match="özgün dosyayı sahiplenemez"):
        protected._remove_owned(manifest)
    assert path.read_bytes() == b"synthetic private log"
    assert protected.target("mod/a.txt").exists()


def test_truthy_text_is_not_explicit_exclusion_approval(service):
    with pytest.raises(ValueError, match="açık kullanıcı"):
        DeploymentService(service.repository, exclusions=(rule(),), exclusions_reviewed="false")


def test_text_log_requires_selection_and_is_never_owned(service):
    path = service.target("Logs/runtime.txt")
    path.parent.mkdir()
    path.write_bytes(b"synthetic game log")
    assert "Logs/runtime.txt" in service.inventory()
    with pytest.raises(ValueError, match="açık kullanıcı"):
        DeploymentService(service.repository, exclusions=(rule("Logs/runtime.txt"),))
    protected = selected(service, rule("Logs/runtime.txt"))
    baseline = protected.baseline()
    path.write_bytes(b"synthetic next launch log")
    assert protected.inventory() == baseline["files"]
    assert protected.excluded_observations()[0]["bytes"] == len(b"synthetic next launch log")
    with pytest.raises(ValueError, match="kullanıcı verisi"):
        prepare(protected, "Logs/runtime.txt")


def test_text_log_reader_source_is_still_protected(service):
    service.repository.ingest([replace(draft(), source_file="Logs/runtime.txt")], {})
    with pytest.raises(ValueError, match="oyun kaynağı"):
        selected(service, rule("Logs/runtime.txt"))
