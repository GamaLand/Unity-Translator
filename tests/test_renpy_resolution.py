"""Disjoint source resolution; audited dialect inspection is tested separately.

These synthetic resolver fixtures inject verified dialect evidence, not engine
code. All real worker/contract paths are covered by the pinned local source QA.
"""

from hashlib import md5
from pathlib import Path

import pytest
from test_renpy_archive import archive
from test_renpy_scripts import approve, fixture

from unitytranslator.discovery import extract_to_project, probe_source
from unitytranslator.filesystem import hash_file
from unitytranslator.renpy_export import export_native
from unitytranslator.renpy_python import PYTHON_BLOCKS_V2, source_order
from unitytranslator.repository import ProjectRepository
from unitytranslator.workers.renpy_script_probe import probe


@pytest.fixture
def verified_resolver(monkeypatch):
    def evidence(*args, **kwargs):
        return {"family": "renpy-symbolic-source-v1", "evidence_kind": "audited_source_contracts",
                "fingerprints": {}, "contracts": {}, "reserved_attributes": [],
                "python_source": PYTHON_BLOCKS_V2}

    def worker(command, **kwargs):
        args = command[3:-1]  # Fixed Python module invocation and stream-report flag.
        return probe(Path(args[0]), args[1], args[2],
                     anchor=args[4] if args[3:4] == ["--anchor"] else None)

    monkeypatch.setattr(
        "unitytranslator.workers.renpy_script_probe.inspect_source_dialect", evidence,
    )
    monkeypatch.setattr("unitytranslator.worker_process.run_json_worker", worker)


def paired(name, raw):
    compiled = b"RENPY RPC2" + b"\0" * 36 + md5(raw, usedforsecurity=False).digest()
    return {name: raw, source_order(name) + ".rpyc": compiled}


def test_disjoint_archives_and_loose_sources_preserve_existing_identity(
    tmp_path, verified_resolver,
):
    paths, source = fixture(tmp_path, 'label loose:\n    e "Existing."\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        old = approve(repo, "Existing.", "Mevcut.")
    first = archive(paths.game / "game/a.rpa", paired(
        "archive_a.rpy", b'label archive_a:\n    e "Archive A."\n',
    ))
    second = archive(paths.game / "game/b.rpa", paired(
        "archive_b.rpy", b'label archive_b:\n    e "Archive B."\n',
    ))
    before = {path: hash_file(path) for path in (source, first, second)}
    extract_to_project(paths, "game/b.rpa")
    report = probe_source(paths, "game/a.rpa")
    assert report["source_resolution"] == "disjoint-basename-union-v1"
    assert {unit["source_text"] for unit in report["units"]} == {
        "Existing.", "Archive A.", "Archive B.",
    }
    assert len(report["paired_source_evidence"]) == 2
    assert {m["container"] for m in report["payloads"][0]["original_members"]} == {
        "game/script.rpy", "game/a.rpa", "game/b.rpa",
    }
    with ProjectRepository(paths) as repo:
        current = next(row for row in repo.page() if row["unit_id"] == old["unit_id"])
        assert current == old
        assert len(repo.page()) == 3
        assert repo.db.execute("SELECT source_file FROM source_descriptors").fetchone()[0] == (
            "game/script.rpy"
        )
        assert export_native(repo, "turkish")["approved_translations"] == 1
    assert before == {path: hash_file(path) for path in before}


def test_archive_overlaps_refuse_instead_of_guessing_precedence(tmp_path, verified_resolver):
    paths, _ = fixture(tmp_path, 'label loose:\n    e "Existing."\n')
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        old = approve(repo, "Existing.", "Mevcut.")
    for name in ("a.rpa", "b.rpa"):
        archive(paths.game / "game" / name, paired(
            "same.rpy", b'label same:\n    e "Ambiguous source."\n',
        ))
    with pytest.raises(ValueError, match="Overlapping"):
        extract_to_project(paths, "game/a.rpa")
    with ProjectRepository(paths) as repo:
        assert repo.page() == [old]


def test_loose_and_archived_source_basename_conflicts_are_not_overrides(
    tmp_path, verified_resolver,
):
    paths, _ = fixture(tmp_path)
    archive(paths.game / "game/a.rpa", paired(
        "same.rpy", b'label same:\n    e "Archive."\n',
    ))
    (paths.game / "game/same_ren.py").write_text(
        '"""renpy\nlabel loose:\n    e "Loose."\n"""\n'
    )
    with pytest.raises(ValueError, match="Conflicting"):
        probe_source(paths, "game/a.rpa")


def test_archived_python_source_requires_its_matching_compiled_basename(
    tmp_path, verified_resolver,
):
    paths, _ = fixture(tmp_path)
    raw = b'"""renpy\nlabel archived_python:\n    e "Static Python source."\n"""\n'
    path = archive(paths.game / "game/a.rpa", paired("other_ren.py", raw))
    before = hash_file(path)
    report = probe_source(paths, "game/a.rpa")
    assert any(row["source_text"] == "Static Python source." for row in report["units"])
    assert report["paired_source_evidence"][0]["compiled"] == "other.rpyc"
    assert hash_file(path) == before
    archive(path, {"other_ren.py": raw})
    with pytest.raises(ValueError, match="missing"):
        probe_source(paths, "game/a.rpa")


def test_compiled_only_omissions_remain_visible_in_otherwise_readable_layout(tmp_path):
    paths, _ = fixture(tmp_path)
    (paths.game / "game/compiled_only.rpyc").write_bytes(b"Not deserialized")
    report = probe_source(paths, "game/script.rpy")
    assert "game/compiled_only.rpyc" in report["excluded_files"]
