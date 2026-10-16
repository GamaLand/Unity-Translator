import json
import os
import sys
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QAbstractTableModel, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QActionGroup,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStyle,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from unitytranslator import __version__
from unitytranslator.review_selection import canonical_all_confirmation
from unitytranslator.ui.bridge import BackendBridge
from unitytranslator.ui.drafts import DraftController
from unitytranslator.ui.i18n import (
    LANGUAGES,
    active_language,
    diagnostic,
    preferred_language,
    save_language,
    tr,
)
from unitytranslator.ui.i18n import (
    localized_issue_label as issue_label,
)
from unitytranslator.ui.text_editor import DataTextEdit
from unitytranslator.validation import (
    format_issues,
    join_plural_branches,
    plural_branches,
)

STATUS = {
    "pending": tr("Pending"),
    "processing": tr("Processing"),
    "translated": tr("Translated"),
    "validation_error": tr("Validation error"),
    "needs_review": tr("Needs review"),
    "approved": tr("Approved"),
}
JOB_STATUS = {
    "queued": tr("Queued"),
    "running": tr("Running"),
    "pausing": tr("Pausing"),
    "paused": tr("Paused"),
    "completed": tr("Completed"),
    "completed_with_errors": tr("Completed with errors"),
    "cancelled": tr("Cancelled"),
    "failed": tr("Failed"),
}


class ReviewModel(QAbstractTableModel):
    columns = [
        ("original_key", tr("Record")),
        ("source_text", tr("Source preview")),
        ("translation", tr("Translation preview")),
        ("category", tr("Category")),
        ("status", tr("Status")),
        ("issues_json", tr("Checks")),
    ]

    def __init__(self):
        super().__init__()
        self.rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent=None):
        return len(self.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            key = self.columns[index.column()][0]
            value = self.rows[index.row()].get(key) or ""
            if key == "status":
                return STATUS.get(value, value)
            if key == "issues_json":
                return "; ".join(issue_label(code) for code in json.loads(value)) if value else ""
            return str(value)[:180].replace("\n", " ↵ ")
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section][1]
        return None


class PluralEditorDialog(QDialog):
    """Bir kaydın dallarını gösterir; DB'ye yazmaz veya onay vermez."""

    labels = {"Plural": tr("Default (plural)"), "One": tr("Singular (1)"), "Zero": tr("Zero (0)")}

    def __init__(self, source, translated, parent=None, is_current=None):
        super().__init__(parent)
        self.original = source
        self.branches = plural_branches(source)
        if len(self.branches) < 2:
            raise ValueError(tr("This record has no supported plural branches."))
        targets = plural_branches(translated) if translated.strip() else {}
        if targets and list(targets) != list(self.branches):
            raise ValueError(
                tr("Draft plural branches do not match the source; fix the main draft first.")
            )
        self.value = None
        self.is_current = is_current
        self.sources = {}
        self.edits = {}
        self.setWindowTitle(tr("Review and edit plural branches"))
        self.resize(1050, 600)
        layout = QVBoxLayout(self)
        note = QLabel(
            tr(
                "Preserve variables and formatting tags. Branch separators "
                "are preserved automatically. Save and review the transferred"
                " draft on the main screen. Check values 0/1/2 in the game "
                "separately."
            )
        )
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        for form, text in self.branches.items():
            tab = QWidget()
            row = QHBoxLayout(tab)
            for heading, content, read_only, fields in (
                (tr("Source"), text, True, self.sources),
                (tr("Translation"), targets.get(form, ""), False, self.edits),
            ):
                column = QVBoxLayout()
                column.addWidget(QLabel(heading))
                editor = QTextEdit() if read_only else DataTextEdit(reference=text)
                editor.setReadOnly(read_only)
                editor.setPlainText(content)
                fields[form] = editor
                column.addWidget(editor)
                row.addLayout(column)
            self.tabs.addTab(tab, self.labels[form])
        layout.addWidget(self.tabs)
        self.feedback = QLabel()
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        buttons = QHBoxLayout()
        self.transfer = QPushButton(tr("Transfer branches to the main draft"))
        self.transfer.clicked.connect(self.apply_draft)
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.transfer)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        for field in self.edits.values():
            field.textChanged.connect(self.validate_draft)
        self.validate_draft()

    def candidate_text(self):
        return join_plural_branches({form: field.value() for form, field in self.edits.items()})

    def validate_draft(self):
        if any(not field.value().strip() for field in self.edits.values()):
            self.transfer.setEnabled(False)
            self.feedback.setText(tr("Enter a translation for every branch."))
            return
        errors = format_issues(self.original, self.candidate_text())
        self.transfer.setEnabled(not errors)
        self.feedback.setText(
            "; ".join(issue_label(code) for code in errors)
            if errors
            else tr("Format check passed. Review the meaning and each branch separately.")
        )

    def apply_draft(self):
        self.validate_draft()
        if not self.transfer.isEnabled():
            return
        if self.is_current is not None and not self.is_current():
            self.feedback.setText(
                tr(
                    "The record or draft changed. Copy your edits to preserve "
                    "them, then reopen the current record."
                )
            )
            return  # Pencere açık kalır; kullanıcının düzenlemesi kaybolmaz.
        self.value = self.candidate_text()
        self.accept()


class CandidateHistoryDialog(QDialog):
    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.history = history
        self.chosen = None
        self.setWindowTitle(tr("Translation history and new candidates · Last 200 revisions"))
        self.resize(1000, 650)
        layout = QVBoxLayout(self)
        self.combo = QComboBox()
        for row in history["revisions"]:
            current_source = row["source_revision"] == history["current"]["source_revision"]
            label = {"model": tr("Model"), "manual": tr("Manual edit"), "import": tr("Import")}[
                row["origin"]
            ]
            self.combo.addItem(
                f"{row['created_at']} · {label} · "
                + (tr("Current source") if current_source else tr("Previous source"))
            )
        layout.addWidget(self.combo)
        split = QSplitter()
        self.source = QTextEdit()
        self.source.setReadOnly(True)
        self.translation = QTextEdit()
        self.translation.setReadOnly(True)
        split.addWidget(self.source)
        split.addWidget(self.translation)
        layout.addWidget(split)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(120)
        layout.addWidget(self.details)
        layout.addWidget(
            QLabel(
                tr(
                    "Candidates from older sources are read-only. The selected "
                    "current candidate becomes a draft and requires separate "
                    "human approval."
                )
            )
        )
        self.replace = QCheckBox(
            tr("I choose to revoke the existing approval for this candidate selection")
        )
        self.replace.setVisible(history["current"]["status"] == "approved")
        layout.addWidget(self.replace)
        self.use = QPushButton(tr("Use selected candidate as draft"))
        self.use.clicked.connect(self.pick)
        layout.addWidget(self.use)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.combo.currentIndexChanged.connect(self.changed)
        self.replace.toggled.connect(self.changed)
        self.changed()

    def changed(self, *args):
        index = self.combo.currentIndex()
        if index < 0:
            self.use.setEnabled(False)
            return
        row = self.history["revisions"][index]
        self.source.setPlainText(row["source_text"])
        self.translation.setPlainText(row["text"])
        self.details.setPlainText(
            "; ".join(issue_label(code) for code in json.loads(row["issues_json"]))
            + "\n"
            + json.dumps(json.loads(row["metadata_json"]), ensure_ascii=False)
        )
        current = self.history["current"]
        self.use.setEnabled(
            bool(
                current["active"]
                and row["source_revision"] == current["source_revision"]
                and row["id"] != current["translation_revision"]
                and (current["status"] != "approved" or self.replace.isChecked())
            )
        )

    def pick(self):
        if self.use.isEnabled():
            self.chosen = self.history["revisions"][self.combo.currentIndex()]["id"]
            self.accept()


