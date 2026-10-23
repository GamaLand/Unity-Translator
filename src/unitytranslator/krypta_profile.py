"""Bounded built-in data profile, pinned to statically reviewed locale-reference evidence."""

from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Any

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.json_boundary import strict_json
from unitytranslator.source_contracts import validate_relative_source
from unitytranslator.textasset_layouts import SCHEMAS

PROFILE_ID = "krypta-fm-textassets"
DATA_FILE = "krypta-fm-profile-v1.json"


def load_profile() -> dict[str, Any]:
    raw = files("unitytranslator.resources").joinpath(DATA_FILE).read_bytes()
    if len(raw) > 256 * 1024:
        raise ValueError("Built-in TextAsset profile size limit exceeded.")
    profile: dict[str, Any] = strict_json(raw)
    if profile.get("format_version") != 1 or profile.get("id") != PROFILE_ID:
        raise ValueError("Unknown built-in TextAsset profile version.")
    if not isinstance(profile.get("sources"), list) or not 1 <= len(profile["sources"]) <= 256:
        raise ValueError("Invalid built-in TextAsset source count.")
    identities = set()
    for source in profile["sources"]:
        validate_relative_source(source["container"])
        if (
            source["schema"] not in SCHEMAS
            or source["locale"] != "en"
            or not isinstance(source["object"], int)
            or isinstance(source["object"], bool)
            or not 0 < source["object"] < 2**63
            or not isinstance(source["name"], str)
            or not 1 <= len(source["name"]) <= 256
        ):
            raise ValueError("Invalid built-in TextAsset source mapping.")
        identity = (source["container"], source["object"])
        if identity in identities:
            raise ValueError("Duplicate built-in TextAsset source mapping.")
        identities.add(identity)
    if "journal_grid" in profile and (
        profile["journal_grid"]
        != {
            "field_token": 67109175,
            "name": "Journal.objectivesDescriptionsENG",
            "schema": "journal-lines-v1",
            "rows": 4,
            "columns": 3,
        }
        or profile.get("textasset_identity_version") != "1"
    ):
        raise ValueError("Unknown built-in journal literal mapping or legacy identity namespace.")
    return profile


def declared_sources(profile: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Normalize built-in source evidence; these names cannot select executable targets."""
    sources = tuple(profile["sources"])
    if "journal_grid" in profile:
        journal = profile["journal_grid"]
        sources += (
            {
                "container": profile["assembly"]["path"],
                "object": journal["field_token"],
                "name": journal["name"],
                "schema": journal["schema"],
                "locale": "en",
            },
        )
    return sources


def textasset_source_id(profile: dict[str, Any], relative: str, name: str, language: str) -> str:
    values = (
        profile["id"],
        profile.get("textasset_identity_version", profile["version"]),
        relative,
        name,
        language,
    )
    return "textasset-v1:" + sha256("\0".join(values).encode("utf-8")).hexdigest()


def evidence_files(profile: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    references = profile["reference_files"]
    if not isinstance(references, list) or not 1 <= len(references) <= 16:
        raise ValueError("Invalid locale-reference evidence count.")
    return (profile["assembly"], *references)


def verify_profile_evidence(game: Path, profile: dict[str, Any]) -> dict[str, str]:
    fingerprints = {}
    total = 0
    for evidence in evidence_files(profile):
        relative = evidence["path"]
        validate_relative_source(relative)
        path = checked_path(game / relative)
        if not path.is_relative_to(game) or not path.is_file():
            raise ValueError("Required TextAsset locale-reference evidence is missing.")
        total += path.stat().st_size
        if path.stat().st_size > 128 * 1024 * 1024 or total > 512 * 1024 * 1024:
            raise ValueError("TextAsset evidence file size limit exceeded.")
        digest = hash_file(path)
        if digest != evidence["sha256"]:
            raise ValueError("TextAsset profile fingerprints do not match this game build.")
        fingerprints[relative] = digest
    return fingerprints
