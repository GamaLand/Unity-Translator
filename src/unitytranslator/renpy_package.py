"""Package reviewed native output for create-new translated-copy installation.

No proprietary game assets, save files, local projects or executable game code are
included. The recipient supplies the matching local build. The bundled fixed
installer copies validated build files into a new independent directory.
"""

import json
import os
import re
import zipfile
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.engines import engine_evidence, renpy_inputs
from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.renpy_archive import read_index
from unitytranslator.renpy_export import (
    MAX_OUTPUT_FILES,
    MAX_TOTAL_BYTES,
    _rows,
    _sources,
    export_native,
)
from unitytranslator.repository import ProjectRepository
from unitytranslator.source_contracts import validate_relative_source

INSTALLER = "renpy-copy.ps1"
METADATA = ".unitytranslator/renpy-copy"
LAUNCHER = "Play-Translated.cmd"
MAX_FILES = 20000
MAX_BYTES = 32 * 1024 * 1024 * 1024
MAX_DEPTH = 32
_VERSION = re.compile(rb"(?m)^version = ['\"]8\.1\.2\.23090503['\"]\r?$")
_PRIVATE_METADATA = {
    ".git", ".hg", ".svn", ".agents", ".codex", ".claude", ".cursor", ".ssh", ".aws",
    ".gnupg", ".env",
}


def _skip_copy(relative: str) -> str | None:
    path = Path(relative)
    parts = tuple(part.casefold() for part in path.parts)
    if parts[:2] == ("game", "saves"):
        return "game/saves: private progress remains in the original build"
    if parts[:2] == ("game", "cache"):
        return "game/cache: the translated copy generates its own caches"
    if "__pycache__" in parts and path.suffix.casefold() == ".pyc":
        return "Python bytecode caches: regenerated in the translated copy"
    if len(parts) == 1 and parts[0] in ("log.txt", "traceback.txt", "errors.txt"):
        return "Root runtime logs: not copied or distributed"
    return None


def copy_build(game: Path, language: str) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    """Inventory the explicit new-copy scope; never change an original inventory."""
    game = checked_path(game)
    if engine_evidence(game)["engine"] != "renpy":
        raise ValueError("Translated-copy installation requires unambiguous Ren'Py evidence.")
    version = checked_path(game / "renpy/vc_version.py")
    if not version.is_file() or version.stat().st_size > 8192 or not _VERSION.search(
        version.read_bytes()
    ):
        raise ValueError("Translated-copy packages require the pinned Ren'Py 8.1.2 build.")
    executables = [checked_path(p) for p in game.glob("*.exe") if p.is_file()]
    if len(executables) != 1:
        raise ValueError("Select a build with one unambiguous root game executable.")
    namespace = checked_path(game / "game/tl" / language)
    if namespace.exists():
        raise ValueError("The target language namespace already exists in the supplied build.")
    for item in renpy_inputs(game)["source_candidates"]:
        if item["kind"] != "archive":
            continue
        index = read_index(checked_path(game / item["path"]))
        prefix = "tl/" + language.casefold() + "/"
        if any(member.name.casefold().startswith(prefix) for member in index.members):
            raise ValueError("The target language namespace already exists inside an archive.")
    pending = [(game, 0)]
    entries = []
    omitted: dict[str, int] = {}
    seen: set[str] = set()
    count, total = 0, 0
    while pending:
        directory, depth = pending.pop()
        with os.scandir(checked_path(directory)) as children:
            for child in children:
                count += 1
                if count > MAX_FILES:
                    raise ValueError("Translated-copy discovery entry limit exceeded.")
                path = checked_path(Path(child.path))
                relative = path.relative_to(game).as_posix()
                validate_relative_source(relative)
                name = path.name.casefold()
                if name in _PRIVATE_METADATA or name.startswith((".aider", ".env.")):
                    raise ValueError(
                        "A reviewed clean game build is required; private tooling or credential "
                        "metadata cannot enter a copy plan: " + relative
                    )
                if path.is_dir():
                    if depth >= MAX_DEPTH:
                        raise ValueError("Translated-copy discovery depth limit exceeded.")
                    pending.append((path, depth + 1))
                    continue
                if not path.is_file():
                    raise ValueError("Translated-copy sources must be regular files.")
                if reason := _skip_copy(relative):
                    omitted[reason] = omitted.get(reason, 0) + 1
                    continue
                if (
                    relative.casefold() == LAUNCHER.casefold()
                    or relative.casefold().startswith(".unitytranslator/")
                ):
                    raise ValueError("The supplied build conflicts with translated-copy metadata.")
                if relative.casefold() in seen:
                    raise ValueError("Ambiguous translated-copy source paths.")
                seen.add(relative.casefold())
                size = path.stat().st_size
                total += size
                if total > MAX_BYTES or path.stat().st_nlink != 1:
                    raise ValueError("Translated-copy source size or link bounds exceeded.")
                entries.append({"path": relative, "sha256": hash_file(path), "bytes": size})
    return (
        executables[0].name,
        sorted(entries, key=lambda e: e["path"]), dict(sorted(omitted.items())),
    )


