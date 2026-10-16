import json
import zipfile
from pathlib import Path

import pytest

from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.protected_source import stage_protected_source


@pytest.fixture
def inputs(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "original.bin").write_bytes(b"synthetic original")
    paths = ProjectPaths(game, tmp_path / "project")
    build, own, catalog = [tmp_path / name for name in ("build", "own", "catalog")]
    for directory in (build, own, catalog):
        directory.mkdir()
    source = build / "source"
    source.mkdir()
    own_files = {
        "LICENSE": b"synthetic own license",
        "adapters/bepinex-protected/ProtectedRuntimeDiagnostics.cs": b"synthetic diagnostics",
        "adapters/bepinex-protected/README.md": b"synthetic protection notes",
        "tools/prepare_protected_preloader.py": b"synthetic recipe",
    }
    for name, data in own_files.items():
        path = own / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    originals = {"LICENSE": b"synthetic upstream license", "BepInEx/Core.cs": b"original core"}
    changes = {}
    for name in ("Preloader.cs", "Entrypoint.cs", "RuntimeFixes/HarmonyInteropFix.cs"):
        original = b"synthetic before " + name.encode()
        relative = "BepInEx.Preloader/" + name
        originals[relative] = original
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)
        before = hash_file(path)
        path.write_bytes(b"synthetic changed " + name.encode())
        changes[name] = {"before": before, "after": hash_file(path)}
    for name, data in originals.items():
        if name.startswith("BepInEx.Preloader/"):
            continue
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    helper = own / "adapters/bepinex-protected/ProtectedRuntimeDiagnostics.cs"
    (source / "BepInEx.Preloader/ProtectedRuntimeDiagnostics.cs").write_bytes(helper.read_bytes())
    (source / "BepInEx.Preloader/ProtectedVersion.cs").write_text(
        'using System.Reflection;\n[assembly: AssemblyVersion("5.4.23.5")]\n'
        '[assembly: AssemblyFileVersion("5.4.23.5")]\n'
        '[assembly: AssemblyDescription("UnityTranslator protection build 2026-10-14")]\n',
        encoding="utf-8",
        newline="\n",
    )
    archive = tmp_path / "upstream.zip"
    commit = "a" * 40
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, data in originals.items():
            zipped.writestr("BepInEx-" + commit + "/" + name, data)
    binary = build / "BepInEx.Preloader.dll"
    binary.write_bytes(b"synthetic DLL; never loaded")
    evidence = {
        "compile_exit_code": 0,
        "references_unchanged": True,
        "upstream_commit": commit,
        "source_archive_sha256": hash_file(archive),
        "changes": changes,
        "diagnostics_source_sha256": hash_file(helper),
        "binary_sha256": hash_file(binary),
        "references_sha256": {"mscorlib.dll": "b" * 64},
        "compiler_sha256": "c" * 64,
        "private_unexpected_field": "C:/private/path",
    }
    (build / "build-evidence.json").write_text(json.dumps(evidence))
    (catalog / "loader-components.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "repository": "BepInEx/BepInEx",
                        "commit": commit,
                        "source_archive_sha256": hash_file(archive),
                    }
                ]
            }
        )
    )
    return paths, dict(build=build, archive=archive, catalog_root=catalog, own_root=own)


def test_source_trace_preserves_license_and_does_not_copy_game_data(inputs):
    paths, kwargs = inputs
    evidence = kwargs["build"] / "build-evidence.json"
    value = json.loads(evidence.read_text())
    value["changes"]["Preloader.cs"]["private_note"] = "C:/private/nested/path"
    evidence.write_text(json.dumps(value))
    before = hash_file(paths.game / "original.bin")
    result = stage_protected_source(paths, **kwargs)
    root = Path(result["directory"])
    manifest = json.loads((root / "source-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "prepared"
    assert manifest["installation_authorized"] is False
    assert manifest["redistribution_package_verified"] is False
    assert (root / "LICENSES/BepInEx-MIT.txt").read_bytes() == b"synthetic upstream license"
    public = json.loads((root / "BUILD-EVIDENCE.json").read_text())
    assert "private_unexpected_field" not in public
    assert "C:/private/path" not in json.dumps(public)
    assert "private_note" not in json.dumps(public)
    for item in manifest["files"]:
        assert hash_file(root / item["path"]) == item["sha256"]
    assert not (root / "mscorlib.dll").exists()
    assert hash_file(paths.game / "original.bin") == before


@pytest.mark.parametrize("change", ["core", "extra", "license", "binary", "helper"])
def test_source_or_binary_mismatch_fails_before_package_creation(inputs, change):
    paths, kwargs = inputs
    source = kwargs["build"] / "source"
    if change == "core":
        (source / "BepInEx/Core.cs").write_bytes(b"unrecorded modification")
    elif change == "extra":
        (source / "game.dll").write_bytes(b"unrecorded binary")
    elif change == "license":
        (source / "LICENSE").unlink()
    elif change == "binary":
        (kwargs["build"] / "BepInEx.Preloader.dll").write_bytes(b"changed")
    else:
        (
            kwargs["own_root"] / "adapters/bepinex-protected/ProtectedRuntimeDiagnostics.cs"
        ).write_bytes(b"changed")
    with pytest.raises(ValueError):
        stage_protected_source(paths, **kwargs)
    assert not paths.output("artifacts").exists()


def test_missing_reference_fingerprints_cannot_be_distributed_as_trace(inputs):
    paths, kwargs = inputs
    evidence = kwargs["build"] / "build-evidence.json"
    value = json.loads(evidence.read_text())
    value.pop("references_sha256")
    evidence.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="derleme kanıtı"):
        stage_protected_source(paths, **kwargs)


def test_copy_error_leaves_failed_manifest_only_in_project(inputs, monkeypatch):
    paths, kwargs = inputs
    original_open = Path.open

    def fail(path, *args, **kw):
        if "LICENSES" in path.parts and args and args[0] == "xb":
            raise OSError("synthetic disk full")
        return original_open(path, *args, **kw)

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(OSError, match="disk full"):
        stage_protected_source(paths, **kwargs)
    manifest = next(paths.project.glob("artifacts/protected-source-*/source-manifest.json"))
    assert json.loads(manifest.read_text())["status"] == "failed"
    assert (paths.game / "original.bin").read_bytes() == b"synthetic original"


def test_windows_version_line_endings_preserved_without_altering_content(inputs):
    paths, kwargs = inputs
    version = kwargs["build"] / "source/BepInEx.Preloader/ProtectedVersion.cs"
    data = version.read_bytes().replace(b"\n", b"\r\n")
    version.write_bytes(data)
    result = stage_protected_source(paths, **kwargs)
    copied = Path(result["directory"]) / "source/BepInEx.Preloader/ProtectedVersion.cs"
    assert copied.read_bytes() == data


def test_extra_version_directive_is_not_a_line_ending_difference(inputs):
    paths, kwargs = inputs
    version = kwargs["build"] / "source/BepInEx.Preloader/ProtectedVersion.cs"
    with version.open("ab") as stream:
        stream.write(b"unexpected source directive")
    with pytest.raises(ValueError, match="sürüm kaynağı"):
        stage_protected_source(paths, **kwargs)
