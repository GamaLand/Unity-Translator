import json
import os
from pathlib import Path

import pytest
from test_ui import wait_for

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from unitytranslator.filesystem import ProjectPaths, hash_file  # noqa: E402
from unitytranslator.i2 import extract_i2  # noqa: E402
from unitytranslator.repository import ProjectRepository  # noqa: E402
from unitytranslator.ui.window import MainWindow, RuntimeSelectionDialog  # noqa: E402


def test_selection_dialog_limit_excludes_unapproved_and_does_not_autoselect():
    QApplication.instance() or QApplication([])
    rows = [
        {
            "unit_id": str(i),
            "original_key": f"UI/{i}",
            "status": "approved",
            "translation": "Türkçe",
            "source_revision": "s",
            "translation_revision": "t",
            "version": 2,
        }
        for i in range(11)
    ]
    rows.append({**rows[0], "status": "needs_review"})
    dialog = RuntimeSelectionDialog(rows)
    assert dialog.table.rowCount() == 11 and dialog.records() == []
    assert not dialog.prepare.isEnabled()
    for index in range(10):
        dialog.table.item(index, 0).setCheckState(Qt.CheckState.Checked)
    assert dialog.prepare.isEnabled() and len(dialog.records()) == 10
    dialog.table.item(10, 0).setCheckState(Qt.CheckState.Checked)
    assert not dialog.prepare.isEnabled()


def test_ui_exports_selected_human_approved_data_and_ignores_stale_result(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    game = tmp_path / "game"
    assembly = game / "Synthetic_Data/Managed/Assembly-CSharp.dll"
    assembly.parent.mkdir(parents=True)
    assembly.write_bytes(b"synthetic metadata; never executed")
    units = extract_i2(
        {
            "m_Name": "synthetic",
            "mLanguages": [{"Name": "English", "Code": "en"}],
            "mTerms": [{"Term": "UI/start", "TermType": 0, "Languages": ["Start {0}"]}],
        },
        "Synthetic_Data/resources.assets",
        1,
    )
    project = tmp_path / "project"
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        repo.ingest(
            units,
            {
                "source": units[0].source_file,
                "unity_versions": ["2017.4.19f1"],
                "i2_candidates": [{"object": 1, "source_set": "synthetic"}],
            },
        )
        row = repo.page()[0]
        repo.edit(row["unit_id"], row["version"], "Başla {0}")
        repo.approve(row["unit_id"], repo.page()[0]["version"])
    before = hash_file(assembly)

    def choose(dialog):
        assert dialog.table.rowCount() == 1
        dialog.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(RuntimeSelectionDialog, "exec", choose)
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.game_path.setText(str(game))
    window.project_path.setText(str(project))
    window.show()
    window.open_project()
    try:
        wait_for(app, lambda: window.review_model.rowCount() == 1)
        window.tabs.setCurrentIndex(6)
        window.runtime_export_button.click()
        wait_for(app, lambda: "deneme verisi hazırlandı" in window.export_status.toPlainText())
        output = next(project.glob("artifacts/i2mono/selection-*.json"))
        assert json.loads(output.read_text(encoding="utf-8"))["entries"][0]["text"] == "Başla {0}"
        assert hash_file(assembly) == before
        message = window.export_status.toPlainText()
        assert "kurulum paketi değildir" in message
        window.completed("runtime_export", {"project_id": "old-project", "request_token": "old"})
        assert window.export_status.toPlainText() == message
        window.completed(
            "runtime_export", {"project_id": window.current_project_id, "request_token": "old"}
        )
        assert window.export_status.toPlainText() == message
        image = Path(".cache/ui-runtime-export.png")
        assert window.grab().save(str(image))
        assert not errors
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
