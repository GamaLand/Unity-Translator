"""Reviewable experimental Krypta trials using the shared ownership/deployment service."""

from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.deployment import DeploymentPlan, DeploymentService, PayloadFile
from unitytranslator.filesystem import hash_file
from unitytranslator.json_boundary import strict_json
from unitytranslator.krypta_profile import load_profile
from unitytranslator.krypta_runtime import KryptaRuntimeKit
from unitytranslator.repository import ProjectRepository, canonical
from unitytranslator.runtime_configuration import bepinex_config_text, doorstop_config_bytes
from unitytranslator.textasset_export import export_payloads

ADAPTER = "krypta-textassets-experimental-trial"


def _inventory(repo: ProjectRepository, relative: str) -> dict[str, str]:
    root = repo.paths.output(relative)
    return {
        path.relative_to(root).as_posix(): hash_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }


def prepare_krypta_review(
    repo: ProjectRepository,
    kit: KryptaRuntimeKit,
    records: list[dict[str, Any]],
    *,
    review_candidates: bool = False,
    service: DeploymentService | None = None,
) -> dict[str, Any]:
    """Stage an exact file plan. Candidate previews never approve translations or install."""
    service = service or DeploymentService(repo)
    if service.repository is not repo:
        raise ValueError("The deployment service must use this project session.")
    service.require_game_closed()
    if any((repo.paths.game / name).exists() for name in ("winhttp.dll", "doorstop_config.ini")):
        raise ValueError("An existing loader conflicts with the create-new Krypta trial plan.")
    profile = load_profile()
    kit.validate()
    kit.check_game(repo, profile["assembly"]["path"])
    payload = export_payloads(
        repo,
        records,
        runtime_candidate=True,
        review_candidates=review_candidates,
    )
    kit.require_payload(Path(payload["folder"]) / "translation.json")
    staged = kit.stage(repo, profile["assembly"]["path"])
    runtime_relative = staged["runtime_relative"]
    identifier = "artifacts/krypta-review-" + uuid4().hex
    for source, relative in (
        (
            staged["plugin"],
            runtime_relative + "/plugins/UnityTranslator/UnityTranslator.KryptaFM.dll",
        ),
        (
            Path(payload["folder"]) / "translation.json",
            runtime_relative + "/plugins/UnityTranslator/translation.json",
        ),
        (staged["winhttp"], identifier + "/winhttp.dll"),
    ):
        destination = repo.paths.output(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(source.read_bytes())
        if hash_file(destination) != hash_file(source):
            raise ValueError("Krypta runtime staging hash mismatch.")
    ini_relative = identifier + "/doorstop_config.ini"
    preloader = repo.paths.output(runtime_relative + "/core/BepInEx.Preloader.dll")
    with repo.paths.output(ini_relative).open("xb") as stream:
        stream.write(doorstop_config_bytes(preloader, enabled=True))
    plan = service.prepare(
        ADAPTER,
        "1",
        [
            (identifier + "/winhttp.dll", "winhttp.dll"),
            (ini_relative, "doorstop_config.ini"),
        ],
    )
    review = {
        "format_version": 1,
        "purpose": ADAPTER,
        "project_id": repo.project_id,
        "plan": asdict(plan),
        "runtime_relative": runtime_relative,
        "runtime_files": _inventory(repo, runtime_relative),
        "kit_files": kit.catalog["files"],
        "selection": records,
        "payload_sha256": hash_file(Path(payload["folder"]) / "translation.json"),
        "selection_state": "unapproved-review-candidates" if review_candidates else "approved",
        "installation_authorized": False,
        "application_verified": False,
        "process_launch_authorized": False,
    }
    relative = identifier + "/review.json"
    repo.paths.write_json(relative, review)
    return {
        "review_relative": relative,
        "review_sha256": hash_file(repo.paths.output(relative)),
        **review,
    }


def install_krypta_review(
    repo: ProjectRepository,
    kit: KryptaRuntimeKit,
    relative: str,
    reviewed_sha256: str,
    *,
    user_action: bool,
    experimental_reviewed: bool,
    service: DeploymentService | None = None,
) -> dict[str, Any]:
    """Revalidate exact reviewed bytes and current approvals before shared create-new writes."""
    if user_action is not True or experimental_reviewed is not True:
        raise ValueError(
            "Installing a Krypta trial requires explicit review of this concrete plan."
        )
    path = repo.paths.output(relative)
    if path.stat().st_size > 1024 * 1024 or hash_file(path) != reviewed_sha256:
        raise ValueError("The reviewed Krypta plan changed or exceeded its size limit.")
    review = strict_json(path.read_bytes())
    if (
        review["format_version"] != 1
        or review["purpose"] != ADAPTER
        or review["project_id"] != repo.project_id
        or review["application_verified"] is not False
        or review["installation_authorized"] is not False
        or review["process_launch_authorized"] is not False
    ):
        raise ValueError("Invalid Krypta review identity.")
    service = service or DeploymentService(repo)
    if service.repository is not repo:
        raise ValueError("The deployment service must use this project session.")
    service.require_game_closed()
    kit.validate()
    kit.check_game(repo, load_profile()["assembly"]["path"])
    runtime = review["runtime_relative"]
    if (
        review["kit_files"] != kit.catalog["files"]
        or _inventory(repo, runtime) != review["runtime_files"]
    ):
        raise ValueError("The reviewed runtime files changed.")
    # Approval itself advances work-item versions. Exact source/translation revisions
    # remain bound to the review, and the approved exporter checks their current versions.
    current = []
    for selected in review["selection"]:
        row = repo.db.execute(
            "SELECT u.source_revision,w.translation_revision,w.version FROM text_units u "
            "JOIN work_items w USING(unit_id) WHERE u.unit_id=? AND u.active=1",
            (selected["unit_id"],),
        ).fetchone()
        if row is None or any(
            row[key] != selected[key] for key in ("source_revision", "translation_revision")
        ):
            raise ValueError("A reviewed translation revision changed.")
        current.append({"unit_id": selected["unit_id"], **dict(row)})
    approved = export_payloads(repo, current, runtime_candidate=True)
    kit.require_payload(Path(approved["folder"]) / "translation.json")
    if hash_file(Path(approved["folder"]) / "translation.json") != review["payload_sha256"]:
        raise ValueError("The approved runtime payload differs from the reviewed candidate.")
    expected_payload = runtime + "/plugins/UnityTranslator/translation.json"
    if hash_file(repo.paths.output(expected_payload)) != review["payload_sha256"]:
        raise ValueError("The staged runtime payload changed.")
    for name, digest in kit.catalog["runtime_files"].items():
        if name.startswith("core/"):
            target = runtime + "/" + name
        elif name.startswith("plugin/"):
            target = runtime + "/plugins/UnityTranslator/" + kit.plugin_name
        else:
            target = Path(relative).parent.as_posix() + "/winhttp.dll"
        if hash_file(repo.paths.output(target)) != digest:
            raise ValueError("A reviewed runtime component is not pinned by the catalog.")
    preloader = repo.paths.output(runtime + "/core/BepInEx.Preloader.dll")
    ini = Path(relative).parent.as_posix() + "/doorstop_config.ini"
    if repo.paths.output(ini).read_bytes() != doorstop_config_bytes(preloader, enabled=True):
        raise ValueError("The reviewed loader configuration changed.")
    if (
        repo.paths.output(runtime + "/config/BepInEx.cfg").read_bytes()
        != bepinex_config_text().encode()
    ):
        raise ValueError("The reviewed runtime configuration changed.")
    value = review["plan"]
    plan = DeploymentPlan(
        value["id"],
        value["adapter"],
        value["adapter_version"],
        value["fingerprint"],
        tuple(PayloadFile(**item) for item in value["files"]),
    )
    expected = [
        PayloadFile(
            Path(relative).parent.as_posix() + "/winhttp.dll",
            "winhttp.dll",
            kit.catalog["runtime_files"]["winhttp.dll"],
        ),
        PayloadFile(ini, "doorstop_config.ini", hash_file(repo.paths.output(ini))),
    ]
    if plan.adapter != ADAPTER or plan.adapter_version != "1" or list(plan.files) != expected:
        raise ValueError("The reviewed create-new file plan changed.")
    recorded = strict_json(repo.paths.output(f"artifacts/plans/{plan.id}.json").read_bytes())
    if canonical(recorded) != canonical(asdict(plan)):
        raise ValueError("The recorded deployment plan changed.")
    return service.install_experimental_trial(
        plan,
        user_action=True,
        experimental_trial_reviewed=True,
    )
