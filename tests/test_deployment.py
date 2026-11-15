from pathlib import Path

import pytest
from deployment_helpers import EXPERIMENTAL_ADAPTERS, install_synthetic_plan

from unitytranslator.deployment import DeploymentService, GameNotClosedError
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.game_process import GameProcessStatus
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def service(tmp_path: Path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "original.bin").write_bytes(b"synthetic original")
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.paths.write_text("artifacts/payload/a.txt", "synthetic plugin")
        repo.paths.write_text("artifacts/payload/b.txt", "synthetic translation")
        yield DeploymentService(repo, process_probe=lambda _: GameProcessStatus("closed"))


def plan(service):
    return service.prepare(
        "synthetic-test-only",
        "1",
        [
            ("artifacts/payload/a.txt", "mod/a.txt"),
            ("artifacts/payload/b.txt", "mod/b.txt"),
        ],
    )


def test_activation_and_removal_preserve_all_original_hashes(service) -> None:
    before = service.inventory()
    prepared = plan(service)
    assert not (service.paths.game / "mod").exists()
    assert install_synthetic_plan(service, prepared)["status"] == "installed"
    assert service.original_changes() == []
    result = service.uninstall(user_action=True)
    assert result["status"] == "removed"
    assert sorted(result["removed"]) == ["mod/a.txt", "mod/b.txt"]
    assert service.inventory() == before
    again = plan(service)
    assert again.fingerprint == prepared.fingerprint


@pytest.mark.parametrize("status", ["running", "unknown"])
def test_game_not_closed_blocks_baseline_and_activation_before_any_new_game_file(service, status):
    prepared = plan(service)
    service.process_probe = lambda _: GameProcessStatus(status)
    with pytest.raises(GameNotClosedError):
        install_synthetic_plan(service, prepared)
    assert not (service.paths.game / "mod").exists()
    assert not service.paths.output("artifacts/deployment.json").exists()


def test_unknown_game_state_cannot_create_first_original_inventory(service):
    service.process_probe = lambda _: GameProcessStatus("unknown")
    with pytest.raises(GameNotClosedError):
        service.baseline()
    assert not service.paths.output("artifacts/original-inventory.json").exists()


def test_running_game_blocks_uninstall_and_preserves_installed_files(service):
    prepared = plan(service)
    install_synthetic_plan(service, prepared)
    before = {file.target: hash_file(service.target(file.target)) for file in prepared.files}
    service.process_probe = lambda _: GameProcessStatus("running")
    with pytest.raises(GameNotClosedError):
        service.uninstall(user_action=True)
    assert {name: hash_file(service.target(name)) for name in before} == before


def test_game_start_mid_activation_preserves_owned_addition_until_closed_recovery(service):
    prepared = plan(service)

    def check(_):
        return GameProcessStatus(
            "running" if (service.paths.game / "mod/a.txt").exists() else "closed"
        )

    service.process_probe = check
    with pytest.raises(GameNotClosedError):
        install_synthetic_plan(service, prepared)
    assert (service.paths.game / "mod/a.txt").is_file()
    assert not (service.paths.game / "mod/b.txt").exists()
    stored = service.read_manifest()
    assert stored["status"] == "recovery_required"
    service.process_probe = lambda _: GameProcessStatus("closed")
    assert service.uninstall(user_action=True)["status"] == "removed"


def test_game_start_mid_removal_records_recovery_and_keeps_remaining_addition(service):
    prepared = plan(service)
    install_synthetic_plan(service, prepared)
    service.process_probe = lambda _: GameProcessStatus(
        "closed" if (service.paths.game / "mod/b.txt").exists() else "running"
    )
    with pytest.raises(GameNotClosedError):
        service.uninstall(user_action=True)
    assert not (service.paths.game / "mod/b.txt").exists()
    assert (service.paths.game / "mod/a.txt").exists()
    assert service.read_manifest()["status"] == "recovery_required"
    service.process_probe = lambda _: GameProcessStatus("closed")
    assert service.uninstall(user_action=True)["status"] == "removed"


