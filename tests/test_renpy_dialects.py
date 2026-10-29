"""Synthetic engine declarations are inspected as data and must never execute."""

import ast

import pytest

from unitytranslator import renpy_dialects
from unitytranslator.renpy_dialects import contract_fingerprint, inspect_source_dialect


@pytest.fixture
def synthetic_contracts(tmp_path, monkeypatch):
    game = tmp_path / "game-root"
    (game / "renpy").mkdir(parents=True)
    registry = {}
    for name, required in renpy_dialects._CONTRACTS.items():
        classes = {}
        functions = []
        for qualified in required:
            if "." in qualified:
                owner, method = qualified.split(".")
                classes.setdefault(owner, []).append(
                    f'    def {method}(self):\n        raise RuntimeError("NEVER EXECUTE")\n'
                )
            else:
                functions.append(f'def {qualified}():\n    raise RuntimeError("NEVER EXECUTE")\n')
        source = 'raise RuntimeError("DO NOT IMPORT THIS FILE")\n' + "\n".join(functions)
        source += "\n".join(f'class {owner}:\n' + "\n".join(methods)
                            for owner, methods in classes.items())
        path = game / "renpy" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        tree = ast.parse(source)
        registry[name] = {qualified: (contract_fingerprint(tree, qualified),)
                          for qualified in required}
    monkeypatch.setattr(renpy_dialects, "_CONTRACTS", registry)
    return game


@pytest.mark.parametrize("version", [b"", b"version = '8.3.6.25022803'\n",
                                    b"version = '9.99.1.99999999'\n"])
def test_known_behavior_is_independent_of_the_claimed_version(synthetic_contracts, version):
    evidence = inspect_source_dialect(synthetic_contracts, version)
    assert evidence["family"] == "renpy-symbolic-source-v1"
    assert evidence["evidence_kind"] == "audited_source_contracts"
    assert len(evidence["fingerprints"]) == 5
    assert evidence["reserved_attributes"] == []


def test_python_two_text_semantics_require_their_own_family(synthetic_contracts):
    with pytest.raises(ValueError, match="Python 2 source-text semantics"):
        inspect_source_dialect(synthetic_contracts, b"version = '7.8.6.25022803'\n")


def test_version_literal_cannot_bypass_missing_or_changed_contracts(synthetic_contracts):
    path = synthetic_contracts / "renpy/ast.py"
    path.write_text(path.read_text().replace('"NEVER EXECUTE"', '"CHANGED BEHAVIOR"'))
    with pytest.raises(ValueError, match="Unverified Ren'Py source behavior"):
        inspect_source_dialect(synthetic_contracts, b"version = '8.1.2.23090503'\n")
    path.unlink()  # Synthetic fixture only.
    with pytest.raises(ValueError, match="Missing or oversized"):
        inspect_source_dialect(synthetic_contracts, b"version = '8.1.2.23090503'\n")


def test_comments_docstrings_and_line_endings_do_not_define_behavior(synthetic_contracts):
    path = synthetic_contracts / "renpy/ast.py"
    path.write_bytes(path.read_bytes().replace(
        b'def get_code(self):\n', b'def get_code(self):\n        """New documentation."""\n'
    ).replace(b"\n", b"\r\n") + b"# A new comment.\r\n")
    assert inspect_source_dialect(synthetic_contracts, b"")["family"] == renpy_dialects.FAMILY


def test_duplicate_or_conditional_contracts_are_unverified(synthetic_contracts):
    path = synthetic_contracts / "renpy/ast.py"
    path.write_text(path.read_text() + '\nclass Say:\n    def get_code(self):\n        pass\n')
    with pytest.raises(ValueError, match="ambiguous"):
        inspect_source_dialect(synthetic_contracts, b"")


def test_contract_size_node_and_cancellation_budgets(synthetic_contracts, monkeypatch):
    with pytest.raises(ValueError, match="cancelled"):
        inspect_source_dialect(synthetic_contracts, b"", cancelled=lambda: True)
    monkeypatch.setattr(renpy_dialects, "MAX_AST_NODES", 1)
    with pytest.raises(ValueError, match="AST limit"):
        inspect_source_dialect(synthetic_contracts, b"")
    monkeypatch.setattr(renpy_dialects, "MAX_CONTRACT_BYTES", 1)
    with pytest.raises(ValueError, match="oversized"):
        inspect_source_dialect(synthetic_contracts, b"")


def test_legacy_profile_stays_narrow_without_engine_source(tmp_path):
    (tmp_path / "renpy").mkdir()
    evidence = inspect_source_dialect(tmp_path, b"version = '8.1.2.23090503'\n")
    assert evidence["evidence_kind"] == "legacy_pinned_source"
    for version in (b"", b"version = '8.3.6.25022803'\n", b"version = '9.0.0.00000000'\n"):
        with pytest.raises(ValueError, match="unverified"):
            inspect_source_dialect(tmp_path, version)
