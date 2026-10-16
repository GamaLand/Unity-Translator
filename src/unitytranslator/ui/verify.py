"""Synthetic offline verification entry for the standalone GUI."""

import json
import os
import struct
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from unitytranslator.discovery import probe_source
from unitytranslator.domain import TextUnitDraft
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.game_process import windows_process_snapshot
from unitytranslator.i2 import extract_i2
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_kit import CORE_NAMES, PortableRuntimeKit, RuntimeKit
from unitytranslator.ui.window import (
    BatchReviewDialog,
    InstallationReviewDialog,
    MainWindow,
    PluralEditorDialog,
    RuntimeSelectionDialog,
)


def verify_worker_launch(paths: ProjectPaths) -> bool:
    """Launch the real reader subprocess with an invalid GUI standard input handle."""
    import ctypes
    from ctypes import wintypes

    game = paths.output("verification-worker/game")
    game.mkdir(parents=True)
    source = game / "synthetic.assets"
    data = b"synthetic non-Unity input; no executable content"
    source.write_bytes(data)
    worker_paths = ProjectPaths(game, paths.output("verification-worker/project"))
    if os.name != "nt":
        return probe_source(worker_paths, source.name)["counts"]["records"] == 0
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    kernel.SetStdHandle.restype = wintypes.BOOL
    previous = kernel.GetStdHandle(-10)
    if not kernel.SetStdHandle(-10, 0xDEADBEEF):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        report = probe_source(worker_paths, source.name)
    finally:
        if not kernel.SetStdHandle(-10, previous):
            raise ctypes.WinError(ctypes.get_last_error())
    return report["counts"]["records"] == 0 and source.read_bytes() == data


def verify_installation(paths: ProjectPaths, app: QApplication) -> bool:
    """Exercise dialogs/plans/removal in a synthetic directory without executing DLLs."""
    from unitytranslator import runtime_kit

    # Separately verify bundled component integrity without loading the DLLs.
    RuntimeKit().validate()
    PortableRuntimeKit().validate()
    game = paths.output("verification-installation/game")
    assembly = game / "Synthetic_Data/Managed/Assembly-CSharp.dll"
    assembly.parent.mkdir(parents=True)
    assembly.write_bytes(b"synthetic assembly; never loaded")
    (game / "UnityPlayer.dll").write_bytes(b"synthetic engine; never loaded")
    asset = game / "Synthetic_Data/resources.assets"
    asset.write_bytes(b"synthetic localization; never loaded")
    header = bytearray(128)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 60, 64)
    header[64:70] = b"PE\0\0\x64\x86"
    (game / "Synthetic.exe").write_bytes(header)
    original = {
        p.relative_to(game): sha256(p.read_bytes()).hexdigest()
        for p in game.rglob("*")
        if p.is_file()
    }
    project = paths.output("verification-installation/project")
    units = extract_i2(
        {
            "m_Name": "synthetic",
            "mLanguages": [{"Name": "English", "Code": "en"}],
            "mTerms": [{"Term": "UI/start", "TermType": 0, "Languages": ["Start {0}"]}],
        },
        "Synthetic_Data/resources.assets",
        1,
    )
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        repo.ingest(
            units,
            {
                "source": units[0].source_file,
                "unity_versions": ["2017.4.19f1"],
                "i2_candidates": [{"object": 1, "source_set": "synthetic"}],
                "sha256_before": sha256(asset.read_bytes()).hexdigest(),
                "sha256_after": sha256(asset.read_bytes()).hexdigest(),
            },
        )
        row = repo.page()[0]
        repo.edit(row["unit_id"], row["version"], "Başla {0} · çğıİöşü")
        repo.approve(row["unit_id"], repo.page()[0]["version"])
    kit = paths.output("verification-installation/kit")
    names = ["core/" + name for name in CORE_NAMES] + [
        "winhttp.dll",
        "plugin/UnityTranslator.I2Mono.dll",
    ]
    for name in names:
        path = kit / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("synthetic inert fixture: " + name).encode())
    catalog = {
        "format_version": 1,
        "purpose": "bundled-i2mono-runtime",
        "assembly_sha256": sha256(assembly.read_bytes()).hexdigest(),
        "managed_references": {"Assembly-CSharp.dll": sha256(assembly.read_bytes()).hexdigest()},
        "unity_player_sha256": sha256((game / "UnityPlayer.dll").read_bytes()).hexdigest(),
        "files": {name: sha256((kit / name).read_bytes()).hexdigest() for name in names},
    }
    catalog["runtime_files"] = catalog["files"]
    previous_catalog, previous_root = runtime_kit.trusted_catalog, runtime_kit.bundled_kit_root
    runtime_kit.trusted_catalog, runtime_kit.bundled_kit_root = lambda: catalog, lambda: kit
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    timer = QTimer()
    state = {"ticks": 0, "step": 0}

    def confirm_remove():
        dialog = app.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            dialog.button(QMessageBox.StandardButton.Yes).click()
        else:
            errors.append(("remove_dialog", "Kaldırma incelemesi açılamadı."))

    def poll():
        state["ticks"] += 1
        dialog = app.activeModalWidget()
        if isinstance(dialog, InstallationReviewDialog):
            if dialog.install.isEnabled() or (game / "winhttp.dll").exists():
                errors.append(("install_consent", "Onay öncesi dosya oluşturuldu."))
                dialog.reject()
            else:
                dialog.reviewed.setChecked(True)
                dialog.install.click()
        elif errors or state["ticks"] > 1500:
            timer.stop()
            window.close()
        elif state["step"] == 0 and window.prepare_installation.isEnabled():
            state["step"] = 1
            window.tabs.setCurrentIndex(7)
            window.prepare_installation.click()
        elif (
            state["step"] == 1 and window.deployment and window.deployment["status"] == "installed"
        ):
            state["step"] = 2
            QTimer.singleShot(0, confirm_remove)
            window.remove_installation.click()
        elif state["step"] == 2 and window.deployment and window.deployment["status"] == "removed":
            state["step"] = 3
            timer.stop()
            window.grab().save(str(paths.output("reports/installation.png")))
            window.close()

    shareable_verified = False
    try:
        window.submit_open_project({"project": str(project), "existing_only": True})
        window.show()
        timer.timeout.connect(poll)
        timer.start(20)
        app.exec()
        if not errors and window.backend_closed:
            from unitytranslator import shareable

            previous_portable = shareable.PortableRuntimeKit
            try:
                shareable.PortableRuntimeKit = lambda: RuntimeKit(kit)
                with ProjectRepository(ProjectPaths(game, project)) as repo:
                    shared = shareable.export_shareable_patch(repo)
                shareable_verified = (
                    shared["records"] == 1
                    and not shared["game_written"]
                    and not shared["requires_unitytranslator"]
                    and Path(shared["path"]).is_file()
                )
            finally:
                shareable.PortableRuntimeKit = previous_portable
    finally:
        runtime_kit.trusted_catalog, runtime_kit.bundled_kit_root = previous_catalog, previous_root
    return bool(
        not errors
        and shareable_verified
        and state["step"] == 3
        and window.backend_closed
        and {
            p.relative_to(game): sha256(p.read_bytes()).hexdigest()
            for p in game.rglob("*")
            if p.is_file()
        }
        == original
    )


