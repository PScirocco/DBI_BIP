""" 再利用ウィジェット（プロトタイプ用） """
from __future__ import annotations

import cv2
import numpy as np

import imio
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


def bgr_to_qimage(bgr: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()


def read_first_frame(path: str) -> np.ndarray | None:
    p = str(path)
    if p.lower().endswith(".mp4"):
        cap = cv2.VideoCapture(p)
        ok, frame = cap.read()
        cap.release()
        return frame if ok else None
    return imio.imread(p)


class ImagePanel(QWidget):
    """ タイトル付きの画像プレビュー。ウィンドウサイズに追従して縮小表示。 """

    def __init__(self, title: str = "", min_h: int = 150):
        super().__init__()
        self._title = QLabel(title)
        self._title.setStyleSheet("font-weight:600;")
        self._view = QLabel("（画像なし）")
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setMinimumHeight(min_h)
        self._view.setStyleSheet(
            "border:1px solid palette(mid); background:#101014; color:#888;")
        self._view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lay.addWidget(self._title)
        lay.addWidget(self._view, 1)
        self._pixmap: QPixmap | None = None

    def set_title(self, t: str) -> None:
        self._title.setText(t)

    def set_bgr(self, bgr: np.ndarray | None) -> None:
        if bgr is None:
            self.set_message("（画像なし）")
            return
        self._pixmap = QPixmap.fromImage(bgr_to_qimage(bgr))
        self._rescale()

    def set_qimage(self, qimg: QImage | None) -> None:
        if qimg is None:
            self.set_message("（画像なし）")
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


class MplCanvas(FigureCanvasQTAgg):
    """ カラーマップ表示 + カーソル位置の値取得 """

    def __init__(self):
        self.fig = Figure(figsize=(4.5, 3.2), layout="tight")
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self._arr: np.ndarray | None = None
        self._cbar = None
        self._hover_cb = None
        self.mpl_connect("motion_notify_event", self._on_move)

    def set_hover_cb(self, cb) -> None:
        self._hover_cb = cb

    def show_array(self, arr: np.ndarray, cmap: str = "viridis", title: str = "") -> None:
        self._arr = arr
        self.ax.clear()
        if self._cbar is not None:
            try:
                self._cbar.remove()
            except Exception:
                pass
            self._cbar = None
        im = self.ax.imshow(arr, cmap=cmap)
        self.ax.set_title(title)
        self._cbar = self.fig.colorbar(im, ax=self.ax, fraction=0.046, pad=0.04)
        self.draw_idle()

    def clear_view(self, msg: str = "") -> None:
        self._arr = None
        self.ax.clear()
        self.ax.set_title(msg)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.draw_idle()

    def _on_move(self, event) -> None:
        if event.inaxes is not self.ax or self._arr is None or self._hover_cb is None:
            return
        if event.xdata is None or event.ydata is None:
            return
        x, y = int(round(event.xdata)), int(round(event.ydata))
        h, w = self._arr.shape
        if 0 <= x < w and 0 <= y < h:
            self._hover_cb(x, y, float(self._arr[y, x]))
