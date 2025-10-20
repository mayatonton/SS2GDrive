import sys, os
from PySide6.QtGui import QGuiApplication, QClipboard
from PySide6.QtCore import QMimeData, QEventLoop, QTimer
def _flush_clipboard(ms:int=200):
    loop=QEventLoop(); QTimer.singleShot(max(1,ms), loop.quit); loop.exec()
def copy_to_clipboard(text:str)->None:
    app=QGuiApplication.instance() or QGuiApplication(sys.argv)
    cb=app.clipboard(); mime=QMimeData(); mime.setText(text)
    cb.clear(QClipboard.Clipboard); cb.setMimeData(mime, QClipboard.Clipboard); _flush_clipboard(250)
    try: cb.clear(QClipboard.Selection); cb.setMimeData(mime, QClipboard.Selection); _flush_clipboard(150)
    except Exception: pass
    if os.environ.get("SS2GD_DEBUG"): print("[clipboard] set text")
