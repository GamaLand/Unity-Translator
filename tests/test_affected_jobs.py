import asyncio
from dataclasses import asdict
from pathlib import Path

from test_jobs import FakeProvider, profile
from test_repository import draft

from unitytranslator.application import ApplicationSession
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.repository import ProjectRepository


def test_affected_job_is_bounded_and_preserves_approved_text(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft(f"UI/{i:02}", "Iron shield") for i in range(12)] + [draft()], {})
        repo.edit("UI/00", 0, "Elle onaylı kalkan")
        repo.approve("UI/00", repo.page()[0]["version"])
        PolicyStore(repo).set_glossary(
            [GlossaryRule(source="Iron", target="Demir", kind="preferred_translation")]
        )
        session = ApplicationSession()
        session.repository = repo
        fake = FakeProvider()
        session.jobs = TranslationJobService(repo, lambda _: fake)
        settings = asdict(profile())
        settings.pop("glossary_version")
        settings.pop("style_version")
        result = asyncio.run(session.dispatch("create_affected_job", {"profile": settings}))
        assert result["count"] == 10
        selected = [
            r[0]
            for r in repo.db.execute(
                "SELECT unit_id FROM job_items WHERE job_id=? ORDER BY unit_id", (result["job_id"],)
            )
        ]
        assert selected == [f"UI/{i:02}" for i in range(10)]
        assert JobStore(repo).job(result["job_id"])["kind"] == "prototype"
        asyncio.run(session.jobs.run(result["job_id"]))
        approved = repo.page()[0]
        assert approved["translation"] == "Elle onaylı kalkan"
        assert approved["status"] == "approved"
        assert len(fake.requests) == 10
        assert repo.page(search="Start")[0]["translation"] is None
