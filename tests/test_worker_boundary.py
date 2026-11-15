"""Reader worker boundary: bounded failures, I2 IPC, digest results and RPA index reuse.

Synthetic inputs only; no game is started and no worker receives game code.
"""

import os
import pickle
import sys
import zlib

import pytest
from test_renpy_archive import archive
from test_renpy_scripts import fixture

from unitytranslator import renpy_archive
from unitytranslator.discovery import _probe_i2_source
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.reader_adapters import I2Reader, RenpyScriptReader
from unitytranslator.renpy_archive import read_index
from unitytranslator.source_contracts import ReaderContext
from unitytranslator.worker_process import SUMMARY_CHARACTERS, run_json_worker
from unitytranslator.workers.renpy_script_probe import (
    DIGEST_COUNTS,
    digest_summary,
    probe,
    valid_digest_summary,
)


def failure(code: str) -> str:
    with pytest.raises(ValueError, match="Source worker failed") as caught:
        run_json_worker([sys.executable, "-c", code], timeout=10, cancelled=lambda: False)
    return str(caught.value)


def test_failure_reports_the_fatal_record_and_last_stderr_line():
    message = failure(
        "import json,sys; sys.stderr.write('Traceback\\n  line\\nKeyError: missing\\n'); "
        "print(json.dumps({'fatal': 'KeyError', 'message': 'missing'})); sys.exit(3)"
    )
    assert message == "Source worker failed (3): KeyError: missing; stderr: KeyError: missing"


def test_failure_summary_is_bounded_and_printable():
    message = failure(
        "import sys; sys.stderr.write('x' * 20000 + '\\x1b[31m\\x00' + 'y' * 5000); "
        "print('not json \\x07' + 'z' * 9000); sys.exit(2)"
    )
    assert "\x1b" not in message and "\x00" not in message and "\x07" not in message
    output, stderr = message.split(": ", 1)[1].split("; ")
    assert output.startswith("output: not json")
    assert len(output) <= len("output: ") + SUMMARY_CHARACTERS
    assert stderr.startswith("stderr: ") and stderr.endswith("...")
    assert len(stderr) <= len("stderr: ") + SUMMARY_CHARACTERS
    assert failure("import sys; sys.exit(4)").endswith("(4): no diagnostic output")


def test_fatal_records_with_lone_surrogates_or_long_escaped_text_are_summarized():
    message = failure(
        "import json,sys; print(json.dumps({'fatal': 'OSError', "
        "'message': 'bad ' + chr(0xDC80) + ' name'})); sys.exit(5)"
    )
    assert message == "Source worker failed (5): OSError: bad name"
    message = failure(
        "import json,sys; print(json.dumps({'fatal': 'ValueError', "
        "'message': chr(0x6E90) * 1024})); sys.exit(6)"
    )
    assert message.startswith("Source worker failed (6): ValueError: " + chr(0x6E90) * 2)
    assert message.endswith("...") and "output:" not in message
    message = failure(
        "import json,sys; print('library warning'); "
        "print(json.dumps({'fatal': 'KeyError', 'message': 'real cause'})); sys.exit(7)"
    )
    assert message == "Source worker failed (7): KeyError: real cause"


def test_deeply_nested_worker_json_is_a_value_error():
    with pytest.raises(ValueError, match="nesting"):
        run_json_worker([sys.executable, "-c", "print('[' * 20000)"], timeout=10,
                        cancelled=lambda: False)


@pytest.mark.parametrize("entry", [
    ["-m", "unitytranslator.workers.unity_probe"],
    ["-c", "import sys; sys.argv = ['unitytranslator', '--unity-worker']; "
           "from unitytranslator.ui.entry import entry; raise SystemExit(entry())"],
])
def test_unity_worker_fatal_records_carry_a_bounded_message(entry):
    with pytest.raises(ValueError, match=r"Source worker failed \(1\): \w+Error: \S"):
        run_json_worker([sys.executable, *entry], timeout=60, cancelled=lambda: False)


def i2_paths(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "synthetic.assets").write_bytes(b"synthetic asset; never executed")
    return ProjectPaths(game, tmp_path / "project")


def test_i2_uses_the_shared_worker_with_cancellation_and_timeout(tmp_path, monkeypatch):
    paths = i2_paths(tmp_path)
    calls = []

    def worker(command, *, timeout, cancelled, max_output):
        assert max_output == 32 * 1024 * 1024
        calls.append((command[-4:], timeout))
        if cancelled():
            raise ValueError("Source extraction was cancelled.")
        return {"units": [], "errors": [], "diagnostics": []}

    monkeypatch.setattr("unitytranslator.worker_process.run_json_worker", worker)
    context = ReaderContext(paths.game, paths.project, "fr", 9)
    report = I2Reader().probe(context, "synthetic.assets").report
    assert report["extraction"] == "unknown"
    assert calls == [([str(paths.game / "synthetic.assets"), "synthetic.assets",
                       str(paths.game), "fr"], 9)]
    checks = []

    def cancellation():  # Cancelled once the worker is running, not before.
        checks.append(1)
        return len(checks) > 1

    with pytest.raises(ValueError, match="cancelled"):
        I2Reader().extract(context, "synthetic.assets", cancellation)
    assert len(calls) == 2


