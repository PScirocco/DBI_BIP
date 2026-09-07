"""再利用ウィジェット（``prototype/widgets.py`` から移植）

- ``ImagePanel`` : タイトル付き画像プレビュー（ウィンドウ追従で縮小表示）
- ``MplCanvas``  : 劣化マップ表示（チャネル色の輝度 / RGB合成）＋ カーソル位置通知

画像 I/O は Unicode パス対応の :mod:`bisim.imio` を使う。
"""
from __future__ import annotations

import cv2
import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from bisim import imio
from bisim.ui.i18n import t


def bgr_to_qimage(bgr: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()


def read_first_frame(path: str) -> np.ndarray | None:
    """静止画 or 動画の先頭フレームを BGR で返す。読めなければ None。"""
    p = str(path)
    if p.lower().endswith(".mp4"):
        cap = cv2.VideoCapture(p)
        ok, frame = cap.read()
        cap.release()
        return frame if ok else None
    return imio.imread(p)


class ImagePanel(QWidget):
    """タイトル付きの画像プレビュー。ウィンドウサイズに追従して縮小表示。"""

    def __init__(self, title: str = "", min_h: int = 150):
        super().__init__()
        self._title = QLabel(title)
        self._title.setStyleSheet("font-weight:600;")
        self._view = QLabel(t("img.none"))
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setMinimumHeight(min_h)
        self._view.setStyleSheet(
            "border:1px solid #b7bcc4; background:#d9dbde; color:#5f6368;")
        self._view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lay.addWidget(self._title)
        lay.addWidget(self._view, 1)
        self._pixmap: QPixmap | None = None

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_bgr(self, bgr: np.ndarray | None) -> None:
        if bgr is None:
            self.set_message(t("img.none"))
            return
        self._pixmap = QPixmap.fromImage(bgr_to_qimage(bgr))
        self._rescale()

    def set_qimage(self, qimg: QImage | None) -> None:
        if qimg is None:
            self.set_message(t("img.none"))
            return
        self._pixmap = QPixmap.fromImage(qimg)
        self._rescale()

    def set_message(self, msg: str) -> None:
        self._pixmap = None
        self._view.setText(msg)

    def _rescale(self) -> None:
        if self._pixmap is not None:
            self._view.setPixmap(self._pixmap.scaled(
                self._view.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):  # noqa: N802
        self._rescale()
        super().resizeEvent(e)


_CH_INDEX = {"r": 0, "g": 1, "b": 2}


class MplCanvas(FigureCanvasQTAgg):
    """劣化マップ表示（チャネル色の輝度 / RGB合成）＋ カーソル位置通知。"""

    def __init__(self):
        self.fig = Figure(figsize=(4.5, 3.2), layout="tight")
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self._shape: tuple[int, int] | None = None
        self._hover_cb = None
        self.mpl_connect("motion_notify_event", self._on_move)

    def set_hover_cb(self, cb) -> None:
        """cb(x:int, y:int)"""
        self._hover_cb = cb

    def show_channel(self, arr01: np.ndarray, channel: str, title: str = "") -> None:
        """0–1 に正規化済みの1チャネルを、そのチャネル色の輝度で表示。"""
        h, w = arr01.shape
        rgb = np.zeros((h, w, 3), dtype=float)
        rgb[..., _CH_INDEX[channel]] = np.clip(arr01, 0.0, 1.0)
        self._draw_rgb(rgb, title)

    def show_rgb(self, rgb01: np.ndarray, title: str = "") -> None:
        self._draw_rgb(np.clip(rgb01, 0.0, 1.0), title)

    def _draw_rgb(self, rgb: np.ndarray, title: str) -> None:
        self._shape = rgb.shape[:2]
        self.ax.clear()
        self.ax.imshow(rgb)
        self.ax.set_title(title)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.draw_idle()

    def clear_view(self, msg: str = "") -> None:
        self._shape = None
        self.ax.clear()
        self.ax.set_title(msg)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.draw_idle()

    def blank_axes(self, xlabel: str = "", ylabel: str = "") -> None:
        """白紙の軸のみ（時系列タブ用・中身なし）。"""
        self._shape = None
        self.ax.clear()
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.grid(alpha=0.3)
        self.draw_idle()

    def _on_move(self, event) -> None:
        if event.inaxes is not self.ax or self._shape is None or self._hover_cb is None:
            return
        if event.xdata is None or event.ydata is None:
            return
        x, y = int(round(event.xdata)), int(round(event.ydata))
        h, w = self._shape
        if 0 <= x < w and 0 <= y < h:
            self._hover_cb(x, y)
