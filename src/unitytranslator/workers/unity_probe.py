"""stdout yalnızca JSON IPC; hiçbir oyun dosyasına yazılmaz."""

import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import UnityPy

from unitytranslator.filesystem import checked_path
from unitytranslator.i2 import extract_i2
from unitytranslator.i2_serialized import read_managed_i2


def probe(path: Path, source: str, game: Path | None = None) -> dict[str, Any]:
    # Stream kullanımı klasörü ve komşu ses/doku dosyalarını otomatik yüklemez.
    with checked_path(path).open("rb") as stream:
        env = UnityPy.load(stream)
        types: Counter[str] = Counter()
        candidates = []
        units: list[dict[str, Any]] = []
        errors = []
        versions: set[str] = set()
        scripts = []
        diagnostics = []
        cache: dict[str, Any] = {}
        for obj in env.objects:
            types[obj.type.name] += 1
            versions.add(str(obj.assets_file.unity_version))
            if obj.type.name == "MonoScript":
                script = obj.read()
                if script.m_Namespace == "I2.Loc":
                    scripts.append(
                        {
                            "object": obj.path_id,
                            "class": script.m_ClassName,
                            "namespace": script.m_Namespace,
                            "assembly": script.m_AssemblyName,
                        }
                    )
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tree = obj.read_typetree()
            except Exception as exc:
                diagnostics.append(
                    {
                        "object": obj.path_id,
                        "code": "type_tree_unavailable",
                        "exception": type(exc).__name__,
                    }
                )
                if game is None:
                    continue
                try:
                    tree = read_managed_i2(obj, path, game, cache)
                except Exception as fallback_error:
                    errors.append(
                        {
                            "object": obj.path_id,
                            "code": "managed_i2_error",
                            "message": str(fallback_error),
                        }
                    )
                    continue
                if tree is None:
                    continue
            if not isinstance(tree, dict):
                continue
            data = tree.get("mSource", tree)
            if isinstance(data, dict) and "mTerms" in data and "mLanguages" in data:
                candidates.append(
                    {
                        "object": obj.path_id,
                        "source_set": data.get("mName") or tree.get("m_Name"),
                        "fields": sorted(data),
                        "languages": data["mLanguages"],
                        "term_count": len(data["mTerms"]),
                        "schema_evidence": tree.get("_schema_evidence"),
                    }
                )
                try:
                    units.extend(
                        asdict(unit) for unit in extract_i2(tree, source, obj.path_id, diagnostics)
                    )
                except ValueError as exc:
                    errors.append(
                        {"object": obj.path_id, "code": "i2_schema_error", "message": str(exc)}
                    )
        return {
            "reader": "UnityPy",
            "reader_version": UnityPy.__version__,
            "unity_versions": sorted(versions),
            "objects": dict(types),
            "i2_scripts": scripts,
            "i2_candidates": candidates,
            "units": units,
            "errors": errors,
            "diagnostics": diagnostics,
        }


if __name__ == "__main__":
    try:
        value = probe(
            Path(sys.argv[1]),
            sys.argv[2],
            checked_path(Path(sys.argv[3])) if len(sys.argv) > 3 else None,
        )
        print(json.dumps(value, ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({"fatal": type(exc).__name__}))
        sys.exit(1)
