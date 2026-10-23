"""Bundled adapter selection cannot be redirected by untrusted profile identifiers."""

from dataclasses import asdict

import pytest
from test_repository import draft

from unitytranslator.profiles import GameProfile
from unitytranslator.reader_adapters import (
    BUILTIN_READERS,
    I2DeploymentAdapter,
    I2Reader,
    ReaderRegistry,
    result_from_report,
)
from unitytranslator.source_contracts import ReaderContext


@pytest.mark.parametrize("identifiers", [(), ("i2", "i2"), ("unknown",), ("os.system",)])
def test_unknown_or_ambiguous_reader_selection_fails_closed(identifiers):
    with pytest.raises(ValueError):
        BUILTIN_READERS.select(identifiers)


def test_registry_is_deterministic_and_rejects_duplicate_code_registrations():
    assert BUILTIN_READERS.select(("i2",)).id == "i2"
    with pytest.raises(ValueError, match="Duplicate"):
        ReaderRegistry((I2Reader(), I2Reader()))


def test_profile_paths_cannot_supply_code_or_external_sources():
    with pytest.raises(ValueError):
        GameProfile("synthetic", "Synthetic", "Game", "../outside.py")
    with pytest.raises(TypeError):
        GameProfile("synthetic", "Synthetic", "Game", "source.assets", command="execute")


def test_i2_contract_retains_original_id_and_has_no_complete_set_side_effect(tmp_path, monkeypatch):
    unit = draft()
    report = {"extraction": "supported", "units": [asdict(unit)], "sha256_before": "a" * 64}
    calls = []

    def probe(paths, relative, timeout, *, source_language):
        calls.append((relative, timeout, source_language))
        return dict(report)

    monkeypatch.setattr("unitytranslator.discovery._probe_i2_source", probe)
    game = tmp_path / "game"
    game.mkdir()
    context = ReaderContext(game, tmp_path / "project", "en", 7)
    result = I2Reader().extract(context, "synthetic.assets", lambda: False)
    assert result.snapshots[0].units == (unit,)
    assert result.snapshots[0].source.logical_id == "legacy-file-v1:synthetic.assets"
    assert result.complete and not result.replace_source_set
    assert calls == [("synthetic.assets", 7, "en")]
    with pytest.raises(ValueError, match="cancelled"):
        I2Reader().extract(context, "synthetic.assets", lambda: True)
    assert len(calls) == 1


def test_incomplete_reader_output_never_activates_and_unknown_adapter_needs_descriptors():
    with pytest.raises(ValueError):
        result_from_report({"extraction": "unknown"})
    with pytest.raises(ValueError):
        result_from_report({"extraction": "supported", "errors": ["bad source"]})
    with pytest.raises(ValueError, match="descriptors"):
        result_from_report(
            {
                "adapter_id": "unknown",
                "extraction": "supported",
                "units": [asdict(draft())],
            }
        )


def test_deployment_contract_delegates_to_authoritative_service():
    class Installation:
        def status(self):
            return {"installation": "unknown"}

        def prepare(self, **options):
            assert options == {"log_reviewed": False}
            raise ValueError("Missing build evidence and current reviewed approvals")

    adapter = I2DeploymentAdapter(Installation())
    assert adapter.probe()["installation"] == "unknown"
    with pytest.raises(ValueError, match="evidence"):
        adapter.prepare(log_reviewed=False)
