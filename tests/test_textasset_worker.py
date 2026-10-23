"""Bounded IPC, profile selection and partial-reader rejection with synthetic inputs."""

import sys
import threading
import time

import pytest

from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.krypta_profile import load_profile, verify_profile_evidence
from unitytranslator.worker_process import run_json_worker


def test_worker_json_and_invalid_results():
    value = run_json_worker(
        [sys.executable, "-c", "print('{\"ok\": true}')"],
        timeout=3,
        cancelled=lambda: False,
    )
    assert value == {"ok": True}
    with pytest.raises(ValueError, match="invalid result"):
        run_json_worker([sys.executable, "-c", "print('[]')"], timeout=3, cancelled=lambda: False)
    with pytest.raises(ValueError, match="IPC"):
        run_json_worker(
            [sys.executable, "-c", "print('x'*10000)"],
            timeout=3,
            cancelled=lambda: False,
            max_output=100,
        )


def test_worker_cancellation_and_timeout_terminate_the_live_child():
    event = threading.Event()
    timer = threading.Timer(0.15, event.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(ValueError, match="cancelled"):
            run_json_worker(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout=3,
                cancelled=event.is_set,
            )
    finally:
        timer.cancel()
    assert time.monotonic() - started < 3
    with pytest.raises(ValueError, match="time limit"):
        run_json_worker(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            timeout=0.1,
            cancelled=lambda: False,
        )


def test_profile_is_data_with_reviewed_locale_evidence_and_explicit_exclusions():
    profile = load_profile()
    assert profile["assembly"]["path"].endswith("Managed/Assembly-CSharp.dll")
    assert len(profile["sources"]) == 36
    assert len([s for s in profile["sources"] if s.get("excluded_reason")]) == 2
    for source in profile["sources"]:
        assert source["references"]
        assert all(
            reference["field"].endswith("ENG") or reference["field"] == "textAssetEng"
            for reference in source["references"]
        )
        assert set(source) <= {
            "container",
            "object",
            "name",
            "schema",
            "locale",
            "references",
            "excluded_reason",
            "excluded_payload_sha256",
        }


def test_game_build_fingerprint_mismatch_and_unsafe_evidence_fail_closed(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    source = game / "assembly.dll"
    source.write_bytes(b"synthetic metadata")
    profile = {
        "assembly": {"path": "assembly.dll", "sha256": hash_file(source)},
        "reference_files": [{"path": "assembly.dll", "sha256": "0" * 64}],
    }
    with pytest.raises(ValueError, match="fingerprints"):
        verify_profile_evidence(game, profile)
    profile["reference_files"][0]["path"] = "../external"
    with pytest.raises(ValueError, match="relative"):
        verify_profile_evidence(game, profile)


def test_shared_discovery_uses_profile_reader_instead_of_scene_guessing(tmp_path, monkeypatch):
    from unitytranslator.discovery import probe_source
    from unitytranslator.reader_adapters import KryptaTextAssetReader
    from unitytranslator.source_contracts import ReaderProbe

    game = tmp_path / "game"
    data = game / "Synthetic_Data"
    data.mkdir(parents=True)
    (data / "app.info").write_text("Under The Sink\nKryptaFM\n", encoding="utf8")
    (data / "level0").write_bytes(b"synthetic scene")
    called = []

    def inspect(self, context, relative):
        called.append((context.source_language, relative))
        return ReaderProbe((), (), {"adapter_id": "krypta-textassets"})

    monkeypatch.setattr(KryptaTextAssetReader, "probe", inspect)
    report = probe_source(ProjectPaths(game, tmp_path / "project"), "Synthetic_Data/level0")
    assert report["adapter_id"] == "krypta-textassets"
    assert called == [("en", "Synthetic_Data/level0")]


def test_partial_textasset_worker_cannot_activate_an_incomplete_source_set(tmp_path, monkeypatch):
    from unitytranslator.reader_adapters import KryptaTextAssetReader
    from unitytranslator.source_contracts import ReaderContext

    profile = load_profile()
    evidence_paths = (
        {profile["assembly"]["path"]}
        | {item["path"] for item in profile["reference_files"]}
        | {item["container"] for item in profile["sources"]}
    )
    game = tmp_path / "game"
    fingerprints = {}
    for relative in evidence_paths:
        path = game / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic evidence")
        fingerprints[relative] = hash_file(path)
    partial = {
        "extraction": "supported",
        "errors": [],
        "fingerprints": fingerprints,
        "units": [],
        "source_descriptors": [],
    }
    monkeypatch.setattr("unitytranslator.worker_process.run_json_worker", lambda *a, **k: partial)
    with pytest.raises(ValueError):
        KryptaTextAssetReader().probe(ReaderContext(game, tmp_path / "project", "en"), "level0")
