"""The workbench stays usable in every locale without touching a user project."""

import os
import subprocess
import sys

import pytest

from unitytranslator.ui.i18n import LANGUAGES


@pytest.mark.parametrize("language", list(LANGUAGES))
def test_workbench_navigation_editors_and_actions_fit_in_each_locale(tmp_path, language):
    code = r'''
from PySide6.QtCore import QObject, Signal, QPoint
from PySide6.QtWidgets import QApplication, QScrollArea
from unitytranslator.ui.i18n import tr
from unitytranslator.ui.window import MainWindow

class Bridge(QObject):
    completed = Signal(str, object)
    failed = Signal(str, str)
    progress = Signal(object)
    stopped = Signal()
    def submit(self, *args):
        pass
    def shutdown(self):
        self.stopped.emit()

app = QApplication([])
window = MainWindow(Bridge())
window.show()
assert not window.save_translation.isEnabled()
assert not window.approve_translation.isEnabled()
assert not window.tabs.buttons[5].isEnabled()
for i in range(window.tabs.count()):
    window.tabs.setTabEnabled(i, True)
window.tabs.buttons[5].click()
assert window.tabs.currentIndex() == 5
window.tabs.buttons[5].click()
assert window.tabs.buttons[5].isChecked()
window.review_model.set_rows([{
    'unit_id': 'synthetic', 'source_revision': 1, 'version': 1,
    'source_text': '<b>Source</b> [NAME]\nSecond line',
    'translation': '<b>Target</b> [NAME]\nSecond line',
    'original_key': 'chapter/' + 'long-source-key/' * 30,
    'category': 'dialogue', 'status': 'translated', 'issues_json': '[]',
}])
window.table.selectRow(0)
assert window.source_editor.toPlainText().startswith('<b>Source</b>')
assert window.save_translation.isEnabled()
assert window.approve_translation.isEnabled()
assert window.record_identity.toolTip().startswith('chapter/')
for width, height in [(1360, 900), (900, 740)]:
    window.resize(width, height)
    app.processEvents()
    assert window.width() == width and window.height() == height
    for page in range(8):
        window.tabs.buttons[page].click()
        app.processEvents()
        assert window.tabs.currentIndex() == page
        assert window.tabs.buttons[page].isChecked()
        assert window.page_heading.text() == window.tabs.tabText(page).split(' · ', 1)[1]
        page_widget = window.tabs.widget(page)
        if isinstance(page_widget, QScrollArea):
            assert page_widget.horizontalScrollBar().maximum() == 0, (page, width)
    window.tabs.buttons[5].click()
    app.processEvents()
    for editor in (window.source_editor, window.translation_editor):
        bottom = editor.mapTo(window, QPoint(editor.width(), editor.height()))
        assert editor.height() >= 90 and editor.width() >= 200
        assert bottom.y() < window.save_translation.mapTo(window, QPoint()).y()
    assert window.table.height() >= 100
    for control in (window.save_translation, window.approve_translation,
                    window.record_actions, window.bulk_review_button):
        top = control.mapTo(window, QPoint())
        bottom = control.mapTo(window, QPoint(control.width(), control.height()))
        assert 0 <= top.x() < bottom.x() <= width
        assert 0 <= top.y() < bottom.y() < height
    window.review_panels.setCurrentIndex(1)
    window.dialogue_references.show()
    window.review_details.setText('Synthetic warning ' * 100)
    app.processEvents()
    assert window.inspector_details.text() == window.review_details.text()
    assert window.review_details.toolTip() == window.review_details.text()
    assert window.save_translation.isVisible()
    assert window.width() == width and window.height() == height
    window.review_panels.setCurrentIndex(0)
    window.review_details.setText('Synthetic check')

# Menu actions follow the existing guarded controls and invoke their exact handler.
control = window.retranslate_page_button
action = window.bulk_review_button.controls[control]
clicked = []
control.clicked.connect(lambda: clicked.append(True))
control.setEnabled(False)
assert not action.isEnabled()
action.trigger()
assert not clicked
control.setEnabled(True)
assert action.isEnabled()
action.trigger()
assert clicked == [True]
window.tabs.setTabEnabled(7, False)
assert not window.tabs.buttons[7].isEnabled()
window.close()
app.processEvents()
assert window.backend_closed
'''
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8",
        timeout=20, env=dict(
            os.environ, QT_QPA_PLATFORM="offscreen", UNITYTRANSLATOR_UI_LANGUAGE=language,
            UNITYTRANSLATOR_CONFIG_HOME=str(tmp_path),
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
