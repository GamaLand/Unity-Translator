"""A busy preparation must be visible and must not start a model after close."""

import os
import subprocess
import sys


def test_preparation_status_duplicate_click_and_close_race(tmp_path):
    code = '''
import time
from PySide6.QtWidgets import QApplication
from unitytranslator.ui.window import MainWindow
app=QApplication([])
window=MainWindow()
window.project_open=True
window.tabs.setTabEnabled(4,True)
window.project_totals={'total':93937,'pilot_eligible':93937,'translated':0,'approved':0}
window.current_job='previous-job'
sent=[]
submit=window.bridge.submit
window.bridge.submit=lambda command,data=None: sent.append((command,data))
window.start_pilot()
window.start_pilot()
assert len(sent)==1 and sent[0][0]=='create_job'
assert window.job_preparing and window.cancel_button.isEnabled()
assert not window.pilot_button.isEnabled()
assert 'no model request yet' in window.job_status.text()
window.on_progress({'kind':'preparation','stage':'context'})
assert 'source context' in window.job_status.text()
window.on_progress({'status':'completed','counts':{},'total':0})
assert 'source context' in window.job_status.text()
window.completed('create_job',{'job_id':None,'count':0,'reason':'preparation_cancelled'})
assert not window.job_preparing and 'cancelled' in window.job_status.text()
assert window.current_job=='previous-job'
window.closing=True
window.completed('create_job',{'job_id':'new-job','count':200})
assert not any(command=='run_job' for command,data in sent)
window.bridge.submit=submit
window.bridge.shutdown()
deadline=time.monotonic()+3
while not window.backend_closed and time.monotonic()<deadline:
 app.processEvents();time.sleep(.005)
assert window.backend_closed
print('preparation UI passed')
'''
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8",
        timeout=15, env=dict(os.environ, QT_QPA_PLATFORM="offscreen",
                             UNITYTRANSLATOR_UI_LANGUAGE="en",
                             UNITYTRANSLATOR_CONFIG_HOME=str(tmp_path)),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "preparation UI passed" in result.stdout
