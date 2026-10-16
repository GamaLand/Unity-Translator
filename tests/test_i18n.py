import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from string import Formatter

import pytest

from unitytranslator.ui import i18n


def fields(message):
    return sorted(field for _, field, _, _ in Formatter().parse(message) if field is not None)


def test_all_eight_catalogs_cover_every_interface_message_with_matching_placeholders():
    english = i18n.catalog("en")
    assert len(i18n.LANGUAGES) == 8 and len(english) >= 300
    for language in i18n.LANGUAGES:
        translated = i18n.catalog(language)
        assert translated.keys() == english.keys()
        for source, text in translated.items():
            assert text.strip() and "\x00" not in text
            assert fields(source) == fields(text), (language, source)
            for token in ("%p%", "%v", "%m", "Kur.cmd"):
                assert source.count(token) == text.count(token), (language, source)
    for name in ("window.py", "drafts.py"):
        tree = ast.parse(
            (Path(__file__).parents[1] / "src/unitytranslator/ui" / name).read_text(
                encoding="utf-8"
            )
        )
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
            ):
                assert node.args and isinstance(node.args[0], ast.Constant)
                assert node.args[0].value in english


def test_english_default_and_saved_preference_do_not_touch_projects(tmp_path, monkeypatch):
    monkeypatch.delenv("UNITYTRANSLATOR_UI_LANGUAGE", raising=False)
    monkeypatch.setenv("UNITYTRANSLATOR_CONFIG_HOME", str(tmp_path))
    assert i18n.preferred_language() == "en"
    i18n.save_language("de")
    assert i18n.preferred_language() == "de"
    with pytest.raises(ValueError):
        i18n.save_language("not-a-language")
    assert i18n.preferred_language() == "de"
    i18n.settings_path().write_text('{"language": "not-a-language"}', encoding="utf-8")
    assert i18n.preferred_language() == "en"
    i18n.settings_path().write_text("broken json", encoding="utf-8")
    assert i18n.preferred_language() == "en"


@pytest.mark.parametrize("language", list(i18n.LANGUAGES))
def test_real_window_and_approval_phrase_in_each_language(tmp_path, language):
    environment = os.environ.copy()
    environment.update(
        UNITYTRANSLATOR_UI_LANGUAGE=language,
        UNITYTRANSLATOR_CONFIG_HOME=str(tmp_path),
        QT_QPA_PLATFORM="offscreen",
        PYTHONIOENCODING="utf-8",
    )
    code = """
import json,time
from pathlib import Path
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication,QMessageBox
from unitytranslator.ui.i18n import active_language,tr,settings_path
from unitytranslator.ui.window import MainWindow,AllApprovalDialog
from unitytranslator.review_selection import canonical_all_confirmation
app=QApplication([])
window=MainWindow()
window.show()
assert window.tabs.tabText(0)==tr('1 · Project')
assert window.tabs.tabText(5)==tr('6 · Review')
menus=window.menuBar().actions()
assert menus[0].text()==tr('Help') and menus[1].text()==tr('Language')
assert len(window.language_actions.actions())==8
assert window.source_language.currentText()=='en'
expected_target=active_language() if active_language()!='en' else 'tr'
assert window.target_language.currentText()==expected_target
opened=[]
open_url=QDesktopServices.openUrl
QDesktopServices.openUrl=lambda url: opened.append(Path(url.toLocalFile())) or True
window.open_help_document('README-WINDOWS.md')
QDesktopServices.openUrl=open_url
assert len(opened)==1 and opened[0].is_file()
assert opened[0].parent.name=='guide' and opened[0].name==active_language()+'.md'
dialog=AllApprovalDialog({'count':201,'warnings':4,'excluded':2},window)
assert dialog.phrase==tr('approve {p0} translations',p0='201')
assert canonical_all_confirmation(201) != ''
assert not dialog.confirm.isEnabled()
dialog.acknowledge.setChecked(True);dialog.confirm.click()
assert dialog.stage==2 and not dialog.confirm.isEnabled()
dialog.confirmation.setText(dialog.phrase);assert dialog.confirm.isEnabled()
dialog.reject()
sent=[]
window.current_project_id='synthetic-project'
window.approve_all_token='ui-token'
submit=window.bridge.submit
window.bridge.submit=lambda command,data=None: sent.append((command,data))
def approve_dialog(item):
 item.acknowledge.setChecked(True);item.confirm.click()
 item.confirmation.setText(item.phrase);item.confirm.click()
 return item.result()
AllApprovalDialog.exec=approve_dialog
window.completed('approve_all_preview',{
 'project_id':'synthetic-project','request_token':'ui-token','token':'preview-token',
 'count':201,'warnings':4,'excluded':2})
assert sent[-1][0]=='approve_all'
assert sent[-1][1]['confirmation']==canonical_all_confirmation(201)
window.bridge.submit=submit
window.source_editor.setPlainText('Original game text: Continue / {0} / I2')
original=active_language()
QMessageBox.information=lambda *args: None
window.select_ui_language('de')
assert json.loads(settings_path().read_text(encoding='utf-8'))['language']=='de'
assert active_language()==original
assert window.source_editor.toPlainText()=='Original game text: Continue / {0} / I2'
window.close()
deadline=time.monotonic()+5
while not window.backend_closed and time.monotonic()<deadline:
 app.processEvents();time.sleep(.01)
assert window.backend_closed
print(json.dumps({'language':original,'passed':True}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {"language": language, "passed": True}