UNIT = {
    "unit_id": "i2:1", "original_key": "Menu/Start", "source_file": "synthetic.assets",
    "source_object": 7, "source_language": "en", "source_text": "Start",
    "source_hash": "0" * 64,
}


def test_i2_complete_units_are_accepted(tmp_path, monkeypatch):
    paths = i2_paths(tmp_path)
    result = {"units": [{**UNIT, "category": "ui", "context": ""}], "errors": []}
    monkeypatch.setattr("unitytranslator.worker_process.run_json_worker", lambda *a, **k: result)
    assert _probe_i2_source(paths, "synthetic.assets")["extraction"] == "supported"


@pytest.mark.parametrize("result", [
    {"units": {}, "errors": []},
    {"units": [], "errors": None},
    {"units": [[]], "errors": []},
    {"units": [{"unit_id": 1, "source_text": "x"}], "errors": []},
    {"units": [{**UNIT, "source_object": True}], "errors": []},
    {"units": [{k: v for k, v in UNIT.items() if k != "source_hash"}], "errors": []},
    {"units": [{**UNIT, "command": "run"}], "errors": []},
    {"units": [{**UNIT, "context": None}], "errors": []},
    {"units": [{**UNIT, "source_object": 2 ** 70}], "errors": []},
    {"units": [], "errors": [], "engine_report": "x"},
    {"units": [], "errors": [], "payloads": [1]},
    {"units": [], "errors": [], "adapter_id": "renpy-scripts"},
    {"units": [], "errors": [], "objects": {"TextAsset": "1"}},
    {"units": [], "errors": [], "unity_versions": [1]},
    {"units": [], "errors": [], "i2_candidates": [1]},
    {"units": [], "errors": ["x"]},
    {"units": [], "errors": [], "diagnostics": [{"code": None}]},
])
def test_i2_rejects_malformed_worker_results(tmp_path, monkeypatch, result):
    paths = i2_paths(tmp_path)
    monkeypatch.setattr("unitytranslator.worker_process.run_json_worker", lambda *a, **k: result)
    with pytest.raises(ValueError, match="invalid result"):
        _probe_i2_source(paths, "synthetic.assets")


def test_i2_worker_output_is_strict_json(tmp_path, monkeypatch):
    paths = i2_paths(tmp_path)
    duplicate = "print('{\"units\": [], \"units\": [], \"errors\": []}')"
    monkeypatch.setattr(
        "unitytranslator.worker_process.run_json_worker",
        lambda command, **kwargs: run_json_worker([sys.executable, "-c", duplicate], **kwargs),
    )
    with pytest.raises(ValueError, match="JSON"):
        _probe_i2_source(paths, "synthetic.assets")


def test_script_worker_returns_only_a_digest_and_counts(tmp_path, monkeypatch):
    from unitytranslator import worker_process

    paths, _ = fixture(tmp_path)
    real = worker_process.run_json_worker
    received = []

    def recording(command, **kwargs):
        assert command[-1] == "--digest-report" and kwargs["max_output"] <= 64 * 1024
        value = real(command, **kwargs)
        received.append(value)
        return value

    monkeypatch.setattr("unitytranslator.worker_process.run_json_worker", recording)
    report = RenpyScriptReader().probe(
        ReaderContext(paths.game, paths.project, "en"), "game/script.rpy",
    ).report
    assert valid_digest_summary(received[0])
    assert set(received[0]) == {"protocol", "report_sha256", "counts"}
    assert received[0]["counts"]["records"] == len(report["units"]) > 0


@pytest.mark.parametrize("change", [
    lambda s: s.update(report_sha256="A" * 64),
    lambda s: s.update(protocol="reader-report-v1"),
    lambda s: s.update(extra=1),
    lambda s: s["counts"].update(records=True),
    lambda s: s["counts"].update(records=-1),
    lambda s: s["counts"].pop("members"),
])
def test_invalid_digest_results_are_refused(tmp_path, monkeypatch, change):
    paths, _ = fixture(tmp_path)
    summary = digest_summary(probe(paths.game, "game/script.rpy", "en"))
    assert valid_digest_summary(summary) and tuple(summary["counts"]) == DIGEST_COUNTS
    change(summary)
    monkeypatch.setattr("unitytranslator.worker_process.run_json_worker", lambda *a, **k: summary)
    with pytest.raises(ValueError, match="invalid digest"):
        RenpyScriptReader().probe(
            ReaderContext(paths.game, paths.project, "en"), "game/script.rpy",
        )


def test_count_mismatch_names_both_record_counts(tmp_path, monkeypatch):
    paths, _ = fixture(tmp_path)
    summary = digest_summary(probe(paths.game, "game/script.rpy", "en"))
    local = summary["counts"]["records"]
    summary["counts"]["records"] = local + 1
    monkeypatch.setattr("unitytranslator.worker_process.run_json_worker", lambda *a, **k: summary)
    with pytest.raises(ValueError, match=f"worker {local + 1} records, local {local}"):
        RenpyScriptReader().probe(
            ReaderContext(paths.game, paths.project, "en"), "game/script.rpy",
        )


