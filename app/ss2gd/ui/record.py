# app/ss2gd/ui/record.py
from __future__ import annotations
import os, sys, threading, time, shutil, subprocess, webbrowser
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMessageBox
)
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtCore import QTimer, QUrl, QObject, Signal, Slot, Qt, QRect

from ..region_select import select_rect
from ..recorder import start_recording, stop_recording
from .overlay_rect import RectHintOverlayManager

# keep_clipboard_alive が無い環境でも落ちないようフォールバック
try:
    from ..clipboard import copy_to_clipboard, keep_clipboard_alive as _keep_clipboard_alive
except Exception:
    from ..clipboard import copy_to_clipboard  # type: ignore
    def _keep_clipboard_alive(ms: int = 1200) -> None:
        pass

DEBUG = bool(os.environ.get("SS2GD_DEBUG"))
def _dbg(msg: str) -> None:
    if DEBUG: print(f"[rec-ui] {msg}", flush=True)

class _GuiInvoker(QObject):
    """ワーカースレッドから安全に GUI スレッドへ処理を投げる"""
    call_signal = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.call_signal.connect(self._call, Qt.QueuedConnection)
    @Slot(object)
    def _call(self, func):
        try:
            func()
        except Exception as e:
            _dbg(f"invoker func error: {e}")

class RecordWindow(QWidget):
    def __init__(self, fps:int=30):
        super().__init__()
        self.setWindowTitle("SS2GDrive Record")
        self.setWindowIcon(QIcon.fromTheme("com.ss2gd.SS2GDrive-record") or QIcon.fromTheme("com.ss2gd.SS2GDrive"))
        self._fps = int(fps)
        self._rect: Optional[Tuple[int,int,int,int]] = None
        self._is_recording = False
        self._started_ts: Optional[float] = None
        self._invoker = _GuiInvoker(self)

        lay = QVBoxLayout(self)
        self.lbl_rect = QLabel("Region: (not selected)")
        self.lbl_status = QLabel("Status: Ready")
        lay.addWidget(self.lbl_rect)
        lay.addWidget(self.lbl_status)

        row1 = QHBoxLayout()
        self.btn_select = QPushButton("Reselect Region")
        self.btn_start  = QPushButton("Start")
        self.btn_stop   = QPushButton("Stop & Upload")
        row1.addWidget(self.btn_select); row1.addWidget(self.btn_start); row1.addWidget(self.btn_stop)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_settings = QPushButton("Settings…")
        self.btn_quit     = QPushButton("Quit")
        row2.addWidget(self.btn_settings); row2.addWidget(self.btn_quit)
        lay.addLayout(row2)

        self.btn_select.clicked.connect(self.on_select)
        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_settings.clicked.connect(self.on_settings)
        self.btn_quit.clicked.connect(self.close)

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._tick)

        # 起動時に矩形選択
        QTimer.singleShot(150, self.on_select)

        # 選択領域の可視化（常時表示用オーバーレイ）
        self._hint = RectHintOverlayManager()

    # -------- helpers ----------
    def _set_status(self, text:str) -> None:
        self.lbl_status.setText(f"Status: {text}")
        _dbg(text)

    def _update_rect_label(self):
        if self._rect:
            x,y,w,h = self._rect
            self.lbl_rect.setText(f"Region: x={x}, y={y}, w={w}, h={h}")
        else:
            self.lbl_rect.setText("Region: (not selected)")

    def _guard_rect(self) -> bool:
        if not self._rect:
            QMessageBox.warning(self, "SS2GDrive", "Please select a region first.")
            return False
        return True

    def _tick(self):
        if self._is_recording and self._started_ts:
            sec = int(time.time() - self._started_ts)
            self._set_status(f"Recording… {sec}s")

    def _set_buttons_recording(self, recording: bool):
        self._is_recording = recording
        self.btn_select.setEnabled(not recording)
        self.btn_start.setEnabled(not recording)
        self.btn_stop.setEnabled(recording)

    def _open_settings(self):
        exe = shutil.which("ss2gd")
        if not exe:
            QMessageBox.critical(self, "SS2GDrive", "ss2gd launcher not found in PATH.")
            return
        try:
            subprocess.Popen([exe, "settings"])
        except Exception as e:
            QMessageBox.critical(self, "SS2GDrive", f"Failed to open settings:\n{e}")

    # -------- slots ----------
    def on_settings(self):
        self._open_settings()

    def on_select(self):
        try:
            r = select_rect()  # (x,y,w,h)
            if not r:
                self._set_status("Selection cancelled")
                return
            self._rect = tuple(int(v) for v in r)
            self._update_rect_label()
            self._set_status("Region selected")
            # 画面に枠を常時表示（録画前＝非録画色）
            x, y, w, h = self._rect
            self._hint.show_rect(QRect(x, y, w, h), recording=self._is_recording)
        except Exception as e:
            self._rect = None
            self._update_rect_label()
            QMessageBox.critical(self, "SS2GDrive", f"Region selection failed:\n{e}")

    def on_start(self):
        if not self._guard_rect(): return
        if self._is_recording: return
        self._set_buttons_recording(True)
        self._started_ts = time.time()
        self.timer.start()
        self._set_status("Starting…")

        def worker():
            err = None
            try:
                # 非同期で録画開始（UI で選んだ rect を渡す）
                start_recording(fps=self._fps, rect=self._rect)
            except Exception as e:
                err = str(e)

            def finish():
                if err:
                    self._set_buttons_recording(False)
                    self.timer.stop()
                    self._set_status(f"Start failed: {err}")
                    QMessageBox.critical(self, "SS2GDrive", f"Start failed:\n{err}")
                else:
                    self._set_status("Recording…")
                    # 録画中は赤系に切替
                    if self._rect:
                        x, y, w, h = self._rect
                        self._hint.show_rect(QRect(x, y, w, h), recording=True)
            self._invoker.call_signal.emit(finish)

        threading.Thread(target=worker, daemon=True).start()

    def on_stop(self):
        if not self._is_recording:
            return

        # 即時 UI 切替（録画停止・アップロードはバックグラウンド）
        self._set_status("Uploading…")
        self.timer.stop()
        self._is_recording = False
        # アップロード中は全部無効化
        self.btn_select.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(False)

        def worker():
            link = None; err = None
            try:
                link = stop_recording(open_browser=False, copy_link=False)
            except Exception as e:
                err = str(e)

            def finish():
                # UI を戻す
                self.btn_select.setEnabled(True)
                self.btn_start.setEnabled(True)
                self.btn_stop.setEnabled(False)

                if err:
                    self._set_status(f"Failed: {err}")
                    QMessageBox.critical(self, "SS2GDrive", f"Stop & Upload failed:\n{err}")
                    return

                self._set_status("Uploaded")
                # 録画終了なので枠を消す
                self._hint.hide()

                if link:
                    try:
                        copy_to_clipboard(link); _keep_clipboard_alive(2000)
                    except Exception:
                        pass
                    try:
                        QDesktopServices.openUrl(QUrl(link))
                    except Exception:
                        try: webbrowser.open(link)
                        except Exception:
                            pass

            self._invoker.call_signal.emit(finish)

        threading.Thread(target=worker, daemon=True).start()

    def closeEvent(self, ev):
        """ウィンドウ終了時の後片付け"""
        try:
            self._hint.close()
        except Exception:
            pass
        super().closeEvent(ev)

def run_window():
    app = QApplication.instance() or QApplication(sys.argv)
    w = RecordWindow()
    w.show(); w.raise_(); w.activateWindow()
    app.exec()

if __name__ == "__main__":
    run_window()
