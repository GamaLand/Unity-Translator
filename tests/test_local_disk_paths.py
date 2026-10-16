import pytest

from unitytranslator import filesystem


@pytest.mark.parametrize("network_target", ["game", "project"])
def test_mapped_network_drive_rejected_before_project_creation(
    tmp_path, monkeypatch, network_target
):
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    rejected = game if network_target == "game" else project
    monkeypatch.setattr(filesystem, "_is_network_drive", lambda path: path == rejected)
    with pytest.raises(filesystem.PolicyError, match="yerel disk"):
        filesystem.ProjectPaths(game, project)
    assert not project.exists()


def test_local_disk_paths_accepted(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    monkeypatch.setattr(filesystem, "_is_network_drive", lambda path: False)
    paths = filesystem.ProjectPaths(game, project)
    assert paths.game == game
    assert paths.project == project
    assert not project.exists()
