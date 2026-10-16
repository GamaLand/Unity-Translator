from dataclasses import replace
from pathlib import Path

import pytest
from test_repository import draft

from unitytranslator.filesystem import ProjectPaths
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.repository import ProjectRepository


@pytest.fixture
def repo(tmp_path: Path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repository:
        repository.ingest([draft()], {})
        repository.edit("UI/start", 0, "Elle onay")
        repository.approve("UI/start", repository.page()[0]["version"])
        current = repository.page()[0]
        assert (
            repository.candidate(
                "UI/start",
                current["source_revision"],
                current["version"],
                "Yeni aday",
                "model",
                {"model": "synthetic"},
                [],
            )
            is False
        )
        yield repository


def test_history_selection_requires_explicit_approval_replacement(repo) -> None:
    history = repo.history("UI/start")
    assert len(history["revisions"]) == 2
    model = next(row for row in history["revisions"] if row["origin"] == "model")
    version = history["current"]["version"]
    with pytest.raises(ValueError, match="açık aday seçimi"):
        repo.select_candidate("UI/start", version, model["id"])
    assert repo.page()[0]["translation"] == "Elle onay"
    assert repo.page()[0]["status"] == "approved"
    repo.select_candidate("UI/start", version, model["id"], replace_approved=True)
    current = repo.page()[0]
    assert current["translation"] == "Yeni aday"
    assert current["status"] != "approved"
    assert current["translation_revision"] == model["id"]
    PolicyStore(repo).set_glossary(
        [GlossaryRule(source="Start", target="Başla", kind="preferred_translation")]
    )
    assert repo.count(affected=True) == 1
    repo.approve("UI/start", current["version"])
    assert repo.count(affected=True) == 0


def test_old_source_and_stale_user_version_cannot_replace_current_text(repo) -> None:
    history = repo.history("UI/start")
    model = next(row for row in history["revisions"] if row["origin"] == "model")
    version = history["current"]["version"]
    with pytest.raises(ValueError, match="değişti"):
        repo.select_candidate("UI/start", version - 1, model["id"], replace_approved=True)
    repo.ingest([replace(draft(), context="new scene")], {})
    with pytest.raises(ValueError, match="değişti"):
        repo.select_candidate(
            "UI/start", repo.page()[0]["version"], model["id"], replace_approved=True
        )
    assert repo.page()[0]["translation"] is None
    assert len(repo.history("UI/start")["revisions"]) == 2
