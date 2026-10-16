import struct
from functools import partial

import pytest

from unitytranslator.deployment import DeploymentService
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.game_process import GameProcessStatus
from unitytranslator.i2 import extract_i2
from unitytranslator.installation import InstallationSession
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_kit import CORE_NAMES


@pytest.fixture
def install_project(tmp_path, monkeypatch):
    game = tmp_path / "game"
    managed = game / "Synthetic_Data/Managed"
    managed.mkdir(parents=True)
    assembly = managed / "Assembly-CSharp.dll"
    assembly.write_bytes(b"synthetic assembly; never executed")
    (game / "UnityPlayer.dll").write_bytes(b"synthetic engine; never executed")
    asset = game / "Synthetic_Data/resources.assets"
    asset.write_bytes(b"synthetic localization; never loaded")
    header = bytearray(128)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 60, 64)
    header[64:70] = b"PE\0\0\x64\x86"
    (game / "Synthetic.exe").write_bytes(header)  # Never launched.
    kit = tmp_path / "kit"
    names = ["core/" + name for name in CORE_NAMES] + [
        "winhttp.dll",
        "plugin/UnityTranslator.I2Mono.dll",
        "LICENSES/synthetic.txt",
    ]
    for name in names:
        path = kit / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("synthetic data only: " + name).encode())
    catalog = {
        "format_version": 1,
        "purpose": "bundled-i2mono-runtime",
        "assembly_sha256": hash_file(assembly),
        "managed_references": {"Assembly-CSharp.dll": hash_file(assembly)},
        "unity_player_sha256": hash_file(game / "UnityPlayer.dll"),
        "files": {name: hash_file(kit / name) for name in names},
        "runtime_files": {name: hash_file(kit / name) for name in names[:-1]},
    }
    monkeypatch.setattr("unitytranslator.runtime_kit.trusted_catalog", lambda: catalog)
    monkeypatch.setattr("unitytranslator.runtime_kit.bundled_kit_root", lambda: kit)
    monkeypatch.setattr(
        "unitytranslator.installation.DeploymentService",
        partial(DeploymentService, process_probe=lambda _: GameProcessStatus("closed")),
    )
    paths = ProjectPaths(game, tmp_path / "project")
    units = extract_i2(
        {
            "m_Name": "synthetic",
            "mLanguages": [{"Name": "English", "Code": "en"}],
            "mTerms": [
                {"Term": "UI/start-" + str(i), "TermType": 0, "Languages": ["Start {0}"]}
                for i in range(23)
            ],
        },
        "Synthetic_Data/resources.assets",
        1,
    )
    with ProjectRepository(paths) as repo:
        repo.ingest(
            units,
            {
                "source": units[0].source_file,
                "unity_versions": ["2017.4.19f1"],
                "i2_candidates": [{"object": 1, "source_set": "synthetic"}],
                "sha256_before": hash_file(asset),
                "sha256_after": hash_file(asset),
            },
        )
        for row in repo.page():
            repo.edit(row["unit_id"], row["version"], "Başla {0} · çğıİöşü")
        for row in repo.page():
            repo.approve(row["unit_id"], row["version"])
        yield repo, kit


