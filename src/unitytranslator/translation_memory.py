"""Opt-in project translation memory: exact-match reuse as unapproved candidates.

Equal source text need not have an equal translation, so reuse never approves,
never replaces a current translation, approval or draft, and never chains: a
candidate created here is never a donor. A key is the exact source text with its
format rules, category, context, target language and verified dialogue window;
model donors also carry their generation profile and glossary/style versions,
which must equal the user-selected profile and the active policies.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from unitytranslator.dialogue_context import CONTEXT_VERSION, DialogueContextStore
from unitytranslator.domain import GenerationProfile
from unitytranslator.policy import PolicyStore
from unitytranslator.repository import (
    MEMORY_ORIGIN_DETAIL,
    ProjectRepository,
    canonical,
    descriptor_format_rules,
    is_memory_metadata,
)
from unitytranslator.validation import format_issues

MEMORY_VERSION = "translation-memory-v1"
# Why a record that shares a key with a donor receives no candidate, in check order.
SKIP_REASONS = (
    "approved",
    "draft",
    "queued",
    "translated",
    "same_text",
    "already_offered",
    "format",
)
MAX_SAMPLES = 20


@dataclass(frozen=True)
class Donor:
    unit_id: str
    original_key: str
    revision: str
    text: str
    kind: str  # "approved" or "model"


def profile_fingerprint(profile: dict[str, Any]) -> str | None:
    """Digest of a generation profile without its glossary/style versions."""
    try:
        value = GenerationProfile(**profile).to_dict()
    except TypeError:
        return None
    value.pop("glossary_version", None)
    value.pop("style_version", None)
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def dialogue_digest(window: dict[str, Any]) -> str:
    """Meaning of a verified window: speaker and neighbouring source, not record IDs."""
    return sha256(
        canonical(
            {
                "version": CONTEXT_VERSION,
                "speaker": window["speaker"],
                "references": [
                    [item["offset"], item["speaker"], item["source"]]
                    for item in window["references"]
                ],
            }
        ).encode("utf-8")
    ).hexdigest()


def key_digest(base: tuple[Any, ...], donor_policy: tuple[str | None, ...] | None) -> str:
    # A JSON list keeps every field separate, so no two different keys can collide.
    return sha256(canonical([MEMORY_VERSION, *base, donor_policy]).encode("utf-8")).hexdigest()


def preview(
    repo: ProjectRepository,
    *,
    include_translated: bool = False,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan exact-match reuse without writing; the token binds the plan and its inputs."""
    policy = PolicyStore(repo)
    policies = (policy.active_version("glossary"), policy.active_version("style"))
    selected = None
    if profile is not None:
        fingerprint = profile_fingerprint(profile) if isinstance(profile, dict) else None
        if fingerprint is None:
            raise ValueError("The generation profile is invalid.")
        selected = (fingerprint, *policies)
    queued = {
        row[0]
        for row in repo.db.execute(
            "SELECT i.unit_id FROM job_items i JOIN jobs j ON j.id=i.job_id "
            "WHERE i.status IN ('queued','processing') "
            "AND j.status IN ('queued','running','pausing','paused')"
        )
    }
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(
        repo.db.execute(
            "SELECT u.unit_id,u.original_key,u.source_revision,d.descriptor_json,s.source_text,"
            "s.source_hash,s.category,s.context,w.status,w.version,w.translation_revision,"
            "w.approved_source,w.approved_translation,"
            "EXISTS(SELECT 1 FROM editor_drafts e WHERE e.unit_id=u.unit_id) AS has_draft,"
            "EXISTS(SELECT 1 FROM policy_impacts p WHERE p.unit_id=u.unit_id) AS impacted "
            "FROM text_units u JOIN source_revisions s ON s.id=u.source_revision "
            "JOIN work_items w USING(unit_id) "
            "LEFT JOIN source_descriptors d ON d.id=u.logical_source_id "
            "WHERE u.active=1 ORDER BY u.unit_id"
        )
    ):
        if index % 4096 == 0:
            repo.check_cancelled()
        groups[(row["source_hash"], row["source_text"], row["category"], row["context"])].append(
            dict(row)
        )
    # Only exact duplicates can share a key; everything else is never read again.
    candidates = [rows for rows in groups.values() if len(rows) > 1]
    hashes = {row["unit_id"]: row["source_hash"] for rows in candidates for row in rows}
    windows = DialogueContextStore(repo).verified_windows(hashes) if hashes else {}
    keyed: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for rows in candidates:
        for row in rows:
            window = windows.get(row["unit_id"])
            row["format_rules"] = descriptor_format_rules(
                row["descriptor_json"],
                row["original_key"],
            )
            base = (
                row["source_text"],
                row["format_rules"],
                row["category"],
                row["context"],
                repo.target_language,
                dialogue_digest(window) if window is not None else None,
            )
            keyed[base].append(row)
    actions: list[dict[str, Any]] = []
    samples: list[dict[str, str]] = []
    conflict_samples: list[dict[str, Any]] = []
    skipped = dict.fromkeys(SKIP_REASONS, 0)
    donors_used = {"approved": 0, "model": 0}
    matches = conflicts = conflict_records = 0
    for base, rows in sorted(keyed.items(), key=lambda item: item[1][0]["unit_id"]):
        if len(rows) < 2:
            continue
        repo.check_cancelled()
        tiers: dict[str, list[Donor]] = {"approved": [], "model": []}
        for row in rows:
            donor = approved_donor(repo, row) or (
                model_donor(repo, row, selected) if selected is not None else None
            )
            if donor is not None:
                tiers[donor.kind].append(donor)
        donor_units = {d.unit_id for tier in tiers.values() for d in tier}
        if not donor_units:
            continue
        matches += 1
        donors_used["approved"] += len(tiers["approved"])
        donors_used["model"] += len(tiers["model"])
        # Approved donors win over model donors; disagreeing donors block the whole key.
        winning = tiers["approved"] or tiers["model"]
        texts = sorted({d.text for d in winning})
        conflicted = len(texts) > 1
        blocked = 0
        for row in rows:
            if any(d.unit_id == row["unit_id"] for d in tiers["approved"]):
                continue  # An approved donor is never a target.
            counted = row["unit_id"] not in donor_units
            reason = target_blocker(row, queued, include_translated)
            if reason is not None:
                skipped[reason] += counted
                continue
            tier = [d for d in winning if d.unit_id != row["unit_id"]]  # Never its own donor.
            if not tier:
                continue
            if conflicted:
                blocked += 1
                continue
            donor = min(tier, key=lambda d: d.unit_id)
            if current_translation_text(repo, row) == donor.text:
                skipped["same_text"] += counted
                continue
            donor_policy = selected if donor.kind == "model" else None
            metadata = memory_metadata(donor, key_digest(base, donor_policy), selected)
            if row["translation_revision"] is not None and already_offered(
                repo, row, donor.text, metadata
            ):
                skipped["already_offered"] += counted
                continue
            if not donor.text.strip() or format_issues(
                row["source_text"],
                donor.text,
                rules=row["format_rules"],
            ):
                skipped["format"] += counted
                continue
            actions.append(
                {
                    "unit_id": row["unit_id"],
                    "source_revision": row["source_revision"],
                    "version": row["version"],
                    "translation_revision": row["translation_revision"],
                    "mode": "current" if row["translation_revision"] is None else "history",
                    "text": donor.text,
                    "metadata": metadata,
                }
            )
            if len(samples) < MAX_SAMPLES:
                samples.append(
                    {
                        "key": row["original_key"][:200],
                        "source": row["source_text"][:200],
                        "text": donor.text[:200],
                        "donor_key": donor.original_key[:200],
                    }
                )
        if blocked:
            # Reported only where a disagreement withholds a candidate from a record.
            conflicts += 1
            conflict_records += blocked
            if len(conflict_samples) < MAX_SAMPLES:
                conflict_samples.append(
                    {
                        "source": base[0][:200],
                        "texts": [text[:200] for text in texts[:3]],
                    }
                )
    actions.sort(key=lambda action: action["unit_id"])
    summary = {
        "candidates": len(actions),
        "current": sum(action["mode"] == "current" for action in actions),
        "history": sum(action["mode"] == "history" for action in actions),
        "matches": matches,
        "donors": donors_used,
        "conflicts": conflicts,
        "conflict_records": conflict_records,
        "skipped": skipped,
        "include_translated": include_translated,
        "model_donors": selected is not None,
    }
    token = sha256(
        canonical(
            {
                "project_id": repo.project_id,
                "version": MEMORY_VERSION,
                "profile": profile,
                "policies": list(policies),
                "actions": actions,
                "summary": summary,
            }
        ).encode("utf-8")
    ).hexdigest()
    return {
        **summary,
        "samples": samples,
        "conflict_samples": conflict_samples,
        "actions": actions,
        "token": token,
        "profile": profile,
    }


