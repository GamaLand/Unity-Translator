"""Stage verified approved TextAsset payloads in a new project directory only."""

import base64
import json
from dataclasses import asdict
from hashlib import sha256
from typing import Any
from uuid import uuid4

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.krypta_profile import declared_sources, load_profile, verify_profile_evidence
from unitytranslator.repository import ProjectRepository, canonical
from unitytranslator.source_contracts import SourceDescriptor, validate_relative_source
from unitytranslator.textasset_layouts import parse_payload
from unitytranslator.validation import format_issues


def export_payloads(
    repo: ProjectRepository,
    records: list[dict[str, Any]] | None = None,
    *,
    runtime_candidate: bool = False,
    review_candidates: bool = False,
) -> dict[str, Any]:
    """Freeze exact revisions; unsupported installation is explicit in the manifest."""
    profile = load_profile() if runtime_candidate else None
    if review_candidates and (profile is None or records is None):
        raise ValueError("Candidate review requires an explicit frozen runtime selection.")
    count_key = "candidate_translations" if review_candidates else "approved_translations"
    if profile is not None:
        if repo.source_language != "en" or repo.target_language != "tr":
            raise ValueError("The experimental Krypta runtime candidate supports en to tr only.")
        verify_profile_evidence(repo.paths.game, profile)
    with repo.transaction():
        sources = [
            SourceDescriptor(**json.loads(row[0]))
            for row in repo.db.execute(
                "SELECT descriptor_json FROM source_descriptors "
                "WHERE adapter_id='krypta-textassets' AND active=1 ORDER BY id"
            )
        ]
        if not sources:
            raise ValueError("No verified TextAsset sources; extract the game text first.")
        if profile is not None and {
            (source.source_file, source.source_object) for source in sources
        } != {
            (item["container"], item["object"])
            for item in declared_sources(profile)
            if not item.get("excluded_reason")
        }:
            raise ValueError("Runtime preparation requires the complete reviewed source set.")
        approved = [
            dict(row)
            for row in repo.db.execute(
                "SELECT u.*,w.version,w.translation_revision,w.approved_source,"
                "w.approved_translation,t.text AS translation,"
                "EXISTS(SELECT 1 FROM editor_drafts d WHERE d.unit_id=u.unit_id) AS has_draft "
                "FROM text_units u JOIN work_items w USING(unit_id) "
                "JOIN translation_revisions t ON t.id=w.translation_revision "
                "JOIN source_descriptors d ON d.id=u.logical_source_id "
                "WHERE u.active=1 AND d.active=1 AND d.adapter_id='krypta-textassets' "
                "AND (w.status='approved' OR (? AND w.status IN ('translated','needs_review'))) "
                "ORDER BY u.unit_id",
                (review_candidates,),
            )
        ]
        eligible = {row["unit_id"]: row for row in approved if not row["has_draft"]}
        if records is None:
            records = [
                {
                    key: row[key]
                    for key in ("unit_id", "source_revision", "translation_revision", "version")
                }
                for row in eligible.values()
            ]
        if not records or len({row["unit_id"] for row in records}) != len(records):
            raise ValueError("Select current approved TextAsset translations without drafts.")
        selection = {}
        for frozen in records:
            row = eligible.get(frozen["unit_id"])
            if (
                row is None
                or any(
                    row[key] != frozen[key]
                    for key in ("source_revision", "translation_revision", "version")
                )
                or (
                    not review_candidates
                    and (
                        row["approved_source"] != row["source_revision"]
                        or row["approved_translation"] != row["translation_revision"]
                    )
                )
            ):
                raise ValueError("Export approval or revision changed; select the records again.")
            selection[row["unit_id"]] = row
        fingerprints: dict[str, str] = {}
        staged: list[tuple[str, bytes, dict[str, Any]]] = []
        runtime_entries = []
        coverage = []
        for source in sources:
            snapshot = repo.db.execute(
                "SELECT ss.metadata_json,s.descriptor_json FROM snapshot_sources s "
                "JOIN source_snapshots ss ON ss.id=s.snapshot_id WHERE s.source_id=? "
                "ORDER BY ss.created_at DESC,ss.rowid DESC LIMIT 1",
                (source.logical_id,),
            ).fetchone()
            if snapshot is None or snapshot[1] != canonical(asdict(source)):
                raise ValueError("TextAsset snapshot metadata is missing or stale; extract again.")
            metadata = json.loads(snapshot[0])
            if metadata.get("complete_source_set") is not True:
                raise ValueError("Incomplete TextAsset snapshots cannot be exported.")
            for path, digest in metadata["fingerprints"].items():
                validate_relative_source(path)
                if path in fingerprints and fingerprints[path] != digest:
                    raise ValueError("Conflicting TextAsset source fingerprint snapshots.")
                fingerprints[path] = digest
            raw = base64.b64decode(metadata["raw_base64"], validate=True)
            document = parse_payload(raw, source.schema_version)
            drafts = {unit.unit_id: unit for unit in document.drafts(source)}
            translated: dict[int, str] = {}
            for unit_id, row in selection.items():
                if row["logical_source_id"] != source.logical_id:
                    continue
                unit = drafts.get(unit_id)
                if (
                    unit is None
                    or row["original_key"] != unit.original_key
                    or format_issues(
                        unit.source_text, row["translation"], rules=source.format_rules
                    )
                ):
                    raise ValueError(
                        "Selected records do not match the verified TextAsset payload."
                    )
                translated[int(unit.original_key.removeprefix("line/"))] = row["translation"]
            payload = document.reconstruct(translated)
            if profile is not None:
                mappings = [
                    item
                    for item in declared_sources(profile)
                    if item["container"] == source.source_file
                    and item["object"] == source.source_object
                ]
                if (
                    len(mappings) != 1
                    or source.profile_id != profile["id"]
                    or mappings[0]["name"] != source.asset_name
                    or mappings[0]["schema"] != source.schema_version
                    or mappings[0].get("excluded_reason")
                    or document.bom
                ):
                    raise ValueError("Runtime source does not match the reviewed built-in mapping.")
                if translated:
                    # No encoding or newline normalization: hashes match TextAsset UTF-8 text.
                    runtime_entries.append(
                        {
                            "source_id": source.logical_id,
                            "asset_name": source.asset_name,
                            "schema": source.schema_version,
                            "source_sha256": sha256(raw).hexdigest(),
                            "target_sha256": sha256(payload).hexdigest(),
                            "text": payload.decode("utf-8", errors="strict"),
                        }
                    )
            name = "payloads/" + sha256(source.logical_id.encode()).hexdigest() + ".txt"
            staged.append(
                (
                    name,
                    payload,
                    {
                        "file": name,
                        "source": asdict(source),
                        "sha256": sha256(payload).hexdigest(),
                        count_key: len(translated),
                        "non_text_structure_verified": True,
                    },
                )
            )
            coverage = metadata.get("coverage", [])
        if sum(item[2][count_key] for item in staged) != len(selection):
            raise ValueError("Some selected translations have no verified active source.")

        def verify_fingerprints() -> None:
            for relative, digest in fingerprints.items():
                path = checked_path(repo.paths.game / relative)
                if not path.is_relative_to(repo.paths.game) or hash_file(path) != digest:
                    raise ValueError("A game source changed; extract and review before exporting.")

        verify_fingerprints()
        if profile is not None:
            verify_profile_evidence(repo.paths.game, profile)
        identity = uuid4().hex
        pending = repo.paths.output("exports/.pending-textasset-" + identity)
        pending.mkdir(parents=True, exist_ok=False)
        pending_relative = pending.relative_to(repo.paths.project).as_posix()
        for relative, payload, _ in staged:
            target = repo.paths.output(pending_relative + "/" + relative)
            target.parent.mkdir(exist_ok=True)
            with target.open("xb") as stream:
                stream.write(payload)
            if hash_file(target) != sha256(payload).hexdigest():
                raise ValueError("Staged TextAsset payload verification failed.")
        manifest = {
            "format_version": 1,
            "kind": "staged-textasset-payloads",
            "selection_state": "unapproved-review-candidates" if review_candidates else "approved",
            "installation": "unsupported",
            "project_id": repo.project_id,
            "source_language": repo.source_language,
            "target_language": repo.target_language,
            "fingerprints": fingerprints,
            "selection": records,
            "payloads": [item[2] for item in staged],
            "coverage": coverage,
            "outside_scope": metadata.get("outside_scope", []),
            "source_files_modified": False,
        }
        repo.paths.write_json(pending_relative + "/manifest.json", manifest)
        if profile is not None:
            if len({entry["asset_name"] for entry in runtime_entries}) != len(runtime_entries):
                raise ValueError("Ambiguous runtime TextAsset names cannot be applied.")
            runtime = {
                "format_version": 1,
                "profile_id": profile["id"],
                "unity_version": profile["unity_version"],
                "assembly_sha256": profile["assembly"]["sha256"],
                "source_language": repo.source_language,
                "target_language": repo.target_language,
                "entries": runtime_entries,
            }
            encoded = canonical(runtime).encode("utf-8")
            if not runtime_entries or len(encoded) > 8 * 1024 * 1024:
                raise ValueError("Runtime payload is empty or exceeds its bounded data contract.")
            with repo.paths.output(pending_relative + "/translation.json").open("xb") as stream:
                stream.write(encoded)
            manifest["runtime_candidate"] = {
                "file": "translation.json",
                "sha256": sha256(encoded).hexdigest(),
                "application_verified": False,
                "installation_authorized": False,
            }
            repo.paths.write_json(pending_relative + "/manifest.json", manifest)
        verify_fingerprints()
        if profile is not None:
            verify_profile_evidence(repo.paths.game, profile)
        # A failed export retains a clearly pending directory, never a published payload set.
        destination = repo.paths.output("exports/textasset-" + identity)
        if destination.exists():
            raise ValueError("Export destination already exists; no files were replaced.")
        pending.rename(destination)
    return {
        "folder": str(destination),
        "manifest": str(destination / "manifest.json"),
        "sources": len(staged),
        count_key: len(selection),
        "installation": "unsupported",
    }
