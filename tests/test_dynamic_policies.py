"""Saved policies take effect between requests, with immutable attempt provenance."""

import asyncio
import json
from dataclasses import replace

import pytest
from test_jobs import profile
from test_pilot_review import interrupted
from test_repository import draft

from unitytranslator.application import ApplicationSession
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.providers import ProviderError
from unitytranslator.repository import ProjectRepository


def policies(target, *, empty=False):
    return {
        "glossary": [] if empty else [GlossaryRule(
            source="Iron", target=target, kind="preferred_translation",
        ).model_dump()],
        "styles": {"default": "Synthetic style " + target},
    }


def record(repo, unit):
    return next(row for row in repo.page() if row["unit_id"] == unit)


@pytest.mark.parametrize("parallel", [1, 2])
@pytest.mark.parametrize("pause_first", [False, True])
def test_saved_changes_apply_after_inflight_requests_and_on_resume(tmp_path, parallel, pause_first):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft(f"UI/{i}", "Iron gate") for i in range(5)], {})
        repo.edit("UI/4", 0, "Existing translation")
        repo.approve("UI/4", 1)
        approved = record(repo, "UI/4")
        session = ApplicationSession()
        session.repository = repo
        calls = []
        arrived, release = asyncio.Event(), asyncio.Event()

        class Provider:
            async def translate_record(self, model, text, *args, **kwargs):
                calls.append((kwargs["glossary"], kwargs["style"]))
                target = kwargs["glossary"][0]["target"]
                if len(calls) <= parallel:
                    if len(calls) == parallel:
                        arrived.set()
                    await release.wait()
                return {"translation": target, "issues": []}

        service = TranslationJobService(repo, lambda _: Provider())
        session.jobs = service

        async def run():
            old = await session.dispatch("set_policies", policies("Demir"))
            initial = replace(profile(), **old)
            store = JobStore(repo)
            job = store.create([f"UI/{i}" for i in range(4)], initial)
            original = store.job(job)["profile_json"]
            task = asyncio.create_task(service.run(job, parallel_requests=parallel))
            try:
                await asyncio.wait_for(arrived.wait(), 3)
                current = await session.dispatch("set_policies", policies("Çelik"))
                if pause_first:
                    service.pause()
            finally:
                release.set()
            result = await asyncio.wait_for(task, 3)
            if pause_first:
                assert result["status"] == "paused"
                result = await service.run(job, parallel_requests=parallel)
            assert result["counts"] == {"completed": 4}
            assert [rules[0]["target"] for rules, _ in calls] == (
                ["Demir"] * parallel + ["Çelik"] * (4 - parallel)
            )
            assert [style for _, style in calls] == (
                ["Synthetic style Demir"] * parallel + ["Synthetic style Çelik"] * (4 - parallel)
            )
            assert store.job(job)["profile_json"] == original
            for index, versions in enumerate([old] * parallel + [current] * (4 - parallel)):
                run = repo.db.execute(
                    "SELECT metadata_json FROM translation_runs WHERE job_id=? AND unit_id=?",
                    (job, f"UI/{index}"),
                ).fetchone()
                metadata = json.loads(run[0])
                revision = json.loads(repo.db.execute(
                    "SELECT metadata_json FROM translation_revisions WHERE id=?",
                    (record(repo, f"UI/{index}")["translation_revision"],),
                ).fetchone()[0])
                for kind, version in versions.items():
                    assert metadata["profile"][kind] == revision[kind] == version
            assert record(repo, "UI/4") == approved
            assert {row["unit_id"] for row in PolicyStore(repo).impacted()} == {
                f"UI/{i}" for i in range(5)
            }

        asyncio.run(run())


def test_retry_uses_saved_removal_of_glossary_rule(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft(text="Iron gate")], {})
        session = ApplicationSession()
        session.repository = repo
        calls = []

        class Provider:
            async def translate_record(self, *args, **kwargs):
                calls.append(kwargs["glossary"])
                if len(calls) == 1:
                    await session.dispatch("set_policies", policies("Çelik", empty=True))
                    raise ProviderError("invalid_response", "Synthetic retry")
                return {"translation": "Kapı", "issues": []}

        async def run():
            versions = await session.dispatch("set_policies", policies("Demir"))
            job = JobStore(repo).create(["UI/start"], replace(profile(), **versions))
            result = await TranslationJobService(repo, lambda _: Provider()).run(job)
            assert result["counts"] == {"completed": 1}
            assert calls[0][0]["target"] == "Demir"
            assert calls[1] == []
            assert record(repo, "UI/start")["status"] == "translated"

        asyncio.run(run())


def test_bulk_uses_current_policies_after_review_without_another_pilot(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        store, pilot, _ = interrupted(repo)
        store.acknowledge_pilot(pilot)
        policy = PolicyStore(repo)
        current = policy.set_styles({"default": "Current saved style"})
        policy.set_glossary([GlossaryRule(source="Start", target="Başla",
                                         kind="preferred_translation")])
        calls = []

        class Provider:
            async def translate_record(self, *args, **kwargs):
                calls.append(kwargs)
                return {"translation": "Başla", "issues": []}

        job = store.create(store.bulk_units(), profile(), "bulk")
        result = asyncio.run(TranslationJobService(repo, lambda _: Provider()).run(job))
        assert result["counts"] == {"completed": 2}
        assert all(call["style"] == "Current saved style" for call in calls)
        assert all(call["glossary"][0]["target"] == "Başla" for call in calls)
        assert policy.active_version("style") == current


def test_invalid_style_save_does_not_partially_change_live_glossary(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        session = ApplicationSession()
        session.repository = repo

        async def run():
            await session.dispatch("set_policies", policies("Demir"))
            before = list(repo.db.iterdump())
            invalid = policies("Çelik")
            invalid["styles"]["default"] = "x" * 2001
            with pytest.raises(ValueError):
                await session.dispatch("set_policies", invalid)
            assert list(repo.db.iterdump()) == before

        asyncio.run(run())


def test_reopened_paused_job_uses_current_saved_policies(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    paths = ProjectPaths(game, tmp_path / "project")
    with ProjectRepository(paths) as repo:
        repo.ingest([draft(text="Iron gate")], {})
        policy = PolicyStore(repo)
        old = policy.set_glossary([GlossaryRule.model_validate(policies("Demir")["glossary"][0])])
        job = JobStore(repo).create(["UI/start"], replace(profile(), glossary_version=old))
        JobStore(repo).pause(job)
        current = policy.set_glossary([
            GlossaryRule.model_validate(policies("Çelik")["glossary"][0]),
        ])
    with ProjectRepository(paths) as repo:
        calls = []

        class Provider:
            async def translate_record(self, *args, **kwargs):
                calls.append(kwargs["glossary"])
                return {"translation": "Çelik", "issues": []}

        result = asyncio.run(TranslationJobService(repo, lambda _: Provider()).run(job))
        assert result["counts"] == {"completed": 1}
        assert calls[0][0]["target"] == "Çelik"
        assert json.loads(JobStore(repo).job(job)["profile_json"])["glossary_version"] == old
        metadata = json.loads(repo.db.execute(
            "SELECT metadata_json FROM translation_revisions",
        ).fetchone()[0])
        assert metadata["glossary_version"] == current
