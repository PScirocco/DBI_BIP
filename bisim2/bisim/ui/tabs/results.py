"""⑤ 結果（仕様 5-⑤）

- 劣化後プレビュー（動画はフレームスライダ）
- 輝度残存率マップ：R / G / B / RGB合成。明るい＝劣化していない。表示する量を選択ボタンで切り替える（フェーズF 5-4）
    - deg1      … ``_deg_{r,g,b}.csv``。基準電流密度での輝度残存率（別の画像の結果どうしの比較に使う）
    - deg2      … ``_deg2_{r,g,b}.csv``。サブモデルの輝度残存率（動画は最後のフレームの値）
    - deg1×deg2 … 表示時に上の2つを掛ける（ファイルは増やさない）。画像にかけた値
    deg2 の無い結果（フェーズF より前の停止結果）では deg2 系のボタンは押せない。
    deg2・deg1×deg2 では、黒（最後に処理した入力フレームでその色が 0）の画素を灰色で表示し、表示範囲と統計から外す
    （黒の画素の deg2 は電流 0 で表の範囲外になり、意味のない値になるため。11/17 決定）
- 累積時間マップ（``_stat_{r,g,b}.csv``）：同上。R/G/B各色ごとに自分の最大値で正規化し明暗反転（暗い＝累積大）
- 時系列：白紙の軸のみ（中身なし。アルゴリズム担当者間で継続検討）
- A/B比較：将来枠（無効表示）

``main.results`` は ``{nn:int -> ResultEntry}``（:mod:`bisim.ui.main_window`）。
"""
from __future__ import annotations

import cv2
import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QHBoxLayout, QLabel, QPushButton, QRadioButton, QSlider, QTabWidget,
    QVBoxLayout, QWidget,
)

from bisim import engine, imio
from bisim.ui.i18n import t
from bisim.ui.widgets import ImagePanel, MplCanvas

CH_KEYS = ["r", "g", "b", "rgb"]
# 累積時間マップの表示スケール（Excel No.9／10/15 MTG 指摘4。2026-10-23）
#   zero  : 0 〜 面内最大（従来）。累積0＝白
#   minmax: 面内最小 〜 面内最大。前ステップからの引き継ぎで全面が底上げされていても、ムラが見える
SCALE_KEYS = ["zero", "minmax"]
# 輝度残存率マップの表示スケール（フェーズF 5-4。2026-11-18）
#   unit  : 0 〜 1（従来）。deg2 は 1 を少し超えることがあり、超えた分は 1（白）として表示
#   minmax: 面内最小 〜 面内最大（黒の画素を除く）。deg2 は 1 の近くに集まるので、ムラを見るときに使う
DEG_SCALE_KEYS = ["unit", "minmax"]
# 輝度残存率マップで表示する量（フェーズF 5-4）
DEG_MODES = ["deg1", "deg2", "deg12"]
# 黒の画素（deg2・deg1×deg2 で除外する画素）の表示色
BLACK_GRAY = 0.5
_CH_INDEX = {"r": 0, "g": 1, "b": 2}


def has_deg2(entry) -> bool:
    """結果に deg2 の出力があるか（フェーズF より前の停止結果には無い）。"""
    return entry is not None and all(f"deg2_{c}" in entry.outputs for c in "rgb")


