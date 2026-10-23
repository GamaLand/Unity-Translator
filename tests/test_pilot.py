"""Representative samples must satisfy the gate despite uneven category sizes."""

from dataclasses import replace

from test_repository import draft

from unitytranslator.filesystem import ProjectPaths
from unitytranslator.pilot import select_pilot
from unitytranslator.repository import ProjectRepository


def test_uneven_categories_fill_sample_without_approved_or_existing_candidates(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        units = [
            replace(draft(f"{category}/{index}", "Source " + "x" * index), category=category)
            for category, count in (("large", 220), ("small", 2))
            for index in range(count)
        ]
        repo.ingest(units, {})
        repo.edit("large/0", 0, "Candidate")
        repo.edit("large/1", 0, "Approved")
        repo.approve("large/1", 1)
        sample = select_pilot(repo)
        assert len(sample) == len(set(sample)) == 200
        assert {"small/0", "small/1"} <= set(sample)
        assert not {"large/0", "large/1"}.intersection(sample)
        assert sample == select_pilot(repo)
        assert len(select_pilot(repo, 10)) == 10