class RuntimeSelectionDialog(QDialog):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Select records for a small translation trial"))
        self.resize(760, 440)
        self.rows = [row for row in rows if row["status"] == "approved"]
        layout = QVBoxLayout(self)
        note = QLabel(
            tr(
                "Select 1–10 approved records from the current review page. "
                "Only translation data is prepared; in-game application is "
                "not yet verified."
            )
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(note)
        self.table = QTableWidget(len(self.rows), 3)
        self.table.setHorizontalHeaderLabels(
            [tr("Select"), tr("Record"), tr("Approved translation")]
        )
        for index, row in enumerate(self.rows):
            choice = QTableWidgetItem()
            choice.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            choice.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(index, 0, choice)
            for column, key in ((1, "original_key"), (2, "translation")):
                item = QTableWidgetItem(row[key] or "")
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(index, column, item)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.count = QLabel()
        layout.addWidget(self.count)
        self.prepare = QPushButton(tr("Prepare selected translation data"))
        self.prepare.clicked.connect(self.accept)
        layout.addWidget(self.prepare)
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.table.itemChanged.connect(self.update_selection)
        self.update_selection()

    def records(self):
        return [
            {
                key: row[key]
                for key in ("unit_id", "source_revision", "translation_revision", "version")
            }
            for index, row in enumerate(self.rows)
            if self.table.item(index, 0).checkState() == Qt.CheckState.Checked
        ]

    def update_selection(self):
        count = len(self.records())
        self.count.setText(tr("{p0} records selected · limit: 10", p0=f"{count}"))
        self.prepare.setEnabled(1 <= count <= 10)


class BatchReviewDialog(QDialog):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.setWindowTitle(tr("Approve reviewed translations as a group"))
        self.resize(1100, 700)
        layout = QVBoxLayout(self)
        note = QLabel(
            tr(
                "Only eligible candidates on this review page are shown. "
                "Drafts and existing approvals are excluded. Select each "
                "record to review source, translation and warnings; check the"
                " records you want to approve."
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        controls = QHBoxLayout()
        select = QPushButton(tr("Select all eligible records"))
        select.clicked.connect(lambda: self.select_records(True))
        clear = QPushButton(tr("Clear selection"))
        clear.clicked.connect(lambda: self.select_records(False))
        controls.addWidget(select)
        controls.addWidget(clear)
        layout.addLayout(controls)
        self.table = QTableWidget(len(rows), 3)
        self.table.setHorizontalHeaderLabels(
            [tr("Select"), tr("Record"), tr("Translation preview")]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        for column in (1, 2):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.Stretch
            )
        for index, row in enumerate(rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(index, 0, check)
            self.table.setItem(index, 1, QTableWidgetItem(row["original_key"]))
            self.table.setItem(
                index, 2, QTableWidgetItem(row["translation"][:180].replace("\n", " ↵ "))
            )
        layout.addWidget(self.table)
        split = QSplitter()
        self.source, self.target = QTextEdit(), QTextEdit()
        for editor in (self.source, self.target):
            editor.setReadOnly(True)
            split.addWidget(editor)
        layout.addWidget(split)
        self.issues = QLabel()
        self.issues.setTextFormat(Qt.TextFormat.PlainText)
        self.issues.setWordWrap(True)
        layout.addWidget(self.issues)
        self.reviewed = QCheckBox(tr("I reviewed the selected sources, translations and warnings."))
        layout.addWidget(self.reviewed)
        self.confirm = QPushButton(tr("Nothing selected"))
        self.confirm.setEnabled(False)
        self.confirm.clicked.connect(self.accept)
        layout.addWidget(self.confirm)
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.table.itemChanged.connect(self.selection_edited)
        self.table.itemSelectionChanged.connect(self.show_record)
        self.reviewed.toggled.connect(self.update_count)
        if rows:
            self.table.selectRow(0)

    def records(self):
        return [
            {
                key: row[key]
                for key in ("unit_id", "source_revision", "translation_revision", "version")
            }
            for index, row in enumerate(self.rows)
            if self.table.item(index, 0).checkState() == Qt.CheckState.Checked
        ]

    def select_records(self, selected):
        self.table.blockSignals(True)
        for index in range(len(self.rows)):
            self.table.item(index, 0).setCheckState(
                Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked
            )
        self.table.blockSignals(False)
        self.selection_edited()

    def selection_edited(self, *args):
        self.reviewed.setChecked(False)
        self.update_count()

    def update_count(self):
        count = len(self.records())
        self.confirm.setText(tr("Approve my {p1} selected translations", p1=f"{count}"))
        self.confirm.setEnabled(count > 0 and self.reviewed.isChecked())

    def show_record(self):
        index = self.table.currentRow()
        if index >= 0:
            row = self.rows[index]
            self.source.setPlainText(row["source_text"])
            self.target.setPlainText(row["translation"])
            warnings = json.loads(row.get("issues_json") or "[]")
            self.issues.setText(
                tr("Warnings: ")
                + (
                    "; ".join(issue_label(code) for code in warnings)
                    or tr("Format check passed; review the meaning yourself.")
                )
            )


class AllApprovalDialog(QDialog):
    def __init__(self, preview, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Approve all translations · 1 / 2"))
        self.resize(600, 330)
        self.stage = 1
        self.phrase = tr("approve {p0} translations", p0=f"{preview['count']}")
        layout = QVBoxLayout(self)
        note = QLabel(
            tr(
                (
                    "Warning: {p1} translations across the entire project will be"
                    " approved. This ignores pages, search and filters. "
                    "Translations become human-approved and eligible for a "
                    "translation package. There is no bulk undo button. Records "
                    "with review warnings: {p3}. Excluded due to drafts or format"
                    " problems: {p5}. Existing approvals, untranslated records "
                    "and active requests are excluded."
                ),
                p1=f"{preview['count']}",
                p3=f"{preview['warnings']}",
                p5=f"{preview['excluded']}",
            )
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(note)
        self.acknowledge = QCheckBox(
            tr("I evaluated the warnings and want to approve all these translations.")
        )
        layout.addWidget(self.acknowledge)
        self.instruction = QLabel(tr("Step 1 does not approve any translations yet."))
        self.instruction.setWordWrap(True)
        self.instruction.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.instruction)
        self.confirmation = QLineEdit()
        self.confirmation.setAccessibleName(tr("Final approval verification text"))
        self.confirmation.hide()
        layout.addWidget(self.confirmation)
        self.confirm = QPushButton(tr("Continue · Go to step 2"))
        self.confirm.setAutoDefault(False)
        self.confirm.setEnabled(False)
        self.confirm.clicked.connect(self.advance)
        layout.addWidget(self.confirm)
        cancel = QPushButton(tr("Cancel"))
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.acknowledge.toggled.connect(self.update_confirmation)
        self.confirmation.textChanged.connect(self.update_confirmation)

    def update_confirmation(self):
        self.confirm.setEnabled(
            self.acknowledge.isChecked()
            and (self.stage == 1 or self.confirmation.text() == self.phrase)
        )

    def advance(self):
        if not self.confirm.isEnabled():
            return
        if self.stage == 1:
            self.stage = 2
            self.setWindowTitle(tr("Approve all translations · 2 / 2"))
            self.acknowledge.setEnabled(False)
            self.instruction.setText(
                tr("For final approval, enter this exact phrase:\n")
                + self.phrase
                + tr("\nCancelling leaves all records unchanged.")
            )
            self.confirmation.show()
            self.confirmation.setFocus()
            self.confirm.setText(tr("Approve all translations now"))
            self.update_confirmation()
        elif self.confirmation.text() == self.phrase:
            self.accept()


class InstallationReviewDialog(QDialog):
    def __init__(self, review, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Game installation plan"))
        self.resize(950, 440)
        layout = QVBoxLayout(self)
        summary = QLabel(
            tr(
                (
                    "{p0} human-approved translations will be applied. Game: "
                    "{p2}. {p4} original files will be protected. Existing files "
                    "are not overwritten. General game compatibility is "
                    "experimental. Start the game yourself with your usual "
                    "launcher after installation."
                ),
                p0=f"{review['records']}",
                p2=f"{review['game']}",
                p4=f"{review['original_files']}",
            )
        )
        summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.setWordWrap(True)
        layout.addWidget(summary)
        table = QTableWidget(len(review["files"]), 2)
        table.setHorizontalHeaderLabels([tr("New file to add to game root"), "SHA-256"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for index, item in enumerate(review["files"]):
            table.setItem(index, 0, QTableWidgetItem(item["target"]))
            table.setItem(index, 1, QTableWidgetItem(item["sha256"]))
        layout.addWidget(table)
        if review["exclusions"]:
            exclusions = QLabel(
                tr("Separately tracked variable files: ")
                + ", ".join(item["path"] for item in review["exclusions"])
            )
            exclusions.setTextFormat(Qt.TextFormat.PlainText)
            exclusions.setWordWrap(True)
            layout.addWidget(exclusions)
        self.reviewed = QCheckBox(
            tr("I reviewed the experimental scope and approve adding these two new files.")
        )
        layout.addWidget(self.reviewed)
        row = QHBoxLayout()
        self.install = QPushButton(tr("Apply approved translations to game"))
        self.install.setEnabled(False)
        self.reviewed.toggled.connect(self.install.setEnabled)
        self.install.clicked.connect(self.accept)
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        row.addWidget(self.install)
        row.addWidget(cancel)
        layout.addLayout(row)


class MainWindow(QMainWindow):
    def __init__(self, bridge=None):
        super().__init__()
        self.setWindowTitle(tr("UnityTranslator — Local translation project"))
        if not QFontDatabase.families():
            # Qt offscreen font keşfi bulunmayabilir; Windows fontu yalnızca okunur.
            fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for name in ("segoeui.ttf", "msyh.ttc"):
                font = fonts / name
                if font.is_file():
                    QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont("Segoe UI", 10))
        self.resize(1280, 850)
        self.bridge = bridge or BackendBridge()
        self.bridge.completed.connect(self.completed)
        self.bridge.failed.connect(self.failed)
        self.bridge.progress.connect(self.on_progress)
        self.bridge.stopped.connect(self.backend_stopped)
        self.offset = 0
        self.review_count = 0
        self.page_pending = False
        self.current_item = None
        self.game_process_token = None
        self.runtime_export_token = None
        self.shareable_export_token = None
        self.current_project_id = None
        self.open_project_folder = None
        self.project_totals = None
        self.deployment = None
        self.deployment_token = None
        self.deployment_status_token = None
        self.installation_kit_available = False
        self.approve_selection_token = None
        self.approve_all_token = None
        self.bulk_readiness_token = None
        self.page_token = None
        self.editor_loading = False
        self.draft_deferred = None
        self.draft_refresh_pending = False
        self.drafts = DraftController(self.bridge, self)
        self.drafts.changed.connect(self.draft_state_changed)
        self.drafts.action_finished.connect(self.draft_action_finished)
        self.drafts.failure.connect(self.draft_failed)
        self.current_job = None
        self.job_summaries = {}
        self.project_open = False
        self.closing = False
        self.backend_closed = False
        self.import_path = None
        self.styles = {}
        self.style_key = "default"
        body = QWidget()
        layout = QVBoxLayout(body)
        title = QLabel("UnityTranslator")
        title.setStyleSheet("font-size: 25px; font-weight: 600; padding: 8px;")
        layout.addWidget(title)
        self.summary = QLabel(
            tr("Select a game folder and a separate project folder. Game files are read-only.")
        )
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.next_step = QPushButton(tr("Create or open a project first"))
        self.next_step.setEnabled(False)
        self.next_step.clicked.connect(self.go_next_step)
        layout.addWidget(self.next_step)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.project_tab()
        self.sources_tab()
        self.model_tab()
        self.policy_tab()
        self.translation_tab()
        self.review_tab()
        self.export_tab()
        self.installation_tab()
        for label in self.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)
        for index in range(1, self.tabs.count()):
            self.tabs.setTabEnabled(index, False)
        self.setCentralWidget(body)
        help_menu = self.menuBar().addMenu(tr("Help"))
        for label, name in (
            (tr("User guide"), "README-WINDOWS.md"),
            (tr("Licenses and source code"), "SOURCE-ACCESS.md"),
        ):
            action = help_menu.addAction(label)
            action.triggered.connect(lambda _, value=name: self.open_help_document(value))
        about = help_menu.addAction(tr("About UnityTranslator"))
        about.triggered.connect(
            lambda: QMessageBox.about(
                self,
                "UnityTranslator",
                tr(
                    (
                        "UnityTranslator {p1} · Local AI translation and review. "
                        "Project code is MIT licensed. Uses Qt for Python / PySide6. "
                        "In-game application is experimental. License and source "
                        "information is in Help."
                    ),
                    p1=f"{__version__}",
                ),
            )
        )
        self.language_menu = self.menuBar().addMenu(tr("Language"))
        self.language_actions = QActionGroup(self)
        self.language_actions.setExclusive(True)
        for code, name in LANGUAGES.items():
            action = self.language_menu.addAction(name)
            action.setCheckable(True)
            action.setData(code)
            action.setChecked(code == preferred_language())
            self.language_actions.addAction(action)
            action.triggered.connect(lambda _, selected=code: self.select_ui_language(selected))
        self.statusBar().showMessage(
            tr("Local processing • Telemetry off • Game application: experimental")
        )
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.refresh)
        self.bulk_timer = QTimer(self)
        self.bulk_timer.setSingleShot(True)
        self.bulk_timer.setInterval(300)
        self.bulk_timer.timeout.connect(self.refresh_bulk_readiness)
        for signal in (
            self.model.editTextChanged,
            self.provider.currentIndexChanged,
            self.address.textChanged,
            self.context_tokens.valueChanged,
            self.output_tokens.valueChanged,
            self.temperature.valueChanged,
            self.structured.toggled,
        ):
            signal.connect(self.schedule_bulk_readiness)
        for key, action in (
            (QKeySequence.StandardKey.Open, self.open_existing_project),
            (QKeySequence.StandardKey.Save, self.save_edit),
            (QKeySequence.StandardKey.Find, self.focus_search),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)

    def tab(self, name):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.tabs.addTab(widget, name)
        return layout

    def project_tab(self):
        layout = self.tab(tr("1 · Project"))
        form = QFormLayout()
        self.game_path = QLineEdit()
        self.project_path = QLineEdit()
        for label, field in (
            (tr("Game folder"), self.game_path),
            (tr("Project folder"), self.project_path),
        ):
            row = QWidget()
            horizontal = QHBoxLayout(row)
            horizontal.setContentsMargins(0, 0, 0, 0)
            horizontal.addWidget(field)
            browse = QPushButton(tr("Select…"))
            browse.clicked.connect(lambda _, f=field: self.choose_directory(f))
            horizontal.addWidget(browse)
            form.addRow(label, row)
        self.source_language = QComboBox()
        self.target_language = QComboBox()
        for combo in (self.source_language, self.target_language):
            combo.setEditable(True)
            combo.addItems(["en", "tr", "fr", "de", "es"])
        self.target_language.setCurrentText("tr")
        form.addRow(tr("Source language"), self.source_language)
        form.addRow(tr("Target language"), self.target_language)
        layout.addLayout(form)
        open_button = QPushButton(tr("Create / open project"))
        open_button.clicked.connect(self.open_project)
        layout.addWidget(open_button)
        existing = QPushButton(tr("Open existing project…"))
        existing.setToolTip(
            tr("Select only the project folder; the saved game and language settings are used.")
        )
        existing.clicked.connect(self.open_existing_project)
        layout.addWidget(existing)
        note = QLabel(
            tr(
                "First use: select a game folder and a separate project "
                "folder, then Create / open project. Continue through Texts →"
                " Model → Translate. Glossary is optional. Use Open existing "
                "project to resume; translations and the saved language pair "
                "are preserved."
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.project_folder_button = QPushButton(tr("Open project folder"))
        self.project_folder_button.setEnabled(False)
        self.project_folder_button.clicked.connect(self.show_project_folder)
        layout.addWidget(self.project_folder_button)
        layout.addStretch()

    def sources_tab(self):
        layout = self.tab(tr("2 · Texts"))
        scan_button = QPushButton(tr("Read-only compatibility scan"))
        scan_button.clicked.connect(lambda: self.bridge.submit("scan"))
        layout.addWidget(scan_button)
        game_check = QPushButton(tr("Check whether the game is running"))
        game_check.clicked.connect(self.check_game_process)
        layout.addWidget(game_check)
        self.game_process_status = QLabel(tr("Game process state has not been checked."))
        self.game_process_status.setWordWrap(True)
        self.game_process_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.game_process_status)
        self.source_file = QComboBox()
        self.source_file.setEditable(True)
        layout.addWidget(QLabel(tr("After scanning, select the source file to inspect:")))
        layout.addWidget(self.source_file)
        extract = QPushButton(tr("Read the source and extract text"))
        extract.clicked.connect(
            lambda: self.bridge.submit("extract", {"source": self.source_file.currentText()})
        )
        layout.addWidget(extract)
        self.discovery = QTextEdit()
        self.discovery.setReadOnly(True)
        layout.addWidget(self.discovery)

    def check_game_process(self):
        if not self.project_open:
            return
        self.game_process_token = uuid4().hex
        self.game_process_status.setText(tr("Checking game process state…"))
        self.bridge.submit("game_process", {"request_token": self.game_process_token})

    def model_tab(self):
        layout = self.tab(tr("3 · Model"))
        form = QFormLayout()
        self.provider = QComboBox()
        self.provider.addItem("LM Studio", "lm-studio")
        self.provider.addItem("llama.cpp", "llama-cpp")
        self.address = QLineEdit("http://127.0.0.1:1234")
        self.model = QComboBox()
        self.model.setEditable(True)
        form.addRow(tr("Provider"), self.provider)
        form.addRow(tr("Local server"), self.address)
        form.addRow(tr("Model"), self.model)
        layout.addLayout(form)
        controls = QHBoxLayout()
        listing = QPushButton(tr("List models"))
        listing.clicked.connect(lambda: self.bridge.submit("models", self.model_data()))
        testing = QPushButton(tr("Synthetic connection / format test"))
        testing.clicked.connect(lambda: self.bridge.submit("connection_test", self.model_data()))
        controls.addWidget(listing)
        controls.addWidget(testing)
        layout.addLayout(controls)
        self.model_status = QLabel(
            tr(
                "The server/model is not started automatically. A generation "
                "test may trigger the server's own automatic loading "
                "settings."
            )
        )
        self.model_status.setWordWrap(True)
        layout.addWidget(self.model_status)
        advanced = QGroupBox(tr("Advanced generation settings"))
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced.setToolTip(
            tr("Start with defaults; check this to show additional settings if needed.")
        )
        advanced_content = QWidget()
        settings = QFormLayout(advanced_content)
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.addWidget(advanced_content)
        advanced_content.setVisible(False)
        advanced.toggled.connect(advanced_content.setVisible)
        self.context_tokens = QSpinBox()
        self.context_tokens.setRange(512, 1_048_576)
        self.context_tokens.setValue(8192)
        self.output_tokens = QSpinBox()
        self.output_tokens.setRange(128, 8192)
        self.output_tokens.setValue(2048)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 2)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(0.2)
        self.structured = QCheckBox(tr("Constrain output with JSON Schema"))
        self.structured.setChecked(True)
        settings.addRow(tr("Context token limit"), self.context_tokens)
        settings.addRow(tr("Output token budget"), self.output_tokens)
        settings.addRow(tr("Generation diversity"), self.temperature)
        settings.addRow(self.structured)
        layout.addWidget(advanced)
        layout.addStretch()
        self.model.currentIndexChanged.connect(self.model_selected)
        self.model.editTextChanged.connect(self.update_next_step)
        self.provider.currentIndexChanged.connect(self.provider_selected)

    def policy_tab(self):
        layout = self.tab(tr("4 · Glossary"))
        layout.addWidget(
            QLabel(
                tr(
                    "Terms are user preferences, not official translations. "
                    "Changes do not automatically retranslate records."
                )
            )
        )
        self.glossary = QTableWidget(0, 4)
        self.glossary.setHorizontalHeaderLabels(
            [
                tr("Source term"),
                tr("Translation / preserved name"),
                tr("Rule"),
                tr("Category (empty: all)"),
            ]
        )
        self.glossary.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.glossary)
        add = QPushButton(tr("Add term"))
        add.clicked.connect(lambda: self.add_rule())
        remove = QPushButton(tr("Remove selected term"))
        remove.clicked.connect(
            lambda: (
                self.glossary.removeRow(self.glossary.currentRow())
                if self.glossary.currentRow() >= 0
                else None
            )
        )
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(remove)
        layout.addLayout(row)
        layout.addWidget(
            QLabel(tr("Category style (the default rule applies to other categories)"))
        )
        self.style_category = QComboBox()
        self.style_category.addItem(tr("Default"), "default")
        self.style_category.currentIndexChanged.connect(self.style_selected)
        layout.addWidget(self.style_category)
        self.style = QTextEdit(
            "Kaynak anlamı ve tonu koru; açık, doğal Türkçe kullan. İçerik ekleme veya yumuşatma."
        )
        self.style.setMaximumHeight(120)
        layout.addWidget(self.style)
        save = QPushButton(tr("Save glossary / style version"))
        save.clicked.connect(self.save_policy)
        layout.addWidget(save)
        self.impact_note = QLabel(
            tr("Policy changes do not automatically translate or change approvals.")
        )
        self.impact_note.setWordWrap(True)
        layout.addWidget(self.impact_note)
        affected = QPushButton(tr("Show only affected records in Review"))
        affected.clicked.connect(self.show_affected)
        layout.addWidget(affected)
        self.affected_job_button = QPushButton(
            tr("Generate candidates for first 10 affected records")
        )
        self.affected_job_button.setEnabled(False)
        self.affected_job_button.setToolTip(
            tr(
                "Approved text is preserved; review new candidates in the job"
                " report or record history."
            )
        )
        self.affected_job_button.clicked.connect(
            lambda: self.bridge.submit("create_affected_job", {"profile": self.profile()})
        )
        layout.addWidget(self.affected_job_button)

    def translation_tab(self):
        layout = self.tab(tr("5 · Translate"))
        parallel_row = QFormLayout()
        self.parallel_requests = QSpinBox()
        self.parallel_requests.setRange(1, 16)
        self.parallel_requests.setValue(1)
        self.parallel_requests.setToolTip(
            tr(
                "Concurrent requests supported by the server. Each queued "
                "generation request waits up to 30 minutes. Translation "
                "continues when minimized. Memory errors pause the job."
            )
        )
        parallel_row.addRow(tr("Parallel requests"), self.parallel_requests)
        layout.addLayout(parallel_row)
        layout.addWidget(
            QLabel(
                tr(
                    "First prepare a representative pilot of up to 200 records "
                    "from different categories and lengths. Full-game jobs "
                    "require pilot review. Automated checks do not replace human "
                    "quality review."
                )
            )
        )
        pilot = QPushButton(tr("Prepare and start representative pilot"))
        pilot.clicked.connect(self.start_pilot)
        layout.addWidget(pilot)
        row = QHBoxLayout()
        self.pause_button = QPushButton(tr("Pause"))
        self.pause_button.clicked.connect(lambda: self.bridge.submit("pause"))
        self.resume_button = QPushButton(tr("Resume"))
        self.resume_button.clicked.connect(
            lambda: (
                self.bridge.submit(
                    "run_job",
                    {
                        "job_id": self.current_job,
                        "parallel_requests": self.parallel_requests.value(),
                    },
                )
                if self.current_job
                else None
            )
        )
        self.cancel_button = QPushButton(tr("Cancel job"))
        self.cancel_button.clicked.connect(
            lambda: self.bridge.submit("cancel", {"job_id": self.current_job})
        )
        for button in (self.pause_button, self.resume_button, self.cancel_button):
            button.setEnabled(False)
            row.addWidget(button)
        layout.addLayout(row)
        self.job_combo = QComboBox()
        self.job_combo.currentIndexChanged.connect(self.job_selected)
        layout.addWidget(self.job_combo)
        self.job_status = QLabel(tr("No job has started yet."))
        self.job_status.setWordWrap(True)
        layout.addWidget(self.job_status)
        self.job_progress = QProgressBar()
        self.job_progress.setRange(0, 1)
        self.job_progress.setValue(0)
        self.job_progress.setFormat(tr("No jobs yet"))
        layout.addWidget(self.job_progress)
        self.bulk_note = QLabel(
            tr("Bulk job unavailable: representative pilot and human review are incomplete.")
        )
        layout.addWidget(self.bulk_note)
        report = QPushButton(tr("Selected job measurements / review report"))
        report.clicked.connect(
            lambda: (
                self.bridge.submit("job_report", {"job_id": self.current_job})
                if self.current_job
                else None
            )
        )
        layout.addWidget(report)
        self.bulk_button = QPushButton(tr("Start bulk translation of pending records"))
        self.bulk_button.setEnabled(False)
        self.bulk_button.clicked.connect(
            lambda: self.bridge.submit("create_job", {"kind": "bulk", "profile": self.profile()})
        )
        layout.addWidget(self.bulk_button)
        layout.addStretch()

    def review_tab(self):
        layout = self.tab(tr("6 · Review"))
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search source, translation or record key…"))
        self.search.textChanged.connect(self.search_changed)
        self.status_filter = QComboBox()
        self.status_filter.addItem(tr("All statuses"), None)
        for key, label in STATUS.items():
            self.status_filter.addItem(label, key)
        self.status_filter.currentIndexChanged.connect(self.filter_changed)
        self.category_filter = QComboBox()
        self.category_filter.addItem(tr("All categories"), None)
        self.category_filter.currentIndexChanged.connect(self.filter_changed)
        row.addWidget(self.search)
        row.addWidget(self.status_filter)
        row.addWidget(self.category_filter)
        self.affected_filter = QCheckBox(tr("Affected by glossary / style"))
        self.affected_filter.toggled.connect(self.filter_changed)
        row.addWidget(self.affected_filter)
        layout.addLayout(row)
        self.review_model = ReviewModel()
        self.table = QTableView()
        self.table.setModel(self.review_model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        layout.addWidget(self.table, 2)
        pagination = QHBoxLayout()
        self.previous_page = QPushButton(tr("Previous 200"))
        self.previous_page.clicked.connect(lambda: self.change_page(-200))
        self.next_page = QPushButton(tr("Next 200"))
        self.next_page.clicked.connect(lambda: self.change_page(200))
        self.previous_page.setEnabled(False)
        self.next_page.setEnabled(False)
        self.page_label = QLabel(tr("0 records"))
        pagination.addWidget(self.previous_page)
        pagination.addWidget(self.page_label)
        pagination.addWidget(self.next_page)
        layout.addLayout(pagination)
        splitter = QSplitter()
        self.source_editor = QTextEdit()
        self.source_editor.setReadOnly(True)
        self.translation_editor = DataTextEdit()
        self.translation_editor.textChanged.connect(self.editor_changed)
        splitter.addWidget(self.source_editor)
        splitter.addWidget(self.translation_editor)
        layout.addWidget(splitter, 1)
        self.review_details = QLabel(
            tr("Select a record. Automated checks do not guarantee meaning.")
        )
        self.review_details.setTextFormat(Qt.TextFormat.PlainText)
        self.review_details.setWordWrap(True)
        layout.addWidget(self.review_details)
        self.draft_status = QLabel(tr("No draft."))
        self.draft_status.setWordWrap(True)
        layout.addWidget(self.draft_status)
        self.discard_draft = QPushButton(tr("Remove draft and open current translation"))
        self.discard_draft.clicked.connect(self.discard_current_draft)
        layout.addWidget(self.discard_draft)
        editing = QHBoxLayout()
        save = QPushButton(tr("Save edits"))
        save.clicked.connect(self.save_edit)
        approve = QPushButton(tr("Approve this translation manually"))
        approve.clicked.connect(self.approve)
        editing.addWidget(save)
        editing.addWidget(approve)
        retranslate = QPushButton(tr("Generate a new candidate for the selected record"))
        retranslate.clicked.connect(self.retranslate_selected)
        editing.addWidget(retranslate)
        history = QPushButton(tr("History / new translation candidates"))
        history.clicked.connect(
            lambda: (
                self.bridge.submit("history", {"unit_id": self.current_item["unit_id"]})
                if self.current_item
                else None
            )
        )
        editing.addWidget(history)
        layout.addLayout(editing)
        batch = QPushButton(tr("Approve reviewed translations on this page…"))
        batch.clicked.connect(self.approve_page)
        layout.addWidget(batch)
        self.plural_button = QPushButton(tr("Edit plural branches"))
        self.plural_button.setEnabled(False)
        self.plural_button.setToolTip(
            tr("Select a record with multiple supported plural branches.")
        )
        self.plural_button.clicked.connect(self.edit_plural_branches)
        layout.addWidget(self.plural_button)
        quality_audit = QPushButton(tr("Recheck quality of existing translations"))
        quality_audit.clicked.connect(lambda: self.bridge.submit("quality_audit"))
        layout.addWidget(quality_audit)
        self.approve_all_button = QPushButton(tr("Approve all translations…"))
        self.approve_all_button.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        )
        self.approve_all_button.setToolTip(
            tr("Pending translations across the whole project. Two-step verification is required.")
        )
        self.approve_all_button.clicked.connect(self.approve_all_translations)
        layout.addWidget(self.approve_all_button)

    def export_tab(self):
        layout = self.tab(tr("7 · Export"))
        note = QLabel(
            tr(
                "Existing game files are not modified. Use Apply to game to "
                "install. A JSON translation project is not an installable "
                "game patch."
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        export = QPushButton(tr("Export translation project as JSON"))
        export.clicked.connect(lambda: self.bridge.submit("export"))
        preview = QPushButton(tr("Preview JSON import…"))
        preview.clicked.connect(self.preview_import)
        self.import_button = QPushButton(tr("Import eligible translations from preview"))
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(
            lambda: self.bridge.submit("import_apply", {"path": self.import_path})
        )
        self.restore_button = QPushButton(tr("Restore selected JSON into an empty project"))
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(
            lambda: self.bridge.submit("import_restore", {"path": self.import_path})
        )
        layout.addWidget(export)
        self.shareable_export_button = QPushButton(tr("Create a shareable translation ZIP"))
        self.shareable_export_button.setToolTip(
            tr(
                "Only approved text and required loader files. The recipient "
                "does not need this program or a model."
            )
        )
        self.shareable_export_button.clicked.connect(self.prepare_shareable_export)
        layout.addWidget(self.shareable_export_button)
        backup = QPushButton(tr("Back up data, drafts and job history"))
        backup.setToolTip(
            tr(
                "The SQLite backup includes sources, translations, approvals,"
                " drafts and job history. Game, model and installation files "
                "are not copied."
            )
        )
        backup.clicked.connect(self.backup_project)
        layout.addWidget(backup)
        self.runtime_export_button = QPushButton(
            tr("Select approved translations for a small trial…")
        )
        self.runtime_export_button.clicked.connect(self.prepare_runtime_export)
        layout.addWidget(self.runtime_export_button)
        layout.addWidget(preview)
        layout.addWidget(self.import_button)
        layout.addWidget(self.restore_button)
        self.export_status = QTextEdit()
        self.export_status.setReadOnly(True)
        layout.addWidget(self.export_status)

    def choose_directory(self, field):
        value = QFileDialog.getExistingDirectory(self, tr("Select folder"), field.text())
        if value:
            field.setText(value)

    def select_ui_language(self, code):
        try:
            save_language(code)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, tr("Could not complete the operation"), str(exc))
            for action in self.language_actions.actions():
                action.setChecked(action.data() == preferred_language())
            return
        QMessageBox.information(
            self,
            tr("Language saved"),
            tr(
                "The interface language will change the next time you open UnityTranslator. "
                "Your project and active translation job are unchanged."
            ),
        )

    def open_help_document(self, name):
        if name not in ("README-WINDOWS.md", "SOURCE-ACCESS.md"):
            return
        folder = (
            Path(sys.executable).parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[3] / "docs"
        )
        document = folder / name
        if name == "README-WINDOWS.md":
            guides = (
                folder / "rehber" if getattr(sys, "frozen", False) else folder.parent / "rehber"
            )
            document = guides / (active_language() + ".md")
        if not document.is_file() and not getattr(sys, "frozen", False):
            resource = (
                files("unitytranslator.resources").joinpath("guides", active_language() + ".md")
                if name == "README-WINDOWS.md"
                else files("unitytranslator.resources").joinpath("SOURCE-ACCESS.md")
            )
            document = Path(str(resource))
        if not document.is_file() or not QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(document))
        ):
            QMessageBox.information(
                self,
                tr("Guide"),
                tr("You can open the document from the application folder:\n") + str(document),
            )

    def installation_tab(self):
        layout = self.tab(tr("8 · Apply to game"))
        note = QLabel(
            tr(
                "Only current human-approved translations are applied. "
                "General game compatibility is experimental; this does not "
                "launch the game. The game must be closed. Preparation shows "
                "a file plan; no game files are written before you approve "
                "it."
            )
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.installation_state = QLabel(tr("Open a project first."))
        self.installation_state.setWordWrap(True)
        layout.addWidget(self.installation_state)
        advanced = QGroupBox(tr("Optional: variable log file"))
        form = QFormLayout(advanced)
        self.installation_log = QLineEdit()
        self.installation_log.setPlaceholderText(
            tr("Full path relative to game root; e.g. Logs/game.log")
        )
        self.installation_log_reviewed = QCheckBox(
            tr("I choose to track only this log file separately")
        )
        form.addRow(tr("Exact file path"), self.installation_log)
        form.addRow(self.installation_log_reviewed)
        layout.addWidget(advanced)
        self.prepare_installation = QPushButton(
            tr("Prepare installation plan for approved translations")
        )
        self.prepare_installation.setEnabled(False)
        self.prepare_installation.clicked.connect(self.prepare_installation_plan)
        layout.addWidget(self.prepare_installation)
        self.remove_installation = QPushButton(tr("Disable translation and remove added files"))
        self.remove_installation.setEnabled(False)
        self.remove_installation.clicked.connect(self.remove_installation_plan)
        layout.addWidget(self.remove_installation)
        refresh = QPushButton(tr("Refresh installation status"))
        refresh.clicked.connect(self.refresh_installation)
        layout.addWidget(refresh)
        self.installation_details = QTextEdit()
        self.installation_details.setReadOnly(True)
        layout.addWidget(self.installation_details)

    def refresh_installation(self):
        if self.project_open:
            self.deployment_status_token = uuid4().hex
            self.bridge.submit(
                "deployment_status",
                {
                    "project_id": self.current_project_id,
                    "request_token": self.deployment_status_token,
                },
            )

    def prepare_installation_plan(self):
        if not self.project_open:
            return
        self.deployment_token = uuid4().hex
        self.setEnabled(False)
        self.installation_state.setText(tr("Preparing installation plan…"))
        self.bridge.submit(
            "deployment_prepare",
            {
                "project_id": self.current_project_id,
                "request_token": self.deployment_token,
                "log_file": self.installation_log.text().strip()
                if self.installation_log.isEnabled()
                else "",
                "log_reviewed": self.installation_log_reviewed.isChecked(),
            },
        )

    def remove_installation_plan(self):
        if not self.deployment:
            return
        names = "\n".join(item["target"] for item in self.deployment["files"])
        if (
            QMessageBox.question(
                self,
                tr("Remove added files"),
                tr(
                    "Only added files with matching ownership and hashes will be "
                    "removed. Modified files are preserved:\n"
                )
                + names,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.deployment_token = uuid4().hex
        self.setEnabled(False)
        self.installation_state.setText(tr("Checking added files and original file hashes…"))
        self.bridge.submit(
            "deployment_remove",
            {
                "project_id": self.current_project_id,
                "request_token": self.deployment_token,
                "plan_id": self.deployment["plan_id"],
                "user_action": True,
            },
        )

    def open_project(self):
        self.draft_deferred = (
            "open",
            {
                "game": self.game_path.text(),
                "project": self.project_path.text(),
                "source_language": self.source_language.currentText(),
                "target_language": self.target_language.currentText(),
            },
        )
        self.setEnabled(False)
        self.drafts.flush()
        self.draft_state_changed()

    def open_existing_project(self):
        value = QFileDialog.getExistingDirectory(
            self, tr("Select an existing project folder"), self.project_path.text()
        )
        if value:
            self.draft_deferred = ("open", {"project": value, "existing_only": True})
            self.setEnabled(False)
            self.drafts.flush()
            self.draft_state_changed()

    def show_project_folder(self):
        if self.open_project_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.open_project_folder))

    def backup_project(self):
        if self.project_open and not self.draft_deferred:
            self.draft_deferred = ("backup", None)
            self.setEnabled(False)
            self.drafts.flush()
            self.draft_state_changed()

    def submit_open_project(self, data):
        self.bridge.submit(
            "open",
            data,
        )
        self.statusBar().showMessage(tr("Opening project…"))

    def model_data(self):
        return {
            "provider": self.provider.currentData(),
            "address": self.address.text(),
            "model": self.model.currentText(),
            "structured_output": self.structured.isChecked(),
        }

    def profile(self):
        return {
            **self.model_data(),
            "context_tokens": self.context_tokens.value(),
            "output_tokens": self.output_tokens.value(),
            "temperature": self.temperature.value(),
        }

    def model_selected(self):
        value = self.model.currentData()
        if isinstance(value, dict) and value.get("context_tokens"):
            self.context_tokens.setValue(value["context_tokens"])

    def provider_selected(self):
        if self.address.text().strip() in ("http://127.0.0.1:1234", "http://127.0.0.1:8080"):
            self.address.setText(
                "http://127.0.0.1:1234"
                if self.provider.currentData() == "lm-studio"
                else "http://127.0.0.1:8080"
            )
        self.model.clear()
        self.model_status.setText(tr("Provider changed. List models or enter a model ID."))

    def focus_search(self):
        if self.project_open:
            self.tabs.setCurrentIndex(5)
            self.search.setFocus()
            self.search.selectAll()

    def go_next_step(self):
        if self.project_open:
            self.tabs.setCurrentIndex(self.next_step.property("target_tab") or 1)

    def update_next_step(self):
        counts = self.project_totals
        if not counts or not self.project_open:
            return
        self.summary.setText(
            tr(
                "{p0} records · {p2} translations · {p4} approved · {p6} → {p8}",
                p0=f"{counts['total']:,}",
                p2=f"{counts['translated']:,}",
                p4=f"{counts['approved']:,}",
                p6=f"{self.source_language.currentText()}",
                p8=f"{self.target_language.currentText()}",
            )
        )
        if not counts["total"]:
            text, tab = tr("Next: extract game text"), 1
        elif counts["translated"] > counts["approved"]:
            text, tab = tr("Next: review translations"), 5
        elif counts["approved"] == counts["total"]:
            if self.installation_kit_available and not (
                self.deployment and self.deployment["status"] != "removed"
            ):
                text, tab = tr("Next: prepare installation plan for approved translations"), 7
            else:
                text, tab = tr("Next: export the translation project"), 6
        elif not self.model.currentText().strip():
            text, tab = tr("Next: select your local model"), 2
        else:
            text, tab = tr("Next: continue translating"), 4
        self.next_step.setText(text)
        self.next_step.setProperty("target_tab", tab)
        self.next_step.setEnabled(True)

    def add_rule(self, value=None):
        value = value or {}
        row = self.glossary.rowCount()
        self.glossary.insertRow(row)
        for column, key in ((0, "source"), (1, "target"), (3, "category")):
            self.glossary.setItem(row, column, QTableWidgetItem(value.get(key) or ""))
        combo = QComboBox()
        combo.addItem(tr("Preferred translation"), "preferred_translation")
        combo.addItem(tr("Keep the name unchanged"), "preserve_name")
        combo.setCurrentIndex(1 if value.get("kind") == "preserve_name" else 0)
        self.glossary.setCellWidget(row, 2, combo)

    def save_policy(self):
        rules = []
        for row in range(self.glossary.rowCount()):
            rules.append(
                {
                    "source": self.glossary.item(row, 0).text(),
                    "target": self.glossary.item(row, 1).text(),
                    "kind": self.glossary.cellWidget(row, 2).currentData(),
                    "category": self.glossary.item(row, 3).text() or None,
                    "case_sensitive": False,
                    "word_boundary": True,
                }
            )
        self.styles[self.style_key] = self.style.toPlainText()
        self.bridge.submit("set_policies", {"glossary": rules, "styles": self.styles.copy()})

    def style_selected(self):
        self.styles[self.style_key] = self.style.toPlainText()
        self.style_key = self.style_category.currentData() or "default"
        self.style.setPlainText(self.styles.get(self.style_key, ""))

    def retranslate_selected(self):
        if self.current_item:
            self.bridge.submit(
                "create_job",
                {
                    "kind": "prototype",
                    "profile": self.profile(),
                    "units": [self.current_item["unit_id"]],
                    "retranslate": True,
                    "approved_candidates": self.current_item["status"] == "approved",
                },
            )

    def start_pilot(self):
        self.bridge.submit("create_job", {"kind": "pilot", "profile": self.profile()})

    def show_affected(self):
        self.search.clear()
        self.status_filter.setCurrentIndex(0)
        self.category_filter.setCurrentIndex(0)
        self.affected_filter.setChecked(True)
        self.tabs.setCurrentIndex(5)
        self.filter_changed()

    def job_selected(self):
        self.current_job = self.job_combo.currentData()
        if self.current_job in self.job_summaries:
            self.on_progress(self.job_summaries[self.current_job])

    def refresh(self):
        if self.project_open:
            self.page_pending = True
            self.previous_page.setEnabled(False)
            self.next_page.setEnabled(False)
            self.page_token = uuid4().hex
            self.bridge.submit(
                "page",
                {
                    "request_token": self.page_token,
                    "offset": self.offset,
                    "search": self.search.text(),
                    "status": self.status_filter.currentData(),
                    "category": self.category_filter.currentData(),
                    "affected": self.affected_filter.isChecked(),
                },
            )

    def search_changed(self):
        self.offset = 0
        self.search_timer.start()

    def filter_changed(self):
        self.offset = 0
        self.refresh()

    def change_page(self, change):
        if self.page_pending or not self.review_count:
            return
        last_offset = ((self.review_count - 1) // 200) * 200
        target = min(last_offset, max(0, self.offset + change))
        if target != self.offset:
            self.offset = target
            self.refresh()

    def selection_changed(self):
        indexes = self.table.selectionModel().selectedRows()
        self.current_item = self.review_model.rows[indexes[0].row()] if indexes else None
        entry = self.drafts.ensure(self.current_item) if self.current_item else None
        self.editor_loading = True
        try:
            self.source_editor.setPlainText(entry["source_text"] if entry else "")
            text = entry["text"] if entry else ""
            if self.translation_editor.value() != text:
                self.translation_editor.setPlainText(text)
            self.translation_editor.reference = entry["source_text"] if entry else ""
        finally:
            self.editor_loading = False
        try:
            supported_plural = (
                bool(self.current_item) and len(plural_branches(entry["source_text"])) > 1
            )
        except ValueError:
            supported_plural = False
        self.plural_button.setEnabled(supported_plural)
        issues = json.loads(self.current_item["issues_json"] or "[]") if self.current_item else []
        self.review_details.setText(
            (
                "; ".join(issue_label(code) for code in issues)
                if issues
                else tr("No automated warnings.")
            )
            + tr("Automated checks do not guarantee meaning; human review is required.")
        )
        self.draft_state_changed()

    def editor_changed(self):
        if self.current_item and not self.editor_loading:
            self.drafts.update(self.current_item, self.translation_editor.value())

    def draft_state_changed(self):
        entry = self.drafts.entries.get(self.current_item["unit_id"]) if self.current_item else None
        stale = entry and (
            entry["source_revision"] != self.current_item["source_revision"]
            or entry["base_version"] != self.current_item["version"]
        )
        if entry and entry.get("error"):
            note = (
                tr("Could not save the draft; the text remains on screen. Retry or copy it.")
                if self.drafts.dirty(entry)
                else tr("Could not save as translation; the local draft is preserved.")
            )
        elif entry and stale:
            note = tr(
                "The source/translation changed. The old source and draft are"
                " preserved but cannot be saved to the current record."
            )
        elif entry and (self.drafts.dirty(entry) or self.drafts.pending):
            note = tr("Saving draft locally…")
        elif entry and entry["revision"]:
            note = tr(
                "Draft saved locally. Saving as a translation and human "
                "approval are separate steps."
            )
        else:
            note = tr("No draft.")
        self.draft_status.setText(note)
        busy = self.drafts.action is not None or self.draft_refresh_pending
        self.translation_editor.setReadOnly(busy or not self.current_item)
        self.table.setEnabled(not busy)
        self.discard_draft.setEnabled(
            bool(entry and (entry["revision"] or self.drafts.dirty(entry))) and not busy
        )
        if self.draft_deferred:
            if self.drafts.has_error:
                self.draft_deferred = None
                self.setEnabled(True)
            elif self.drafts.settled:
                action, data = self.draft_deferred
                self.draft_deferred = None
                if action == "open":
                    self.submit_open_project(data)
                elif action == "backup":
                    self.bridge.submit("backup")
                else:
                    self.closing = True
                    self.statusBar().showMessage(tr("Finishing the active job safely…"))
                    self.bridge.shutdown()

    def draft_action_finished(self, action, unit):
        self.draft_refresh_pending = True
        self.refresh()

    def draft_failed(self, command, message):
        self.draft_deferred = None
        self.setEnabled(True)
        self.failed("draft", message)

    def discard_current_draft(self):
        if not self.current_item or self.drafts.action:
            return
        answer = QMessageBox.question(
            self,
            tr("Remove draft"),
            tr("This record's draft will be removed. Continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.drafts.request_action("discard", self.current_item["unit_id"])

    def edit_plural_branches(self):
        if not self.current_item or self.drafts.action or self.draft_refresh_pending:
            return
        identity = tuple(
            self.current_item[key] for key in ("unit_id", "source_revision", "version")
        )
        draft = self.translation_editor.value()

        def is_current():
            return (
                self.current_item is not None
                and tuple(
                    self.current_item[key] for key in ("unit_id", "source_revision", "version")
                )
                == identity
                and self.translation_editor.value() == draft
            )

        try:
            source = self.drafts.entries[self.current_item["unit_id"]]["source_text"]
            dialog = PluralEditorDialog(source, draft, self, is_current)
        except ValueError as error:
            self.failed("plural_edit", str(error))
            return
        if dialog.exec() and dialog.value is not None:
            self.translation_editor.setPlainText(dialog.value)

    def save_edit(self):
        if self.current_item:
            if self.drafts.action or self.draft_refresh_pending:
                return
            entry = self.drafts.ensure(self.current_item)
            if entry["revision"] or self.drafts.dirty(entry):
                self.drafts.request_action("commit", self.current_item["unit_id"])
                return
            self.bridge.submit(
                "edit",
                {
                    "unit_id": self.current_item["unit_id"],
                    "version": self.current_item["version"],
                    "text": self.translation_editor.value(),
                },
            )

    def approve(self):
        if self.current_item:
            entry = self.drafts.ensure(self.current_item)
            if (
                self.drafts.action
                or self.draft_refresh_pending
                or entry["revision"]
                or self.drafts.dirty(entry)
            ):
                self.failed("approve", tr("Save the draft as a translation before approving it."))
                return
            if self.translation_editor.value() != (self.current_item["translation"] or ""):
                self.failed(
                    "approve", tr("Save your edits before approving the current translation.")
                )
                return
            self.bridge.submit(
                "approve",
                {"unit_id": self.current_item["unit_id"], "version": self.current_item["version"]},
            )

    def approve_page(self):
        if not self.project_open or self.drafts.action or self.draft_refresh_pending:
            return
        rows = []
        for row in self.review_model.rows:
            draft = self.drafts.entries.get(row["unit_id"])
            if (
                row["status"] not in ("translated", "needs_review")
                or not row["translation"]
                or row.get("editor_draft")
                or (draft and (draft["revision"] or self.drafts.dirty(draft)))
                or format_issues(row["source_text"], row["translation"])
            ):
                continue
            rows.append(dict(row))
        if not rows:
            QMessageBox.information(
                self,
                tr("Group review"),
                tr(
                    "No eligible candidates on this page. Create translations and"
                    " save any drafts first."
                ),
            )
            return
        project_id = self.current_project_id
        dialog = BatchReviewDialog(rows, self)
        if dialog.exec() and dialog.reviewed.isChecked() and project_id == self.current_project_id:
            self.approve_selection_token = uuid4().hex
            self.bridge.submit(
                "approve_selection",
                {
                    "project_id": project_id,
                    "request_token": self.approve_selection_token,
                    "records": dialog.records(),
                    "user_action": True,
                    "reviewed": True,
                },
            )

    def approve_all_translations(self):
        if not self.project_open or self.drafts.action or self.draft_refresh_pending:
            return
        if any(self.drafts.dirty(entry) for entry in self.drafts.entries.values()):
            QMessageBox.information(
                self, tr("Unsaved edits"), tr("Wait for edits to be saved first.")
            )
            return
        self.approve_all_token = uuid4().hex
        self.approve_all_button.setEnabled(False)
        self.bridge.submit(
            "approve_all_preview",
            {
                "project_id": self.current_project_id,
                "request_token": self.approve_all_token,
            },
        )

    def schedule_bulk_readiness(self):
        self.bulk_readiness_token = None
        self.bulk_button.setEnabled(False)
        if self.project_open and not self.closing:
            self.bulk_timer.start()

    def refresh_bulk_readiness(self):
        if self.project_open and not self.closing:
            self.bulk_readiness_token = uuid4().hex
            self.bridge.submit(
                "bulk_readiness",
                {
                    "project_id": self.current_project_id,
                    "request_token": self.bulk_readiness_token,
                    "profile": self.profile(),
                },
            )

    def preview_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Select translation project"), "", "JSON (*.json)"
        )
        if path:
            self.import_path = path
            self.bridge.submit("import_preview", {"path": path})

    def prepare_shareable_export(self):
        if not self.project_open or not self.current_project_id:
            return
        self.shareable_export_token = uuid4().hex
        self.shareable_export_button.setEnabled(False)
        self.bridge.submit(
            "shareable_export",
            {"project_id": self.current_project_id, "request_token": self.shareable_export_token},
        )

    def prepare_runtime_export(self):
        project_id = self.current_project_id
        dialog = RuntimeSelectionDialog(self.review_model.rows, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if project_id != self.current_project_id:
            self.failed("runtime_export", tr("The project changed; select the records again."))
            return
        self.runtime_export_token = uuid4().hex
        self.bridge.submit(
            "runtime_export",
            {
                "project_id": project_id,
                "request_token": self.runtime_export_token,
                "records": dialog.records(),
            },
        )

    def completed(self, command, result):
        if command == "open":
            self.current_item = None
            self.current_project_id = result["project_id"]
            self.drafts.reset(self.current_project_id)
            self.review_model.set_rows([])
            self.draft_refresh_pending = False
            self.setEnabled(True)
            self.game_process_token = None
            self.runtime_export_token = None
            self.shareable_export_token = None
            self.shareable_export_button.setEnabled(True)
            self.deployment_token = None
            self.deployment_status_token = None
            self.deployment = None
            self.installation_kit_available = False
            self.installation_details.clear()
            self.installation_log.clear()
            self.installation_log_reviewed.setChecked(False)
            self.approve_selection_token = None
            self.approve_all_token = None
            self.approve_all_button.setEnabled(True)
            self.bulk_readiness_token = None
            self.game_process_status.setText(tr("Game process state has not been checked."))
            self.project_open = True
            self.current_job = None
            self.job_summaries = {}
            self.job_status.setText(tr("No job selected yet."))
            self.job_progress.setRange(0, 1)
            self.job_progress.setValue(0)
            self.job_progress.setFormat(tr("No jobs yet"))
            self.project_totals = None
            self.next_step.setEnabled(False)
            self.open_project_folder = result.get("project_path", self.project_path.text())
            self.project_path.setText(self.open_project_folder)
            self.game_path.setText(result.get("game_path", self.game_path.text()))
            self.project_folder_button.setEnabled(True)
            for index in range(1, self.tabs.count()):
                self.tabs.setTabEnabled(index, True)
            self.source_language.setCurrentText(result["source_language"])
            self.target_language.setCurrentText(result["target_language"])
            self.summary.setText(
                tr(
                    "Project open · {p1} → {p3} · Game files are read-only",
                    p1=f"{result['source_language']}",
                    p3=f"{result['target_language']}",
                )
            )
            self.offset = 0
            self.category_filter.blockSignals(True)
            self.category_filter.clear()
            self.category_filter.addItem(tr("All categories"), None)
            self.category_filter.blockSignals(False)
            profile = result.get("last_profile")
            if profile:
                self.provider.setCurrentIndex(max(0, self.provider.findData(profile["provider"])))
                self.address.setText(profile["address"])
                self.model.setCurrentText(profile["model"])
                self.context_tokens.setValue(profile["context_tokens"])
                self.output_tokens.setValue(profile["output_tokens"])
                self.temperature.setValue(profile["temperature"])
                self.structured.setChecked(profile["structured_output"])
            self.refresh()
            self.bridge.submit("policies")
            self.bridge.submit("jobs")
            self.refresh_installation()
            self.schedule_bulk_readiness()
        elif command == "approve_all_preview":
            if (
                result["project_id"] != self.current_project_id
                or result["request_token"] != self.approve_all_token
            ):
                return
            self.approve_all_button.setEnabled(True)
            if not result["count"]:
                QMessageBox.information(
                    self,
                    tr("All translations"),
                    tr("No pending translations are eligible for approval."),
                )
                return
            dialog = AllApprovalDialog(result, self)
            if (
                dialog.exec()
                and dialog.stage == 2
                and dialog.confirmation.text() == dialog.phrase
                and result["project_id"] == self.current_project_id
            ):
                self.approve_all_button.setEnabled(False)
                self.bridge.submit(
                    "approve_all",
                    {
                        "project_id": self.current_project_id,
                        "request_token": self.approve_all_token,
                        "token": result["token"],
                        "user_action": True,
                        "confirmation": canonical_all_confirmation(result["count"]),
                    },
                )
        elif command in ("approve_selection", "approve_all"):
            if result["project_id"] != self.current_project_id or result["request_token"] != (
                self.approve_all_token if command == "approve_all" else self.approve_selection_token
            ):
                return
            if command == "approve_all":
                self.approve_all_button.setEnabled(True)
                self.approve_all_token = None
            self.refresh()
            self.refresh_installation()
            self.bridge.submit("policies")
            self.review_details.setText(
                tr("Approved {p0} selected translations.", p0=f"{result['approved']}")
            )
        elif command == "bulk_readiness":
            if (
                result["project_id"] != self.current_project_id
                or result["request_token"] != self.bulk_readiness_token
            ):
                return
            self.bulk_button.setEnabled(result["allowed"])
            self.bulk_note.setText(
                tr("Bulk job ready: the pilot was reviewed for this profile and sources.")
                if result["allowed"]
                else tr("Bulk job unavailable: review the pilot for this profile/sources.")
            )
        elif command.startswith("deployment_"):
            expected_token = (
                self.deployment_status_token
                if command == "deployment_status"
                else self.deployment_token
            )
            if (
                result["project_id"] != self.current_project_id
                or result["request_token"] != expected_token
                or self.closing
            ):
                return
            if command != "deployment_status":
                self.setEnabled(True)
            if command == "deployment_status":
                self.deployment = result["deployment"]
                self.installation_kit_available = result["kit_available"]
                self.update_next_step()
                active = bool(self.deployment and self.deployment["status"] != "removed")
                self.prepare_installation.setEnabled(
                    result["kit_available"] and result["approved"] > 0 and not active
                )
                self.remove_installation.setEnabled(active)
                self.installation_log.setEnabled(not result["baseline_exists"])
                self.installation_log_reviewed.setEnabled(not result["baseline_exists"])
                self.installation_state.setText(
                    (tr("Installation recorded. ") if active else tr("No active installation. "))
                    + tr("{p0} current approved translations. ", p0=f"{result['approved']}")
                    + result["kit_reason"]
                )
                if result["exclusions"]:
                    self.installation_log.setText(
                        ", ".join(item["path"] for item in result["exclusions"])
                    )
                if self.deployment and not self.installation_details.toPlainText():
                    self.installation_details.setPlainText(
                        tr("Status: ")
                        + {
                            "installed": tr("Active (experimental)"),
                            "removed": tr("Removed"),
                            "installing": tr("Partial installation"),
                            "recovery_required": tr("Recovery required"),
                        }.get(self.deployment["status"], self.deployment["status"])
                        + "\n"
                        + "\n".join(item["target"] for item in self.deployment["files"])
                    )
            elif command == "deployment_prepare":
                dialog = InstallationReviewDialog(result, self)
                if dialog.exec() and dialog.reviewed.isChecked():
                    self.setEnabled(False)
                    self.installation_state.setText(
                        tr("Checking installation and original file hashes…")
                    )
                    self.bridge.submit(
                        "deployment_install",
                        {
                            "project_id": self.current_project_id,
                            "request_token": self.deployment_token,
                            "review_id": result["review_id"],
                            "user_action": True,
                            "experimental_reviewed": True,
                        },
                    )
                else:
                    self.refresh_installation()
            else:
                if command == "deployment_install":
                    self.installation_details.setPlainText(
                        tr(
                            "Installation completed; original files are unchanged. Start "
                            "the game with your usual launcher. Runtime files remain in "
                            "the project folder; do not move the project while installed."
                        )
                    )
                else:
                    self.installation_details.setPlainText(
                        tr(
                            (
                                "Removed additions: {p1}; preserved additions: {p3}. Changed "
                                "original files: {p5}. Translations remain in the project "
                                "folder.\n"
                            ),
                            p1=f"{len(result['removed'])}",
                            p3=f"{len(result['preserved'])}",
                            p5=f"{len(result['original_changes'])}",
                        )
                        + "\n".join(result["preserved"])
                    )
                self.refresh_installation()
        elif command == "game_process":
            if (
                result["project_id"] != self.current_project_id
                or result["request_token"] != self.game_process_token
            ):
                return  # Eski oturum/istek sonucu yeni durum etiketi değildir.
            labels = {
                "closed": tr("The game was observed closed."),
                "running": tr("The game is running. Close it before installing/removing files."),
                "unknown": tr("Could not verify that the game is closed."),
            }
            reasons = {
                "no_executable_identity": tr("Could not identify the game executable."),
                "game_entry_limit": tr("Game file scan limit exceeded."),
                "process_or_path_inspection_failed": tr("Process or path query could not finish."),
            }
            self.game_process_status.setText(
                labels.get(result["status"], labels["unknown"])
                + " "
                + reasons.get(result["reason"], "")
                + tr("\nObservation time (UTC): {p1}", p1=f"{result['observed_at']}")
                + tr(
                    "\nThis observation is not installation approval. In-game "
                    "application is not yet verified."
                )
            )
        elif command == "page":
            if (
                result.get("project_id") != self.current_project_id
                or result.get("request_token") != self.page_token
            ):
                return
            self.page_pending = False
            self.offset = result["offset"]
            self.review_count = result["count"]
            self.previous_page.setEnabled(self.offset > 0)
            self.next_page.setEnabled(self.offset + len(result["rows"]) < result["count"])
            self.project_totals = result.get("totals")
            self.update_next_step()
            self.draft_refresh_pending = False
            selected = self.current_item["unit_id"] if self.current_item else None
            self.review_model.set_rows(result["rows"])
            self.selection_changed()
            if selected is not None:
                for index, row in enumerate(result["rows"]):
                    if row["unit_id"] == selected:
                        self.table.selectRow(index)
                        break
            self.page_label.setText(
                tr(
                    "{p0} records · {p2}–{p4}",
                    p0=f"{result['count']}",
                    p2=f"{(result['offset'] + 1 if result['rows'] else 0)}",
                    p4=f"{result['offset'] + len(result['rows'])}",
                )
            )
            if self.category_filter.count() == 1:
                self.category_filter.blockSignals(True)
                for category in result["categories"]:
                    self.category_filter.addItem(category, category)
                self.category_filter.blockSignals(False)
                self.style_category.blockSignals(True)
                for category in result["categories"]:
                    if self.style_category.findData(category) < 0:
                        self.style_category.addItem(category, category)
                self.style_category.blockSignals(False)
        elif command == "scan":
            report = result["result"]
            self.source_file.clear()
            self.source_file.addItems(
                [
                    item["path"]
                    for item in sorted(report["source_candidates"], key=lambda i: i["size"])
                ]
            )
            if report.get("recommendations"):
                self.source_file.setCurrentText(report["recommendations"][0]["source"])
            self.discovery.setPlainText(
                tr(
                    (
                        "Runtime indicators: {p1} · {p3} source candidates. Text "
                        "extraction: not yet verified. Game application: not yet "
                        "verified. Report: {p5}"
                    ),
                    p1=f"{', '.join(report['runtime_indicators']) or tr('Unknown')}",
                    p3=f"{len(report['source_candidates'])}",
                    p5=f"{result['report']}",
                )
            )
            if report.get("recommendations"):
                self.discovery.append(
                    tr(
                        "The first source candidate for this game profile was "
                        "selected. The reader will verify its structure."
                    )
                )
        elif command == "extract":
            self.discovery.append(
                tr(
                    (
                        "Extraction complete: {p1} records, {p3} characters. Source "
                        "hashes match before/after. {p5}"
                    ),
                    p1=f"{result['counts']['records']}",
                    p3=f"{result['counts']['characters']}",
                    p5=f"{result['report']}",
                )
            )
            self.refresh()
            self.schedule_bulk_readiness()
        elif command == "models":
            previous_model = self.model.currentText()
            self.model.clear()
            for model in result:
                self.model.addItem(model["id"], model)
            previous_index = self.model.findText(previous_model)
            if previous_index >= 0:
                self.model.setCurrentIndex(previous_index)
            self.model_status.setText(
                tr("Model list received. Loaded state: ")
                + ", ".join(
                    f"{item['id']}: "
                    + {True: tr("Loaded"), False: tr("Not loaded")}.get(
                        item["loaded"], "bilinmiyor"
                    )
                    for item in result
                )
            )
        elif command == "connection_test":
            self.model_status.setText(
                tr(
                    (
                        "Generation and format check passed: {p1}. No human quality "
                        "approval was granted."
                    ),
                    p1=f"{result['translation']}",
                )
            )
        elif command == "policies":
            self.glossary.setRowCount(0)
            for value in result["glossary"]:
                self.add_rule(value)
            self.styles = result["styles"].copy()
            self.style.setPlainText(self.styles.get(self.style_key, ""))
            self.impact_note.setText(
                tr(
                    (
                        "{p0} records affected by policy changes; regeneration "
                        "requires user action. Approved text is preserved."
                    ),
                    p0=f"{len(result['impacted'])}",
                )
            )
            self.affected_job_button.setEnabled(bool(result["impacted"]))
        elif command == "set_policies":
            self.bridge.submit("policies")
            self.schedule_bulk_readiness()
        elif command in ("create_job", "create_affected_job"):
            self.current_job = result["job_id"]
            self.job_status.setText(tr("Job prepared for {p0} records.", p0=f"{result['count']}"))
            self.job_progress.setRange(0, 0)
            self.job_progress.setFormat(tr("Waiting for the first response…"))
            self.job_combo.setEnabled(False)
            self.parallel_requests.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.bridge.submit(
                "run_job",
                {"job_id": self.current_job, "parallel_requests": self.parallel_requests.value()},
            )
        elif command == "run_job":
            self.on_progress(result)
            self.bridge.submit("jobs")
            self.refresh()
            self.schedule_bulk_readiness()
        elif command in ("pause", "cancel"):
            self.bridge.submit("jobs")
            self.refresh()
        elif command == "job_report":
            dialog = PilotReportDialog(result["report"], result["path"], self)
            if dialog.exec() and dialog.acknowledged:
                self.bridge.submit("pilot_seen", {"job_id": result["report"]["job_id"]})
        elif command == "pilot_seen":
            self.bulk_note.setText(
                tr("Pilot review saved. Bulk jobs are available for the same profile and sources.")
            )
            self.schedule_bulk_readiness()
        elif command == "jobs":
            self.job_summaries = {job["job_id"]: job for job in result}
            selected = self.current_job
            self.job_combo.blockSignals(True)
            self.job_combo.clear()
            for job in result:
                self.job_combo.addItem(
                    f"{job['job_id'][:8]} · {JOB_STATUS.get(job['status'], job['status'])}",
                    job["job_id"],
                )
            index = self.job_combo.findData(selected)
            self.job_combo.setCurrentIndex(max(0, index))
            self.job_combo.blockSignals(False)
            self.current_job = self.job_combo.currentData()
            if self.current_job in self.job_summaries:
                self.on_progress(self.job_summaries[self.current_job])
        elif command == "history":
            dialog = CandidateHistoryDialog(result, self)
            if dialog.exec() and dialog.chosen:
                self.bridge.submit(
                    "select_candidate",
                    {
                        "unit_id": result["unit_id"],
                        "version": result["current"]["version"],
                        "revision": dialog.chosen,
                        "replace_approved": dialog.replace.isChecked(),
                    },
                )
        elif command == "quality_audit":
            self.review_details.setText(
                tr(
                    (
                        "Checked {p0} translations; {p2} records have warnings. "
                        "Record states and approvals are preserved.\n"
                    ),
                    p0=f"{result['audited_current_translations']}",
                    p2=f"{result['flagged_records']}",
                )
                + result["html_path"]
            )
            self.export_status.setPlainText(
                tr("Recheck reports:\n") + result["html_path"] + "\n" + result["json_path"]
            )
        elif command in ("edit", "approve", "select_candidate", "import_apply", "import_restore"):
            self.refresh()
            self.refresh_installation()
            if command == "approve":
                self.bridge.submit("policies")
            if command == "import_apply":
                self.export_status.setPlainText(
                    tr(
                        "Imported {p0} translation candidates. Existing approvals are preserved.",
                        p0=f"{result['applied']}",
                    )
                )
                self.import_button.setEnabled(False)
            if command == "import_restore":
                self.export_status.setPlainText(
                    tr(
                        (
                            "Restored {p0} records with history. Imported approvals "
                            "remain archive information; review and approve translations "
                            "again in this project."
                        ),
                        p0=f"{result['restored_units']}",
                    )
                )
                self.restore_button.setEnabled(False)
                self.bridge.submit("policies")
        elif command == "export":
            self.export_status.setPlainText(tr("Translation project exported:\n") + result)
        elif command == "shareable_export":
            if (
                result.get("project_id") != self.current_project_id
                or result.get("request_token") != self.shareable_export_token
            ):
                return
            self.shareable_export_button.setEnabled(True)
            self.export_status.setPlainText(
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
        elif command == "backup":
            self.setEnabled(True)
            self.export_status.setPlainText(
                tr("Data backup created and integrity verified:\n")
                + result["folder"]
                + tr(
                    "\nIncludes translations, approvals, drafts and job history. "
                    "This is not a backup of the game installation or generated "
                    "packages. Open this backup folder with Open existing "
                    "project."
                )
            )
        elif command == "runtime_export":
            if (
                result["project_id"] != self.current_project_id
                or result["request_token"] != self.runtime_export_token
            ):
                return
            self.export_status.setPlainText(
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
        elif command == "import_preview":
            self.export_status.setPlainText(
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
            self.import_button.setEnabled(
                bool(result["applicable"] or result["archive_applicable"])
            )
            self.restore_button.setEnabled(result["restore_available"])
        actions = {
            "open": tr("Project opened. Continue in Texts."),
            "scan": tr("Scan complete. Select the source and extract text."),
            "extract": tr("Text is ready. Connect to your local server in Model."),
            "models": tr("Model list received. Select the model to use."),
            "export": tr("Translation project exported."),
            "backup": tr("Data backup created."),
            "edit": tr("Translation saved."),
            "approve": tr("Translation approved."),
        }
        if command not in ("page", "policies", "jobs", "bulk_readiness", "deployment_status"):
            self.statusBar().showMessage(actions.get(command, tr("Operation completed.")), 8000)

    def on_progress(self, result):
        if result.get("kind") == "deployment":
            if result["project_id"] == self.current_project_id:
                self.installation_state.setText(diagnostic(result["message"]))
            return
        counts = result["counts"]
        self.job_combo.setEnabled(result["status"] not in ("running", "pausing"))
        self.parallel_requests.setEnabled(result["status"] not in ("running", "pausing"))
        self.pause_button.setEnabled(result["status"] == "running")
        self.resume_button.setEnabled(result["status"] in ("queued", "paused"))
        self.cancel_button.setEnabled(
            result["status"] in ("queued", "running", "pausing", "paused")
        )
        finished = sum(
            counts.get(status, 0) for status in ("completed", "failed", "skipped", "cancelled")
        )
        self.job_progress.setRange(0, max(1, result["total"]))
        self.job_progress.setValue(finished)
        self.job_progress.setFormat(tr("%p% · %v / %m records finished"))
        rate = result.get("records_per_minute")
        eta = result.get("active_generation_eta_seconds")
        speed = (
            tr("{p0} records/min", p0=f"{rate:.1f}")
            if rate is not None
            else tr("No speed measurement")
            if result["status"] in ("completed", "completed_with_errors", "cancelled", "failed")
            else tr("Waiting for the first speed measurement")
        )
        if eta is None:
            remaining = tr("Remaining generation time: waiting for first measurement")
        elif eta >= 3600:
            remaining = tr(
                "Remaining generation: approximately {p1} hr {p3} min",
                p1=f"{int(eta // 3600)}",
                p3=f"{int(eta % 3600 // 60)}",
            )
        elif eta >= 60:
            remaining = tr(
                "Remaining generation: approximately {p1} min {p3} sec",
                p1=f"{int(eta // 60)}",
                p3=f"{int(eta % 60)}",
            )
        else:
            remaining = tr("Remaining generation: approximately {p1} sec", p1=f"{int(eta)}")
        self.job_status.setText(
            tr(
                "{p0} · {p2}/{p4} completed · {p6} errors · {p8} sec total request time\n",
                p0=f"{JOB_STATUS.get(result['status'], result['status'])}",
                p2=f"{counts.get('completed', 0)}",
                p4=f"{result['total']}",
                p6=f"{counts.get('failed', 0)}",
                p8=f"{result['generation_seconds']}",
            )
            + speed
            + " · "
            + remaining
            + tr(
                "\nMeasurements are single-request equivalents; actual time "
                "differs with parallel requests."
            )
        )
        reason = result.get("pause_reason")
        if reason and reason != "user":
            descriptions = {
                "timeout": tr("The model response exceeded the timeout. Reduce parallel requests."),
                "connection": tr("Could not connect to the local model server."),
                "out_of_memory": tr("Model server out of memory."),
                "not_found": tr("The selected model or endpoint was not found."),
                "unauthorized": tr("The model server denied access."),
                "unsupported_option": tr("The model server does not support a generation option."),
            }
            self.job_status.setText(
                self.job_status.text()
                + tr("\nAutomatically paused: ")
                + descriptions.get(reason, tr("Model server error."))
            )

    def failed(self, command, message):
        message = diagnostic(message)
        if command in ("approve_all_preview", "approve_all"):
            self.approve_all_button.setEnabled(True)
            self.approve_all_token = None
        if command == "shareable_export":
            self.shareable_export_button.setEnabled(True)
        if command == "page":
            self.page_pending = False
        if command == "run_job":
            self.job_combo.setEnabled(True)
            self.parallel_requests.setEnabled(True)
            self.job_progress.setRange(0, 1)
            self.job_progress.setValue(0)
            self.job_progress.setFormat(tr("Job stopped"))
        if command.startswith("deployment_"):
            self.setEnabled(True)
            self.installation_state.setText(message)
        if command.startswith("editor_draft_"):
            return  # Taslak controller'ı tek uçuşlu isteğin hatasını işler.
        if command == "open":
            self.setEnabled(True)
            if not self.project_open:
                self.current_item = None
                self.review_model.set_rows([])
                for index in range(1, self.tabs.count()):
                    self.tabs.setTabEnabled(index, False)
        if command == "backup":
            self.setEnabled(True)
        self.statusBar().showMessage(message)
        if self.closing:
            return
        QMessageBox.warning(self, tr("Could not complete the operation"), message)

    def closeEvent(self, event):
        self.bulk_timer.stop()
        if self.backend_closed:
            event.accept()
        else:
            event.ignore()
            if not self.closing and not self.draft_deferred:
                self.setEnabled(False)
                self.draft_deferred = ("close", None)
                self.drafts.flush()
                self.draft_state_changed()

    def backend_stopped(self):
        self.backend_closed = True
        self.close()


class PilotReportDialog(QDialog):
    def __init__(self, report, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Pilot measurements and source / translation review"))
        self.resize(1100, 750)
        self.acknowledged = False
        layout = QVBoxLayout(self)
        counts = report["progress"]["counts"]
        summary = QLabel(
            tr(
                (
                    "{p0} records · {p2} successful · {p4} errors · {p6} retries."
                    " Generation requests: {p8} sec · median {p10} sec · p95 "
                    "{p12} sec. Human approved: {p14} · edited after generation: "
                    "{p16}. These measurements do not guarantee linguistic "
                    "accuracy."
                ),
                p0=f"{report['record_count']}",
                p2=f"{counts.get('completed', 0)}",
                p4=f"{counts.get('failed', 0)}",
                p6=f"{report['retry_count']}",
                p8=f"{report['progress']['generation_seconds']}",
                p10=f"{report['median_request_seconds']}",
                p12=f"{report['p95_request_seconds']}",
                p14=f"{report['human_approved_records']}",
                p16=f"{report['changed_after_generation']}",
            )
        )
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(summary)
        if report["record_count"] > 200:
            layout.addWidget(
                QLabel(tr("Showing the first 200 records; filter the rest in Review."))
            )
        model = ReviewModel()
        model.set_rows([{**row, "status": row["review_status"]} for row in report["records"][:200]])
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        layout.addWidget(table, 2)
        pair = QSplitter()
        source = QTextEdit()
        source.setReadOnly(True)
        target = QTextEdit()
        target.setReadOnly(True)
        pair.addWidget(source)
        pair.addWidget(target)
        layout.addWidget(pair, 1)

        def selected():
            indexes = table.selectionModel().selectedRows()
            if indexes:
                row = model.rows[indexes[0].row()]
                source.setPlainText(row["source_text"])
                target.setPlainText(
                    row["translation"]
                    or tr("Translation rejected: ") + (row["error_code"] or "bilinmiyor")
                )

        table.selectionModel().selectionChanged.connect(selected)
        label = QLabel(tr("Local report: ") + path)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.reviewed = QCheckBox(
            tr(
                "I reviewed the pilot results and linguistic quality. "
                "Problematic records remain separate."
            )
        )
        layout.addWidget(self.reviewed)
        acknowledge = QPushButton(tr("Save pilot review"))
        acknowledge.setEnabled(False)
        eligible = report["kind"] == "pilot" and report["progress"]["status"] in (
            "completed",
            "completed_with_errors",
        )
        self.reviewed.toggled.connect(lambda checked: acknowledge.setEnabled(checked and eligible))
        acknowledge.clicked.connect(self.acknowledge)
        layout.addWidget(acknowledge)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.reject)
        layout.addWidget(close)

    def acknowledge(self):
        self.acknowledged = True
        self.accept()


def launch() -> int:
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
