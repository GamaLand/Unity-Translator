"""C# adaptörünü statik oyun referanslarıyla derler; kurulum veya oyun başlatmaz."""

import argparse
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--managed", type=Path, required=True)
    parser.add_argument("--bepinex-core", type=Path, required=True)
    parser.add_argument("--csc", type=Path, required=True, help="Kurulu Roslyn csc.dll")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    managed = checked_path(args.managed)
    paths = ProjectPaths(managed.parent.parent, root)
    references = [
        managed / name
        for name in (
            "mscorlib.dll",
            "System.dll",
            "System.Core.dll",
            "UnityEngine.dll",
            "UnityEngine.CoreModule.dll",
            "UnityEngine.JSONSerializeModule.dll",
            "Assembly-CSharp.dll",
        )
    ] + [checked_path(args.bepinex_core) / "BepInEx.dll"]
    before = {str(path): hash_file(path) for path in references}
    output = paths.output(".cache/i2mono-build/UnityTranslator.I2Mono.dll")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = paths.output(f".cache/i2mono-build/tmp-{uuid4().hex}/UnityTranslator.I2Mono.dll")
    temporary.parent.mkdir()
    evidence = ".cache/i2mono-build/build-evidence.json"
    paths.write_json(evidence, {"status": "building", "game_executed": False})
    command = [
        "dotnet",
        str(checked_path(args.csc)),
        "/noconfig",
        "/nostdlib+",
        "/target:library",
        "/langversion:7.3",
        "/deterministic+",
        "/debug-",
        "/out:" + str(temporary),
    ]
    command.extend("/reference:" + str(path) for path in references)
    command.extend(
        str(root / "adapters/i2mono" / name)
        for name in (
            "TranslationCore.cs",
            "PayloadJson.cs",
            "Plugin.cs",
            "MemoryLanguage.cs",
        )
    )
    environment = os.environ.copy()
    environment.update(
        DOTNET_CLI_TELEMETRY_OPTOUT="1",
        DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
        DOTNET_CLI_HOME=str(root / ".cache/dotnet"),
        DOTNET_GENERATE_ASPNET_CERTIFICATE="false",
    )
    try:
        result = subprocess.run(command, env=environment, check=False)
        if any(hash_file(Path(path)) != digest for path, digest in before.items()):
            raise ValueError("Referans assembly derleme sırasında değişti; çıktı doğrulanmadı.")
        if result.returncode != 0:
            paths.write_json(evidence, {"status": "failed", "game_executed": False})
            return result.returncode
        paths.output(".cache/i2mono-build/UnityTranslator.I2Mono.dll")
        os.replace(checked_path(temporary), output)
        paths.write_json(
            evidence,
            {
                "status": "compiled",
                "compiler": "Roslyn",
                "references_sha256": before,
                "output_sha256": hash_file(output),
                "game_executed": False,
                "application_verified": False,
            },
        )
        print(output)
        return 0
    except Exception:
        paths.write_json(evidence, {"status": "failed", "game_executed": False})
        raise
    finally:
        checked_path(temporary).unlink(missing_ok=True)
        checked_path(temporary.parent).rmdir()


if __name__ == "__main__":
    raise SystemExit(main())
