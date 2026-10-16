"""Review active I2 trial settings without installing during preparation."""

from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.deployment import DeploymentPlan, DeploymentService, PayloadFile
from unitytranslator.filesystem import hash_file
from unitytranslator.i2_trial import _read_manifest, validate_i2_trial
from unitytranslator.repository import ProjectRepository, canonical
from unitytranslator.runtime_configuration import doorstop_config_bytes


def prepare_activation_review(
    repo: ProjectRepository, trial_relative: str, service: DeploymentService
) -> dict[str, Any]:
    if service.repository is not repo or service.read_baseline() is None:
        raise ValueError("Aynı proje oturumunda hazır özgün envanter gerekli.")
    validate_i2_trial(repo, trial_relative)
    trial_path = repo.paths.output(trial_relative)
    before = hash_file(trial_path)
    trial = _read_manifest(trial_path)
    relative = "artifacts/i2-active-review-" + uuid4().hex
    ini_relative = relative + "/doorstop_config.ini"
    ini = repo.paths.output(ini_relative)
    ini.parent.mkdir(parents=True)
    preloader = repo.paths.output(trial["runtime_relative"] + "/core/BepInEx.Preloader.dll")
    with ini.open("xb") as stream:
        stream.write(doorstop_config_bytes(preloader, enabled=True))
    winhttp = next(item for item in trial["proposed_game_files"] if item["target"] == "winhttp.dll")
    plan = service.prepare(
        "i2mono-experimental-trial",
        "1",
        [
            (winhttp["source"], "winhttp.dll"),
            (ini_relative, "doorstop_config.ini"),
        ],
    )
    validate_i2_trial(repo, trial_relative)
    if hash_file(trial_path) != before:
        raise ValueError("Deneme önizlemesi hazırlık sırasında değişti.")
    review = {
        "format_version": 1,
        "purpose": "i2mono-active-trial-review",
        "status": "prepared",
        "project_id": repo.project_id,
        "trial_manifest": trial_relative,
        "trial_sha256": before,
        "plan": asdict(plan),
        "loader_enabled": True,
        "installation_authorized": False,
        "application_verified": False,
        "process_launch_authorized": False,
    }
    manifest_relative = relative + "/activation-review.json"
    repo.paths.write_json(manifest_relative, review)
    return {"review_relative": manifest_relative, **review}


def validate_activation_review(
    repo: ProjectRepository, review_relative: str, service: DeploymentService
) -> DeploymentPlan:
    if service.repository is not repo:
        raise ValueError("Deneme ve koruma servisi aynı proje oturumunda olmalı.")
    review = _read_manifest(repo.paths.output(review_relative))
    if (
        review["format_version"] != 1
        or review["purpose"] != "i2mono-active-trial-review"
        or review["status"] != "prepared"
        or review["project_id"] != repo.project_id
        or review["loader_enabled"] is not True
        or review["installation_authorized"] is not False
        or review["application_verified"] is not False
        or review["process_launch_authorized"] is not False
    ):
        raise ValueError("Etkin deneme inceleme kimliği geçersiz.")
    trial_relative = review["trial_manifest"]
    validate_i2_trial(repo, trial_relative)
    if hash_file(repo.paths.output(trial_relative)) != review["trial_sha256"]:
        raise ValueError("İncelenen deneme önizlemesi değişti.")
    trial = _read_manifest(repo.paths.output(trial_relative))
    value = review["plan"]
    plan = DeploymentPlan(
        value["id"],
        value["adapter"],
        value["adapter_version"],
        value["fingerprint"],
        tuple(PayloadFile(**item) for item in value["files"]),
    )
    baseline = service.read_baseline()
    if baseline is None or plan.fingerprint != baseline["fingerprint"]:
        raise ValueError("Deneme planı özgün envanterle eşleşmiyor.")
    recorded = _read_manifest(repo.paths.output(f"artifacts/plans/{plan.id}.json"))
    winhttp = next(item for item in trial["proposed_game_files"] if item["target"] == "winhttp.dll")
    ini_relative = Path(review_relative).parent.as_posix() + "/doorstop_config.ini"
    expected = [
        PayloadFile(winhttp["source"], "winhttp.dll", winhttp["sha256"]),
        PayloadFile(
            ini_relative, "doorstop_config.ini", hash_file(repo.paths.output(ini_relative))
        ),
    ]
    preloader = repo.paths.output(trial["runtime_relative"] + "/core/BepInEx.Preloader.dll")
    if (
        canonical(recorded) != canonical(asdict(plan))
        or plan.adapter != "i2mono-experimental-trial"
        or plan.adapter_version != "1"
        or list(plan.files) != expected
        or repo.paths.output(ini_relative).read_bytes()
        != doorstop_config_bytes(preloader, enabled=True)
    ):
        raise ValueError("Etkin deneme dosya planı veya ayar içeriği değişti.")
    return plan


def install_reviewed_trial(
    repo: ProjectRepository,
    review_relative: str,
    service: DeploymentService,
    *,
    user_action: bool,
    experimental_trial_reviewed: bool,
) -> dict[str, Any]:
    if user_action is not True or experimental_trial_reviewed is not True:
        raise ValueError("İncelenen deneysel kurulum açık kullanıcı seçimi gerektirir.")
    plan = validate_activation_review(repo, review_relative, service)
    return service.install_experimental_trial(
        plan, user_action=user_action, experimental_trial_reviewed=experimental_trial_reviewed
    )
