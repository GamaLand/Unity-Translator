"""Compile the scoped Krypta FM runtime against metadata-only local game references."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.krypta_profile import load_profile, verify_profile_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--csc", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    game, loader, csc = map(checked_path, (args.game, args.loader, args.csc))
    profile = load_profile()
    verified = verify_profile_evidence(game, profile)
    managed = game / Path(profile["assembly"]["path"]).parent
    references = [
        managed / name
        for name in (
            "mscorlib.dll",
            "netstandard.dll",
            "System.dll",
            "System.Core.dll",
            "UnityEngine.dll",
            "UnityEngine.CoreModule.dll",
            "UnityEngine.JSONSerializeModule.dll",
            "Assembly-CSharp.dll",
        )
    ] + [loader / "BepInEx/core" / name for name in ("BepInEx.dll", "0Harmony.dll")]
    before = {str(path): hash_file(path) for path in references}
    native_hash = hash_file(game / "UnityPlayer.dll")
    output = checked_path(root / ".cache" / ("kryptafm-build-" + uuid4().hex))
    output.mkdir()
    identity = output / "BuildIdentity.cs"
    identity.write_text(
        "namespace UnityTranslator.KryptaFM { internal static class BuildIdentity {\n"
        + 'public const string UnityVersion="'
        + profile["unity_version"]
        + '";\n'
        + 'public const string AssemblySha256="'
        + profile["assembly"]["sha256"]
        + '";\n'
        + 'public const string UnityPlayerSha256="'
        + native_hash
        + '";\n}}\n',
        encoding="utf-8",
    )
    binary = output / "UnityTranslator.KryptaFM.dll"
    sources = [
        root / "adapters/kryptafm" / name
        for name in (
            "TranslationCore.cs",
            "PayloadJson.cs",
            "Plugin.cs",
        )
    ] + [identity]
    command = [
        "dotnet",
        str(csc),
        "/noconfig",
        "/nostdlib+",
        "/target:library",
        "/langversion:7.3",
        "/deterministic+",
        "/debug-",
        "/out:" + str(binary),
    ]
    command += ["/reference:" + str(path) for path in references] + [str(path) for path in sources]
    environment = os.environ.copy()
    environment.update(
        DOTNET_CLI_TELEMETRY_OPTOUT="1",
        DOTNET_GENERATE_ASPNET_CERTIFICATE="false",
        DOTNET_CLI_HOME=str(root / ".cache/dotnet"),
    )
    completed = subprocess.run(command, env=environment, check=False, stdin=subprocess.DEVNULL)
    unchanged = all(hash_file(Path(path)) == digest for path, digest in before.items())
    unchanged = unchanged and hash_file(game / "UnityPlayer.dll") == native_hash
    verify_profile_evidence(game, profile)
    evidence = {
        "adapter_id": "krypta-textassets-runtime",
        "compile_exit_code": completed.returncode,
        "references_unchanged": unchanged,
        "references_sha256": before,
        "source_files": {path.name: hash_file(path) for path in sources},
        "compiler_sha256": hash_file(csc),
        "unity_player_sha256": native_hash,
        "profile_evidence": verified,
        "game_executed": False,
        "application_verified": False,
        "installation_authorized": False,
        "binary_sha256": hash_file(binary) if completed.returncode == 0 else None,
    }
    (output / "build-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), **evidence}, indent=2))
    return completed.returncode if unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
