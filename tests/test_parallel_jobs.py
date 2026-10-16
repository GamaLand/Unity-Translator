import asyncio

import pytest
from test_jobs import FakeProvider, profile
from test_repository import draft

from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.repository import ProjectRepository


@pytest.mark.parametrize("action", ["complete", "pause", "cancel"])
@pytest.mark.parametrize("parallel", [4, 16])
def test_parallel_requests_are_bounded_and_settle_without_orphans(tmp_path, action, parallel):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        size = parallel * 2
        repo.ingest([draft(f"UI/{i}", f"Text {i}") for i in range(size)], {})
        store = JobStore(repo)
        # Pilot capacity permits this synthetic multi-worker check without a bulk gate bypass.
        job = store.create([r["unit_id"] for r in repo.page()], profile(), kind="pilot")
        active = 0
        maximum = 0
        arrived = asyncio.Event()
        service = TranslationJobService(repo, lambda _: provider)

        class Provider(FakeProvider):
            async def translate_record(self, model, text, *args, **kwargs):
                nonlocal active, maximum
                self.requests.append(text)
                active += 1
                maximum = max(maximum, active)
                if active == parallel:
                    arrived.set()
                    if action == "pause":
                        service.pause()
                    elif action == "cancel":
                        service.cancel()
                try:
                    await asyncio.wait_for(arrived.wait(), timeout=3)
                    await asyncio.sleep(0)
                    return {"translation": "Çeviri", "issues": []}
                finally:
                    active -= 1

        provider = Provider()
        result = asyncio.run(service.run(job, parallel_requests=parallel))
        assert maximum == parallel
        assert active == 0
        assert service.active_job is None
        assert not result["counts"].get("processing")
        assert len(provider.requests) == len(set(provider.requests))
        if action == "complete":
            assert result["counts"] == {"completed": size}
        elif action == "pause":
            assert result["status"] == "paused"
            assert result["counts"] == {"completed": parallel, "queued": parallel}
        else:
            assert result["status"] == "cancelled"
            assert result["counts"] == {"cancelled": size}
            assert all(row["translation"] is None for row in repo.page())


@pytest.mark.parametrize("parallel", [0, 17, True, 1.5, "4"])
def test_invalid_parallel_setting_does_not_start_job(tmp_path, parallel):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft()], {})
        store = JobStore(repo)
        job = store.create(["UI/start"], profile())
        with pytest.raises(ValueError, match="Paralel"):
            asyncio.run(TranslationJobService(repo).run(job, parallel_requests=parallel))
        assert store.job(job)["status"] == "queued"
