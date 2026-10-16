"""Plain data editor that preserves project text across Qt paragraph normalization."""

import re

from PySide6.QtWidgets import QTextEdit


class DataTextEdit(QTextEdit):
    def __init__(self, parent=None, reference=""):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.reference = reference
        self._loaded = ""
        self._shadow = ""

    def setPlainText(self, text):
        self._loaded = text
        super().setPlainText(text)
        self._shadow = self.document().toRawText()

    def value(self):
        raw = self.document().toRawText()
        if raw == self._shadow:
            return self._loaded
        # Qt normalizes LF/CRLF/CR into paragraph separators. If the paragraph count
        # matches, restore the current translation's line endings, or the source's as fallback.
        # A changed count uses LF; the strict format validator will reject a mismatch.
        endings = re.findall(r"\r\n|\r|\n|\u2029", self._loaded or self.reference)
        if raw.count("\u2029") != len(endings):
            return raw.replace("\u2029", "\n")
        index = iter(endings)
        return re.sub("\u2029", lambda _: next(index), raw)
