from copy import deepcopy

import pytest

from unitytranslator.i2 import extract_i2


def synthetic_tree() -> dict:
    return {
        "m_Name": "SyntheticSource",
        "mLanguages": [{"Name": "Turkish", "Code": "tr"}, {"Name": "English", "Code": "en"}],
        "mTerms": [
            {"Term": "menu/start", "TermType": 0, "Languages": ["Başla", "Start"]},
            {"Term": "dialog/start", "TermType": 0, "Languages": ["Başla", "Start"]},
            {"Term": "font/reference", "TermType": 1, "Languages": ["font", "font"]},
        ],
    }


def test_language_mapping_identity_and_control_fields() -> None:
    tree = synthetic_tree()
    units = extract_i2(tree, "synthetic.assets", 1)
    assert len(units) == 2
    assert units[0].source_text == "Start"
    assert units[0].unit_id != units[1].unit_id
    updated = deepcopy(tree)
    updated["mTerms"][0]["Languages"][1] = "Continue"
    moved = extract_i2(updated, "moved.assets", 999)
    assert moved[0].unit_id == units[0].unit_id
    assert moved[0].source_hash != units[0].source_hash


@pytest.mark.parametrize("issue", ["language", "missing", "duplicate"])
def test_untrusted_schema_is_rejected(issue: str) -> None:
    tree = synthetic_tree()
    if issue == "language":
        tree["mLanguages"][1] = {"Name": "Unknown", "Code": "xx"}
    elif issue == "missing":
        tree["mTerms"][0]["Languages"][1] = ""
    else:
        tree["mTerms"][1]["Term"] = "menu/start"
    with pytest.raises(ValueError):
        extract_i2(tree, "synthetic.assets", 1)


def test_empty_source_is_reported_and_other_records_preserved() -> None:
    tree = synthetic_tree()
    tree["mTerms"][0]["Languages"][1] = ""
    diagnostics = []
    units = extract_i2(tree, "synthetic.assets", 1, diagnostics)
    assert len(units) == 1
    assert diagnostics == [{"object": 1, "key": "menu/start", "code": "empty_source_excluded"}]
