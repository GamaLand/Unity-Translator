"""Build a self-contained local distribution ZIP from approved translations."""

import json
import zipfile
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.deployment import DeploymentService
from unitytranslator.filesystem import hash_file
from unitytranslator.krypta_profile import load_profile
from unitytranslator.krypta_runtime import KryptaRuntimeKit
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_configuration import bepinex_config_text
from unitytranslator.runtime_export import export_selected_runtime
from unitytranslator.runtime_kit import RUNTIME_NAMES, PortableRuntimeKit

PATCH_FOLDER = "UnityTranslatorPatch"


def supports_shareable_patch(repo: ProjectRepository) -> bool:
    """Availability is separate from final source, kit and approval validation."""
    adapters = {
        row[0]
        for row in repo.db.execute(
            "SELECT DISTINCT coalesce(d.adapter_id,'i2') FROM text_units u "
            "LEFT JOIN source_descriptors d ON d.id=u.logical_source_id WHERE u.active=1"
        )
    }
    if adapters == {"i2"}:
        return True
    if adapters != {"krypta-textassets"} or (
        repo.source_language != "en" or repo.target_language != "tr"
    ):
        return False
    profiles = {
        row[0] for row in repo.db.execute(
            "SELECT DISTINCT d.profile_id FROM text_units u JOIN source_descriptors d "
            "ON d.id=u.logical_source_id WHERE u.active=1"
        )
    }
    return profiles == {load_profile()["id"]}


def _krypta_components(
    kit: KryptaRuntimeKit, portable: PortableRuntimeKit
) -> list[tuple[str, Path, bool, str]]:
    """Compose the unchanged scoped plugin with the separately guarded portable loader."""
    kit.validate()
    kit.require_trial_evidence()
    portable.validate()
    # All shared runtime components must match, except the separately built loader.
    for name in (kit.runtime_names & portable.runtime_names) - {"core/BepInEx.Preloader.dll"}:
        if kit.catalog["runtime_files"][name] != portable.catalog["runtime_files"][name]:
            raise ValueError("The portable and Krypta runtime component versions differ.")
    components = []
    for name in kit.catalog["files"]:
        if name == "core/BepInEx.Preloader.dll":
            source = portable.root / name
            expected = portable.catalog["files"][name]
        else:
            source = kit.root / name
            expected = kit.catalog["files"][name]
        if name == "winhttp.dll":
            target = name
        elif name.startswith("core/"):
            target = PATCH_FOLDER + "/BepInEx/" + name
        elif name.startswith("plugin/"):
            target = PATCH_FOLDER + "/BepInEx/plugins/UnityTranslator/" + Path(name).name
        else:
            target = PATCH_FOLDER + "/support/krypta/" + name
        components.append((target, source, name in kit.runtime_names, expected))
    for name in portable.catalog["files"]:
        if name not in portable.runtime_names:
            components.append((PATCH_FOLDER + "/support/portable/" + name,
                               portable.root / name, False, portable.catalog["files"][name]))
    return components


