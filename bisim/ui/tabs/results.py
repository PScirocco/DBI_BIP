"""⑤ 結果（仕様 5-⑤）

- 劣化後プレビュー（動画はフレームスライダ）
- 1/劣化率マップ（``_deg_{r,g,b}.csv``）：R / G / B / RGB合成。明るい＝劣化していない
- 累積時間マップ（``_stat_{r,g,b}.csv``）：同上。面内最大で正規化
- 時系列：白紙の軸のみ（中身なし。アルゴリズム担当者間で継続検討）
- A/B比較：将来枠（無効表示）

``main.results`` は ``{nn:int -> ResultEntry}``（:mod:`bisim.ui.main_window`）。
"""
from __future__ import annotations

import cv2
import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QTabWidget, QVBoxLayout, QWidget,
)

from bisim import imio
from bisim.ui.i18n import t
from bisim.ui.widgets import ImagePanel, MplCanvas

CH_KEYS = ["r", "g", "b", "rgb"]


class _MapView(QWidget):
    """1/劣化率マップ / 累積時間マップ の共通ビュー。

    各チャネルはそのチャネル色の輝度で表示（黒=劣化大 / 明=劣化小）。RGB合成も可。
    """

    def __init__(self, main, kind: str):
        super().__init__()
        self.main = main
        self.kind = kind            # "deg" | "stat"
        self._raw: dict | None = None
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.lbl_view = QLabel(t("map.view"))
        self.cmb_ch = QComboBox()
        self.cmb_ch.addItems([t(f"map.ch.{k}") for k in CH_KEYS])
        self.b_reload = QPushButton(t("btn.reload"))
        self.cmb_ch.currentIndexChanged.connect(self.reload)
        self.b_reload.clicked.connect(self.reload)
        top.addWidget(self.lbl_view)
        top.addWidget(self.cmb_ch)
        top.addWidget(self.b_reload)
        top.addStretch(1)
        lay.addLayout(top)

        self.canvas = MplCanvas()
        self.canvas.set_hover_cb(self._hover)
        lay.addWidget(self.canvas, 1)

        self.lbl_hover = QLabel(t("map.hover.none"))
        self.lbl_stats = QLabel(t("map.stats.none"))
        lay.addWidget(self.lbl_hover)
        lay.addWidget(self.lbl_stats)

    def _hover(self, x, y):
        if self._raw is None:
            return
        sel = self.cmb_ch.currentIndex()
        if sel < 3:
            c = "rgb"[sel]
            self.lbl_hover.setText(
                t("map.hover.ch", x=x, y=y, ch=c.upper(), v=self._raw[c][y, x]))
        else:
            vals = "  ".join(f"{c.upper()}={self._raw[c][y, x]:.4f}" for c in "rgb")
            self.lbl_hover.setText(t("map.hover.rgb", x=x, y=y, vals=vals))

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.reload()

    def reload(self):
        entry = self.main.current_result()
        if entry is None:
            self.canvas.clear_view(t("map.none"))
            self.lbl_stats.setText(t("map.stats.none"))
            self._raw = None
            return
        try:
            raw = {c: _load_csv(entry.outputs[f"{self.kind}_{c}"]) for c in "rgb"}
        except (OSError, KeyError, ValueError):
            self.canvas.clear_view(t("map.csv_fail"))
            self._raw = None
            return
        self._raw = raw
        idx = entry.nn
        label = t("map.label.deg") if self.kind == "deg" else t("map.label.stat")

        if self.kind == "deg":
            vmax, rng = 1.0, t("map.range01")
        else:
            vmax = max((float(np.nanmax(raw[c])) for c in "rgb"), default=1.0) or 1.0
            rng = t("map.rangev", v=f"{vmax:.3g}")

        def norm(a):
            return np.clip(a / vmax, 0.0, 1.0)

        sel = self.cmb_ch.currentIndex()
        if sel < 3:
            c = "rgb"[sel]
            self.canvas.show_channel(
                norm(raw[c]), c,
                t("map.title.ch", idx=idx, label=label, ch=c.upper(), rng=rng))
            a = raw[c]
            self.lbl_stats.setText(t("map.stats.ch", ch=c.upper(),
                                     mn=np.nanmin(a), mx=np.nanmax(a), me=np.nanmean(a)))
        else:
            rgb = np.stack([norm(raw["r"]), norm(raw["g"]), norm(raw["b"])], axis=-1)
            self.canvas.show_rgb(rgb, t("map.title.rgb", idx=idx, label=label, rng=rng))
            self.lbl_stats.setText(
                " / ".join(f"{c.upper()} mean {np.nanmean(raw[c]):.4g}" for c in "rgb"))

    def retranslate(self):
        self.lbl_view.setText(t("map.view"))
        self.b_reload.setText(t("btn.reload"))
        cur = self.cmb_ch.currentIndex()
        self.cmb_ch.blockSignals(True)
        self.cmb_ch.clear()
        self.cmb_ch.addItems([t(f"map.ch.{k}") for k in CH_KEYS])
        self.cmb_ch.setCurrentIndex(max(cur, 0))
        self.cmb_ch.blockSignals(False)
        self.lbl_hover.setText(t("map.hover.none"))
        self.reload()


class ResultsTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.lbl_idx = QLabel(t("res.idx"))
        self.cmb_idx = QComboBox()
        self.cmb_idx.currentIndexChanged.connect(self._on_idx)
        top.addWidget(self.lbl_idx)
        top.addWidget(self.cmb_idx)
        top.addStretch(1)
        lay.addLayout(top)

        self.sub = QTabWidget()
        lay.addWidget(self.sub, 1)

        # -- preview --
        w_prev = QWidget()
        pl = QVBoxLayout(w_prev)
        self.pv = ImagePanel(t("res.preview.title"), min_h=260)
        self.lbl_frame = QLabel(t("run.dash"))
        self.sld = QSlider(Qt.Orientation.Horizontal)
        self.sld.setEnabled(False)
        self.sld.valueChanged.connect(self._on_frame)
        pl.addWidget(self.pv, 1)
        pl.addWidget(self.lbl_frame)
        pl.addWidget(self.sld)
        self.sub.addTab(w_prev, t("res.sub.preview"))

        # -- maps --
        self.view_deg = _MapView(main, "deg")
        self.view_stat = _MapView(main, "stat")
        self.sub.addTab(self.view_deg, t("res.sub.deg"))
        self.sub.addTab(self.view_stat, t("res.sub.stat"))

        # -- time series (blank axes only) --
        self._ts_page = QWidget()
        tl = QVBoxLayout(self._ts_page)
        self.lbl_ts = QLabel(t("res.ts.note"))
        self.lbl_ts.setWordWrap(True)
        self.canvas_ts = MplCanvas()
        tl.addWidget(self.lbl_ts)
        tl.addWidget(self.canvas_ts, 1)
        self.sub.addTab(self._ts_page, t("res.sub.ts"))
        self.canvas_ts.blank_axes(t("res.ts.x"), t("res.ts.y"))

        # -- A/B (future) --
        w_ab = QWidget()
        al = QVBoxLayout(w_ab)
        self.lbl_ab = QLabel(t("res.ab.note"))
        self.lbl_ab.setWordWrap(True)
        al.addWidget(self.lbl_ab)
        al.addStretch(1)
        self.sub.addTab(w_ab, t("res.sub.ab"))

        self.sub.currentChanged.connect(self._on_subtab)
        self._cap = None

    # -- registration --
    def add_result(self, nn: int):
        if self.cmb_idx.findText(str(nn)) < 0:
            self.cmb_idx.addItem(str(nn))
        self.cmb_idx.setCurrentText(str(nn))
        self._on_idx()

    def clear_results(self):
        self.cmb_idx.clear()
        self._release_cap()
        self.pv.set_message(t("res.none"))

    def current_idx(self) -> int | None:
        txt = self.cmb_idx.currentText()
        return int(txt) if txt.isdigit() else None

    # -- preview --
    def _on_idx(self):
        self._load_preview()
        cur = self.sub.currentWidget()
        if cur in (self.view_deg, self.view_stat):
            cur.reload()

    def _on_subtab(self, _i):
        cur = self.sub.currentWidget()
        if cur in (self.view_deg, self.view_stat):
            cur.reload()

    def _release_cap(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _load_preview(self):
        self._release_cap()
        entry = self.main.current_result()
        if entry is None:
            self.pv.set_message(t("res.none"))
            self.sld.setEnabled(False)
            self.lbl_frame.setText(t("run.dash"))
            return
        if entry.is_movie and entry.outputs.get("movie"):
            self._cap = cv2.VideoCapture(str(entry.outputs["movie"]))
            n = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.sld.setEnabled(True)
            self.sld.setRange(0, max(n - 1, 0))
            self.sld.setValue(0)
            self._show_frame(0)
        elif entry.outputs.get("image"):
            self.sld.setEnabled(False)
            self.lbl_frame.setText(t("run.dash"))
            self.pv.set_bgr(imio.imread(str(entry.outputs["image"])))
        else:
            self.sld.setEnabled(False)
            self.pv.set_message(t("res.none"))

    def _on_frame(self, v):
        self._show_frame(v)

    def _show_frame(self, v):
        if self._cap is None:
            return
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, v)
        ok, frame = self._cap.read()
        if ok:
            self.pv.set_bgr(frame)
            self.lbl_frame.setText(t("res.frame", v=v))

    def retranslate(self):
        self.lbl_idx.setText(t("res.idx"))
        for i, key in enumerate(["res.sub.preview", "res.sub.deg", "res.sub.stat",
                                 "res.sub.ts", "res.sub.ab"]):
            self.sub.setTabText(i, t(key))
        self.pv.set_title(t("res.preview.title"))
        self.lbl_ab.setText(t("res.ab.note"))
        self.lbl_ts.setText(t("res.ts.note"))
        self.canvas_ts.blank_axes(t("res.ts.x"), t("res.ts.y"))
        self.view_deg.retranslate()
        self.view_stat.retranslate()


def _load_csv(path) -> np.ndarray:
    arr = np.loadtxt(str(path), delimiter=",", dtype=float)
    if arr.ndim == 2 and np.all(np.isnan(arr[:, -1])):   # trailing comma 対策
        arr = arr[:, :-1]
    return arr