def test_game_start_during_inventory_does_not_freeze_unverified_baseline(service):
    checks = []

    def check(_):
        checks.append(True)
        return GameProcessStatus("closed" if len(checks) == 1 else "running")

    service.process_probe = check
    with pytest.raises(GameNotClosedError):
        service.baseline()
    assert not service.paths.output("artifacts/original-inventory.json").exists()


@pytest.mark.parametrize(
    "action,reviewed",
    [(False, False), (True, False), (False, True), (True, None), ("true", True), (True, 1)],
)
def test_install_gate_requires_literal_user_action_and_trial_review(
    service, action, reviewed
) -> None:
    prepared = plan(service)
    with pytest.raises(ValueError, match="separate, explicit user trial choice"):
        service.install_experimental_trial(
            prepared, user_action=action, experimental_trial_reviewed=reviewed
        )
    assert not (service.paths.game / "mod").exists()
    assert not service.paths.output("artifacts/deployment.json").exists()


def test_install_path_refuses_plans_other_than_the_limited_trial(service) -> None:
    before = service.inventory()
    prepared = plan(service)
    with pytest.raises(ValueError, match="accepts only the limited I2 trial plan"):
        service.install_experimental_trial(
            prepared, user_action=True, experimental_trial_reviewed=True
        )
    assert service.inventory() == before
    assert not service.paths.output("artifacts/deployment.json").exists()


LOADER_TARGETS = ("winhttp.dll", "doorstop_config.ini")


@pytest.mark.parametrize("adapter", sorted(EXPERIMENTAL_ADAPTERS))
@pytest.mark.parametrize(
    "version,targets",
    [
        ("2", LOADER_TARGETS),  # Wrong adapter version.
        ("1", LOADER_TARGETS[:1]),  # One file instead of the two loader files.
        ("1", (*LOADER_TARGETS, "mod/c.txt")),  # Three files.
        ("1", ("winhttp.dll", "mod/a.txt")),  # Two files, but not the loader target set.
    ],
    ids=["adapter-version", "one-file", "three-files", "target-set"],
)
def test_limited_trial_guard_refuses_each_other_experimental_plan_shape(
    service, adapter, version, targets
) -> None:
    service.paths.write_text("artifacts/payload/c.txt", "synthetic extra")
    sources = ("artifacts/payload/a.txt", "artifacts/payload/b.txt", "artifacts/payload/c.txt")
    before = service.inventory()
    prepared = service.prepare(adapter, version, list(zip(sources, targets, strict=False)))
    assert prepared.adapter == adapter and len(prepared.files) == len(targets)
    with pytest.raises(ValueError, match="accepts only the limited I2 trial plan"):
        service.install_experimental_trial(
            prepared, user_action=True, experimental_trial_reviewed=True
        )
    assert service.inventory() == before
    assert not any((service.paths.game / target).exists() for target in targets)
    assert not service.paths.output("artifacts/deployment.json").exists()


@pytest.mark.parametrize(
    "target", ["original.bin", "../outside", "C:\\outside", "file:stream", "NUL.txt"]
)
def test_existing_or_escaping_target_refused_before_game_writes(service, target) -> None:
    before = service.inventory()
    with pytest.raises(ValueError):
        service.prepare("synthetic", "1", [("artifacts/payload/a.txt", target)])
    assert service.inventory() == before


def test_changed_user_addition_is_preserved_on_removal(service) -> None:
    prepared = plan(service)
    install_synthetic_plan(service, prepared)
    modified = service.paths.game / "mod/a.txt"
    modified.write_text("user edit", encoding="utf-8")
    result = service.uninstall(user_action=True)
    assert result["status"] == "recovery_required"
    assert result["preserved"] == ["mod/a.txt"]
    assert modified.read_text(encoding="utf-8") == "user edit"
    assert result["original_changes"] == []


def test_changed_original_never_restored_from_backup(service) -> None:
    prepared = plan(service)
    install_synthetic_plan(service, prepared)
    original = service.paths.game / "original.bin"
    original.write_bytes(b"external game update")
    result = service.uninstall(user_action=True)
    assert result["original_changes"] == ["original.bin"]
    assert result["status"] == "recovery_required"
    assert original.read_bytes() == b"external game update"


