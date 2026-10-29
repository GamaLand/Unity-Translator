"""Synthetic review, approval and ownership gates; no game binaries or processes."""

import json

import pytest
from test_textasset_pipeline import first, synthetic_runtime_profile
from test_textasset_pipeline import repo as synthetic_repo  # noqa: F401

from unitytranslator.deployment import DeploymentService
from unitytranslator.filesystem import hash_file
from unitytranslator.game_process import GameProcessStatus
from unitytranslator.krypta_runtime import KryptaRuntimeKit
from unitytranslator.krypta_trial import install_krypta_review, prepare_krypta_review
from unitytranslator.runtime_kit import CORE_NAMES


@pytest.mark.parametrize("change", [None, "missing", "plugin", "scope", "observed"])
def test_trial_readiness_is_bound_to_observed_binary(change):
    kit = KryptaRuntimeKit.__new__(KryptaRuntimeKit)
    evidence = {
        "format_version": 1,
        "scope": "limited-user-accepted",
        "plugin_sha256": "a" * 64,
        "observed": ["startup", "menu", "options", "menu-to-game", "pause", "subtitles"],
    }
    kit.catalog = {
        "runtime_files": {"plugin/" + kit.plugin_name: "a" * 64},
        "ui_trial_evidence": evidence,
    }
    if change == "missing":
        kit.catalog.pop("ui_trial_evidence")
    elif change == "plugin":
        evidence["plugin_sha256"] = "b" * 64
    elif change == "scope":
        evidence["scope"] = "universal"
    elif change == "observed":
        evidence["observed"] = ["menu"]
    if change is None:
        kit.require_trial_evidence()
    else:
        with pytest.raises(ValueError, match="missing or stale"):
            kit.require_trial_evidence()


@pytest.mark.parametrize(
    "entries", [[{"schema": "journal-lines-v1"}], None, ["bad"], [{"schema": []}]]
)
def test_old_runtime_cannot_prepare_a_new_or_malformed_schema(tmp_path, entries):
    kit = KryptaRuntimeKit.__new__(KryptaRuntimeKit)
    kit.catalog = {}
    path = tmp_path / "translation.json"
    path.write_text(json.dumps({"entries": entries}))
    with pytest.raises(ValueError):
        kit.require_payload(path)
    if entries == [{"schema": "journal-lines-v1"}]:
        kit.catalog = {"supported_schemas": ["journal-lines-v1"]}
        kit.require_payload(path)


@pytest.fixture
def trial(synthetic_repo, monkeypatch):  # noqa: F811
    repo = synthetic_repo
    profile = synthetic_runtime_profile(repo, monkeypatch)
    profile["assembly"]["path"] = "shared.assets"
    monkeypatch.setattr("unitytranslator.krypta_trial.load_profile", lambda: profile)
    kit = KryptaRuntimeKit.__new__(KryptaRuntimeKit)
    kit.root = repo.paths.project.parent / "synthetic-kit"
    inventory = {}
    for name in [
        *("core/" + name for name in CORE_NAMES),
        "plugin/UnityTranslator.KryptaFM.dll",
        "winhttp.dll",
    ]:
        path = kit.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("Synthetic never executed: " + name).encode())
        inventory[name] = hash_file(path)
    kit.catalog = {
        "files": inventory,
        "runtime_files": inventory,
        "assembly_sha256": hash_file(repo.paths.game / "shared.assets"),
    }
    monkeypatch.setattr(kit, "check_game", lambda repository, relative: None)
    service = DeploymentService(repo, process_probe=lambda _: GameProcessStatus("closed"))
    row = first(repo)
    repo.edit(row["unit_id"], row["version"], "< geri")
    row = first(repo)
    selection = [
        {
            key: row[key]
            for key in (
                "unit_id",
                "source_revision",
                "translation_revision",
                "version",
            )
        }
    ]
    review = prepare_krypta_review(repo, kit, selection, review_candidates=True, service=service)
    return repo, kit, service, review


def install(trial, **kwargs):
    repo, kit, service, review = trial
    return install_krypta_review(
        repo,
        kit,
        review["review_relative"],
        review["review_sha256"],
        user_action=kwargs.get("user_action", True),
        experimental_reviewed=True,
        service=service,
    )


def test_preparation_does_not_install_or_approve(trial):
    repo, _, _, review = trial
    assert review["selection_state"] == "unapproved-review-candidates"
    assert not review["installation_authorized"]
    assert first(repo)["status"] == "translated"
    assert not (repo.paths.game / "winhttp.dll").exists()
    with pytest.raises(ValueError, match="review"):
        install(trial, user_action=False)
    with pytest.raises(ValueError):
        install(trial)
    assert not (repo.paths.game / "winhttp.dll").exists()


