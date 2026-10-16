"""Debounced single-flight coordination of local Qt editor drafts."""

from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal

from unitytranslator.ui.i18n import tr


class DraftController(QObject):
    changed = Signal()
    action_finished = Signal(str, str)
    failure = Signal(str, str)

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.project_id = None
        self.entries = {}
        self.pending = None
        self.action = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.flush)
        bridge.completed.connect(self.completed)
        bridge.failed.connect(self.failed)

    def reset(self, project_id):
        if self.pending or self.action or any(self.dirty(e) for e in self.entries.values()):
            raise ValueError(tr("Cannot switch projects while a draft is unsaved."))
        self.timer.stop()
        self.project_id = project_id
        self.entries.clear()
        self.changed.emit()

    @staticmethod
    def dirty(entry):
        return entry["text"] != entry["persisted_text"]

    @property
    def settled(self):
        return (
            self.pending is None
            and self.action is None
            and not any(self.dirty(e) for e in self.entries.values())
        )

    @property
    def has_error(self):
        return any(e.get("error") and self.dirty(e) for e in self.entries.values())

    def ensure(self, row):
        unit = row["unit_id"]
        entry = self.entries.get(unit)
        if entry and (entry["revision"] or self.dirty(entry) or self.pending):
            return entry
        saved = row.get("editor_draft")
        if saved:
            entry = {**saved, "persisted_text": saved["text"]}
        else:
            entry = {
                "unit_id": unit,
                "source_revision": row["source_revision"],
                "source_text": row["source_text"],
                "base_version": row["version"],
                "text": row["translation"] or "",
                "revision": 0,
                "persisted_text": row["translation"] or "",
            }
        self.entries[unit] = entry
        return entry

    def update(self, row, text):
        entry = self.ensure(row)
        entry["text"] = text
        entry.pop("error", None)
        self.timer.start()
        self.changed.emit()

    def flush(self):
        self.timer.stop()
        if self.pending:
            return
        for unit, entry in self.entries.items():
            if self.action == ("discard", unit):
                continue  # An explicit discard must not save the most recently edited text.
            if self.dirty(entry) and not entry.get("error"):
                self.send(
                    "put",
                    unit,
                    {
                        "source_revision": entry["source_revision"],
                        "base_version": entry["base_version"],
                        "text": entry["text"],
                        "expected_revision": entry["revision"],
                    },
                )
                return
        if self.action:
            action, unit = self.action
            entry = self.entries[unit]
            if self.has_error and action != "discard":
                self.action = None
                self.changed.emit()
                return
            if action == "discard" and not entry["revision"]:
                self.finish_action(action, unit)
            else:
                self.send(action, unit, {"expected_revision": entry["revision"]})
        self.changed.emit()

    def send(self, action, unit, data):
        token = uuid4().hex
        command = "editor_draft_" + action
        self.pending = (command, unit, token, data.get("text"))
        self.bridge.submit(
            command,
            {
                **data,
                "project_id": self.project_id,
                "unit_id": unit,
                "request_token": token,
            },
        )
        self.changed.emit()

    def request_action(self, action, unit):
        if self.action:
            return
        self.entries[unit].pop("error", None)
        self.action = (action, unit)
        self.changed.emit()
        self.flush()

    def finish_action(self, action, unit):
        self.entries.pop(unit, None)
        self.action = None
        self.action_finished.emit(action, unit)
        self.changed.emit()

    def completed(self, command, result):
        if not command.startswith("editor_draft_") or not self.pending:
            return
        expected, unit, token, text = self.pending
        if (
            command != expected
            or result.get("project_id") != self.project_id
            or result.get("request_token") != token
            or result.get("unit_id") != unit
        ):
            return
        self.pending = None
        if command == "editor_draft_put":
            entry = self.entries[unit]
            entry["revision"] = result["draft"]["revision"]
            entry["persisted_text"] = text
            entry.pop("error", None)
        else:
            self.finish_action(command.removeprefix("editor_draft_"), unit)
        self.flush()

    def failed(self, command, message):
        if not self.pending or self.pending[0] != command:
            return
        unit = self.pending[1]
        self.entries[unit]["error"] = message
        self.pending = self.action = None
        self.failure.emit(command, message)
        self.changed.emit()
