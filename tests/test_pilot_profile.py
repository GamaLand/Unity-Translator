"""Restore exact reviewed settings explicitly, without weakening the bulk gate."""
import asyncio
from dataclasses import replace

import pytest
from test_jobs import profile
from test_pilot_review import interrupted

from unitytranslator.application import ApplicationSession
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.repository import ProjectRepository


def saved_policy(policy, term):
    glossary = policy.set_glossary([GlossaryRule(
        source=term, target=term, kind="preserve_name",
    )])
    style = policy.set_styles({"default": "Synthetic style " + term})
    return glossary, style


@pytest.mark.parametrize("pinned_policy", [False, True])
def test_policy_change_is_diagnosed_and_explicit_selection_restores_exact_pilot(
    tmp_path, pinned_policy,
):
    game = tmp_path / "game"
    game.mkdir()

    async def run():
        session = ApplicationSession()
        try:
            await session.dispatch("open", {
                "game": str(game), "project": str(tmp_path / "project"),
            })
            repo = session.repo
            policy = PolicyStore(repo)
            old = saved_policy(policy, "Old") if pinned_policy else (None, None)
            initial = replace(profile(), glossary_version=old[0], style_version=old[1])
            store, job, _ = interrupted(repo, generation_profile=initial)
            store.acknowledge_pilot(job)
            saved_policy(policy, "New")
            rows = repo.page() + repo.page(offset=200)
            versions = list(repo.db.execute("SELECT * FROM glossary_versions"))
            styles = list(repo.db.execute("SELECT * FROM style_versions"))
            request = {"project_id": repo.project_id, "profile": {
                k: v for k, v in initial.to_dict().items()
                if k not in ("glossary_version", "style_version")
            }}
            readiness = await session.dispatch("bulk_readiness", request)
            assert readiness["reason"] == "profile_changed" and not readiness["allowed"]
            assert readiness["different_fields"] == ["glossary_version", "style_version"]
            assert readiness["pilot_job_id"] == job
            action = {"project_id": repo.project_id, "job_id": job, "request_token": "choice"}
            with pytest.raises(ValueError, match="Explicitly"):
                await session.dispatch("use_pilot_profile", action)
            assert policy.active_version("glossary") != old[0]
            result = await session.dispatch("use_pilot_profile", {**action, "user_action": True})
            assert result["profile"] == initial.to_dict()
            assert result["request_token"] == "choice"
            assert (policy.active_version("glossary"), policy.active_version("style")) == old
            assert list(repo.db.execute("SELECT * FROM glossary_versions")) == versions
            assert list(repo.db.execute("SELECT * FROM style_versions")) == styles
            assert repo.page() + repo.page(offset=200) == rows
            assert (await session.dispatch("bulk_readiness", request))["allowed"]
            assert (await session.dispatch("create_job", {
                "kind": "bulk", "profile": request["profile"],
            }))["count"] == 2
        finally:
            await session.close()

    asyncio.run(run())


def test_unreviewed_or_stale_pilots_cannot_select_settings(tmp_path):
    game = tmp_path / "game"
    game.mkdir()

    async def run():
        session = ApplicationSession()
        try:
            await session.dispatch("open", {
                "game": str(game), "project": str(tmp_path / "project"),
            })
            store, job, units = interrupted(session.repo)
            action = {"project_id": session.repo.project_id, "job_id": job, "user_action": True}
            with pytest.raises(ValueError, match="reviewed"):
                await session.dispatch("use_pilot_profile", action)
            store.acknowledge_pilot(job)
            with pytest.raises(ValueError, match="current project"):
                await session.dispatch("use_pilot_profile", {**action, "project_id": "old"})
            session.repo.ingest([replace(unit, context="changed") for unit in units], {})
            readiness = store.bulk_readiness(profile())
            assert readiness["reason"] == "source_changed" and not readiness["pilot_job_id"]
            with pytest.raises(ValueError, match="current sources"):
                await session.dispatch("use_pilot_profile", action)
        finally:
            await session.close()

    asyncio.run(run())


def test_policy_version_selection_validates_both_versions_before_writing(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        policy = PolicyStore(repo)
        saved_policy(policy, "New")
        before = list(repo.db.iterdump())
        with pytest.raises(ValueError):
            policy.select_pinned_versions(None, "missing")
        assert list(repo.db.iterdump()) == before


def test_desktop_selects_reviewed_pilot_settings_after_policy_change(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from test_ui import wait_for

    from unitytranslator.ui.window import MainWindow

    game = tmp_path / "game"
    game.mkdir()
    paths = ProjectPaths(game, tmp_path / "project")
    with ProjectRepository(paths) as repo:
        store, job, _ = interrupted(repo)
        store.acknowledge_pilot(job)
        saved_policy(PolicyStore(repo), "New")
    app = QApplication.instance()
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.game_path.setText(str(game))
    window.project_path.setText(str(paths.project))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: bool(window.reviewed_pilot_id))
        assert not window.bulk_button.isEnabled()
        assert "sözlük" in window.bulk_note.text().lower()
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
        window.pilot_profile_button.click()
        assert window.reviewed_pilot_id == job and not window.bulk_button.isEnabled()
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
        window.pilot_profile_button.click()
        wait_for(app, lambda: window.bulk_button.isEnabled())
        assert window.profile()["output_tokens"] == profile().output_tokens
        assert not errors
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
    with ProjectRepository(paths) as repo:
        assert PolicyStore(repo).active_version("glossary") is None
        assert repo.db.execute("SELECT count(*) FROM glossary_versions").fetchone()[0] == 1
        assert JobStore(repo).job(job)["report_seen"] == 1
