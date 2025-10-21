# app/ss2gd/region_select.py
from __future__ import annotations
import sys
from typing import Tuple, Optional, List

from PySide6.QtCore import Qt, QRect, QPoint, Signal, QEventLoop
from PySide6.QtGui import QGuiApplication, QPainter, QColor, QPen, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget, QRubberBand

class _SelectOverlay(QWidget):
    """各モニタ上に出す半透明オーバーレイ。ドラッグで矩形選択。"""
    finished = Signal(QRect)   # ウィンドウ座標の矩形を返す

    def __init__(self, screen_geom: QRect):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._geom = QRect(screen_geom)
        self.setGeometry(self._geom)
        self._dragging = False
        self._origin = QPoint()
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)
        self._rubber.hide()
        self._dim_color = QColor(0, 0, 0, 100)
        self._frame_pen = QPen(QColor(255, 255, 255, 220), 2, Qt.DotLine)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), self._dim_color)
        if self._rubber.isVisible():
            p.setPen(self._frame_pen)
            p.drawRect(self._rubber.geometry())

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.finished.emit(QRect())  # cancel
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._origin = e.pos()
            self._rubber.setGeometry(QRect(self._origin, self._origin))
            self._rubber.show()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._dragging:
            rect = QRect(self._origin, e.pos()).normalized()
            self._rubber.setGeometry(rect)
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            rect = self._rubber.geometry().normalized()
            self._rubber.hide()
            if rect.width() <= 1 or rect.height() <= 1:
                self.finished.emit(QRect())  # cancel
                return
            self.finished.emit(rect)  # ローカル座標（後でグローバルに直す）

def select_rect() -> Tuple[int, int, int, int]:
    """
    画面を暗転オーバーレイしてドラッグ矩形を選ばせる。
    戻り値は (x, y, w, h) の“グローバル座標”。Esc/0サイズでキャンセル時は RuntimeError。
    既に QApplication が動作中でも、ローカル QEventLoop だけを回すので安全。
    """
    app = QApplication.instance() or QApplication(sys.argv)
    screens = QGuiApplication.screens()
    if not screens:
        raise RuntimeError("No screens")

    overlays: List[_SelectOverlay] = []
    result_rect_global: Optional[QRect] = None
    loop = QEventLoop()

    def on_finished_from(ov: _SelectOverlay, rect_local: QRect):
        nonlocal result_rect_global
        if rect_local.isNull() or rect_local.width() <= 1 or rect_local.height() <= 1:
            result_rect_global = QRect()
        else:
            g = QRect(rect_local)
            g.translate(ov.geometry().topLeft())  # ローカル→グローバル
            result_rect_global = g
        for w in overlays:
            w.close()
        loop.quit()  # ← app.exec() は使わずローカルループだけを終了

    for s in screens:
        ov = _SelectOverlay(s.geometry())
        ov.finished.connect(lambda rect, o=ov: on_finished_from(o, rect))
        ov.showFullScreen()
        overlays.append(ov)

    # 常にローカルイベントループのみ実行（既存アプリに干渉しない）
    loop.exec()

    if not result_rect_global or result_rect_global.isNull():
        raise RuntimeError("Selection canceled")

    return (
        int(result_rect_global.x()),
        int(result_rect_global.y()),
        int(result_rect_global.width()),
        int(result_rect_global.height()),
    )

__all__ = ["select_rect"]