@pytest.fixture
def parses(monkeypatch):
    count = []
    real = renpy_archive.literal_index

    def counting(raw):
        count.append(1)
        return real(raw)

    monkeypatch.setattr("unitytranslator.renpy_archive.literal_index", counting)
    return count


def members(count=40):
    return {f"script{i:03}.rpy": f'label l{i}:\n    "Line {i}."\n'.encode() for i in range(count)}


def test_index_is_parsed_once_per_archive_identity(tmp_path, parses):
    path = archive(tmp_path / "synthetic.rpa", members())
    index = read_index(path)
    for name, raw in members().items():
        assert index.read_member(name) == raw
    assert read_index(path) is index
    assert len(parses) == 1


def rewrite_index_keeping_size_and_time(path, rename):
    """Change only index bytes; size and modification time stay identical."""
    status = path.stat()
    raw = path.read_bytes()
    offset = int(raw[8:24], 16)
    index = pickle.loads(zlib.decompress(raw[offset:]))  # Our own synthetic test index.
    changed = zlib.compress(pickle.dumps(
        {rename(name): value for name, value in index.items()}, protocol=4,
    ))
    assert len(changed) == len(raw) - offset
    path.write_bytes(raw[:offset] + changed)
    os.utime(path, ns=(status.st_atime_ns, status.st_mtime_ns))
    assert (path.stat().st_size, path.stat().st_mtime_ns) == (status.st_size, status.st_mtime_ns)


def test_index_region_change_with_same_size_and_time_is_detected(tmp_path, parses):
    path = archive(tmp_path / "synthetic.rpa", members(3))
    index = read_index(path)
    rewrite_index_keeping_size_and_time(path, lambda name: name.replace("script", "scrapt"))
    with pytest.raises(ValueError, match="index changed"):
        index.read_member("script000.rpy")
    fresh = read_index(path)
    assert fresh is not index and {m.name for m in fresh.members} == {
        "scrapt000.rpy", "scrapt001.rpy", "scrapt002.rpy",
    }
    assert len(parses) == 2


def test_replaced_archive_is_parsed_again_and_old_index_refuses_reads(tmp_path, parses):
    path = archive(tmp_path / "synthetic.rpa", members(2))
    index = read_index(path)
    archive(path, {"other.rpy": b"label other:\n    \"Other.\"\n"})
    with pytest.raises(ValueError, match="changed"):
        index.read_member("script000.rpy")
    assert [m.name for m in read_index(path).members] == ["other.rpy"]
    assert len(parses) == 2


def test_cache_is_bounded(tmp_path, monkeypatch, parses):
    monkeypatch.setattr("unitytranslator.renpy_archive.INDEX_CACHE_SIZE", 2)
    paths = [archive(tmp_path / f"a{i}.rpa", members(1)) for i in range(3)]
    for path in paths:
        read_index(path)
    read_index(paths[0])
    assert len(parses) == 4
    assert len(renpy_archive._CACHE) <= 2


def test_mtime_only_change_keeps_reading_the_same_index(tmp_path, parses):
    path = archive(tmp_path / "synthetic.rpa", members(2))
    index = read_index(path)
    status = path.stat()
    os.utime(path, ns=(status.st_atime_ns, status.st_mtime_ns + 10**9))
    assert index.read_member("script001.rpy") == members(2)["script001.rpy"]
    assert read_index(path).index_sha256 == index.index_sha256
    assert sum(key[0] == str(index.path) for key in renpy_archive._CACHE) == 1


def test_cache_holds_a_whole_probe_but_is_bounded_by_members(tmp_path, monkeypatch, parses):
    paths = [archive(tmp_path / f"many{i}.rpa", members(1)) for i in range(12)]
    for _ in range(2):
        for path in paths:
            read_index(path)
    assert len(parses) == 12
    monkeypatch.setattr("unitytranslator.renpy_archive.INDEX_CACHE_MEMBERS", 3)
    big = archive(tmp_path / "big.rpa", members(5))
    read_index(big)
    assert list(renpy_archive._CACHE.values())[-1].path == big.resolve()
    assert len(renpy_archive._CACHE) == 1


def test_legacy_stream_report_worker_mode_matches_the_digest(tmp_path):
    from unitytranslator.report_stream import MAX_REPORT_BYTES, report_digest

    paths, _ = fixture(tmp_path)
    command = [sys.executable, "-m", "unitytranslator.workers.renpy_script_probe",
               str(paths.game), "game/script.rpy", "en"]
    streamed = run_json_worker([*command, "--stream-report"], timeout=60,
                               cancelled=lambda: False, max_output=MAX_REPORT_BYTES,
                               stream_report=True)
    summary = run_json_worker([*command, "--digest-report"], timeout=60,
                              cancelled=lambda: False)
    assert report_digest(streamed) == summary["report_sha256"]
    assert summary == digest_summary(probe(paths.game, "game/script.rpy", "en"))
