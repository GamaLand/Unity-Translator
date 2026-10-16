"""Remove registered shim/root-log writes from pinned source without running the loader."""

import argparse
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from uuid import uuid4

from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("Upstream kaynak beklenen koruma değişikliğine uymuyor.")
    return text.replace(old, new)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable", action="store_true")
    for name in ("source-archive", "managed", "loader", "csc"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "adapters/i2mono/loader-components.json").read_text())
    upstream = next(item for item in catalog["sources"] if item["repository"] == "BepInEx/BepInEx")
    archive = checked_path(args.source_archive)
    if hash_file(archive) != upstream["source_archive_sha256"]:
        raise ValueError("Upstream kaynak arşivi hash'i eşleşmiyor.")
    managed, loader, csc = map(checked_path, (args.managed, args.loader, args.csc))
    paths = ProjectPaths(managed.parent.parent, root)
    output = paths.output(".cache/protected-preloader-" + uuid4().hex)
    prefix = "BepInEx-" + upstream["commit"] + "/"
    members = []
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            if not entry.filename.startswith(prefix) or entry.is_dir():
                continue
            name = entry.filename[len(prefix) :]
            part = Path(name)
            if (
                part.is_absolute()
                or part.drive
                or ".." in part.parts
                or entry.file_size > 64 * 1024 * 1024
            ):
                raise ValueError("Kaynak arşivi güvenli değil.")
            members.append((entry, name))
        output.mkdir(parents=True)
        for entry, name in members:
            target = checked_path(output / "source" / name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(zipped.read(entry))
    source = output / "source/BepInEx.Preloader"
    changes = {}
    path = source / "Preloader.cs"
    before = hash_file(path)
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    text = replace_once(
        text, "HarmonyInteropFix.Apply();", "// UnityTranslator: persistent DLL shim disabled."
    )
    old = (
        "File.WriteAllText(\n\t\t\t\t\tPath.Combine(Paths.GameRootPath, "
        '$"preloader_{DateTime.Now:yyyyMMdd_HHmmss_fff}.log"),\n\t\t\t\t\tlog + ex);'
    )
    text = replace_once(text, old, "ProtectedRuntimeDiagnostics.TryWrite(log + ex);")
    path.write_text(
        "// Modified by UnityTranslator, 2026-10-14: no persistent shim/game-root error logs.\n"
        + text,
        encoding="utf-8",
    )
    changes["Preloader.cs"] = {"before": before, "after": hash_file(path)}
    path = source / "Entrypoint.cs"
    before = hash_file(path)
    text = path.read_text(encoding="utf-8-sig")
    text = replace_once(
        text,
        "EnvVars.LoadVars();",
        "if (!ProtectedRuntimeDiagnostics.IsExternalRuntime()) return;\n"
        "\t\t\t\tEnvVars.LoadVars();",
    )
    text = replace_once(
        text,
        "File.WriteAllText(silentExceptionLog, ex.ToString());",
        "ProtectedRuntimeDiagnostics.TryWrite(ex.ToString());",
    )
    path.write_text(
        "// Modified by UnityTranslator, 2026-10-14: exclusive external diagnostics only.\n" + text,
        encoding="utf-8",
    )
    changes["Entrypoint.cs"] = {"before": before, "after": hash_file(path)}
    path = source / "RuntimeFixes/HarmonyInteropFix.cs"
    before = hash_file(path)
    path.write_text(
        "// Modified by UnityTranslator, 2026-10-14: persistent assembly shim removed.\n"
        "namespace BepInEx.Preloader.RuntimeFixes {\n"
        "internal static class HarmonyInteropFix { public static void Apply() { } }\n}\n",
        encoding="utf-8",
    )
    changes["RuntimeFixes/HarmonyInteropFix.cs"] = {"before": before, "after": hash_file(path)}
    helper = (
        root
        / "adapters/bepinex-protected"
        / ("PortableRuntimeDiagnostics.cs" if args.portable else "ProtectedRuntimeDiagnostics.cs")
    )
    shutil.copyfile(helper, source / "ProtectedRuntimeDiagnostics.cs")
    version = source / "ProtectedVersion.cs"
    version.write_text(
        'using System.Reflection;\n[assembly: AssemblyVersion("5.4.23.5")]\n'
        '[assembly: AssemblyFileVersion("5.4.23.5")]\n'
        '[assembly: AssemblyDescription("UnityTranslator protection build 2026-10-14")]\n',
        encoding="utf-8",
        newline="\n",
    )
    references = [managed / name for name in ("mscorlib.dll", "System.dll", "System.Core.dll")]
    references += [
        loader / "BepInEx/core" / name
        for name in (
            "BepInEx.dll",
            "0Harmony.dll",
            "Mono.Cecil.dll",
            "MonoMod.Utils.dll",
            "MonoMod.RuntimeDetour.dll",
        )
    ]
    reference_hashes = {str(path): hash_file(path) for path in references}
    binary = output / "BepInEx.Preloader.dll"
    command = [
        "dotnet",
        str(csc),
        "/noconfig",
        "/nostdlib+",
        "/target:library",
        "/langversion:latest",
        "/optimize+",
        "/out:" + str(binary),
    ]
    command += ["/reference:" + str(path) for path in references]
    command += [str(path) for path in sorted(source.rglob("*.cs"))]
    result = subprocess.run(command, check=False)
    unchanged = all(hash_file(Path(path)) == digest for path, digest in reference_hashes.items())
    evidence = {
        "portable": args.portable,
        "upstream_commit": upstream["commit"],
        "source_archive_sha256": hash_file(archive),
        "changes": changes,
        "diagnostics_source_sha256": hash_file(helper),
        "compile_exit_code": result.returncode,
        "references_unchanged": unchanged,
        "references_sha256": {Path(path).name: digest for path, digest in reference_hashes.items()},
        "compiler_sha256": hash_file(csc),
        "game_executed": False,
        "application_verified": False,
        "binary_sha256": hash_file(binary) if result.returncode == 0 and binary.exists() else None,
    }
    (output / "build-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), **evidence}, indent=2))
    return result.returncode if unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
