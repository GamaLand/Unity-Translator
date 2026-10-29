import asyncio
import json

import pytest
from test_repository import draft

from unitytranslator.application import ApplicationSession
from unitytranslator.domain import GenerationProfile
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.repository import ProjectRepository


@pytest.mark.parametrize("status", ["queued", "paused"])
@pytest.mark.parametrize("changed", ["provider", "address", "model"])
def test_run_rejects_changed_model_selection_before_claim_or_provider(tmp_path, status, changed):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft()], {})
        profile = GenerationProfile("lm-studio", "http://127.0.0.1:1234", "old-model", 8192)
        store = JobStore(repo)
        job = store.create(["UI/start"], profile)
        if status == "paused":
            store.pause(job)
        original = dict(store.job(job))
        selected = {key: profile.to_dict()[key] for key in ("provider", "address", "model")}
        selected[changed] = {
            "provider": "llama-cpp", "address": "http://127.0.0.1:8080", "model": "new-model",
        }[changed]

        def forbidden_provider(_):
            pytest.fail("A mismatched selection must not reach any model server")

        session = ApplicationSession()
        session.repository = repo
        session.jobs = TranslationJobService(repo, forbidden_provider)
        with pytest.raises(ValueError, match="differs from this job's saved settings"):
            asyncio.run(session.dispatch("run_job", {"job_id": job, "model_selection": selected}))
        assert dict(store.job(job)) == original
        assert store.progress(job)["counts"] == {"queued": 1}
        assert repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == 0
        assert session.jobs.active_job is None


@pytest.mark.parametrize("with_selection", [False, True])
def test_matching_or_legacy_run_keeps_saved_profile(tmp_path, with_selection):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft()], {})
        profile = GenerationProfile("llama-cpp", "http://127.0.0.1:8080", "new-model", 8192)
        store = JobStore(repo)
        job = store.create(["UI/start"], profile)
        requests = []

        class Provider:
            async def translate_record(self, model, *args, **kwargs):
                requests.append(model)
                return {"translation": "Başla", "issues": []}

        def factory(saved):
            assert saved == profile
            return Provider()

        session = ApplicationSession()
        session.repository = repo
        session.jobs = TranslationJobService(repo, factory)
        data = {"job_id": job}
        if with_selection:
            data["model_selection"] = {
                "provider": "llama-cpp", "address": "http://127.0.0.1:8080/v1/",
                "model": "new-model",
            }
        result = asyncio.run(session.dispatch("run_job", data))
        assert result["counts"] == {"completed": 1}
        assert requests == ["new-model"]
        assert json.loads(store.job(job)["profile_json"]) == profile.to_dict()
