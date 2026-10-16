"""Deneysel preloader için çevrimdışı kaynak/ikili izlenebilirliği; kurulum yapmaz."""

import re
import zipfile
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file
from unitytranslator.json_boundary import strict_json
from unitytranslator.loader_support import confined

_CHANGES = {"Preloader.cs", "Entrypoint.cs", "RuntimeFixes/HarmonyInteropFix.cs"}
_PREFIX = "BepInEx.Preloader/"
_LIMIT = 64 * 1024 * 1024


def _read(path: Path) -> bytes:
    with checked_path(path).open("rb") as stream:
        value = stream.read(_LIMIT + 1)
    if len(value) > _LIMIT:
        raise ValueError("Kaynak paketi dosya boyut sınırı aşıldı.")
    return value


def stage_protected_source(
    paths: ProjectPaths, *, build: Path, archive: Path, catalog_root: Path, own_root: Path
) -> dict[str, Any]:
    build, archive, catalog_root, own_root = map(
        checked_path, (build, archive, catalog_root, own_root)
    )
    catalog = strict_json(_read(confined(catalog_root, "loader-components.json")))
    upstream = next(item for item in catalog["sources"] if item["repository"] == "BepInEx/BepInEx")
    if hash_file(archive) != upstream["source_archive_sha256"]:
        raise ValueError("Upstream kaynak arşivi katalogla eşleşmiyor.")
    evidence_bytes = _read(confined(build, "build-evidence.json"))
    evidence = strict_json(evidence_bytes)
    if (
        evidence["compile_exit_code"] != 0
        or evidence["references_unchanged"] is not True
        or evidence["upstream_commit"] != upstream["commit"]
        or evidence["source_archive_sha256"] != upstream["source_archive_sha256"]
        or set(evidence["changes"]) != _CHANGES
        or not evidence.get("references_sha256")
        or not re.fullmatch(r"[a-f0-9]{64}", evidence.get("compiler_sha256", ""))
    ):
        raise ValueError("Kaynak paketinin derleme kanıtı eksik veya geçersiz.")
    references = evidence["references_sha256"]
    for name, digest in references.items():
        if Path(name).name != name or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Derleme referansı kişisel yol içeremez; ad/hash gerekli.")
    binary = confined(build, "BepInEx.Preloader.dll")
    if hash_file(binary) != evidence["binary_sha256"]:
        raise ValueError("Kaynak paketinin ikili dosyası derleme kanıtıyla eşleşmiyor.")
    source = confined(build, "source")
    expected: dict[str, str] = {}
    prefix = "BepInEx-" + upstream["commit"] + "/"
    total = 0
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            if item.is_dir():
                continue
            if not item.filename.startswith(prefix):
                raise ValueError("Upstream kaynak arşivi kökü geçersiz.")
            name = item.filename[len(prefix) :]
            confined(source, name)
            total += item.file_size
            if len(expected) >= 1000 or item.file_size > _LIMIT or total > _LIMIT:
                raise ValueError("Upstream kaynak arşivi boyut sınırı aşıldı.")
            if name.casefold() in {key.casefold() for key in expected}:
                raise ValueError("Upstream kaynak yolu yineleniyor.")
            before = sha256(zipped.read(item)).hexdigest()
            if name.startswith(_PREFIX) and name[len(_PREFIX) :] in _CHANGES:
                change = evidence["changes"][name[len(_PREFIX) :]]
                if change["before"] != before:
                    raise ValueError("Değişiklik upstream kaynak hash'iyle eşleşmiyor.")
                expected[name] = change["after"]
            else:
                expected[name] = before
    helper_name = (
        "PortableRuntimeDiagnostics.cs"
        if evidence.get("portable") is True
        else "ProtectedRuntimeDiagnostics.cs"
    )
    helper = confined(own_root, "adapters/bepinex-protected/" + helper_name)
    if hash_file(helper) != evidence["diagnostics_source_sha256"]:
        raise ValueError("Diagnostics kaynağı derleme kanıtından sonra değişti.")
    expected[_PREFIX + "ProtectedRuntimeDiagnostics.cs"] = evidence["diagnostics_source_sha256"]
    version_name = _PREFIX + "ProtectedVersion.cs"
    version = (
        b'using System.Reflection;\n[assembly: AssemblyVersion("5.4.23.5")]\n'
        b'[assembly: AssemblyFileVersion("5.4.23.5")]\n'
        b'[assembly: AssemblyDescription("UnityTranslator protection build 2026-10-14")]\n'
    )
    version_bytes = _read(confined(source, version_name))
    if version_bytes not in (version, version.replace(b"\n", b"\r\n")):
        raise ValueError("Koruma sürüm kaynağı beklenen içerikle eşleşmiyor.")
    expected[version_name] = sha256(version_bytes).hexdigest()
    actual = set()
    for entry in source.rglob("*"):
        path = checked_path(entry)
        if path.is_file():
            name = path.relative_to(source).as_posix()
            actual.add(name)
            if name not in expected or hash_file(path) != expected[name]:
                raise ValueError(f"Beklenmeyen veya değiştirilmiş kaynak dosyası bulundu: {name}")
    if actual != set(expected) or "LICENSE" not in expected:
        raise ValueError("Kaynak ağacı veya upstream lisans bildirimi eksik.")
    pending = [
        (confined(source, name), "source/" + name, digest)
        for name, digest in sorted(expected.items())
    ]
    for incoming, name in (
        (binary, "binary/BepInEx.Preloader.dll"),
        (confined(own_root, "LICENSE"), "LICENSES/UnityTranslator-MIT.txt"),
        (confined(source, "LICENSE"), "LICENSES/BepInEx-MIT.txt"),
        (
            confined(own_root, "tools/prepare_protected_preloader.py"),
            "tools/prepare_protected_preloader.py",
        ),
        (confined(own_root, "adapters/bepinex-protected/README.md"), "PROTECTION-NOTES.md"),
    ):
        pending.append((incoming, name, hash_file(incoming)))
    relative = "artifacts/protected-source-" + uuid4().hex
    output = paths.output(relative)
    if any(
        output.is_relative_to(root) or root.is_relative_to(output) for root in (build, catalog_root)
    ):
        raise ValueError("Kaynak paketi derleme/katalog ağacıyla örtüşemez.")
    manifest: dict[str, Any] = {
        "format_version": 1,
        "purpose": "protected-preloader-source-trace",
        "status": "staging",
        "upstream_commit": upstream["commit"],
        "files": [],
        "installation_authorized": False,
        "application_verified": False,
        "redistribution_package_verified": False,
    }
    manifest_name = relative + "/source-manifest.json"
    paths.write_json(manifest_name, manifest)
    try:
        for incoming, name, digest in pending:
            data = _read(incoming)
            if sha256(data).hexdigest() != digest:
                raise ValueError("Kaynak kopyası hazırlık sırasında değişti.")
            target = paths.output(relative + "/" + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            manifest["files"].append(
                {"path": name, "sha256": hash_file(target), "bytes": len(data)}
            )
        public_evidence = {
            key: evidence[key]
            for key in (
                "upstream_commit",
                "source_archive_sha256",
                "changes",
                "diagnostics_source_sha256",
                "compile_exit_code",
                "references_unchanged",
                "references_sha256",
                "compiler_sha256",
                "binary_sha256",
            )
        }
        public_evidence["changes"] = {
            name: {key: evidence["changes"][name][key] for key in ("before", "after")}
            for name in sorted(_CHANGES)
        }
        if evidence.get("portable") is True:
            public_evidence["portable"] = True
        paths.write_json(relative + "/BUILD-EVIDENCE.json", public_evidence)
        paths.write_text(
            relative + "/README.txt",
            "Experimental preloader source/binary traceability; "
            "not an installation or release package.\n"
            "The upstream MIT and UnityTranslator MIT notices are retained separately.\n"
            "No game DLLs, models or game text; references contain only names and hashes.\n"
            "Run the build tool inside a UnityTranslator checkout "
            "with the legacy Mono references.\n"
            "Dependency sources/licenses are additionally required in the loader support package.\n"
            "Identical-hash rebuilding and real-game compatibility have not been established.\n",
        )
        for name in ("BUILD-EVIDENCE.json", "README.txt"):
            target = paths.output(relative + "/" + name)
            manifest["files"].append(
                {"path": name, "sha256": hash_file(target), "bytes": target.stat().st_size}
            )
        manifest["status"] = "prepared"
        paths.write_json(manifest_name, manifest)
    except Exception:
        manifest["status"] = "failed"
        paths.write_json(manifest_name, manifest)
        raise
    return {"directory": str(output), "files": len(manifest["files"]), "status": "prepared"}
