import asyncio
import json
from pathlib import Path

import httpx
import pytest

from unitytranslator.application import ApplicationSession
from unitytranslator.capabilities import discovery_capabilities
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.i2 import extract_i2
from unitytranslator.language import DEFAULT_STYLE, language_index, normalize_language
from unitytranslator.policy import GlossaryRule
from unitytranslator.providers import LocalProvider
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_payload import export_runtime_payload
from unitytranslator.validation import review_issues


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("jp", "ja"),
        (" IT ", "it"),
        ("pt_br", "pt-BR"),
        ("zh_hant_tw", "zh-Hant-TW"),
    ],
)
def test_language_codes(raw, expected):
    assert normalize_language(raw) == expected


@pytest.mark.parametrize("value", ["", "Japanese", "en/../../", "en\\tr", "en\ntr"])
def test_invalid_codes(value):
    with pytest.raises(ValueError):
        normalize_language(value)


def test_language_selection_requires_unique_source_and_respects_regions():
    assert language_index([{"Code": "fr"}, {"Code": "en"}], "fr") == 0
    assert language_index([{"Name": "Italian"}], "it") == 0
    assert language_index([{"Code": "pt-BR"}, {"Code": "pt-PT"}], "pt-BR") == 0
    assert language_index([{"Code": "en-GB"}], "en") == 0
    for codes, requested in [
        (["pt-BR", "pt-PT"], "pt"),
        (["en-GB"], "en-US"),
        (["en", "en"], "en"),
        (["fr"], "ja"),
    ]:
        with pytest.raises(ValueError, match="missing or ambiguous"):
            language_index([{"Code": code} for code in codes], requested)


@pytest.mark.parametrize(
    ("source", "target", "text", "translated"),
    [
        ("fr", "en", "Commencer {0}", "Start {0}"),
        ("en", "ja", "Start {0}", "開始 {0}"),
        ("ja", "it", "開始 {0}", "Inizia {0}"),
        ("de", "ar", "Starten {0}", "ابدأ {0}"),
        ("it", "pt-BR", "Inizia {0}", "Iniciar {0}"),
    ],
)
def test_extract_approve_export_language_pair(tmp_path, source, target, text, translated):
    game = tmp_path / "game"
    managed = game / "Synthetic_Data/Managed"
    managed.mkdir(parents=True)
    assembly = managed / "Assembly-CSharp.dll"
    assembly.write_bytes(b"synthetic metadata")
    original_hash = hash_file(assembly)
    tree = {
        "m_Name": "synthetic",
        "mLanguages": [{"Code": source}],
        "mTerms": [{"Term": "UI/start", "TermType": 0, "Languages": [text]}],
    }
    units = extract_i2(tree, "Synthetic_Data/resources.assets", 1, source_language=source)
    assert units[0].source_language == source and units[0].source_text == text
    paths = ProjectPaths(game, tmp_path / "project")
    with ProjectRepository(paths, source, target) as repo:
        repo.ingest(units, {})
        row = repo.page()[0]
        repo.edit(row["unit_id"], row["version"], translated)
        repo.approve(row["unit_id"], repo.page()[0]["version"])
        output = export_runtime_payload(
            repo,
            source_set="synthetic",
            unity_version="2017.4.19f1",
            assembly_relative="Synthetic_Data/Managed/Assembly-CSharp.dll",
            target_name=target,
        )
        payload = json.loads(Path(output["path"]).read_text(encoding="utf-8"))
        assert payload["format_version"] == 2
        assert (payload["source_language"], payload["target_language"]) == (source, target)
        assert payload["entries"][0]["text"] == translated
        assert payload["entries"][0]["source_sha256"] == units[0].source_hash
    # Reopening with default constructor arguments does not reset the stored pair or approvals.
    with ProjectRepository(paths) as repo:
        assert (repo.source_language, repo.target_language) == (source, target)
        assert repo.page()[0]["status"] == "approved"
    assert hash_file(assembly) == original_hash


def test_application_forwards_source_language_to_worker(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    captured = []

    def probe(paths, source, *, source_language, cancellation=None):
        captured.append(source_language)
        units = extract_i2(
            {
                "m_Name": "synthetic",
                "mLanguages": [{"Code": "it"}],
                "mTerms": [{"Term": "UI/start", "TermType": 0, "Languages": ["Inizia"]}],
            },
            source,
            1,
            source_language=source_language,
        )
        from dataclasses import asdict

        report = {
            "extraction": "supported",
            "counts": {"records": 1},
            "units": [asdict(unit) for unit in units],
        }
        report["capabilities"] = discovery_capabilities(report, inspected=True).to_dict()
        return report

    monkeypatch.setattr("unitytranslator.application.probe_source", probe)

    async def run():
        session = ApplicationSession()
        try:
            await session.dispatch(
                "open",
                {
                    "game": str(game),
                    "project": str(tmp_path / "project"),
                    "source_language": "it",
                    "target_language": "ja",
                },
            )
            result = await session.dispatch("extract", {"source": "synthetic.assets"})
            assert session.repo.page()[0]["source_text"] == "Inizia"
            assert result["capabilities"]["translation"]["status"] == "supported"
            assert result["capabilities"]["installation"]["status"] == "unknown"
        finally:
            await session.close()

    asyncio.run(run())
    assert captured == ["it"]


def test_sample_uses_selected_target_and_neutral_prompt():
    def handler(request):
        payload = json.loads(request.content)
        messages = payload["messages"]
        assert "Turkish" not in messages[0]["content"]
        data = json.loads(messages[1]["content"])
        assert data["target_language"] == "ja"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"translations": [{"id": "sample", "text": "開始"}]}
                            )
                        }
                    }
                ]
            },
        )

    provider = LocalProvider("lm-studio", "http://localhost:1234", httpx.MockTransport(handler))
    result = asyncio.run(provider.translate_sample("synthetic", "Start", target_language="ja"))
    assert result["translation"] == "開始"
    assert "Turkish" not in DEFAULT_STYLE and "target language" in DEFAULT_STYLE


def test_glossary_and_number_checks_follow_language():
    rule = GlossaryRule(source="start", target="INIZIA", kind="preferred_translation")
    assert rule.matches("inizia", "UI", target=True, language="it")
    assert "numeric_content_review" not in review_issues(
        "Cost 1,234.5", "Costo 1.234,5", source_language="en", target_language="it"
    )
    assert "numeric_content_review" in review_issues(
        "開始 10", "Inizia 11", source_language="ja", target_language="it"
    )
    assert "protected_content_mismatch" not in review_issues(
        "Start {0}", "開始 {0}", source_language="en", target_language="ja"
    )
