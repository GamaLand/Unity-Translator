"""Synthetic RPA indexes only; never deserialize a game object or import game code."""

import pickle
import zlib

import pytest

from unitytranslator.renpy_archive import inspect_archive, literal_index, read_index


def archive(path, members=None, *, encoded_index=None):
    members = members or {"screens/menu.rpy": b'screen menu():\n    textbutton _("Start")\n'}
    key = 0x42424242
    data, index = b"", {}
    for name, content in members.items():
        index[name] = [(34 + len(data) ^ key, len(content) ^ key, b"")]
        data += content
    encoded = pickle.dumps(index, protocol=4) if encoded_index is None else encoded_index
    header = f"RPA-3.0 {34 + len(data):016x} {key:08x}\n".encode()
    assert len(header) == 34
    path.write_bytes(header + data + zlib.compress(encoded))
    return path


def test_literal_rpa_index_and_member_read_do_not_write_or_execute_sources(tmp_path):
    path = archive(tmp_path / "synthetic.rpa")
    before = path.read_bytes()
    index = read_index(path)
    assert len(index.members) == 1
    assert index.read_member("screens/menu.rpy").startswith(b"screen menu():")
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_python_dialect_members_are_reported_separately_from_plain_python(tmp_path):
    path = archive(tmp_path / "synthetic.rpa", {
        "scripts/dialogue_ren.py": b'raise RuntimeError("NEVER EXECUTE")',
        "scripts/ordinary.py": b'_("Not an input")',
        "script.rpy": b'label start:\n    "Hello."\n',
    })
    before = path.read_bytes()
    report = inspect_archive(path)
    assert report["renpy_python_sources"] == 1
    assert report["extensions"][".py"] == 2
    assert path.read_bytes() == before


@pytest.mark.parametrize("payload", [
    b"cos\nsystem\n.", b"\x80\x04\x8c\x02os\x8c\x06system\x93.",
    b"\x80\x04)R.", b"\x80\x04)\x81.", b"\x80\x04)\x92.",
    b"\x80\x04)Poutside\n.", b"\x80\x04)\x97.",
])
def test_object_call_global_and_persistent_opcodes_are_never_resolved(payload):
    with pytest.raises(ValueError):
        literal_index(payload)


@pytest.mark.parametrize("name", [
    "../escape.rpy", "/absolute.rpy", "C:/escape.rpy", "x\\y.rpy", "a//b.rpy", "a/./b.rpy",
])
def test_archive_paths_cannot_escape_or_become_commands(tmp_path, name):
    with pytest.raises(ValueError):
        read_index(archive(tmp_path / "synthetic.rpa", {name: b"synthetic"}))


def test_duplicate_casefolded_members_and_outside_offsets_fail_closed(tmp_path):
    path = tmp_path / "synthetic.rpa"
    with pytest.raises(ValueError, match="Ambiguous"):
        read_index(archive(path, {"Menu.rpy": b"a", "menu.rpy": b"b"}))
    raw = pickle.dumps({"bad.rpy": [(0 ^ 0x42424242, 100 ^ 0x42424242, b"")]}, protocol=4)
    with pytest.raises(ValueError, match="data region"):
        read_index(archive(path, encoded_index=raw))


def test_index_trailing_data_bombs_and_fragment_cycles_are_rejected(tmp_path, monkeypatch):
    path = archive(tmp_path / "synthetic.rpa")
    path.write_bytes(path.read_bytes() + b"trailing")
    with pytest.raises(ValueError, match="trailing data"):
        read_index(path)
    monkeypatch.setattr("unitytranslator.renpy_archive.MAX_INDEX", 16)
    with pytest.raises(ValueError, match="bounds"):
        read_index(archive(path))


def test_changed_index_and_oversized_member_are_rejected(tmp_path):
    path = archive(tmp_path / "synthetic.rpa")
    index = read_index(path)
    with pytest.raises(ValueError, match="oversized"):
        index.read_member("screens/menu.rpy", limit=1)
    archive(path, {"other.rpy": b"changed"})
    with pytest.raises(ValueError, match="changed"):
        index.read_member("screens/menu.rpy")


def test_literal_index_rejects_duplicate_dictionary_assignment_and_cycles(tmp_path):
    # A duplicate literal key must not silently replace an earlier archive entry.
    payload = b"\x80\x04}\x8c\x01a]s\x8c\x01a]s."
    with pytest.raises(ValueError, match="Duplicate"):
        literal_index(payload)
    cyclic = []
    cyclic.append(cyclic)
    path = archive(
        tmp_path / "synthetic.rpa", encoded_index=pickle.dumps({"x": cyclic}, protocol=4),
    )
    with pytest.raises(ValueError, match="descriptor"):
        read_index(path)


def test_scan_reports_archive_sources_without_claiming_extraction(tmp_path):
    from unitytranslator.engines import renpy_inputs

    root = tmp_path / "game-root"
    (root / "game").mkdir(parents=True)
    path = archive(root / "game/archive.rpa", {
        "screens/menu.rpy": b"synthetic", "screens/menu.rpyc": b"not decoded",
    })
    before = path.read_bytes()
    evidence = inspect_archive(path)
    assert evidence["members"] == 2
    assert evidence["extensions"] == {".rpy": 1, ".rpyc": 1}
    assert evidence["translation_templates"] == 0
    assert evidence["extraction"] == "unsupported"
    assert evidence["installation"] == "unsupported"
    candidate = renpy_inputs(root)["source_candidates"][0]
    assert candidate["archive_inspection"] == evidence
    assert path.read_bytes() == before


def test_member_prefix_is_part_of_logical_length(tmp_path):
    key = 0x42424242
    encoded = pickle.dumps({"x.rpy": [(34 ^ key, 5 ^ key, b"pre")]}, protocol=4)
    path = archive(tmp_path / "synthetic.rpa", {"x.rpy": b"ab"}, encoded_index=encoded)
    assert read_index(path).read_member("x.rpy") == b"preab"
