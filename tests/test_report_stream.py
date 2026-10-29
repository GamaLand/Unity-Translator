"""Synthetic framed reports: bounded transfer, ordering, tampering and cancellation."""

import io
import json
import sys
from hashlib import sha256

import pytest

from unitytranslator.report_stream import (
    MAX_FRAME_BYTES,
    PROTOCOL,
    read_report,
    report_digest,
    write_report,
)
from unitytranslator.worker_process import run_json_worker


def encoded(value):
    stream = io.StringIO()
    write_report(value, stream)
    return stream.getvalue().encode("ascii")


def frames(events):
    content = b"".join((json.dumps(event, separators=(",", ":")) + "\n").encode()
                       for event in [{"event": "begin", "protocol": PROTOCOL}, *events])
    return content + (json.dumps({"event": "end", "frames": len(events),
                                  "sha256": sha256(content).hexdigest()}) + "\n").encode()


def test_large_nested_report_roundtrip_preserves_unicode_and_exact_data():
    value = {"units": [{"id": i, "text": "Merhaba \U0001f600 [name]" * 40}
                       for i in range(500)],
             "payloads": [{"members": [{"raw": "a" * 350000}]}], "complete": True}
    raw = encoded(value)
    assert len(raw) > MAX_FRAME_BYTES
    assert max(map(len, raw.splitlines(keepends=True))) <= MAX_FRAME_BYTES
    assert read_report(io.BytesIO(raw), cancelled=lambda: False) == value
    assert read_report(io.BytesIO(raw.replace(b"\n", b"\r\n")),
                       cancelled=lambda: False) == value
    assert report_digest(value) == report_digest(dict(reversed(list(value.items()))))


@pytest.mark.parametrize("events", [
    [{"event": "dict", "path": []},
     {"event": "value", "path": ["key"], "value": 1},
     {"event": "value", "path": ["key"], "value": 2}],
    [{"event": "list", "path": []}, {"event": "value", "path": [1], "value": 1}],
    [{"event": "dict", "path": []}, {"event": "value", "path": ["absent", 0], "value": 1}],
    [{"event": "value", "path": [], "value": []}],
    [{"event": "dict", "path": []}, {"event": "value", "path": [-1], "value": 1}],
    [{"event": "dict", "path": []}, {"event": "string", "path": ["key"]},
     {"event": "value", "path": ["other"], "value": 1}],
    [{"event": "dict", "path": []}, {"event": "string", "path": ["key"]}],
    [{"event": "dict", "path": []},
     {"event": "value", "path": ["key"], "value": 1, "unexpected": True}],
])
def test_duplicate_missing_out_of_order_and_unfinished_paths_are_refused(events):
    with pytest.raises(ValueError):
        read_report(io.BytesIO(frames(events)), cancelled=lambda: False)


@pytest.mark.parametrize("alter", [
    lambda raw: raw[:-5], lambda raw: raw + b"extra", lambda raw: raw.replace(b'"ok"', b'"no"'),
    lambda raw: raw.replace(b'"frames":1', b'"frames":true'),
])
def test_truncated_trailing_changed_or_wrongly_typed_reports_are_refused(alter):
    with pytest.raises(ValueError):
        read_report(io.BytesIO(alter(encoded({"ok": True}))), cancelled=lambda: False)


def test_report_frame_total_string_node_and_depth_budgets(monkeypatch):
    raw = encoded({"value": "a" * 300000})
    with pytest.raises(ValueError, match="oversized"):
        read_report(io.BytesIO(raw), cancelled=lambda: False, max_bytes=500)
    with pytest.raises(ValueError, match="oversized"):
        read_report(io.BytesIO(b"x" * (MAX_FRAME_BYTES + 1)), cancelled=lambda: False)
    monkeypatch.setattr("unitytranslator.report_stream.MAX_STRING_BYTES", 100)
    with pytest.raises(ValueError, match="string limit"):
        read_report(io.BytesIO(raw), cancelled=lambda: False)
    monkeypatch.setattr("unitytranslator.report_stream.MAX_NODES", 2)
    with pytest.raises(ValueError, match="node"):
        read_report(io.BytesIO(encoded({"a": [1, 2, 3]})), cancelled=lambda: False)
    monkeypatch.setattr("unitytranslator.report_stream.MAX_NODES", 1000)
    monkeypatch.setattr("unitytranslator.report_stream.MAX_DEPTH", 2)
    with pytest.raises(ValueError, match="nesting"):
        read_report(io.BytesIO(frames([
            {"event": "value", "path": [], "value": {"a": {"b": {"c": 1}}}},
        ])), cancelled=lambda: False)


def test_cancelled_report_never_returns_partial_data():
    with pytest.raises(ValueError, match="cancelled"):
        read_report(io.BytesIO(encoded({"ok": True})), cancelled=lambda: True)


def test_stream_protocol_is_explicit_and_legacy_worker_contract_stays_available():
    command = [sys.executable, "-c", (
        "import sys; from unitytranslator.report_stream import write_report; "
        "write_report({'ok':True}, sys.stdout)"
    )]
    assert run_json_worker(command, timeout=5, cancelled=lambda: False,
                           stream_report=True) == {"ok": True}
    with pytest.raises(ValueError, match="protocol"):
        run_json_worker([sys.executable, "-c", "print('{\"ok\":true}')"], timeout=5,
                        cancelled=lambda: False, stream_report=True)
