"""Read declared TextAssets and the pinned journal grid; game assemblies remain data."""

import base64
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

import UnityPy

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.journal_grid import read_journal_grid
from unitytranslator.krypta_profile import (
    load_profile,
    textasset_source_id,
    verify_profile_evidence,
)
from unitytranslator.source_contracts import SourceDescriptor
from unitytranslator.textasset_layouts import MAX_PAYLOAD_BYTES, parse_payload


def probe(game: Path, source_language: str) -> dict[str, Any]:
    game = checked_path(game)
    profile = load_profile()
    if source_language != "en":
        raise ValueError("This reviewed TextAsset profile requires English as the source language.")
    fingerprints = verify_profile_evidence(game, profile)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in profile["sources"]:
        grouped[source["container"]].append(source)
    units: list[dict[str, Any]] = []
    descriptors = []
    payloads = []
    coverage = []
    total_size = 0
    for relative, sources in sorted(grouped.items()):
        path = checked_path(game / relative)
        if not path.is_relative_to(game) or not path.is_file():
            raise ValueError("A required TextAsset source container is missing.")
        total_size += path.stat().st_size
        if path.stat().st_size > 128 * 1024 * 1024 or total_size > 384 * 1024 * 1024:
            raise ValueError("TextAsset container size limit exceeded.")
        fingerprint = hash_file(path)
        fingerprints[relative] = fingerprint
        with path.open("rb") as stream:
            env = UnityPy.load(stream)
            if (
                len(env.files) != 1
                or type(next(iter(env.files.values()))).__name__ != "SerializedFile"
            ):
                raise ValueError("This TextAsset reader supports serialized containers only.")
            objects = list(env.objects)
            if len(objects) > 100000:
                raise ValueError("TextAsset container object count limit exceeded.")
            by_id = {obj.path_id: obj for obj in objects}
            selected = {source["object"] for source in sources}
            coverage.append(
                {
                    "container": relative,
                    "textassets": sum(obj.type.name == "TextAsset" for obj in objects),
                    "selected_sources": len(selected),
                    "excluded_objects": [
                        obj.path_id
                        for obj in objects
                        if obj.type.name == "TextAsset" and obj.path_id not in selected
                    ],
                    "exclusion_reason": "outside_verified_english_references",
                }
            )
            for source in sources:
                obj = by_id.get(source["object"])
                if obj is None or obj.type.name != "TextAsset":
                    raise ValueError("A declared TextAsset is missing or has changed type.")
                if str(obj.assets_file.unity_version) != profile["unity_version"]:
                    raise ValueError("TextAsset Unity version differs from the reviewed build.")
                if obj.byte_size > MAX_PAYLOAD_BYTES + 4096:
                    raise ValueError("TextAsset serialized object size limit exceeded.")
                asset = obj.read()
                if asset.m_Name != source["name"]:
                    raise ValueError("TextAsset name does not match its verified locale reference.")
                raw = asset.m_Script.encode("utf-8", "surrogateescape")
                if len(raw) > MAX_PAYLOAD_BYTES:
                    raise ValueError("TextAsset payload size limit exceeded.")
                payload_hash = sha256(raw).hexdigest()
                if source.get("excluded_reason"):
                    if payload_hash != source["excluded_payload_sha256"]:
                        raise ValueError("An excluded payload changed; source review is required.")
                    coverage.append(
                        {
                            "container": relative,
                            "object": obj.path_id,
                            "name": asset.m_Name,
                            "excluded_reason": source["excluded_reason"],
                            "sha256": payload_hash,
                        }
                    )
                    continue
                descriptor = SourceDescriptor(
                    textasset_source_id(profile, relative, asset.m_Name, source_language),
                    "krypta-textassets",
                    profile["id"],
                    source["schema"],
                    relative,
                    obj.path_id,
                    source_language,
                    fingerprint,
                    "literal-lines-v1",
                    asset.m_Name,
                    payload_hash,
                )
                document = parse_payload(raw, source["schema"])
                if document.reconstruct({}) != raw:
                    raise ValueError("TextAsset source reconstruction is not lossless.")
                drafts = document.drafts(descriptor)
                units.extend(asdict(unit) for unit in drafts)
                descriptors.append(asdict(descriptor))
                payloads.append(
                    {
                        "logical_id": descriptor.logical_id,
                        "raw_base64": base64.b64encode(raw).decode("ascii"),
                    }
                )
                coverage.append(
                    {
                        "container": relative,
                        "object": obj.path_id,
                        "name": asset.m_Name,
                        "schema": source["schema"],
                        "records": len(drafts),
                    }
                )
        if hash_file(path) != fingerprint:
            raise ValueError("TextAsset source container changed during reading.")
    if "journal_grid" in profile:
        grid = read_journal_grid(game)
        mapping = profile["journal_grid"]
        if grid.field_token != mapping["field_token"]:
            raise ValueError("Journal field token differs from the reviewed mapping.")
        raw = grid.payload
        relative = profile["assembly"]["path"]
        identity = sha256(
            "\0".join((profile["id"], relative, str(grid.field_token), "en")).encode()
        ).hexdigest()
        descriptor = SourceDescriptor(
            "assembly-grid-v1:" + identity,
            "krypta-textassets",
            profile["id"],
            mapping["schema"],
            relative,
            grid.field_token,
            "en",
            fingerprints[relative],
            "literal-lines-v1",
            mapping["name"],
            sha256(raw).hexdigest(),
        )
        document = parse_payload(raw, mapping["schema"])
        drafts = document.drafts(descriptor)
        descriptors.append(asdict(descriptor))
        units.extend(asdict(unit) for unit in drafts)
        payloads.append(
            {
                "logical_id": descriptor.logical_id,
                "raw_base64": base64.b64encode(raw).decode("ascii"),
            }
        )
        coverage.append(
            {
                "container": relative,
                "object": grid.field_token,
                "name": mapping["name"],
                "schema": mapping["schema"],
                "records": len(drafts),
                "kind": "static-journal-literal-grid",
            }
        )
    verify_profile_evidence(game, profile)
    return {
        "reader": "UnityPy",
        "reader_version": UnityPy.__version__,
        "adapter_id": "krypta-textassets",
        "adapter_version": "1",
        "profile_id": profile["id"],
        "profile_version": profile["version"],
        "unity_versions": [profile["unity_version"]],
        "runtime_indicators": ["Mono"],
        "container_indicators": ["serialized_asset"],
        "units": units,
        "source_descriptors": descriptors,
        "payloads": payloads,
        "coverage": coverage,
        "outside_scope": profile["outside_scope"],
        "fingerprints": fingerprints,
        "complete_source_set": True,
        "errors": [],
        "diagnostics": [],
        "extraction": "supported",
        "application": "unsupported",
    }


def main() -> int:
    try:
        result = probe(Path(sys.argv[1]), sys.argv[2])
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({"fatal": type(exc).__name__, "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
