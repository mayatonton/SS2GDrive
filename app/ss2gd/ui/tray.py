# app/ss2gd/ss2gd/ui/tray.py
from __future__ import annotations

import os, sys, time, asyncio, threading, webbrowser, shutil, subprocess

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget,
    QVBoxLayout, QLabel, QPushButton, QMessageBox
)
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtCore import QTimer, QUrl, QObject, Signal, Slot, Qt  # ← Qt を追加

from ..config import load_settings

# keep_clipboard_alive が無い環境でも落ちないようフォールバック
try:
    from ..clipboard import copy_to_clipboard, keep_clipboard_alive as _keep_clipboard_alive
except Exception:
    from ..clipboard import copy_to_clipboard  # type: ignore
    def _keep_clipboard_alive(ms: int = 1200) -> None:
        pass  # tray常駐では不要

from ..screenshot_portal import take_interactive_screenshot
from ..drive_uploader import upload_and_share


def _dbg(msg: str) -> None:
    if os.getenv("SS2GD_DEBUG"):
        print(f"[tray] {msg}", file=sys.stderr, flush=True)


class _GuiInvoker(QObject):
    """任意の callable を GUI スレッドで実行するヘルパ"""
    call_signal = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.call_signal.connect(self._call, Qt.QueuedConnection)  # GUI スレッドでキュー実行

    @Slot(object)
    def _call(self, func) -> None:
        try:
            func()
        except Exception as e:
            _dbg(f"invoker func error: {e}")


class TrayApp:
    """System tray controller with fallback mini window."""

    def __init__(self, force_window: bool = False) -> None:
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.tray: QSystemTrayIcon | None = None
        self.win: QWidget | None = None
        self._force_window = bool(force_window)
        self._invoker = _GuiInvoker()  # GUI スレッド所属

        if not self._force_window and QSystemTrayIcon.isSystemTrayAvailable():
            self._make_tray()
        else:
            _dbg("using fallback window")
            self._make_fallback_window()

    # ---------- UI building ----------

    def _make_tray(self) -> None:
        icon = QIcon.fromTheme("com.ss2gd.SS2GDrive")
        self.tray = QSystemTrayIcon(icon, self.app)
        menu = QMenu()

        act_shot = menu.addAction("Snap && Upload")
        act_set = menu.addAction("Settings…")
        menu.addSeparator()
        act_quit = menu.addAction("Quit")

        act_shot.triggered.connect(self.on_shot)
        act_set.triggered.connect(self.on_settings)
        act_quit.triggered.connect(self.app.quit)

        self.tray.setContextMenu(menu)
        self.tray.setToolTip("SS2GDrive")
        self.tray.show()
        _dbg("tray shown")

    def _make_fallback_window(self) -> None:
        self.win = QWidget()
        self.win.setWindowTitle("SS2GDrive")

        lay = QVBoxLayout(self.win)
        lay.addWidget(QLabel("Tray is not available.\nUse this window instead."))

        self.btn_shot = QPushButton("Snap & Upload")
        self.btn_set = QPushButton("Settings…")
        self.btn_quit = QPushButton("Quit")

        self.btn_shot.clicked.connect(self.on_shot)
        self.btn_set.clicked.connect(self.on_settings)
        self.btn_quit.clicked.connect(self.app.quit)

        lay.addWidget(self.btn_shot); lay.addWidget(self.btn_set); lay.addWidget(self.btn_quit)

        self.win.show()
        self.win.raise_(); self.win.activateWindow(); self.win.showNormal()
        _dbg("fallback window shown")

    # ---------- helpers ----------

    def _mime_from_settings(self) -> str:
        st = load_settings()
        fmt = (st.get("image_format") or "png").lower()
        return "image/jpeg" if fmt in ("jpg", "jpeg") else "image/png"

    def _open_settings(self) -> None:
        """設定ダイアログを別プロセスで開く（ss2gd settings）"""
        exe = shutil.which("ss2gd")
        if not exe:
            QMessageBox.critical(self.win if self.win else None, "SS2GDrive", "ss2gd launcher not found in PATH.")
            return
        try:
            subprocess.Popen([exe, "settings"])
            _dbg("launched settings via ss2gd settings")
        except Exception as e:
            QMessageBox.critical(self.win if self.win else None, "SS2GDrive", f"Failed to open settings:\n{e}")

    # ---------- slots ----------

    def on_settings(self) -> None:
        self._open_settings()

    def on_shot(self) -> None:
        """Snap & Upload（UI非ブロッキング、失敗はダイアログ）"""
        btn = getattr(self, "btn_shot", None)
        if btn:
            btn.setEnabled(False); btn.setText("Working…")

        def worker() -> None:
            link = None; err = None
            try:
                _dbg("take_interactive_screenshot() start")
                path = take_interactive_screenshot()
                _dbg(f"screenshot path: {path!r}")
                if not path or not os.path.exists(path):
                    raise RuntimeError("Screenshot canceled or not saved")

                mime = self._mime_from_settings()
                base = time.strftime("SS_%Y%m%d_%H%M%S")
                _dbg(f"upload_and_share({mime}, {base})")
                link = upload_and_share(path, mime, base)
                _dbg(f"uploaded: {link}")
            except Exception as e:
                err = str(e); _dbg(f"error: {err}")

            def finish() -> None:
                _dbg("finish() on GUI thread")
                if btn:
                    btn.setEnabled(True); btn.setText("Snap & Upload")
                if link:
                    try:
                        copy_to_clipboard(link); _keep_clipboard_alive(2000)
                    except Exception as e2:
                        _dbg(f"clipboard err: {e2}")
                    try:
                        QDesktopServices.openUrl(QUrl(link))
                    except Exception as e3:
                        _dbg(f"QDesktopServices err: {e3}")
                        try: webbrowser.open(link)
                        except Exception as e4: _dbg(f"webbrowser err: {e4}")
                else:
                    QMessageBox.critical(self.win if self.win else None, "SS2GDrive",
                                         f"Snap & Upload failed:\n{err or 'unknown error'}")

            # GUIスレッドへディスパッチ
            self._invoker.call_signal.emit(finish)

        threading.Thread(target=worker, daemon=True).start()

    # ---------- lifecycle ----------

    def run(self) -> None:
        self.app.exec()


if __name__ == "__main__":
    app = TrayApp(force_window=("--window" in sys.argv))
    app.run()