def _cmd(action: str) -> bytes:
    return (
        '@echo off\r\nsetlocal\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass '
        f'-File "%~dp0{INSTALLER}" -Action {action}\r\n'
        'if errorlevel 1 pause\r\n'
    ).encode("ascii")


def export_copy_package(repo: ProjectRepository, language: str) -> dict[str, Any]:
    """Stage native output, then freeze its approvals and a matching-copy build plan."""
    adapters = {row[0] for row in repo.db.execute(
        "SELECT DISTINCT d.adapter_id FROM text_units u "
        "JOIN source_descriptors d ON d.id=u.logical_source_id WHERE u.active=1"
    )}
    if adapters not in ({"renpy-templates"}, {"renpy-scripts"}):
        raise ValueError(
            "A translated-copy package requires one complete native Ren'Py source set."
        )
    staged = export_native(repo, language)
    native_root = checked_path(Path(staged["folder"]))
    native = json.loads(checked_path(Path(staged["manifest"])).read_bytes())
    executable, build, omitted = copy_build(repo.paths.game, language)
    rows, sources = _rows(repo), _sources(repo)
    selected = [{key: row[key] for key in (
        "unit_id", "source_revision", "translation_revision", "version",
    )} for row in rows if row["status"] == "approved"]
    if selected != native["selection"] or any(row["has_draft"] for row in rows):
        raise ValueError("Native approvals or drafts changed before package preparation.")
    if {source.logical_id: source.fingerprint for source in sources} != {
        item["source"]["logical_id"]: item["source"]["fingerprint"]
        for item in native["coverage"]
    }:
        raise ValueError("Native source ownership changed before package preparation.")
    identity = uuid4().hex
    installer = files("unitytranslator.resources").joinpath(INSTALLER).read_bytes()
    launcher = (
        '@echo off\r\nsetlocal\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass '
        f'-File "%~dp0{METADATA.replace('/', chr(92))}\\{INSTALLER}" -Action Launch\r\n'
        'if errorlevel 1 pause\r\n'
    ).encode("ascii")
    payloads: dict[str, bytes] = {}
    for item in native["coverage"]:
        for output in item.get("files", [item] if "file" in item else []):
            path = checked_path(native_root / output["file"])
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != output["sha256"]:
                raise ValueError("Staged native payload changed before packaging.")
            if output["file"] in payloads:
                raise ValueError("Duplicate native output path.")
            payloads[output["file"]] = raw
    if len(payloads) > MAX_OUTPUT_FILES or sum(map(len, payloads.values())) > MAX_TOTAL_BYTES:
        raise ValueError("Translated-copy payload bounds exceeded.")
    if not payloads:
        raise ValueError("No approved native payloads are available for packaging.")
    package = {
        "format_version": native["format_version"],
        "purpose": "unitytranslator-renpy-translated-copy",
        "package_id": identity, "language": language, "game_executable": executable,
        "copy_folder": "UnityTranslatorRenpy-" + identity,
        "metadata_folder": METADATA, "launcher": LAUNCHER,
        "copy_files": build, "copy_omissions": omitted,
        "save_policy": "Separate saves; the installer never changes original saves or game files.",
        "payloads": [{"path": name, "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}
                     for name, raw in sorted(payloads.items())],
        "installer_sha256": sha256(installer).hexdigest(),
        "launcher_sha256": sha256(launcher).hexdigest(),
        "records": len(selected), "approved_revisions": selected,
        "source_language": repo.source_language, "target_language": repo.target_language,
        "input_fingerprints": native["fingerprints"],
        "syntax_version": native["syntax_version"],
        "dialect_evidence": native.get("dialect_evidence", {"family": "native-template-v1"}),
        "source_resolution": native.get("source_resolution", "template-language-folder-v1"),
        "runtime_write_scope": "The new translated copy, including its own local saves and caches.",
    }
    encoded = (json.dumps(package, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(encoded) > 32 * 1024 * 1024:
        raise ValueError("Translated-copy manifest size limit exceeded.")
    readme = (
        b"UnityTranslator Ren'Py translated-copy installation package\n\n"
        b"1. Close the game. Extract this package outside the original game.\n"
        b"2. Run Install.cmd. Select the matching original game and a separate output parent.\n"
        b"3. Review the exact create-new file plan and type INSTALL. No game is launched.\n"
        b"4. Use Play-Translated.cmd in the new copy to explicitly launch the selected language.\n"
        b"The recipient needs Windows PowerShell, not Python, a model or UnityTranslator.\n"
        b"Original saves/logs/caches are not copied. The new copy starts with separate saves.\n"
        b"Remove.cmd removes only unchanged owned copy files. Runtime-created or modified files\n"
        b"are preserved and reported; a partial removal is never reported as complete.\n"
        b"No original game file is distributed in this ZIP. Keep your original game.\n"
        b"Coverage and translation quality remain limited to the reviewed source subset.\n"
    )
    evidence = {key: native[key] for key in (
        "format_version", "parser_version", "syntax_version", "format_rules", "source_language",
        "target_language", "language_mapping", "fingerprints", "coverage", "outside_scope",
        "selection",
    )}
    if "exclusion_counts" in native:
        evidence["exclusion_counts"] = native["exclusion_counts"]
    if "dialect_evidence" in native:
        evidence["dialect_evidence"] = native["dialect_evidence"]
        evidence["version_evidence"] = native["version_evidence"]
        evidence["source_resolution"] = native["source_resolution"]
    contents = {
        "package.json": encoded, INSTALLER: installer,
        "Install.cmd": _cmd("Install"), "Remove.cmd": _cmd("Remove"),
        "Play-Translated.cmd": launcher, "README.txt": readme,
        "LICENSE.txt": files("unitytranslator.resources").joinpath(
            "renpy-copy-LICENSE.txt"
        ).read_bytes(),
        "support/renpy-source-NOTICE.txt": files("unitytranslator.resources").joinpath(
            "renpy-source-NOTICE.txt"
        ).read_bytes(),
        "native-manifest.json": (
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        ).encode(),
        **{"payload/" + name: raw for name, raw in payloads.items()},
    }
    pending = repo.paths.output("exports/.pending-renpy-copy-" + identity + ".zip")
    pending.parent.mkdir(parents=True, exist_ok=True)
    with (
        pending.open("xb") as output,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for name, raw in sorted(contents.items()):
            archive.writestr(name, raw)
    with zipfile.ZipFile(pending) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(contents):
            raise ValueError("Translated-copy ZIP verification failed.")
        if any(archive.read(name) != raw for name, raw in contents.items()):
            raise ValueError("Translated-copy ZIP content changed before publication.")
    if _rows(repo) != rows or _sources(repo) != sources:
        raise ValueError("Native source, approval or draft changed during packaging.")
    if copy_build(repo.paths.game, language) != (executable, build, omitted):
        raise ValueError("Original build files changed during packaging.")
    for relative, digest in native["fingerprints"].items():
        if hash_file(checked_path(repo.paths.game / relative)) != digest:
            raise ValueError("Native input evidence changed during packaging.")
    destination = repo.paths.output("exports/renpy-copy-" + identity + ".zip")
    if destination.exists():
        raise ValueError("Translated-copy ZIP destination exists; no file was replaced.")
    pending.rename(destination)
    return {
        "path": str(destination), "sha256": hash_file(destination), "records": len(selected),
        "copy_files": len(build), "copy_bytes": sum(entry["bytes"] for entry in build),
        "copy_omissions": omitted, "requires_unitytranslator": False,
        "installation_mode": "new-translated-copy", "original_game_modified": False,
        "native_export": staged,
    }
