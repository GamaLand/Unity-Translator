import asyncio
import json
from dataclasses import replace
from pathlib import Path

from test_jobs import FakeProvider, profile
from test_repository import draft

from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore, TranslationJobService
from unitytranslator.reports import job_report, save_current_quality_audit, save_review_html
from unitytranslator.repository import ProjectRepository


def test_estimate_does_not_extrapolate_unmeasured_strata(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft(), replace(draft("Other/key"), category="Other")], {})
        job = JobStore(repo).create(["UI/start"], profile())
        asyncio.run(TranslationJobService(repo, lambda _: FakeProvider()).run(job))
        report = job_report(repo, job)
        estimate = report["project_time_estimate"]
        assert estimate["covered_records"] == 1
        assert estimate["unmeasured_records"] == 1
        assert estimate["complete_project_estimate"] is False
        assert estimate["human_review_seconds"] is None


def test_new_quality_audit_does_not_rewrite_legacy_candidate_or_human_approval(
    tmp_path: Path,
) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        key = "<script>legacy</script>"
        repo.ingest([draft(key, "Cannot move")], {})
        repo.edit(key, 0, "Hareket eder")
        repo.approve(key, repo.page()[0]["version"])
        # Eski kontrol sürümünden kalan adayın fixture'ı; üretimde revizyonlar değişmez.
        repo.db.execute("UPDATE translation_revisions SET issues_json='[]'")
        before = list(repo.db.iterdump())
        report = save_current_quality_audit(repo)
        assert report["audited_current_translations"] == 1
        assert report["newly_flagged_records"] == 1
        assert report["issue_counts"] == {"negation_content_review": 1}
        assert list(repo.db.iterdump()) == before
        assert repo.page()[0]["status"] == "approved"
        content = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
        assert content["records"][0]["new_issues"] == ["negation_content_review"]
        html = Path(report["html_path"]).read_text(encoding="utf-8")
        assert "<script>" not in html and "&lt;script&gt;" in html
        assert "Olumsuzluk" in html and "default-src &#39;none&#39;" in html


def test_review_html_escapes_data_and_distinguishes_pilot_from_approval(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    key = '<script src="https://example.invalid/x"></script>'
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft(key)], {})
        store = JobStore(repo)
        job = store.create([key], profile(), "pilot")
        asyncio.run(TranslationJobService(repo, lambda _: FakeProvider()).run(job))
        store.acknowledge_pilot(job)
        html = save_review_html(repo, job).read_text(encoding="utf-8")
        assert "<script" not in html
        assert "&lt;script" in html
        assert "default-src 'none'" in html
        assert "kullanıcı tarafından onaylandı" in html
        assert "0 kayıt tek tek onaylandı" in html