def test_payload_change_after_plan_is_rejected(service) -> None:
    prepared = plan(service)
    service.paths.write_text("artifacts/payload/b.txt", "changed package")
    with pytest.raises(ValueError, match="The package or target changed after preparation"):
        install_synthetic_plan(service, prepared)
    assert not (service.paths.game / "mod").exists()


def test_partial_failure_rolls_back_only_created_matching_files(service, monkeypatch) -> None:
    prepared = plan(service)
    save = service.save_manifest

    def fail_after_first_file(manifest):
        save(manifest)
        if manifest["status"] == "installing" and manifest["files"][0]["state"] == "installed":
            raise OSError("synthetic disk full")

    monkeypatch.setattr(service, "save_manifest", fail_after_first_file)
    with pytest.raises(OSError, match="disk full"):
        install_synthetic_plan(service, prepared)
    assert service.inventory() == service.baseline()["files"]


def test_crash_recovery_preserves_unclaimed_file_and_removes_owned_file(service) -> None:
    prepared = plan(service)
    install_synthetic_plan(service, prepared)
    manifest = service.read_manifest()
    manifest["status"] = "installing"
    manifest["files"][1]["state"] = "planned"
    manifest["files"][1].pop("inode")
    manifest["files"][1].pop("device")
    service.save_manifest(manifest)
    result = service.uninstall(user_action=True)
    assert result["preserved"] == ["mod/b.txt"]
    assert result["removed"] == ["mod/a.txt"]
    assert service.original_changes() == []


def test_hardlinked_payload_is_refused(service) -> None:
    linked = service.paths.project / "artifacts/payload/linked.txt"
    linked.hardlink_to(service.paths.game / "original.bin")
    before = hash_file(service.paths.game / "original.bin")
    with pytest.raises(ValueError, match="Hard link"):
        service.prepare("synthetic", "1", [("artifacts/payload/linked.txt", "mod/linked.txt")])
    assert hash_file(service.paths.game / "original.bin") == before


def test_original_file_cannot_be_claimed_even_by_malformed_local_receipt(service) -> None:
    prepared = plan(service)
    install_synthetic_plan(service, prepared)
    manifest = service.read_manifest()
    original = service.paths.game / "original.bin"
    info = original.stat()
    manifest["files"][0].update(
        target="ORIGINAL.bin", sha256=hash_file(original), device=info.st_dev, inode=info.st_ino
    )
    before = service.inventory()
    with pytest.raises(ValueError, match="cannot claim an original file"):
        service._remove_owned(manifest)
    assert service.inventory() == before


def test_partial_created_file_is_preserved_after_crash(service) -> None:
    prepared = plan(service)
    install_synthetic_plan(service, prepared)
    manifest = service.read_manifest()
    manifest["status"] = "installing"
    manifest["files"][1]["state"] = "created"
    service.save_manifest(manifest)
    (service.paths.game / "mod/b.txt").write_bytes(b"partial")
    result = service.uninstall(user_action=True)
    assert result["preserved"] == ["mod/b.txt"]
    assert (service.paths.game / "mod/b.txt").read_bytes() == b"partial"
    assert service.original_changes() == []


@pytest.mark.parametrize("targets", [("mod/a.txt", "MOD/A.txt"), ("mod", "mod/a.txt")])
def test_case_alias_and_file_directory_conflicts_are_refused(service, targets) -> None:
    with pytest.raises(ValueError, match="duplicated or conflicts|targets conflict"):
        service.prepare(
            "synthetic",
            "1",
            [
                ("artifacts/payload/a.txt", targets[0]),
                ("artifacts/payload/b.txt", targets[1]),
            ],
        )
    assert not (service.paths.game / "mod").exists()


def test_new_game_file_invalidates_fingerprint_before_activation(service) -> None:
    prepared = plan(service)
    (service.paths.game / "new-update.bin").write_bytes(b"game update")
    with pytest.raises(ValueError, match="The game changed after preparation"):
        install_synthetic_plan(service, prepared)
    assert not (service.paths.game / "mod").exists()
