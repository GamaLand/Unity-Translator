"""Export page: exports, packages and imports."""

from typing import Any

from unitytranslator.ui.i18n import tr
from unitytranslator.ui.pages.base import STOP, Completion, PageController


class ExportController(PageController):
    """Complete Export page results."""

    COMMANDS = {
        "import_apply": "import_changed",
        "import_restore": "import_changed",
        "export": "exported",
        "renpy_export": "renpy_exported",
        "renpy_package": "renpy_packaged",
        "textasset_export": "textassets_exported",
        "shareable_export": "shareable_exported",
        "runtime_export": "runtime_exported",
        "import_preview": "import_previewed",
    }

    def import_changed(self, command: str, result: Any) -> Completion:
        window = self.window
        window.refresh()
        window.refresh_installation()
        if command == "import_apply":
            window.export_status.setPlainText(
                tr(
                    "Imported {p0} translation candidates. Existing approvals are preserved.",
                    p0=f"{result['applied']}",
                )
            )
            window.import_button.setEnabled(False)
        if command == "import_restore":
            window.export_status.setPlainText(
                tr(
                    (
                        "Restored {p0} records with history. Imported approvals "
                        "remain archive information; review and approve translations "
                        "again in this project."
                    ),
                    p0=f"{result['restored_units']}",
                )
            )
            window.restore_button.setEnabled(False)
            window.bridge.submit("policies")
        return None

    def exported(self, command: str, result: Any) -> Completion:
        window = self.window
        window.export_status.setPlainText(tr("Translation project exported:\n") + result)
        return None

    def renpy_exported(self, command: str, result: Any) -> Completion:
        window = self.window
        if result.get("project_id") != window.current_project_id:
            return STOP
        window.export_status.setPlainText(tr(
            "Staged {files} Ren'Py files with {approved} approved translations. "
            "Files remain in the project. Folder: {folder}",
            files=str(result["files"]), approved=str(result["approved_translations"]),
            folder=result["folder"],
        ))
        return None

    def renpy_packaged(self, command: str, result: Any) -> Completion:
        window = self.window
        if result.get("project_id") != window.current_project_id:
            return STOP
        window.export_status.setPlainText(tr(
            "Created a Ren'Py ZIP with {records} approved translations. "
            "Install.cmd adds the patch to the selected game without copying it. ZIP: {path}",
            records=str(result["records"]), path=result["path"],
        ))
        return None

    def textassets_exported(self, command: str, result: Any) -> Completion:
        window = self.window
        if result.get("project_id") != window.current_project_id:
            return STOP
        window.export_status.setPlainText(tr(
            "Exported {sources} payloads with {approved} approved translations. "
            "Staged data only; use Apply to game for a reviewed installation. Folder: {folder}",
            sources=str(result["sources"]), approved=str(result["approved_translations"]),
            folder=result["folder"],
        ))
        return None

    def shareable_exported(self, command: str, result: Any) -> Completion:
        window = self.window
        if (
            result.get("project_id") != window.current_project_id
            or result.get("request_token") != window.shareable_export_token
        ):
            return STOP
        window.shareable_export_button.setEnabled(window.shareable_available)
        window.export_status.setPlainText(
            tr(
                (
                    "Shareable ZIP ready: {p1} · {p3} approved records · {p5} MiB"
                    " ZIP. The recipient extracts the ZIP and selects the game "
                    "folder with Kur.cmd. UnityTranslator, Python or a model is "
                    "not required. Existing files are not overwritten. "
                    "Compatibility is experimental; the game version is checked "
                    "on installation."
                ),
                p1=f"{result['path']}",
                p3=f"{result['records']}",
                p5=f"{result['bytes'] / 1048576:.1f}",
            )
        )
        return None

    def runtime_exported(self, command: str, result: Any) -> Completion:
        window = self.window
        if (
            result["project_id"] != window.current_project_id
            or result["request_token"] != window.runtime_export_token
        ):
            return STOP
        window.export_status.setPlainText(
            tr(
                (
                    "Trial data prepared for {p0} approved translations: {p2}. "
                    "In-game application is not yet verified. This file is not an"
                    " installation package. No files were added to the game "
                    "folder."
                ),
                p0=f"{result['records']}",
                p2=f"{result['path']}",
            )
        )
        return None

    def import_previewed(self, command: str, result: Any) -> Completion:
        window = self.window
        window.export_status.setPlainText(
            tr(
                (
                    "Eligible: {p1} · Conflicting human approvals: {p3} · "
                    "Different source revisions: {p5} · Missing: {p7} · "
                    "Importable history: {p9} · Archive ID conflicts: {p11}. "
                    "Approved records are not automatically overwritten. Restore "
                    "requires an empty project; imported approvals are not local "
                    "approvals."
                ),
                p1=f"{len(result['applicable'])}",
                p3=f"{len(result['approved_conflicts'])}",
                p5=f"{len(result['source_conflicts'])}",
                p7=f"{len(result['unknown'])}",
                p9=f"{len(result['archive_applicable'])}",
                p11=f"{len(result['archive_conflicts'])}",
            )
        )
        window.import_button.setEnabled(
            bool(result["applicable"] or result["archive_applicable"])
        )
        window.restore_button.setEnabled(result["restore_available"])
        return None
