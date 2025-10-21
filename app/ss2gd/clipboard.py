# app/ss2gd/ss2gd/clipboard.py
import sys
from PySide6.QtGui import QGuiApplication, QClipboard
from PySide6.QtCore import QMimeData, QEventLoop, QTimer

def _app() -> QGuiApplication:
    return QGuiApplication.instance() or QGuiApplication(sys.argv)

def copy_to_clipboard(text: str) -> None:
    """テキストをクリップボード（+ X11 の Selection があればそこにも）に入れる。"""
    app = _app()
    cb: QClipboard = app.clipboard()
    mime = QMimeData()
    mime.setText(text)

    # 通常のクリップボード
    cb.clear(QClipboard.Clipboard)
    cb.setMimeData(mime, QClipboard.Clipboard)

    # X11 の中ボタン貼り付け（Selection）が使える環境ならそちらにも
    try:
        cb.clear(QClipboard.Selection)
        cb.setMimeData(mime, QClipboard.Selection)
    except Exception:
        pass

def keep_clipboard_alive(ms: int = 1200) -> None:
    """
    直後にプロセスが終了しても貼り付けが生きるよう、短時間だけイベントループを回す。
    CLI 実行直後に終了するケース（.desktop 起動など）で有効。
    """
    app = _app()
    loop = QEventLoop()
    QTimer.singleShot(int(ms), loop.quit)
    loop.exec()
