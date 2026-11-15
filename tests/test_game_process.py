import os
from pathlib import Path

import pytest

from unitytranslator.game_process import (
    GameProcessStatus,
    ProcessImage,
    classify_game_processes,
    inspect_game_processes,
    windows_process_snapshot,
)


def test_game_process_matching_uses_selected_root_not_only_executable_name(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    process = ProcessImage(10, "Game.exe", other / "Game.exe")
    assert classify_game_processes(game, {"Game.exe"}, (process,)).status == "closed"
    same = ProcessImage(20, "Game.exe", game / "Game.exe")
    helper = ProcessImage(30, "Helper.exe", game / "tools/Helper.exe")
    result = classify_game_processes(game, {"Game.exe"}, (process, same, helper))
    assert result.status == "running"
    assert result.running_pids == (20, 30)


@pytest.mark.parametrize("image", [None, Path("relative.exe"), Path(r"\\?\C:\Game.exe")])
def test_unreadable_or_unsafe_game_named_image_is_unknown(tmp_path, image):
    game = tmp_path / "game"
    game.mkdir()
    result = classify_game_processes(game, {"Game.exe"}, (ProcessImage(10, "GAME.EXE", image),))
    assert result.status == "unknown"
    assert result.ambiguous_pids == (10,)


def test_unrelated_protected_process_is_not_persisted_as_game_process(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    result = classify_game_processes(game, {"Game.exe"}, (ProcessImage(4, "System", None),))
    assert result == GameProcessStatus("closed")
    assert classify_game_processes(game, set(), ()).status == "unknown"


def test_snapshot_failure_cannot_be_reported_as_closed(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    (game / "Game.exe").write_bytes(b"synthetic image identity")

    def broken():
        raise OSError("synthetic inspection error")

    monkeypatch.setattr("unitytranslator.game_process.windows_process_snapshot", broken)
    assert inspect_game_processes(game).status == "unknown"


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only API")
def test_real_windows_snapshot_can_query_own_process_without_starting_or_stopping_it():
    rows = windows_process_snapshot()
    own = next(row for row in rows if row.pid == os.getpid())
    assert own.image is not None and own.image.is_absolute()
    result = classify_game_processes(own.image.parent, {own.name}, (own,))
    assert result.status == "running" and result.running_pids == (os.getpid(),)


def test_tree_inspection_failure_has_its_own_reason_and_message(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from unitytranslator.deployment import DeploymentService, GameNotClosedError

    game = tmp_path / "game"
    game.mkdir()
    (game / "Game.exe").write_bytes(b"synthetic image identity")
    monkeypatch.setattr("unitytranslator.game_process.windows_process_snapshot", lambda: ())
    assert inspect_game_processes(game).status == "closed"
    if os.name == "nt":
        import _winapi

        outside = tmp_path / "outside"
        outside.mkdir()
        _winapi.CreateJunction(str(outside), str(game / "linked"))
        result = inspect_game_processes(game)
        assert (result.status, result.reason) == ("unknown", "game_tree_uninspectable")
    for reason, message in (
        ("game_tree_uninspectable", "cannot be inspected for running programs"),
        ("game_entry_limit", "cannot be inspected for running programs"),
        ("process_or_path_inspection_failed", "Close the game and check again"),
        ("no_executable_identity", "Close the game and check again"),
    ):
        service = SimpleNamespace(
            paths=SimpleNamespace(game=game),
            process_probe=lambda _game, reason=reason: GameProcessStatus("unknown", reason=reason),
        )
        with pytest.raises(GameNotClosedError, match=message):
            DeploymentService.require_game_closed(service)  # type: ignore[arg-type]


def test_missing_or_file_game_root_is_not_reported_as_an_uninspectable_tree(tmp_path):
    missing = tmp_path / "moved-game"
    regular = tmp_path / "game.txt"
    regular.write_bytes(b"not a folder")
    for root in (missing, regular):
        assert inspect_game_processes(root) == GameProcessStatus(
            "unknown", reason="no_executable_identity"
        )