def test_exact_approved_trial_uses_shared_receipt_and_removal(trial):
    repo, _, service, _ = trial
    original = hash_file(repo.paths.game / "shared.assets")
    row = first(repo)
    repo.approve(row["unit_id"], row["version"])
    result = install(trial)
    assert result["application_verified"] is False
    manifest = service.read_manifest()
    assert manifest["status"] == "installed"
    assert {item["target"] for item in manifest["files"]} == {"winhttp.dll", "doorstop_config.ini"}
    assert not service.original_changes()
    service.uninstall(user_action=True)
    assert hash_file(repo.paths.game / "shared.assets") == original
    assert not (repo.paths.game / "winhttp.dll").exists()


@pytest.mark.parametrize("changed", ["revision", "review", "payload", "plugin", "extra"])
def test_changed_review_runtime_or_revision_blocks_install(trial, changed):
    repo, _, _, review = trial
    row = first(repo)
    repo.approve(row["unit_id"], row["version"])
    if changed == "revision":
        row = first(repo)
        repo.edit(row["unit_id"], row["version"], "< changed")
    elif changed == "review":
        with repo.paths.output(review["review_relative"]).open("ab") as stream:
            stream.write(b" ")
    else:
        relative = review["runtime_relative"] + "/plugins/UnityTranslator/"
        name = {
            "payload": "translation.json",
            "plugin": "UnityTranslator.KryptaFM.dll",
            "extra": "Other.dll",
        }[changed]
        repo.paths.output(relative + name).write_bytes(b"synthetic changed data")
    with pytest.raises(ValueError):
        install(trial)
    assert not (repo.paths.game / "winhttp.dll").exists()


def test_experimental_plan_cannot_use_normal_activation(trial):
    repo, _, service, review = trial
    from unitytranslator.deployment import DeploymentPlan, PayloadFile

    value = review["plan"]
    plan = DeploymentPlan(
        value["id"],
        value["adapter"],
        "1",
        value["fingerprint"],
        tuple(PayloadFile(**item) for item in value["files"]),
    )
    with pytest.raises(ValueError):
        service.activate(plan, user_action=True, adapter_verified=True)


def test_ready_ui_adapter_uses_the_same_review_receipt_and_removal(trial, monkeypatch):
    from unitytranslator.installation import InstallationSession
    from unitytranslator.krypta_trial import load_profile
    from unitytranslator.reader_adapters import KryptaDeploymentAdapter, deployment_adapter_for

    repo, kit, service, _ = trial
    kit.catalog["ui_trial_enabled"] = True
    monkeypatch.setattr("unitytranslator.installation.KryptaRuntimeKit", lambda: kit)
    monkeypatch.setattr(
        "unitytranslator.installation.DeploymentService", lambda repository: service
    )
    monkeypatch.setattr("unitytranslator.installation.load_profile", load_profile)
    row = first(repo)
    repo.approve(row["unit_id"], row["version"])
    session = InstallationSession(repo)
    assert isinstance(deployment_adapter_for(session), KryptaDeploymentAdapter)
    assert session.status()["kit_available"] is True
    review = session.prepare()
    assert review["adapter_kind"] == "krypta"
    assert {item["target"] for item in review["files"]} == {"winhttp.dll", "doorstop_config.ini"}
    result = session.install(review["review_id"], user_action=True, experimental_reviewed=True)
    assert result["application_verified"] is False
    assert not service.original_changes()
    session.remove(service.read_manifest()["plan_id"], user_action=True)
    assert not service.original_changes()


def test_krypta_qt_installation_uses_review_and_owned_remove(trial, monkeypatch):
    from test_installation import test_qt_installation_flow_uses_review_dialog_and_safe_remove

    from unitytranslator.krypta_trial import load_profile

    repo, kit, _, _ = trial
    kit.catalog["ui_trial_enabled"] = True  # Synthetic kit only; no production gate is changed.
    row = first(repo)
    repo.approve(row["unit_id"], row["version"])
    monkeypatch.setattr("unitytranslator.installation.KryptaRuntimeKit", lambda: kit)
    monkeypatch.setattr("unitytranslator.installation.load_profile", load_profile)
    monkeypatch.setattr(
        "unitytranslator.installation.DeploymentService",
        lambda repository: DeploymentService(
            repository, process_probe=lambda _: GameProcessStatus("closed")
        ),
    )
    test_qt_installation_flow_uses_review_dialog_and_safe_remove((repo, kit.root), monkeypatch)