def verify_runtime_export(paths: ProjectPaths, app: QApplication) -> bool:
    """Exercise frozen approval, selection and data export without executing DLLs."""
    game = paths.output("verification-runtime/game")
    assembly = game / "Synthetic_Data/Managed/Assembly-CSharp.dll"
    assembly.parent.mkdir(parents=True)
    assembly.write_bytes(b"synthetic metadata; never loaded")
    original_hash = sha256(assembly.read_bytes()).hexdigest()
    project = paths.output("verification-runtime/project")
    units = extract_i2(
        {
            "m_Name": "synthetic",
            "mLanguages": [{"Name": "English", "Code": "en"}],
            "mTerms": [
                {"Term": key, "TermType": 0, "Languages": ["Start {0}"]}
                for key in ("UI/start", "UI/zz-candidate-1", "UI/zz-candidate-2")
            ],
        },
        "Synthetic_Data/resources.assets",
        1,
    )
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
        repo.edit(row["unit_id"], row["version"], "Başla {0} · çğıİöşü")
        repo.approve(row["unit_id"], repo.page()[0]["version"])
        for candidate in repo.page()[1:]:
            repo.edit(candidate["unit_id"], candidate["version"], "Başla {0} · çğıİöşü")
    window = MainWindow()
    errors = []
    results = []
    backups = []
    approvals = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.bridge.completed.connect(
        lambda command, result: results.append(result) if command == "runtime_export" else None
    )
    window.bridge.completed.connect(
        lambda command, result: backups.append(result) if command == "backup" else None
    )
    window.bridge.completed.connect(
        lambda command, result: approvals.append(result) if command == "approve_selection" else None
    )
    window.game_path.setText(str(game))
    window.project_path.setText(str(project))
    window.show()
    window.submit_open_project({"project": str(project), "existing_only": True})
    timer = QTimer()
    state = {"ticks": 0, "submitted": False}

    def choose():
        dialog = app.activeModalWidget()
        if not isinstance(dialog, RuntimeSelectionDialog) or dialog.table.rowCount() != 1:
            errors.append(("runtime_selection", "Sentetik kayıt seçimi açılamadı."))
            if dialog is not None:
                dialog.reject()
            return
        dialog.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        dialog.prepare.click()

    def choose_batch():
        dialog = app.activeModalWidget()
        if not isinstance(dialog, BatchReviewDialog) or len(dialog.rows) != 2:
            errors.append(("batch_review", "Grup incelemesi açılamadı."))
            if dialog is not None:
                dialog.reject()
            return
        if dialog.records() or dialog.confirm.isEnabled():
            errors.append(("batch_consent", "İnceleme seçimi başlangıçta boş olmalı."))
            dialog.reject()
            return
        dialog.select_records(True)
        dialog.reviewed.setChecked(True)
        dialog.confirm.click()

    def poll():
        state["ticks"] += 1
        if errors or state["ticks"] > 1500:
            timer.stop()
            window.close()
        elif not state["submitted"] and window.review_model.rowCount() == 3:
            state["submitted"] = True
            window.tabs.setCurrentIndex(6)
            QTimer.singleShot(0, choose)
            window.runtime_export_button.click()
        elif results and not state.get("batch_submitted"):
            if not window.grab().save(str(paths.output("reports/runtime-export.png"))):
                errors.append(("runtime_screenshot", "Deneme veri görüntüsü kaydedilemedi."))
            state["batch_submitted"] = True
            QTimer.singleShot(0, choose_batch)
            window.approve_page()
        elif approvals and not state.get("backup_submitted"):
            state["backup_submitted"] = True
            window.backup_project()
        elif backups:
            timer.stop()
            if not window.grab().save(str(paths.output("reports/project-backup.png"))):
                errors.append(("backup_screenshot", "Yedek görüntüsü kaydedilemedi."))
            window.close()

    timer.timeout.connect(poll)
    timer.start(20)
    app.exec()
    if errors or not results or not backups or not approvals or approvals[-1]["approved"] != 2:
        return False
    with ProjectRepository(ProjectRepository.existing_paths(Path(backups[-1]["folder"]))) as saved:
        if saved.count(status="approved") != 3:
            return False
    result = results[-1]
    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    return bool(
        result["records"] == 1
        and result["game_written"] is False
        and result["application"] == "unknown"
        and payload["entries"][0]["text"] == "Başla {0} · çğıİöşü"
        and sha256(assembly.read_bytes()).hexdigest() == original_hash
        and window.backend_closed
    )