def approved_donor(repo: ProjectRepository, row: dict[str, Any]) -> Donor | None:
    """The human-approved translation of the current source, unless it awaits re-review."""
    if (
        row["status"] != "approved"
        or row["approved_translation"] is None
        or row["approved_source"] != row["source_revision"]
        or row["impacted"]
    ):
        return None
    revision = repo.db.execute(
        "SELECT id,source_revision,text,metadata_json FROM translation_revisions WHERE id=?",
        (row["approved_translation"],),
    ).fetchone()
    if (
        revision is None
        or revision["source_revision"] != row["source_revision"]
        or (is_memory_metadata(json.loads(revision["metadata_json"])))
    ):
        return None
    if format_issues(row["source_text"], revision["text"], rules=row["format_rules"]):
        return None
    return Donor(row["unit_id"], row["original_key"], revision["id"], revision["text"], "approved")


def model_donor(
    repo: ProjectRepository,
    row: dict[str, Any],
    selected: tuple[str, str | None, str | None],
) -> Donor | None:
    """An unapproved, warning-free model translation made with the selected settings."""
    if row["status"] != "translated" or row["translation_revision"] is None or (row["has_draft"]):
        return None
    revision = repo.db.execute(
        "SELECT id,source_revision,text,origin,metadata_json,issues_json "
        "FROM translation_revisions WHERE id=?",
        (row["translation_revision"],),
    ).fetchone()
    if (
        revision is None
        or revision["origin"] != "model"
        or revision["source_revision"] != row["source_revision"]
        or json.loads(revision["issues_json"])
    ):
        return None
    metadata = json.loads(revision["metadata_json"])
    if (
        is_memory_metadata(metadata)
        or (metadata.get("glossary_version"), metadata.get("style_version")) != selected[1:]
    ):
        return None
    run = repo.db.execute(
        "SELECT metadata_json FROM translation_runs WHERE id=?",
        (metadata.get("run_id"),),
    ).fetchone()
    profile = json.loads(run[0]).get("profile") if run is not None else None
    if not isinstance(profile, dict) or profile_fingerprint(profile) != selected[0]:
        return None
    if format_issues(row["source_text"], revision["text"], rules=row["format_rules"]):
        return None
    return Donor(row["unit_id"], row["original_key"], revision["id"], revision["text"], "model")


