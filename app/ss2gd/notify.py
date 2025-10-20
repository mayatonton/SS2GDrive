import sys
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtGui import QIcon
_tray=None
def _ensure_tray():
    global _tray
    app=QApplication.instance() or QApplication(sys.argv)
    if _tray is None: _tray=QSystemTrayIcon(QIcon.fromTheme("camera-photo")); _tray.show()
    return _tray
def notify(summary:str, body:str=""):
    _ensure_tray().showMessage(summary, body)