class _MapView(QWidget):
    """輝度残存率マップ / 累積時間マップ の共通ビュー。

    各チャネルはそのチャネル色の輝度で表示（黒=劣化大 / 明=劣化小）。RGB合成も可。
    累積時間マップは明暗を反転し、輝度残存率マップと同じ向き（暗=累積大）に揃える。
    正規化の最大値は R/G/B で共通ではなく**各色ごと**（評価反映3 B-2。チャンネル間で
    最大値の桁が大きく異なると、共通基準では小さい方のチャンネルが常に明るいまま
    埋もれて反転が見えにくくなるため）。
    輝度残存率マップは deg1／deg2／deg1×deg2 を選択ボタンで切り替える（フェーズF 5-4）。
    """

    def __init__(self, main, kind: str):
        super().__init__()
        self.main = main
        self.kind = kind            # "deg" | "stat"
        self._raw: dict | None = None
        self._mask: dict | None = None          # 黒の画素（deg2・deg1×deg2 のときだけ）
        lay = QVBoxLayout(self)

        # 表示する量（輝度残存率マップだけ）
        self.lbl_mode = QLabel(t("map.deg.mode"))
        self.grp_mode = QButtonGroup(self)
        self.rb_mode: dict = {}
        if kind == "deg":
            row = QHBoxLayout()
            row.addWidget(self.lbl_mode)
            for i, k in enumerate(DEG_MODES):
                rb = QRadioButton(t(f"map.deg.{k}"))
                self.grp_mode.addButton(rb, i)
                self.rb_mode[k] = rb
                row.addWidget(rb)
            self.rb_mode["deg1"].setChecked(True)
            self.grp_mode.idToggled.connect(self._on_mode)
            row.addStretch(1)
            lay.addLayout(row)
        else:
            self.lbl_mode.hide()

        top = QHBoxLayout()
        self.lbl_view = QLabel(t("map.view"))
        self.cmb_ch = QComboBox()
        self.cmb_ch.addItems([t(f"map.ch.{k}") for k in CH_KEYS])
        self.b_reload = QPushButton(t("btn.reload"))
        self.cmb_ch.currentIndexChanged.connect(self.reload)
        self.b_reload.clicked.connect(self.reload)
        top.addWidget(self.lbl_view)
        top.addWidget(self.cmb_ch)
        # 表示スケールの切替（累積時間マップ：0〜最大／面内最小〜最大、輝度残存率マップ：0〜1／面内最小〜最大）
        self.lbl_scale = QLabel(t("map.scale"))
        self.cmb_scale = QComboBox()
        self.cmb_scale.addItems(self._scale_texts())
        self.cmb_scale.currentIndexChanged.connect(self.reload)
        top.addWidget(self.lbl_scale)
        top.addWidget(self.cmb_scale)
        top.addWidget(self.b_reload)
        top.addStretch(1)
        lay.addLayout(top)

        # 注記（輝度残存率マップだけ：表示している量の意味、deg1×deg2 のずれ、黒の画素の扱い）
        self.lbl_note = QLabel("")
        self.lbl_note.setWordWrap(True)
        lay.addWidget(self.lbl_note)
        if kind != "deg":
            self.lbl_note.hide()

        self.canvas = MplCanvas()
        self.canvas.set_hover_cb(self._hover)
        lay.addWidget(self.canvas, 1)

        self.lbl_hover = QLabel(t("map.hover.none"))
        self.lbl_stats = QLabel(t("map.stats.none"))
        lay.addWidget(self.lbl_hover)
        lay.addWidget(self.lbl_stats)

    # -- 選択の状態 --
    def _scale_keys(self) -> list:
        return DEG_SCALE_KEYS if self.kind == "deg" else SCALE_KEYS

    def _scale_texts(self) -> list:
        pre = "map.degscale" if self.kind == "deg" else "map.scale"
        return [t(f"{pre}.{k}") for k in self._scale_keys()]

    def scale_key(self) -> str:
        """表示スケール（累積時間マップ："zero" | "minmax"、輝度残存率マップ："unit" | "minmax"）。"""
        return self._scale_keys()[max(self.cmb_scale.currentIndex(), 0)]

    def mode_key(self) -> str | None:
        """輝度残存率マップで表示している量（"deg1" | "deg2" | "deg12"）。累積時間マップは None。"""
        if self.kind != "deg":
            return None
        i = self.grp_mode.checkedId()
        return DEG_MODES[i] if 0 <= i < len(DEG_MODES) else "deg1"

    def _on_mode(self, _id, checked):
        if checked:
            self.reload()

    def _sync_mode_buttons(self, entry) -> bool:
        """deg2 の有無で deg2 系のボタンを押せる／押せないにする。押せないのに選ばれていたら deg1 に戻す。"""
        ok = has_deg2(entry)
        for k in ("deg2", "deg12"):
            rb = self.rb_mode[k]
            rb.setEnabled(ok)
            rb.setToolTip("" if ok or entry is None else t("map.deg.no_deg2"))
        if not ok and self.mode_key() != "deg1":
            self.grp_mode.blockSignals(True)
            self.rb_mode["deg1"].setChecked(True)
            self.grp_mode.blockSignals(False)
        return ok

    def _black_mask(self, entry) -> dict | None:
        """黒の画素（最後に処理した入力フレームでその色が 0）。実行時にエンジンが求めて結果に持たせている。"""
        return getattr(entry, "input_black", None)

    # -- 表示 --
    def _hover(self, x, y):
        if self._raw is None:
            return
        sel = self.cmb_ch.currentIndex()

        def black(c):
            return self._mask is not None and bool(self._mask[c][y, x])

        if sel < 3:
            c = "rgb"[sel]
            txt = t("map.hover.ch", x=x, y=y, ch=c.upper(), v=self._raw[c][y, x])
            self.lbl_hover.setText(txt + (t("map.hover.black") if black(c) else ""))
        else:
            vals = "  ".join(f"{c.upper()}={self._raw[c][y, x]:.4f}" + (t("map.hover.black") if black(c) else "")
                             for c in "rgb")
            self.lbl_hover.setText(t("map.hover.rgb", x=x, y=y, vals=vals))

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.reload()

    def _load_raw(self, entry) -> dict:
        mode = self.mode_key()
        if self.kind == "stat" or mode == "deg1":
            return {c: _load_csv(entry.outputs[f"{self.kind}_{c}"]) for c in "rgb"}
        if mode == "deg2":
            return {c: _load_csv(entry.outputs[f"deg2_{c}"]) for c in "rgb"}
        return {c: _load_csv(entry.outputs[f"deg_{c}"]) * _load_csv(entry.outputs[f"deg2_{c}"]) for c in "rgb"}

    def _note_text(self, entry, has2: bool) -> str:
        mode = self.mode_key()
        parts = [t(f"map.note.{mode}")]
        if mode == "deg1" and entry is not None and not has2:
            parts.append(t("map.deg.no_deg2"))
        if mode in ("deg2", "deg12") and self._raw is not None:
            if self._mask is None:
                parts.append(t("map.note.black_none"))
            else:
                n = sum(int(self._mask[c].sum()) for c in "rgb")
                parts.append(t("map.note.black", n=n))
        return "\n".join(parts)

    def reload(self):
        entry = self.main.current_result()
        has2 = self._sync_mode_buttons(entry) if self.kind == "deg" else False
        self._mask = None
        if entry is None:
            self.canvas.clear_view(t("map.none"))
            self.lbl_stats.setText(t("map.stats.none"))
            self._raw = None
            self.lbl_note.setText(self._note_text(None, False) if self.kind == "deg" else "")
            return
        try:
            raw = self._load_raw(entry)
        except (OSError, KeyError, ValueError):
            self.canvas.clear_view(t("map.csv_fail"))
            self._raw = None
            if self.kind == "deg":
                self.lbl_note.setText(self._note_text(entry, has2))
            return
        self._raw = raw
        mode = self.mode_key()
        if mode in ("deg2", "deg12"):
            mask = self._black_mask(entry)
            if mask is not None and all(mask[c].shape == raw[c].shape for c in "rgb"):
                self._mask = mask
        if self.kind == "deg":
            self.lbl_note.setText(self._note_text(entry, has2))
        idx = entry.nn
        label = t(f"map.label.{mode}") if self.kind == "deg" else t("map.label.stat")

        def valid(c):
            """範囲と統計に使う値（黒の画素を除く）。"""
            a = raw[c]
            return a[~self._mask[c]] if self._mask is not None else a.ravel()

        def vstat(c, fn, default):
            v = valid(c)
            v = v[~np.isnan(v)]
            return float(fn(v)) if v.size else default

        # 正規化は色ごと（評価反映3 B-2）：deg は 0–1（既に残存率そのもの）または面内最小〜最大、
        # stat は R/G/B それぞれ自分自身の最大値で正規化してから反転する。
        # チャンネル間で最大値の桁が大きく違うと、共通の最大値で揃えると他チャンネルが
        # 常に明るいまま埋もれて反転が見えにくくなるため（RGB合成で特に顕著だった）。
        minmax = self.scale_key() == "minmax"
        if self.kind == "deg":
            if minmax:
                vmax_of = {c: vstat(c, np.max, 1.0) for c in "rgb"}
                vmin_of = {c: vstat(c, np.min, 0.0) for c in "rgb"}
            else:
                vmax_of = {c: 1.0 for c in "rgb"}
                vmin_of = {c: 0.0 for c in "rgb"}
        else:
            vmax_of = {c: (float(np.nanmax(raw[c])) or 1.0) for c in "rgb"}
            vmin_of = {c: (float(np.nanmin(raw[c])) if minmax else 0.0) for c in "rgb"}

        def norm(c):
            return self._norm(raw[c], vmax_of[c], vmin_of[c])

        def rng_ch(c):
            if self.kind == "deg":
                if minmax:
                    return t("map.deg.range_mm", lo=f"{vmin_of[c]:.4g}", v=f"{vmax_of[c]:.4g}")
                return t("map.range01")
            if minmax:
                return t("map.rangev_mm", lo=f"{vmin_of[c]:.3g}", v=f"{vmax_of[c]:.3g}")
            return t("map.rangev", v=f"{vmax_of[c]:.3g}")

        def nblack(c):
            return int(self._mask[c].sum()) if self._mask is not None else 0

        sel = self.cmb_ch.currentIndex()
        if sel < 3:
            c = "rgb"[sel]
            rng = rng_ch(c)
            title = t("map.title.ch", idx=idx, label=label, ch=c.upper(), rng=rng)
            if self._mask is not None:
                h, w = raw[c].shape
                rgb = np.zeros((h, w, 3), dtype=float)
                rgb[..., _CH_INDEX[c]] = norm(c)
                rgb[self._mask[c]] = BLACK_GRAY
                self.canvas.show_rgb(rgb, title)
            else:
                self.canvas.show_channel(norm(c), c, title)
            stats = t("map.stats.ch", ch=c.upper(), mn=vstat(c, np.min, np.nan),
                      mx=vstat(c, np.max, np.nan), me=vstat(c, np.mean, np.nan))
            if self._mask is not None:
                stats += t("map.stats.black", n=nblack(c))
            self.lbl_stats.setText(stats)
        else:
            planes = {c: norm(c) for c in "rgb"}
            if self._mask is not None:
                # 黒の色成分は、その画素で光っている色の平均で埋める（色味が出ないように）。全色が黒なら灰色
                lit = {c: ~self._mask[c] for c in "rgb"}
                cnt = sum(lit[c].astype(int) for c in "rgb")
                tot = sum(np.where(lit[c], planes[c], 0.0) for c in "rgb")
                fill = np.where(cnt > 0, tot / np.maximum(cnt, 1), BLACK_GRAY)
                planes = {c: np.where(lit[c], planes[c], fill) for c in "rgb"}
            rgb = np.stack([planes["r"], planes["g"], planes["b"]], axis=-1)
            if self.kind == "deg":
                if minmax:
                    rng = t("map.deg.range_rgb_mm",
                            **{c: f"{vmin_of[c]:.4g}–{vmax_of[c]:.4g}" for c in "rgb"})
                else:
                    rng = t("map.range01")
            elif minmax:
                rng = t("map.rangev_rgb_mm", **{c: f"{vmin_of[c]:.3g}–{vmax_of[c]:.3g}" for c in "rgb"})
            else:
                rng = t("map.rangev_rgb", r=f"{vmax_of['r']:.3g}",
                        g=f"{vmax_of['g']:.3g}", b=f"{vmax_of['b']:.3g}")
            self.canvas.show_rgb(rgb, t("map.title.rgb", idx=idx, label=label, rng=rng))
            self.lbl_stats.setText(
                " / ".join(f"{c.upper()} mean {vstat(c, np.mean, np.nan):.4g}" for c in "rgb"))

    def _norm(self, a: np.ndarray, vmax: float, vmin: float = 0.0) -> np.ndarray:
        """表示用の 0–1 正規化（vmin→0、vmax→1）。stat は明暗反転（暗=累積大）、deg はそのまま（明=劣化少）。

        面内が一様（vmax == vmin）のときは全面 0（stat は反転して白）。
        """
        span = vmax - vmin
        v = np.clip((a - vmin) / span, 0.0, 1.0) if span > 0 else np.zeros_like(a, dtype=float)
        return (1.0 - v) if self.kind == "stat" else v

    def retranslate(self):
        self.lbl_view.setText(t("map.view"))
        self.b_reload.setText(t("btn.reload"))
        cur = self.cmb_ch.currentIndex()
        self.cmb_ch.blockSignals(True)
        self.cmb_ch.clear()
        self.cmb_ch.addItems([t(f"map.ch.{k}") for k in CH_KEYS])
        self.cmb_ch.setCurrentIndex(max(cur, 0))
        self.cmb_ch.blockSignals(False)
        self.lbl_scale.setText(t("map.scale"))
        cur_s = self.cmb_scale.currentIndex()
        self.cmb_scale.blockSignals(True)
        self.cmb_scale.clear()
        self.cmb_scale.addItems(self._scale_texts())
        self.cmb_scale.setCurrentIndex(max(cur_s, 0))
        self.cmb_scale.blockSignals(False)
        self.lbl_mode.setText(t("map.deg.mode"))
        for k, rb in self.rb_mode.items():
            rb.setText(t(f"map.deg.{k}"))
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
            self.lbl_frame.setText(self._frame_text(v))

    def _frame_text(self, v: int) -> str:
        """フレーム番号＋そのフレーム時点の Aging 時間（前ステップまでの累積込み）。"""
        entry = self.main.current_result()
        if entry is not None and entry.seconds_per_frame > 0:
            t_sec = entry.base_aging_seconds + v * entry.seconds_per_frame
            return t("res.frame_aging", v=v, aging=engine.format_aging(t_sec))
        return t("res.frame", v=v)

    def retranslate(self):
        self.lbl_idx.setText(t("res.idx"))
        for i, key in enumerate(["res.sub.preview", "res.sub.deg", "res.sub.stat",
                                 "res.sub.ts", "res.sub.ab"]):
            self.sub.setTabText(i, t(key))
        self.pv.set_title(t("res.preview.title"))
        if self._cap is not None:
            self.lbl_frame.setText(self._frame_text(self.sld.value()))
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
