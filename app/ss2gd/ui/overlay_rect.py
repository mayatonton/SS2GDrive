# app/ss2gd/ui/overlay_rect.py
from __future__ import annotations
from typing import List
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QGuiApplication, QPainter, QPen, QColor, QScreen
from PySide6.QtWidgets import QWidget

class _RectLayer(QWidget):
    """各スクリーン全面に被せる透明・非干渉の描画レイヤ。選択矩形の枠だけ描く。"""
    def __init__(self, screen: QScreen):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        try:
            # 可能ならコンポジタに完全クリックスルーを伝える
            self.setWindowFlag(Qt.WindowTransparentForInput, True)
        except Exception:
            pass

        self._screen = screen
        self._global_rect = QRect()
        # 色：録画前=シアン、録画中=赤
        self._pen_idle = QPen(QColor(0, 180, 255, 230), 2)
        self._pen_rec  = QPen(QColor(255, 60, 60, 230), 2)
        self._recording = False

        self._update_geom()

    def _update_geom(self):
        # パネル/タイトルバーの影響を受けない「物理的な」画面座標
        g = self._screen.geometry()
        self.setGeometry(g)

    def set_global_rect(self, r: QRect, recording: bool):
        self._global_rect = QRect(r)
        self._recording = bool(recording)
        self.update()

    def paintEvent(self, _ev):
        if self._global_rect.isNull():
            return
        p = QPainter(self)
        # グローバル→この画面ローカル
        g = self._screen.geometry()
        local = QRect(self._global_rect)
        local.translate(-g.topLeft())
        local = local.intersected(self.rect())
        if not local.isNull():
            p.setPen(self._pen_rec if self._recording else self._pen_idle)
            p.drawRect(local.adjusted(0, 0, -1, -1))

class RectHintOverlayManager:
    """矩形ヒントの表示/非表示を管理（完全クリックスルーで操作を妨げない）。"""
    def __init__(self):
        self._layers: List[_RectLayer] = []
        self._global_rect = QRect()
        self._recording   = False
        self._build_layers()

        app = QGuiApplication.instance()
        if app:
            app.screenAdded.connect(self._rebuild)
            app.screenRemoved.connect(self._rebuild)

    def show_rect(self, rect: QRect, recording: bool = False):
        """グローバル座標の矩形を表示（recording=True で色を赤に）。"""
        self._global_rect = QRect(rect)
        self._recording = bool(recording)
        if not self._layers:
            self._build_layers()
        for ly in self._layers:
            ly._update_geom()
            ly.set_global_rect(self._global_rect, self._recording)
            ly.show()
            ly.raise_()

    def hide(self):
        for ly in self._layers:
            ly.hide()

    def close(self):
        for ly in self._layers:
            try:
                ly.close()
            except Exception:
                pass
        self._layers.clear()

    # ---- internal ----
    def _build_layers(self):
        self._layers = [ _RectLayer(s) for s in QGuiApplication.screens() ]

    def _rebuild(self, *args):
        self.hide()
        self._build_layers()
        if not self._global_rect.isNull():
            self.show_rect(self._global_rect, self._recording)
