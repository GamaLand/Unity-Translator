"""Interrupted pilot review keeps sample, source and human-approval boundaries."""
from dataclasses import replace

import pytest
from test_jobs import profile
from test_repository import draft

from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore
from unitytranslator.reports import job_report
from unitytranslator.repository import ProjectRepository


def interrupted(repo, attempted=200, successful=198, generation_profile=None):
    units = [draft(f"UI/{index:03d}") for index in range(201)]
    repo.ingest(units, {})
    store = JobStore(repo)
    job = store.create([unit.unit_id for unit in units[:200]],
                       generation_profile or profile(), "pilot")
    store.start(job)
    for index in range(attempted):
        item = store.claim(job)
        assert item is not None
        run = store.attempt(item, {})
        if index < successful:
            assert store.finish(item, {"translation": "Başla", "issues": []}, run)
        elif index == attempted - 1:
            break  # Model request interrupted after the representative sample was attempted.
        else:
            store.fail(item, "output_truncated")
    store.cancel(job)
    return store, job, units


def test_attempted_cancelled_pilot_can_unlock_bulk_without_approving_or_replacing_results(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        store, job, _ = interrupted(repo)
        before = repo.page() + repo.page(offset=200)
        revisions = repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0]
        report = job_report(repo, job)
        assert report["progress"]["counts"] == {"completed": 198, "failed": 1, "cancelled": 1}
        assert report["pilot_review_eligible"] is True
        assert not store.pilot_reviewed(profile())
        store.acknowledge_pilot(job)
        assert store.pilot_reviewed(profile())
        assert store.job(job)["status"] == "cancelled"
        assert repo.page() + repo.page(offset=200) == before
        assert repo.db.execute("SELECT count(*) FROM translation_revisions").fetchone()[0] == (
            revisions
        )
        assert not any(row["status"] == "approved" for row in before)
        assert len(store.bulk_units()) == 2  # Interrupted sample and untouched project record.
        store.create(store.bulk_units(), profile(), "bulk")
        assert not store.pilot_reviewed(replace(profile(), output_tokens=4096))


@pytest.mark.parametrize(("attempted", "successful"), [(199, 198), (200, 0), (0, 0)])
def test_cancelled_pilot_requires_attempted_full_sample_and_actual_results(
    tmp_path, attempted, successful,
):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        store, job, _ = interrupted(repo, attempted, successful)
        assert job_report(repo, job)["pilot_review_eligible"] is False
        with pytest.raises(ValueError, match="örneklemi"):
            store.acknowledge_pilot(job)
        assert not store.pilot_reviewed(profile())


def test_cancelled_pilot_review_remains_source_bound(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        store, job, units = interrupted(repo)
        store.acknowledge_pilot(job)
        repo.ingest([replace(unit, context="Changed") for unit in units], {})
        assert not store.pilot_reviewed(profile())
        report = job_report(repo, job)
        assert report["pilot_review_eligible"] is False
        assert report["pilot_review_blocker"] == "source_changed"
        with pytest.raises(ValueError, match="Kaynak"):
            store.acknowledge_pilot(job)


def test_pilot_dialog_refreshes_stale_report_and_enables_only_eligible_review(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from unitytranslator.ui.i18n import tr
    from unitytranslator.ui.window import PilotReportDialog

    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        store, job, _ = interrupted(repo)
        report = job_report(repo, job)
        dialog = PilotReportDialog(report, "synthetic.json")
        save = next(b for b in dialog.findChildren(QPushButton)
                    if b.text() == tr("Save pilot review"))
        assert not save.isEnabled()
        dialog.reviewed.setChecked(True)
        QApplication.processEvents()
        assert save.isEnabled()
        save.click()
        assert dialog.acknowledged and dialog.result() == 1
        assert store.job(job)["report_seen"] == 0  # Dialog alone never writes the database.
        dialog.close()

        stale = {**report, "pilot_review_eligible": False,
                 "progress": {**report["progress"], "status": "running"}}
        dialog = PilotReportDialog(stale, "synthetic.json")
        dialog.reviewed.setChecked(True)
        assert not next(b for b in dialog.findChildren(QPushButton)
                        if b.text() == tr("Save pilot review")).isEnabled()
        assert any("198" in label.text() for label in dialog.findChildren(QLabel))
        refresh = next(b for b in dialog.findChildren(QPushButton)
                       if b.text() == tr("Refresh pilot report"))
        refresh.click()
        assert dialog.result() == 2 and not dialog.acknowledged
        dialog.close()
