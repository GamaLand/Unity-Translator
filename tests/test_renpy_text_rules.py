"""renpy-text-v2 defaults, explicit upgrade and rule continuity; synthetic sources only."""

import json

import pytest
from test_jobs import profile
from test_renpy_scripts import approve, fixture

from unitytranslator.discovery import extract_to_project
from unitytranslator.jobs import JobStore
from unitytranslator.repository import ProjectRepository

SOURCE = '''label start:
    e "Hello [name!q]. 100% sure."
    $ day = _("Day %d of %(total)s")
    $ start = _("Start")
'''


def rows(repo: ProjectRepository) -> dict[str, dict]:
    return {row["source_text"]: row for row in repo.page()}


def descriptor_rules(repo: ProjectRepository) -> set[str]:
    return {
        json.loads(row[0])["format_rules"]
        for row in repo.db.execute("SELECT descriptor_json FROM source_descriptors")
    }


def test_new_projects_start_with_string_printf_protection(tmp_path) -> None:
    paths, _ = fixture(tmp_path, SOURCE)
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        assert descriptor_rules(repo) == {"renpy-text-v2"}
        current = rows(repo)
        assert repo.format_rules(current["Hello [name!q]. 100% sure."]["unit_id"]) == (
            "renpy-text-v1"
        )
        key = current["Day %d of %(total)s"]
        assert repo.format_rules(key["unit_id"]) == "renpy-text-v2"
        with pytest.raises(ValueError):
            repo.edit(key["unit_id"], key["version"], "Gün")


def v1_project(tmp_path):
    paths, path = fixture(tmp_path, SOURCE)
    extract_to_project(paths, "game/script.rpy", format_rules="renpy-text-v1")
    with ProjectRepository(paths) as repo:
        approve(repo, "Hello [name!q]. 100% sure.", "Merhaba [name!q]. %100 eminim.")
        approve(repo, "Day %d of %(total)s", "Gün")  # Lossy, but valid under v1.
        approve(repo, "Start", "Başla")
    return paths, path


def test_explicit_upgrade_invalidates_only_failing_string_approvals(tmp_path) -> None:
    paths, _ = v1_project(tmp_path)
    with ProjectRepository(paths) as repo:
        before = rows(repo)
        pilot_identity = JobStore(repo).fingerprint()
    extract_to_project(paths, "game/script.rpy")  # A plain re-extraction keeps v1.
    with ProjectRepository(paths) as repo:
        assert descriptor_rules(repo) == {"renpy-text-v1"}
        assert rows(repo) == before
        assert JobStore(repo).fingerprint() == pilot_identity
    extract_to_project(paths, "game/script.rpy", format_rules="renpy-text-v2")
    with ProjectRepository(paths) as repo:
        assert descriptor_rules(repo) == {"renpy-text-v2"}
        after = rows(repo)
        assert {k: r["unit_id"] for k, r in after.items()} == {
            k: r["unit_id"] for k, r in before.items()
        }
        for kept in ("Hello [name!q]. 100% sure.", "Start"):
            assert after[kept]["status"] == "approved"
            assert after[kept]["version"] == before[kept]["version"]
        lossy = after["Day %d of %(total)s"]
        assert lossy["status"] == "needs_review"
        assert lossy["version"] == before["Day %d of %(total)s"]["version"] + 1
        assert lossy["translation_revision"] == before["Day %d of %(total)s"][
            "translation_revision"
        ]
        with pytest.raises(ValueError, match="protected format"):
            repo.approve(lossy["unit_id"], lossy["version"])
        snapshots = repo.db.execute("SELECT metadata_json FROM source_snapshots")
        record = [
            json.loads(row[0]) for row in snapshots
            if json.loads(row[0]).get("kind") == "format_rules_upgrade"
        ]
        assert len(record) == 1
        assert record[0]["invalidated_units"] == [lossy["unit_id"]]
        assert record[0]["invalidated_approvals"] == 1
        # A rule upgrade changes the pilot identity, so bulk work needs a new pilot.
        assert JobStore(repo).fingerprint() != pilot_identity


def test_downgrade_and_non_renpy_rules_are_refused(tmp_path) -> None:
    paths, _ = fixture(tmp_path, SOURCE)
    extract_to_project(paths, "game/script.rpy")
    with pytest.raises(ValueError, match="downgraded"):
        extract_to_project(paths, "game/script.rpy", format_rules="renpy-text-v1")
    with pytest.raises(ValueError, match="only be selected"):
        extract_to_project(paths, "game/script.rpy", format_rules="protected-i2-v4")


def test_upgrade_is_refused_while_a_job_is_queued(tmp_path) -> None:
    paths, _ = fixture(tmp_path, SOURCE)
    extract_to_project(paths, "game/script.rpy", format_rules="renpy-text-v1")
    with ProjectRepository(paths) as repo:
        JobStore(repo).create([r["unit_id"] for r in repo.page()], profile(), kind="pilot")
        before = list(repo.db.iterdump())
    with pytest.raises(ValueError, match="before upgrading"):
        extract_to_project(paths, "game/script.rpy", format_rules="renpy-text-v2")
    with ProjectRepository(paths) as repo:
        assert descriptor_rules(repo) == {"renpy-text-v1"}
        # Only the new snapshot row from the refused attempt could differ; none was written.
        assert list(repo.db.iterdump()) == before


def test_upgrade_also_invalidates_failing_retired_string_approvals(tmp_path) -> None:
    paths, path = v1_project(tmp_path)
    path.write_text(SOURCE.replace('    $ day = _("Day %d of %(total)s")\n', ""),
                    encoding="utf-8")
    extract_to_project(paths, "game/script.rpy")
    extract_to_project(paths, "game/script.rpy", format_rules="renpy-text-v2")
    path.write_text(SOURCE, encoding="utf-8")
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        restored = rows(repo)["Day %d of %(total)s"]
        assert restored["status"] == "needs_review"
        assert rows(repo)["Start"]["status"] == "approved"


def test_portable_archive_with_mixed_renpy_rules_is_refused(tmp_path) -> None:
    from unitytranslator.portable import PortableService

    paths, _ = fixture(tmp_path, SOURCE)
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        archive = json.loads(PortableService(repo).export().read_bytes())
    extra = dict(archive["source_descriptors"][0])
    extra.update(logical_id="renpy-script-8.1.2-v1:game/other.rpy", source_file="game/other.rpy",
                 format_rules="renpy-text-v1")
    archive["source_descriptors"].append(extra)
    target = tmp_path / "mixed.json"
    target.write_text(json.dumps(archive), encoding="utf-8")
    other = tmp_path / "other"
    other_paths, _ = fixture(other, SOURCE)
    with ProjectRepository(other_paths) as repo, pytest.raises(ValueError, match="one text rule"):
        PortableService(repo).read(target)