def target_blocker(
    row: dict[str, Any],
    queued: set[str],
    include_translated: bool,
) -> str | None:
    if row["status"] == "approved" or row["approved_translation"] is not None:
        return "approved"
    if row["has_draft"]:
        return "draft"
    if row["unit_id"] in queued:
        return "queued"
    if row["translation_revision"] is not None and not include_translated:
        return "translated"
    return None


def current_translation_text(repo: ProjectRepository, row: dict[str, Any]) -> str | None:
    if row["translation_revision"] is None:
        return None
    found = repo.db.execute(
        "SELECT text FROM translation_revisions WHERE id=?",
        (row["translation_revision"],),
    ).fetchone()
    return None if found is None else str(found[0])


def already_offered(
    repo: ProjectRepository,
    row: dict[str, Any],
    text: str,
    metadata: dict[str, Any],
) -> bool:
    """True when this exact candidate is already stored for the current source.

    Revision IDs are content addressed over the text, the complete memory provenance,
    the review checks version and the format rules, so only a revision with today's
    donor, key, policies and checks matches. A candidate with older provenance or
    issues computed by older checks is never reused; a fresh one is added instead.
    """
    revision, _ = repo.candidate_identity(
        row["unit_id"], row["source_revision"], text, "import", metadata
    )
    return (
        repo.db.execute(
            "SELECT 1 FROM translation_revisions WHERE id=? AND source_revision=?",
            (revision, row["source_revision"]),
        ).fetchone()
        is not None
    )


def memory_metadata(
    donor: Donor,
    digest: str,
    selected: tuple[str, str | None, str | None] | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "origin_detail": MEMORY_ORIGIN_DETAIL,
        "memory_version": MEMORY_VERSION,
        "key_digest": digest,
        "donor_kind": donor.kind,
        "donor_unit": donor.unit_id,
        "donor_key": donor.original_key,
        "donor_revision": donor.revision,
        "human_approved": False,
    }
    if donor.kind == "model" and selected is not None:
        metadata["donor_profile_fingerprint"] = selected[0]
        metadata["glossary_version"] = selected[1]
        metadata["style_version"] = selected[2]
    return metadata


def apply(
    repo: ProjectRepository,
    frozen: dict[str, Any],
    *,
    user_action: bool,
) -> int:
    """Revalidate the complete preview and add its candidates in one transaction."""
    if user_action is not True:
        raise ValueError("Reusing translation memory requires an explicit user action.")
    with repo.transaction():
        current = preview(
            repo,
            include_translated=frozen["include_translated"],
            profile=frozen["profile"],
        )
        if current["token"] != frozen["token"] or not current["actions"]:
            raise ValueError("Translation memory matches changed. Open the preview again.")
        for action in current["actions"]:
            if action["mode"] == "history":
                repo.add_history_candidate(
                    action["unit_id"],
                    action["source_revision"],
                    action["text"],
                    "import",
                    action["metadata"],
                )
                continue
            # The normal candidate path recomputes issues and status; an identical stored
            # revision (same provenance and checks) is reused by its content address.
            changed = repo.candidate(
                action["unit_id"],
                action["source_revision"],
                action["version"],
                action["text"],
                "import",
                action["metadata"],
                [],
            )
            if not changed:
                raise ValueError("Translation memory matches changed. Open the preview again.")
    return len(current["actions"])
