import json

import pytest
from test_i2_trial import prepared
from test_i2_trial import trial as trial_fixture  # noqa: F401

from unitytranslator.deployment import DeploymentService, GameNotClosedError
from unitytranslator.game_process import GameProcessStatus
from unitytranslator.i2_activation import (
    install_reviewed_trial,
    prepare_activation_review,
    validate_activation_review,
)
from unitytranslator.runtime_configuration import doorstop_config_bytes


@pytest.fixture
def active(trial_fixture):  # noqa: F811 — pytest fixture injection
    repo, args = trial_fixture
    trial_relative, _ = prepared(repo, args)
    service = DeploymentService(repo, process_probe=lambda _: GameProcessStatus("closed"))
    service.baseline()
    review = prepare_activation_review(repo, trial_relative, service)
    return repo, args, service, review


def test_enabled_review_is_project_only_and_does_not_alter_disabled_preview(active):
    repo, args, service, review = active
    plan = validate_activation_review(repo, review["review_relative"], service)
    assert review["loader_enabled"] is True and review["installation_authorized"] is False
    assert review["application_verified"] is False
    assert not (repo.paths.game / "winhttp.dll").exists()
    assert service.inventory() == service.baseline()["files"]
    ini = repo.paths.output(plan.files[1].source)
    preloader = repo.paths.output(args["runtime_relative"] + "/core/BepInEx.Preloader.dll")
    assert ini.read_bytes() == doorstop_config_bytes(preloader, enabled=True)
    trial = json.loads(repo.paths.output(review["trial_manifest"]).read_text(encoding="utf-8"))
    disabled = next(
        item["source"]
        for item in trial["proposed_game_files"]
        if item["target"] == "doorstop_config.ini"
    )
    assert repo.paths.output(disabled).read_bytes() == doorstop_config_bytes(preloader)
    with pytest.raises(ValueError, match="normal doğrulanmış"):
        service.activate(plan, user_action=True, adapter_verified=True)


@pytest.mark.parametrize("choice", [False, None, "true", "false", 1])
def test_experimental_install_requires_literal_explicit_choice(active, choice):
    repo, _, service, review = active
    with pytest.raises(ValueError, match="açık kullanıcı"):
        install_reviewed_trial(
            repo,
            review["review_relative"],
            service,
            user_action=True,
            experimental_trial_reviewed=choice,
        )
    assert not (repo.paths.game / "winhttp.dll").exists()
    assert not repo.paths.output("artifacts/deployment.json").exists()


def test_synthetic_trial_install_and_uninstall_keep_application_unverified(active):
    repo, _, service, review = active
    result = install_reviewed_trial(
        repo, review["review_relative"], service, user_action=True, experimental_trial_reviewed=True
    )
    assert result["status"] == "installed"
    assert result["experimental"] is True and result["application_verified"] is False
    assert service.original_changes() == []
    removed = service.uninstall(user_action=True)
    assert removed["status"] == "removed"
    assert set(removed["removed"]) == {"winhttp.dll", "doorstop_config.ini"}
    assert service.inventory() == service.baseline()["files"]


@pytest.mark.parametrize("change", ["approval", "ini", "plan", "game-update", "running", "unknown"])
def test_changes_after_review_block_before_any_game_addition(active, change):
    repo, _, service, review = active
    if change == "approval":
        row = repo.page()[0]
        repo.edit(row["unit_id"], row["version"], "Başlat {0}")
    elif change == "ini":
        repo.paths.output(review["plan"]["files"][1]["source"]).write_bytes(b"changed config")
    elif change == "plan":
        value = json.loads(repo.paths.output(review["review_relative"]).read_text(encoding="utf-8"))
        value["plan"]["files"][1]["target"] = "original.bin"
        repo.paths.write_json(review["review_relative"], value)
    elif change == "game-update":
        (repo.paths.game / "new-update.bin").write_bytes(b"external game update")
    else:
        service.process_probe = lambda _: GameProcessStatus(change)
    with pytest.raises((ValueError, GameNotClosedError)):
        install_reviewed_trial(
            repo,
            review["review_relative"],
            service,
            user_action=True,
            experimental_trial_reviewed=True,
        )
    assert not (repo.paths.game / "winhttp.dll").exists()
    assert not (repo.paths.game / "doorstop_config.ini").exists()
