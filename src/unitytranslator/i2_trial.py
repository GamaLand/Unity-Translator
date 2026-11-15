"""Project-local I2 trial previews; preparation does not authorize installation."""

import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.json_boundary import strict_json
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_configuration import bepinex_config_text, doorstop_config_bytes
from unitytranslator.runtime_payload import export_runtime_payload


def _read_manifest(path: Path, max_bytes: int = 4 * 1024 * 1024) -> dict[str, Any]:
    path = checked_path(path)
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("The trial manifest exceeds the size limit.")
    value = strict_json(data)
    if not isinstance(value, dict):
        raise ValueError("The trial manifest must be an object.")
    return value


def _runtime_files(runtime: Path, project: Path) -> set[str]:
    result = set()
    for entry in runtime.rglob("*"):
        path = checked_path(entry)
        if path.is_file():
            result.add(path.relative_to(project).as_posix())
    return result


def prepare_i2_trial(
    repo: ProjectRepository,
    *,
    runtime_relative: str,
    plugin: Path,
    plugin_evidence: Path,
    winhttp: Path,
    winhttp_sha256: str,
    source_set: str,
    unity_version: str,
    assembly_relative: str,
    target_name: str,
    selected_unit_ids: set[str],
    record_limit: int = 10,
) -> dict[str, Any]:
    if type(record_limit) is not int or not 1 <= record_limit <= 100_000:
        raise ValueError("Invalid record limit.")
    paths = repo.paths
    runtime = paths.output(runtime_relative)
    base = _read_manifest(runtime / "runtime-base-manifest.json")
    if base["status"] != "prepared" or base["purpose"] != "experimental-external-runtime-base":
        raise ValueError("A prepared external runtime is required for the trial.")
    for item in base["files"]:
        if hash_file(paths.output(runtime_relative + "/" + item["file"])) != item["sha256"]:
            raise ValueError("The runtime changed after preparation.")
    settings = base["settings"]
    if settings["loader_enabled"] is not False:
        raise ValueError("Preparation must keep the loader disabled.")
    for name, digest in (
        (settings["runtime_config"], settings["runtime_config_sha256"]),
        (settings["doorstop_ini"], settings["doorstop_ini_sha256"]),
    ):
        path = checked_path(Path(name))
        if not path.is_relative_to(paths.project) or hash_file(path) != digest:
            raise ValueError("A runtime setting is outside the project or has changed.")
    if Path(settings["runtime_config"]).read_bytes() != bepinex_config_text().encode(
        "utf-8"
    ) or Path(settings["doorstop_ini"]).read_bytes() != doorstop_config_bytes(
        runtime / "core/BepInEx.Preloader.dll"
    ):
        raise ValueError("The runtime settings content does not match the disabled trial policy.")
    expected = {runtime_relative + "/" + item["file"] for item in base["files"]}
    expected.update(
        {
            runtime_relative + "/runtime-base-manifest.json",
            Path(settings["runtime_config"]).relative_to(paths.project).as_posix(),
        }
    )
    if _runtime_files(runtime, paths.project) != expected:
        raise ValueError("An unexpected file was added to the runtime.")
    plugin, plugin_evidence, winhttp = map(checked_path, (plugin, plugin_evidence, winhttp))
    evidence = _read_manifest(plugin_evidence)
    plugin_hash = hash_file(plugin)
    if evidence["status"] != "compiled" or evidence["output_sha256"] != plugin_hash:
        raise ValueError("The plugin build evidence does not match.")
    assembly = checked_path(paths.game / assembly_relative)
    if not assembly.is_relative_to(paths.game) or evidence["references_sha256"].get(
        str(assembly)
    ) != hash_file(assembly):
        raise ValueError("The plugin game assembly reference has changed.")
    if hash_file(winhttp) != winhttp_sha256:
        raise ValueError("The Doorstop DLL hash does not match.")
    for name in ("winhttp.dll", "doorstop_config.ini"):
        if checked_path(paths.game / name).exists():
            raise ValueError(
                "A game target conflicts with an existing file; the trial was not prepared."
            )
    destination = paths.output(runtime_relative + "/plugins/UnityTranslator")
    if destination.exists():
        raise ValueError("An existing plugin trial is not overwritten.")
    identifier = "artifacts/i2-trial-" + uuid4().hex
    manifest_name = identifier + "/trial-preview.json"
    manifest: dict[str, Any] = {
        "format_version": 1,
        "purpose": "i2mono-experimental-trial-preview",
        "status": "preparing",
        "project_id": repo.project_id,
        "runtime_relative": runtime_relative,
        "installation_authorized": False,
        "application_verified": False,
        "baseline_required": True,
        "loader_enabled": False,
        "assembly_relative": assembly_relative,
        "assembly_sha256": hash_file(assembly),
        "record_limit": record_limit,
    }
    paths.write_json(manifest_name, manifest)
    try:
        payload = export_runtime_payload(
            repo,
            source_set=source_set,
            unity_version=unity_version,
            assembly_relative=assembly_relative,
            target_name=target_name,
            relative=runtime_relative + "/plugins/UnityTranslator/translation.json",
            selected_unit_ids=selected_unit_ids,
            max_records=record_limit,
        )
        for incoming, name, digest in (
            (
                plugin,
                runtime_relative + "/plugins/UnityTranslator/UnityTranslator.I2Mono.dll",
                plugin_hash,
            ),
            (winhttp, identifier + "/game-files/winhttp.dll", winhttp_sha256),
            (
                Path(settings["doorstop_ini"]),
                identifier + "/game-files/doorstop_config.ini",
                settings["doorstop_ini_sha256"],
            ),
        ):
            target = paths.output(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with incoming.open("rb") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            if hash_file(target) != digest:
                raise ValueError("A trial copy failed the hash check.")
        immutable = []
        for path in sorted(runtime.rglob("*")):
            path = checked_path(path)
            if path.is_file():
                immutable.append(
                    {
                        "relative": path.relative_to(paths.project).as_posix(),
                        "sha256": hash_file(path),
                    }
                )
        for name in ("winhttp.dll", "doorstop_config.ini"):
            relative = identifier + "/game-files/" + name
            immutable.append({"relative": relative, "sha256": hash_file(paths.output(relative))})
        manifest.update(
            status="prepared",
            payload=payload,
            immutable_files=immutable,
            proposed_game_files=[
                {
                    "source": identifier + "/game-files/" + name,
                    "target": name,
                    "sha256": hash_file(paths.output(identifier + "/game-files/" + name)),
                }
                for name in ("winhttp.dll", "doorstop_config.ini")
            ],
        )
        paths.write_json(manifest_name, manifest)
    except Exception:
        manifest["status"] = "failed"
        paths.write_json(manifest_name, manifest)
        raise
    return {
        "manifest": str(paths.output(manifest_name)),
        "records": payload["records"],
        "status": "prepared",
    }


def validate_i2_trial(repo: ProjectRepository, manifest_relative: str) -> dict[str, Any]:
    manifest = _read_manifest(repo.paths.output(manifest_relative))
    if (
        manifest["project_id"] != repo.project_id
        or manifest["status"] != "prepared"
        or manifest["purpose"] != "i2mono-experimental-trial-preview"
        or manifest["format_version"] != 1
        or manifest["loader_enabled"] is not False
        or manifest["installation_authorized"] is not False
    ):
        raise ValueError("The trial project or preparation identity is invalid.")
    assembly = checked_path(repo.paths.game / manifest["assembly_relative"])
    if (
        not assembly.is_relative_to(repo.paths.game)
        or assembly.name != "Assembly-CSharp.dll"
        or hash_file(assembly) != manifest["assembly_sha256"]
    ):
        raise ValueError("The trial game assembly changed.")
    frozen_records = manifest["payload"]["reviewed_records"]
    record_limit = manifest.get("record_limit", 10)
    if (
        type(record_limit) is not int
        or not 1 <= record_limit <= 100_000
        or not 1 <= len(frozen_records) <= record_limit
        or len(frozen_records) != manifest["payload"]["records"]
    ):
        raise ValueError("The trial record limit is invalid.")
    if len({item["unit_id"] for item in frozen_records}) != len(frozen_records):
        raise ValueError("Trial record identities are duplicated.")
    immutable = {item["relative"]: item["sha256"] for item in manifest["immutable_files"]}
    if len(immutable) != len(manifest["immutable_files"]):
        raise ValueError("Trial files are duplicated.")
    payload_path = checked_path(Path(manifest["payload"]["path"]))
    payload_relative = manifest["runtime_relative"] + "/plugins/UnityTranslator/translation.json"
    if (
        payload_path != repo.paths.output(payload_relative)
        or immutable.get(payload_relative) != manifest["payload"]["sha256"]
    ):
        raise ValueError("The trial text file does not match.")
    for item in manifest["immutable_files"]:
        if hash_file(repo.paths.output(item["relative"])) != item["sha256"]:
            raise ValueError("A trial file changed after preparation.")
    payload = _read_manifest(payload_path, 64 * 1024 * 1024)
    entries = payload["entries"]
    if len(entries) != len(frozen_records) or payload["assembly_sha256"] != hash_file(assembly):
        raise ValueError(
            "The trial text content does not match the record or assembly information."
        )
    entry_by_id = {
        sha256("\0".join(("i2-v1", item["source_set"], item["key"])).encode()).hexdigest(): item
        for item in entries
    }
    if set(entry_by_id) != {item["unit_id"] for item in frozen_records}:
        raise ValueError("The trial text identities do not match the reviewed records.")
    for frozen in frozen_records:
        row = repo.db.execute(
            "SELECT u.source_revision,w.translation_revision,w.version,w.status,w.approved_source,"
            "w.approved_translation,u.active,s.source_hash,t.text "
            "FROM text_units u JOIN work_items w USING(unit_id) "
            "JOIN source_revisions s ON s.id=u.source_revision "
            "JOIN translation_revisions t ON t.id=w.translation_revision "
            "WHERE u.unit_id=?",
            (frozen["unit_id"],),
        ).fetchone()
        if (
            row is None
            or not row["active"]
            or row["status"] != "approved"
            or any(
                row[key] != frozen[key]
                for key in ("source_revision", "translation_revision", "version")
            )
            or row["approved_source"] != row["source_revision"]
            or row["approved_translation"] != row["translation_revision"]
            or entry_by_id[frozen["unit_id"]]["source_sha256"] != row["source_hash"]
            or entry_by_id[frozen["unit_id"]]["text"] != row["text"]
        ):
            raise ValueError("A reviewed record for the trial changed; prepare the trial again.")
    runtime = repo.paths.output(manifest["runtime_relative"])
    actual = _runtime_files(runtime, repo.paths.project)
    expected = {
        item["relative"]
        for item in manifest["immutable_files"]
        if item["relative"].startswith(manifest["runtime_relative"] + "/")
    }
    if actual != expected:
        raise ValueError("An unexpected file was added to the runtime.")
    proposed = manifest["proposed_game_files"]
    if len(proposed) != 2 or {item["target"] for item in proposed} != {
        "winhttp.dll",
        "doorstop_config.ini",
    }:
        raise ValueError("The trial game targets are invalid.")
    trial_relative = Path(manifest_relative).parent.as_posix()
    for item in proposed:
        if (
            item["source"] != trial_relative + "/game-files/" + item["target"]
            or immutable.get(item["source"]) != item["sha256"]
        ):
            raise ValueError("A trial game file does not match.")
        if checked_path(repo.paths.game / item["target"]).exists():
            raise ValueError("A trial game target now conflicts with an existing file.")
    if repo.paths.output(
        trial_relative + "/game-files/doorstop_config.ini"
    ).read_bytes() != doorstop_config_bytes(
        runtime / "core/BepInEx.Preloader.dll"
    ) or repo.paths.output(
        manifest["runtime_relative"] + "/config/BepInEx.cfg"
    ).read_bytes() != bepinex_config_text().encode("utf-8"):
        raise ValueError("The trial settings content does not match the disabled loader policy.")
    return {
        "records": manifest["payload"]["records"],
        "files_unchanged": True,
        "human_approvals_current": True,
        "baseline_required": True,
        "installation_authorized": False,
        "application_verified": False,
    }