def original_hashes(repo):
    return {
        p.relative_to(repo.paths.game).as_posix(): hash_file(p)
        for p in repo.paths.game.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize("target", ["winhttp.dll", "doorstop_config.ini"])
def test_foreign_loader_conflict_does_not_capture_baseline_or_stage_artifacts(
    install_project, target
):
    repo, _ = install_project
    loader = repo.paths.game / target
    loader.write_bytes(b"another installation; do not touch")
    before = original_hashes(repo)
    flow = InstallationSession(repo)
    with pytest.raises(ValueError, match=target):
        flow.prepare()
    assert DeploymentService(repo).read_baseline() is None
    assert original_hashes(repo) == before
    assert not repo.paths.output("artifacts").exists()
    assert flow.pending is None


def test_prepare_install_remove_uses_all_approved_records_and_requires_explicit_actions(
    install_project,
):
    repo, _ = install_project
    original = original_hashes(repo)
    approvals = repo.page(status="approved")
    flow = InstallationSession(repo)
    review = flow.prepare()
    assert review["records"] == 23 and len(review["files"]) == 2
    assert original_hashes(repo) == original  # Preparation writes only project artifacts.
    for consent in (False, 1, "true"):
        with pytest.raises(ValueError, match="açık kullanıcı"):
            flow.install(review["review_id"], user_action=consent, experimental_reviewed=True)
    result = flow.install(review["review_id"], user_action=True, experimental_reviewed=True)
    assert result["status"] == "installed" and result["application_verified"] is False
    assert result["original_changes"] == []
    status = flow.status()
    with pytest.raises(ValueError, match="açık kullanıcı"):
        flow.remove(status["deployment"]["plan_id"], user_action=False)
    removed = flow.remove(status["deployment"]["plan_id"], user_action=True)
    assert removed["status"] == "removed" and not removed["original_changes"]
    assert original_hashes(repo) == original
    assert repo.page(status="approved") == approvals


@pytest.mark.parametrize("change", ["approval", "runtime", "review", "engine", "asset"])
def test_changed_review_or_inputs_cannot_install(install_project, change):
    repo, _ = install_project
    flow = InstallationSession(repo)
    review = flow.prepare()
    if change == "approval":
        row = repo.page()[0]
        repo.edit(row["unit_id"], row["version"], "Yeni {0}")
    elif change == "runtime":
        extra = next(repo.paths.project.glob("artifacts/external-runtime-*/BepInEx/patchers"))
        (extra / "extra.dll").write_bytes(b"synthetic untrusted patcher; never executed")
    elif change == "review":
        repo.paths.output(review["review_relative"]).write_text("{}", encoding="utf-8")
    elif change == "engine":
        (repo.paths.game / "UnityPlayer.dll").write_bytes(b"changed synthetic engine")
    else:
        (repo.paths.game / "Synthetic_Data/resources.assets").write_bytes(
            b"changed synthetic source"
        )
    with pytest.raises(ValueError):
        flow.install(review["review_id"], user_action=True, experimental_reviewed=True)
    assert not (repo.paths.game / "winhttp.dll").exists()
    assert not (repo.paths.game / "doorstop_config.ini").exists()


def test_modified_owned_file_is_preserved_on_removal(install_project):
    repo, _ = install_project
    flow = InstallationSession(repo)
    review = flow.prepare()
    flow.install(review["review_id"], user_action=True, experimental_reviewed=True)
    (repo.paths.game / "winhttp.dll").write_bytes(b"user-modified addition; never executed")
    result = flow.remove(flow.status()["deployment"]["plan_id"], user_action=True)
    assert result["status"] == "recovery_required" and result["preserved"] == ["winhttp.dll"]
    assert (
        repo.paths.game / "winhttp.dll"
    ).read_bytes() == b"user-modified addition; never executed"
    assert not (repo.paths.game / "doorstop_config.ini").exists()


def test_runtime_kit_tamper_is_rejected(install_project):
    repo, kit = install_project
    source = kit / "core/BepInEx.Preloader.dll"
    source.write_bytes(b"changed synthetic loader")
    with pytest.raises(ValueError, match="değişmiş"):
        InstallationSession(repo).prepare()
    assert not (repo.paths.game / "winhttp.dll").exists()


def test_qt_installation_flow_uses_review_dialog_and_safe_remove(install_project, monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from test_ui import wait_for

    from unitytranslator.ui.window import InstallationReviewDialog, MainWindow

    repo, _ = install_project
    original = original_hashes(repo)
    paths = repo.paths
    repo.close()
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    errors, reviewed = [], []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    timer = QTimer()

    def review_dialog():
        dialog = app.activeModalWidget()
        if isinstance(dialog, InstallationReviewDialog):
            assert not dialog.install.isEnabled()
            assert not (paths.game / "winhttp.dll").exists()
            dialog.reviewed.setChecked(True)
            reviewed.append(True)
            dialog.install.click()

    timer.timeout.connect(review_dialog)
    timer.start(10)
    try:
        window.submit_open_project({"project": str(paths.project), "existing_only": True})
        window.show()
        wait_for(app, lambda: window.prepare_installation.isEnabled() or errors)
        assert not errors
        window.tabs.setCurrentIndex(7)
        window.prepare_installation.click()
        wait_for(
            app, lambda: window.deployment and window.deployment["status"] == "installed" or errors
        )
        assert reviewed == [True] and not errors
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes
        )
        window.remove_installation.click()
        wait_for(
            app, lambda: window.deployment and window.deployment["status"] == "removed" or errors
        )
        assert not errors
        assert {
            p.relative_to(paths.game).as_posix(): hash_file(p)
            for p in paths.game.rglob("*")
            if p.is_file()
        } == original
    finally:
        timer.stop()
        window.close()
        wait_for(app, lambda: window.backend_closed)