def verify_ui(game: str, project: str) -> int:
    paths = ProjectPaths(Path(game), Path(project))
    if paths.project.exists():
        raise ValueError("UI doğrulaması yeni ve boş bir proje yolu gerektirir.")
    if any(paths.game.iterdir()):
        raise ValueError("UI doğrulaması yalnızca boş sentetik oyun klasöründe çalışır.")
    source = "Start {0}\r\nNext\u00a0line"
    plain_target = "Başla {0} · Iıİi çğöşü\r\nSonraki\u00a0satır"
    plural_source = "{[N]} turns[i2p_One]{[N]} turn[i2p_Zero]No turns"
    plural_target = "{[N]} tur[i2p_One]{[N]} tur[i2p_Zero]Tur yok"
    unfinished = "Yarım {\r\nçğıİöşü\u00a0"
    with ProjectRepository(paths) as repo:
        repo.ingest(
            [
                TextUnitDraft(
                    f"synthetic-{index}",
                    f"UI/{index:04}",
                    "synthetic.assets",
                    1,
                    "en",
                    plural_source if index == 1 else source,
                    sha256((plural_source if index == 1 else source).encode()).hexdigest(),
                    "UI",
                )
                for index in range(601)
            ],
            {"kind": "synthetic_ui_verification"},
        )
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    errors = []
    process_results = []
    window.bridge.completed.connect(
        lambda command, result: (
            process_results.append(result) if command == "game_process" else None
        )
    )
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, error: errors.append((command, error)))
    window.game_path.setText(str(paths.game))
    window.project_path.setText(str(paths.project))
    window.show()
    window.open_project()
    state = {"step": 0, "ticks": 0}
    timer = QTimer()

    def fill_plural_dialog():
        dialog = app.activeModalWidget()
        if not isinstance(dialog, PluralEditorDialog):
            errors.append(("plural_editor", "Çoğul düzenleyici açılmadı."))
            if dialog is not None:
                dialog.reject()
            return
        for form, text in {"Plural": "{[N]} tur", "One": "{[N]} tur", "Zero": "Tur yok"}.items():
            dialog.edits[form].setPlainText(text)
        dialog.tabs.setCurrentIndex(1)
        output = paths.output("reports/plural-editor.png")
        output.parent.mkdir(parents=True, exist_ok=True)
        if not dialog.grab().save(str(output)):
            errors.append(("plural_screenshot", "Çoğul görüntüsü kaydedilemedi."))
        if dialog.transfer.isEnabled():
            dialog.transfer.click()
        else:
            errors.append(("plural_format", "Sentetik çoğul taslağı kontrolü geçmedi."))
            dialog.reject()

    def poll():
        state["ticks"] += 1
        rows = window.review_model.rows
        if errors or state["ticks"] > 1500:
            timer.stop()
            paths.write_json("reports/ui-verification.json", {"passed": False, "errors": errors})
            window.close()
        elif state["step"] == 0 and len(rows) == 200:
            window.check_game_process()
            state["step"] = 10
        elif state["step"] == 10 and process_results:
            observed = process_results[-1]
            if observed["status"] != "unknown" or observed["reason"] != "no_executable_identity":
                errors.append(("game_process", "Boş sentetik oyunun durumu belirsiz olmalı."))
            window.tabs.setCurrentIndex(5)
            window.table.selectRow(0)
            window.translation_editor.setPlainText(plain_target)
            window.save_edit()
            state["step"] = 1
        elif state["step"] == 1 and rows and rows[0]["translation"] == plain_target:
            window.table.selectRow(0)
            window.approve()
            state["step"] = 2
        elif state["step"] == 2 and rows and rows[0]["status"] == "approved":
            window.table.selectRow(1)
            state["step"] = 3
            QTimer.singleShot(0, fill_plural_dialog)
            window.plural_button.click()
            if window.translation_editor.toPlainText() != plural_target:
                errors.append(("plural_transfer", "Çoğul taslağı aktarılamadı."))
            else:
                window.save_edit()
            state["step"] = 4
        elif state["step"] == 4 and rows and rows[1]["translation"] == plural_target:
            if rows[1]["status"] != "needs_review" or rows[0]["status"] != "approved":
                errors.append(("plural_approval", "Onay/dal inceleme durumu eşleşmiyor."))
            prompt_present = (
                files("unitytranslator.resources").joinpath("translate-plural-v2.txt").is_file()
            )
            if not prompt_present:
                errors.append(("plural_prompt", "Çoğul istem kaynağı pakette bulunamadı."))
            output = paths.output("reports/ui.png")
            output.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(output)):
                errors.append(("screenshot", "Arayüz görüntüsü kaydedilemedi."))
            paths.write_json(
                "reports/ui-verification.json",
                {
                    "passed": not errors,
                    "errors": errors,
                    "rows_in_model": len(rows),
                    "source_records": 601,
                    "approved_translation": rows[0]["translation"],
                    "plural_editor_verified": not errors,
                    "plural_prompt_present": prompt_present,
                    "plural_translation": rows[1]["translation"],
                    "editor_unicode_preserved": rows[0]["translation"] == plain_target,
                },
            )
            state["step"] = 5
            timer.stop()
            window.table.selectRow(2)
            window.translation_editor.setPlainText(unfinished)
            window.close()

    timer.timeout.connect(poll)
    timer.start(20)
    app.exec()
    report = json.loads(paths.output("reports/ui-verification.json").read_text(encoding="utf-8"))
    report["game_process_verified"] = bool(
        process_results
        and process_results[-1]["status"] == "unknown"
        and process_results[-1]["reason"] == "no_executable_identity"
    )
    try:
        report["windows_process_api_verified"] = any(
            item.pid == os.getpid() and item.image is not None and item.image.is_file()
            for item in windows_process_snapshot()
        )
    except OSError:
        report["windows_process_api_verified"] = False
    with ProjectRepository(paths) as reopened:
        saved = EditorDraftStore(reopened).get("synthetic-2")
        report["draft_autosave_verified"] = (
            saved is not None
            and saved["text"] == unfinished
            and reopened.page()[2]["translation"] is None
            and reopened.page()[0]["status"] == "approved"
        )
    report["runtime_export_verified"] = verify_runtime_export(paths, app)
    report["batch_approval_verified"] = report["runtime_export_verified"]
    report["installation_verified"] = verify_installation(paths, app)
    report["shareable_export_verified"] = report["installation_verified"]
    report["worker_invalid_stdin_verified"] = verify_worker_launch(paths)
    report["passed"] = (
        report["passed"]
        and report["draft_autosave_verified"]
        and report["game_process_verified"]
        and report["windows_process_api_verified"]
        and report["runtime_export_verified"]
        and report["installation_verified"]
        and report["worker_invalid_stdin_verified"]
    )
    paths.write_json("reports/ui-verification.json", report)
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["passed"] else 1