def export_shareable_patch(repo: ProjectRepository) -> dict[str, Any]:
    if not supports_shareable_patch(repo):
        raise ValueError(
            "Shareable installation ZIPs are unavailable for this source adapter. "
            "Use approved game-text export; it is not an installation package."
        )
    selected = [
        dict(row)
        for row in repo.db.execute(
            "SELECT u.unit_id,u.source_revision,w.translation_revision,w.version FROM text_units u "
            "JOIN work_items w USING(unit_id) WHERE u.active=1 AND w.status='approved' "
            "ORDER BY u.unit_id"
        )
    ]
    adapter = repo.db.execute(
        "SELECT coalesce(d.adapter_id,'i2') FROM text_units u "
        "LEFT JOIN source_descriptors d ON d.id=u.logical_source_id WHERE u.active=1 LIMIT 1"
    ).fetchone()[0]
    portable = PortableRuntimeKit()
    if adapter == "krypta-textassets":
        krypta = KryptaRuntimeKit()
        components = _krypta_components(krypta, portable)
        assembly_relative = load_profile()["assembly"]["path"]
        krypta.check_game(repo, assembly_relative)
        context = export_selected_runtime(repo, selected, record_limit=100_000)
        krypta.require_payload(Path(context["path"]))
        payload_manifest = json.loads(Path(context["manifest"]).read_text(encoding="utf-8"))
        context["source_fingerprints"] = payload_manifest["fingerprints"]
        kit: KryptaRuntimeKit | PortableRuntimeKit = krypta
    else:
        context = export_selected_runtime(repo, selected, record_limit=100_000)
        kit = portable
        kit.validate()
        assembly_relative = context["assembly_relative"]
        kit.check_game(repo, assembly_relative)
        components = []
        for name in kit.catalog["files"]:
            if name == "winhttp.dll":
                target = name
            elif name.startswith("core/"):
                target = PATCH_FOLDER + "/BepInEx/" + name
            elif name.startswith("plugin/"):
                target = PATCH_FOLDER + "/BepInEx/plugins/UnityTranslator/" + Path(name).name
            else:
                target = PATCH_FOLDER + "/support/" + name
            components.append((target, kit.root / name, name in RUNTIME_NAMES,
                               kit.catalog["files"][name]))
    for relative, expected in context["source_fingerprints"].items():
        if expected is None or hash_file(repo.paths.game / relative) != expected:
            raise ValueError("Oyun kaynağı değişmiş; yeniden çıkarın.")
    identifier = uuid4().hex
    folder = repo.paths.output("exports/shareable-" + identifier)
    folder.mkdir(parents=True)
    inventory = []
    runtime_bytes = 0

    def put(target: str, data: bytes, runtime: bool = False) -> None:
        nonlocal runtime_bytes
        relative = folder.relative_to(repo.paths.project).as_posix() + "/payload/" + target
        path = repo.paths.output(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        inventory.append({"path": target, "sha256": hash_file(path), "bytes": len(data)})
        if runtime:
            runtime_bytes += len(data)

    for target, source, runtime, expected in components:
        data = source.read_bytes()
        if sha256(data).hexdigest() != expected:
            raise ValueError("A runtime component changed while preparing the shareable ZIP.")
        put(target, data, runtime)
    if adapter == "krypta-textassets":
        put(PATCH_FOLDER + "/support/RUNTIME-COMPOSITION.json", json.dumps({
            "format_version": 1,
            "adapter": adapter,
            "plugin_sha256": kit.catalog["runtime_files"]["plugin/" + kit.plugin_name],
            "preloader_sha256": portable.catalog["runtime_files"]["core/BepInEx.Preloader.dll"],
            "preloader_sources": "portable/SOURCES/protected-preloader.zip",
            "plugin_sources": "krypta/SOURCES/UnityTranslator-KryptaFM.zip",
            "note": "Source kit inventories describe their own builds. The active runtime "
                    "uses the Krypta plugin and shared core, with the portable preloader. "
                    "This portable combination has synthetic validation; gameplay observation "
                    "used the same plugin with the external preloader.",
        }, indent=2).encode())
    put(PATCH_FOLDER + "/portable-runtime-v1.marker", b"UnityTranslator portable runtime v1\n")
    put(PATCH_FOLDER + "/BepInEx/config/BepInEx.cfg", bepinex_config_text().encode(), True)
    put(
        PATCH_FOLDER + "/BepInEx/plugins/UnityTranslator/translation.json",
        Path(context["path"]).read_bytes(),
        True,
    )
    assembly = Path(assembly_relative)
    executable = assembly.parts[0][:-5] + ".exe"
    game_files = {
        str(assembly.parent / name).replace("\\", "/"): digest
        for name, digest in kit.catalog["managed_references"].items()
    }
    game_files["UnityPlayer.dll"] = kit.catalog["unity_player_sha256"]
    game_files[executable] = hash_file(repo.paths.game / executable)
    game_files.update(context["source_fingerprints"])
    baseline = DeploymentService(repo).read_baseline()
    if baseline is not None:
        game_files.update(baseline["files"])
    manifest = {
        "format_version": 1,
        "purpose": "unitytranslator-shareable-patch",
        "package_id": identifier,
        "patch_folder": PATCH_FOLDER,
        "game_executable": executable,
        "game_files": game_files,
        "records": len(selected),
        "experimental": True,
        "adapter": adapter,
        "files": inventory,
    }
    (folder / "package.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    resources = files("unitytranslator.resources")
    script = resources.joinpath("patch-installer.ps1").read_bytes()
    (folder / "patch.ps1").write_bytes(b"\xef\xbb\xbf" + script.removeprefix(b"\xef\xbb\xbf"))
    for filename, action in (
        ("Install.cmd", "Install"),
        ("Uninstall.cmd", "Remove"),
        ("Kur.cmd", "Install"),
        ("Kaldir.cmd", "Remove"),
    ):
        (folder / filename).write_bytes(
            (
                '@echo off\r\n"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" '
                '-NoProfile -ExecutionPolicy Bypass -File "%~dp0patch.ps1" -Action '
                + action
                + "\r\npause\r\n"
            ).encode("ascii")
        )
    (folder / "README.txt").write_text(
        "UnityTranslator shareable translation patch\n\n"
        "Extract the ZIP into a separate folder. Run Install.cmd and choose the game folder.\n"
        "Review the displayed file paths and hashes, then type INSTALL to approve that plan.\n"
        "The game must be closed. UnityTranslator, Python, LM Studio "
        "and a model are not required.\n"
        "The installer adds UnityTranslatorPatch, winhttp.dll and doorstop_config.ini.\n"
        "Existing files or folders are never overwritten. Remove an earlier installation first.\n"
        "Use the original UnityTranslator project to remove a project-managed trial.\n"
        "Uninstall.cmd removes only this package's files with matching ownership and hashes.\n"
        "Modified files are preserved. If you move the game, uninstall and reinstall the patch.\n"
        "The loader path is generated on the recipient's computer.\n"
        "Kur.cmd and Kaldir.cmd are equivalent legacy launcher names.\n"
        "Experimental: matching Windows x64 game required. Check fonts, RTL layout and plurals.\n"
        "No game files, model or project database are included.\n"
        "Component licenses and sources are under UnityTranslatorPatch/support.\n",
        encoding="utf-8-sig",
    )
    destination = folder.with_suffix(".zip")
    pending = folder.with_suffix(".pending.zip")
    with zipfile.ZipFile(pending, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    with zipfile.ZipFile(pending) as archive:
        if archive.testzip() is not None:
            raise ValueError("Dağıtım ZIP kontrolü başarısız.")
    kit.check_game(repo, assembly_relative)
    for relative, expected in game_files.items():
        if hash_file(repo.paths.game / relative) != expected:
            raise ValueError("A game source changed while preparing the shareable ZIP.")
    for frozen in selected:
        current = repo.db.execute(
            "SELECT u.source_revision,w.translation_revision,w.version,w.status,"
            "EXISTS(SELECT 1 FROM editor_drafts d WHERE d.unit_id=u.unit_id) AS has_draft "
            "FROM text_units u JOIN work_items w USING(unit_id) WHERE u.unit_id=? AND u.active=1",
            (frozen["unit_id"],),
        ).fetchone()
        if (current is None or current["status"] != "approved" or current["has_draft"] or any(
            current[key] != frozen[key]
            for key in ("source_revision", "translation_revision", "version")
        )):
            raise ValueError("An approved revision changed while preparing the shareable ZIP.")
    pending.rename(destination)
    return {
        "path": str(destination),
        "records": len(selected),
        "bytes": destination.stat().st_size,
        "runtime_bytes": runtime_bytes,
        "sha256": hash_file(destination),
        "requires_unitytranslator": False,
        "game_written": False,
        "experimental": True,
    }
