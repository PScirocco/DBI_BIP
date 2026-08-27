""" 5つのタブ（プロトタイプ用 UX 検証） """
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

import imio
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSlider, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from state import (
    FOLDER_LABELS, MODEL_ROWS, Step, load_model_csv, load_simconf_csv,
)
from widgets import ImagePanel, MplCanvas, bgr_to_qimage, read_first_frame

IMG_FILTER = "画像・動画 (*.png *.mp4);;すべて (*)"
CMAPS = ["viridis", "magma", "inferno", "turbo", "gray", "RdYlBu_r"]
INIT_STRESS_ITEMS = [("none", "なし（ゼロから）"), ("prev", "前ステップから継承"), ("file", "ファイル指定")]


# --------------------------------------------------------------------------- #
#  ① フォルダ設定
# --------------------------------------------------------------------------- #
class FoldersTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.edits: dict[str, QLineEdit] = {}
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "各ファイルの入っているフォルダ。既定値は既存コードの構成（dbi_common / dbi_input / dbi_conf / dbi_output）。"))
        form = QFormLayout()
        for key, label in FOLDER_LABELS.items():
            row = QHBoxLayout()
            edit = QLineEdit(self.main.state.folders[key])
            edit.editingFinished.connect(lambda k=key: self._on_edit(k))
            btn = QPushButton("参照…")
            btn.clicked.connect(lambda _=False, k=key: self._browse(k))
            row.addWidget(edit, 1)
            row.addWidget(btn)
            w = QWidget()
            w.setLayout(row)
            form.addRow(label, w)
            self.edits[key] = edit
        lay.addLayout(form)
        lay.addStretch(1)

    def _on_edit(self, key):
        self.main.state.folders[key] = self.edits[key].text().strip()

    def _browse(self, key):
        cur = self.main.state.folders[key]
        d = QFileDialog.getExistingDirectory(self, FOLDER_LABELS[key], cur)
        if d:
            self.main.state.folders[key] = d
            self.edits[key].setText(d)

    def refresh(self):
        for key, edit in self.edits.items():
            if edit.text() != self.main.state.folders[key]:
                edit.setText(self.main.state.folders[key])


# --------------------------------------------------------------------------- #
#  ② 実行ステップ
# --------------------------------------------------------------------------- #
class StepsTab(QWidget):
    HEADERS = ["#", "名前", "種別", "入力画像", "ヒートマップ", "初期ストレス", "状態"]

    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.cellDoubleClicked.connect(lambda *_: self.main.goto_config())
        lay.addWidget(self.table, 1)

        btns = QHBoxLayout()
        for text, slot in [
            ("追加", self._add), ("複製", self._dup), ("削除", self._del),
            ("↑", lambda: self._move(-1)), ("↓", lambda: self._move(1)),
            ("設定を編集 →", self.main.goto_config),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

    # -- data ops --
    def _add(self):
        self.main.state.steps.append(Step(name=f"ステップ{len(self.main.state.steps) + 1}"))
        self.main.steps_changed()
        self._select_row(len(self.main.state.steps) - 1)

    def _dup(self):
        r = self.current_row()
        if r is None:
            return
        import copy
        s = copy.deepcopy(self.main.state.steps[r])
        s.name += " (複製)"
        s.status = "未実行"
        self.main.state.steps.insert(r + 1, s)
        self.main.steps_changed()
        self._select_row(r + 1)

    def _del(self):
        r = self.current_row()
        if r is None:
            return
        del self.main.state.steps[r]
        self.main.steps_changed()

    def _move(self, d):
        r = self.current_row()
        if r is None:
            return
        j = r + d
        steps = self.main.state.steps
        if 0 <= j < len(steps):
            steps[r], steps[j] = steps[j], steps[r]
            self.main.steps_changed()
            self._select_row(j)

    # -- selection --
    def current_row(self):
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _select_row(self, r):
        if 0 <= r < self.table.rowCount():
            self.table.selectRow(r)

    def _on_select(self):
        self.main.select_step(self.current_row())

    # -- view --
    def refresh(self):
        steps = self.main.state.steps
        self.table.blockSignals(True)
        self.table.setRowCount(len(steps))
        for i, s in enumerate(steps):
            init = {"none": "ゼロ", "prev": f"前 #{i} 継承", "file": "ファイル"}[s.init_stress]
            values = [str(i + 1), s.name, s.kind_label, s.input_image or "―",
                      s.heatmap or "―", init, s.status]
            for c, v in enumerate(values):
                self.table.setItem(i, c, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)
        if self.main.current_row is not None and self.main.current_row < len(steps):
            self._select_row(self.main.current_row)


# --------------------------------------------------------------------------- #
#  ③ ステップ設定
# --------------------------------------------------------------------------- #
class StepConfigTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.step: Step | None = None
        self.row: int | None = None

        root = QHBoxLayout(self)

        # ---- 左：フォーム ----
        form_host = QWidget()
        form = QVBoxLayout(form_host)

        self.lbl_head = QLabel("ステップ未選択")
        self.lbl_head.setStyleSheet("font-size:15px; font-weight:600;")
        form.addWidget(self.lbl_head)

        f1 = QFormLayout()
        self.ed_name = QLineEdit()
        f1.addRow("名前", self.ed_name)

        self.ed_img = QLineEdit()
        self.ed_img.setReadOnly(True)
        b_img = QPushButton("参照…")
        b_img.clicked.connect(lambda: self._pick_file("input_image"))
        f1.addRow("入力画像", self._with_btn(self.ed_img, b_img))

        self.ed_ht = QLineEdit()
        self.ed_ht.setReadOnly(True)
        b_ht = QPushButton("参照…")
        b_ht.clicked.connect(lambda: self._pick_file("heatmap"))
        f1.addRow("ヒートマップ", self._with_btn(self.ed_ht, b_ht))

        self.lbl_kind = QLabel("―")
        f1.addRow("種別（自動判定）", self.lbl_kind)
        form.addLayout(f1)

        # 初期ストレス（Aging 再開）
        gb = QGroupBox("初期ストレス（Aging 再開）")
        g = QVBoxLayout(gb)
        self.cmb_init = QComboBox()
        for _, label in INIT_STRESS_ITEMS:
            self.cmb_init.addItem(label)
        self.cmb_init.currentIndexChanged.connect(self._on_init_changed)
        g.addWidget(self.cmb_init)
        self.file_host = QWidget()
        fg = QFormLayout(self.file_host)
        self.ed_sr, self.ed_sg, self.ed_sb = QLineEdit(), QLineEdit(), QLineEdit()
        for lab, ed in [("stat_r", self.ed_sr), ("stat_g", self.ed_sg), ("stat_b", self.ed_sb)]:
            bb = QPushButton("参照…")
            bb.clicked.connect(lambda _=False, e=ed: self._pick_stat(e))
            fg.addRow(lab, self._with_btn(ed, bb))
        g.addWidget(self.file_host)
        form.addWidget(gb)

        # モデルパラメータ
        gb2 = QGroupBox("モデルパラメータ（Master Model）")
        g2 = QVBoxLayout(gb2)
        self.tbl_model = QTableWidget(len(MODEL_ROWS), 3)
        self.tbl_model.setHorizontalHeaderLabels(["R", "G", "B"])
        self.tbl_model.setVerticalHeaderLabels(MODEL_ROWS)
        self.tbl_model.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_model.setMaximumHeight(190)
        g2.addWidget(self.tbl_model)
        hb = QHBoxLayout()
        b_load = QPushButton("CSVから読込")
        b_load.clicked.connect(self._load_model_csv)
        b_save = QPushButton("CSVへ保存")
        b_save.clicked.connect(self._save_model_csv)
        hb.addWidget(b_load)
        hb.addWidget(b_save)
        hb.addStretch(1)
        g2.addLayout(hb)
        form.addWidget(gb2)

        # Sim条件
        gb3 = QGroupBox("Sim条件")
        f3 = QFormLayout(gb3)
        self.sp_accel = self._dspin(1.0, 1e9, 100.0)
        self.sp_tl = self._dspin(-50.0, 200.0, 1.0)
        self.sp_th = self._dspin(-50.0, 300.0, 1.0)
        self.sp_aging = self._dspin(0.0, 1e6, 1.0)
        f3.addRow("ACCEL_RATIO", self.sp_accel)
        f3.addRow("TMP_L [℃]", self.sp_tl)
        f3.addRow("TMP_H [℃]", self.sp_th)
        f3.addRow("AGING_TIME（現状未使用）", self.sp_aging)
        form.addWidget(gb3)

        # BC設定（未使用）＋ 将来拡張
        gb4 = QGroupBox("BC設定 / 処理パイプライン（将来拡張・現在は無効）")
        g4 = QVBoxLayout(gb4)
        g4.addWidget(QLabel("BC設定（DBV_NIT, Duty）: 現行モデルは未使用"))
        for t in ["BIP 前処理", "DBI 補正", "ピーク輝度制御"]:
            cb = QCheckBox(t)
            cb.setEnabled(False)
            g4.addWidget(cb)
        cb_ab = QCheckBox("補正あり / なし を比較実行")
        cb_ab.setEnabled(False)
        g4.addWidget(cb_ab)
        form.addWidget(gb4)

        self.btn_apply = QPushButton("この設定を適用")
        self.btn_apply.clicked.connect(self._apply)
        form.addWidget(self.btn_apply)
        form.addStretch(1)

        # ---- 右：プレビュー ----
        prev_host = QWidget()
        pv = QVBoxLayout(prev_host)
        self.pv_img = ImagePanel("入力画像")
        self.pv_ht = ImagePanel("ヒートマップ画像")
        self.pv_prev = ImagePanel("前回の Aging 結果")
        pv.addWidget(self.pv_img, 1)
        pv.addWidget(self.pv_ht, 1)
        pv.addWidget(self.pv_prev, 1)

        root.addWidget(form_host, 3)
        root.addWidget(prev_host, 2)

        self.set_enabled(False)

    # -- helpers --
    @staticmethod
    def _with_btn(edit, btn):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        h.addWidget(btn)
        return w

    @staticmethod
    def _dspin(lo, hi, step):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(3)
        s.setSingleStep(step)
        return s

    def set_enabled(self, on: bool):
        for w in (self.ed_name, self.ed_img, self.ed_ht, self.cmb_init, self.tbl_model,
                  self.sp_accel, self.sp_tl, self.sp_th, self.sp_aging, self.btn_apply):
            w.setEnabled(on)

    # -- load / collect --
    def load(self, step: Step | None, row: int | None):
        self.step, self.row = step, row
        if step is None:
            self.lbl_head.setText("ステップ未選択")
            self.set_enabled(False)
            for p in (self.pv_img, self.pv_ht, self.pv_prev):
                p.set_message("（ステップ未選択）")
            return
        self.set_enabled(True)
        self.lbl_head.setText(f"ステップ #{row + 1} の設定")
        self.ed_name.setText(step.name)
        self.ed_img.setText(step.input_image)
        self.ed_ht.setText(step.heatmap)
        self.lbl_kind.setText(step.kind_label)
        self.cmb_init.setCurrentIndex([k for k, _ in INIT_STRESS_ITEMS].index(step.init_stress))
        self.ed_sr.setText(step.stress_r)
        self.ed_sg.setText(step.stress_g)
        self.ed_sb.setText(step.stress_b)
        self._fill_model_table(step.model)
        self.sp_accel.setValue(step.simconf["ACCEL_RATIO"])
        self.sp_tl.setValue(step.simconf["TMP_L"])
        self.sp_th.setValue(step.simconf["TMP_H"])
        self.sp_aging.setValue(step.simconf["AGING_TIME"])
        self._on_init_changed()
        self._refresh_previews()

    def _fill_model_table(self, model: dict):
        for r, key in enumerate(MODEL_ROWS):
            for c in range(3):
                self.tbl_model.setItem(r, c, QTableWidgetItem(f"{model[key][c]:g}"))

    def _collect_into_step(self) -> bool:
        s = self.step
        s.name = self.ed_name.text().strip() or s.name
        s.init_stress = [k for k, _ in INIT_STRESS_ITEMS][self.cmb_init.currentIndex()]
        s.stress_r, s.stress_g, s.stress_b = (
            self.ed_sr.text().strip(), self.ed_sg.text().strip(), self.ed_sb.text().strip())
        try:
            for r, key in enumerate(MODEL_ROWS):
                s.model[key] = [float(self.tbl_model.item(r, c).text()) for c in range(3)]
        except (ValueError, AttributeError):
            QMessageBox.warning(self, "入力エラー", "モデルパラメータ表に数値でない値があります。")
            return False
        s.simconf["ACCEL_RATIO"] = self.sp_accel.value()
        s.simconf["TMP_L"] = self.sp_tl.value()
        s.simconf["TMP_H"] = self.sp_th.value()
        s.simconf["AGING_TIME"] = self.sp_aging.value()
        return True

    def _apply(self):
        if self.step is None or not self._collect_into_step():
            return
        self.main.steps_changed()
        self.main.statusBar().showMessage("ステップ設定を適用しました", 3000)

    # -- file pickers --
    def _pick_file(self, folder_key: str):
        if self.step is None:
            return
        start = self.main.state.folders[folder_key]
        path, _ = QFileDialog.getOpenFileName(self, FOLDER_LABELS[folder_key], start, IMG_FILTER)
        if not path:
            return
        p = Path(path)
        self.main.state.folders[folder_key] = str(p.parent)   # フォルダ設定も更新
        if folder_key == "input_image":
            self.step.input_image = p.name
            self.ed_img.setText(p.name)
            self.lbl_kind.setText(self.step.kind_label)
        else:
            self.step.heatmap = p.name
            self.ed_ht.setText(p.name)
        self.main.folders_changed()
        self.main.steps_changed()
        self._refresh_previews()

    def _pick_stat(self, edit: QLineEdit):
        start = self.main.state.folders["output"]
        path, _ = QFileDialog.getOpenFileName(self, "ストレスCSV", start, "CSV (*.csv)")
        if path:
            edit.setText(path)

    def _on_init_changed(self):
        key = [k for k, _ in INIT_STRESS_ITEMS][self.cmb_init.currentIndex()]
        self.file_host.setVisible(key == "file")
        self._refresh_prev_preview(key)

    # -- previews --
    def _refresh_previews(self):
        s = self.step
        fi = self.main.state.folders["input_image"]
        fh = self.main.state.folders["heatmap"]
        self.pv_img.set_bgr(read_first_frame(str(Path(fi) / s.input_image)) if s.input_image else None)
        self.pv_ht.set_bgr(read_first_frame(str(Path(fh) / s.heatmap)) if s.heatmap else None)
        self._refresh_prev_preview(s.init_stress)

    def _refresh_prev_preview(self, key: str):
        if key != "prev" or self.row is None or self.row == 0:
            self.pv_prev.set_message("（初回 Aging / 継承なし）")
            return
        prev_idx = self.row  # 前ステップの idx（1始まり）＝ 現在行の row（0始まり）
        out = Path(self.main.state.folders["output"])
        for ext in (".png", ".mp4"):
            cand = out / f"{prev_idx}_out_img{ext}"
            if cand.exists():
                self.pv_prev.set_title(f"前回の Aging 結果  (#{prev_idx}_out_img{ext})")
                self.pv_prev.set_bgr(read_first_frame(str(cand)))
                return
        self.pv_prev.set_title("前回の Aging 結果")
        self.pv_prev.set_message(f"step #{prev_idx} は未実行です")

    # -- model csv --
    def _load_model_csv(self):
        start = self.main.state.folders["model"]
        path, _ = QFileDialog.getOpenFileName(self, "モデルパラメータCSV", start, "CSV (*.csv)")
        if not path:
            return
        m = load_model_csv(path)
        if m is None:
            QMessageBox.warning(self, "読込失敗", "CSV を読めませんでした。")
            return
        self.main.state.folders["model"] = str(Path(path).parent)
        self.step.model = m
        self._fill_model_table(m)
        self.main.folders_changed()

    def _save_model_csv(self):
        if self.step is None or not self._collect_into_step():
            return
        start = str(Path(self.main.state.folders["model"]) / "degparam_mm.csv")
        path, _ = QFileDialog.getSaveFileName(self, "モデルパラメータCSV", start, "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            for key in MODEL_ROWS:
                f.write(",".join([key] + [f"{v:g}" for v in self.step.model[key]]) + "\n")
        self.main.statusBar().showMessage(f"保存: {path}", 3000)


# --------------------------------------------------------------------------- #
#  ④ 実行
# --------------------------------------------------------------------------- #
class RunTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)

        btns = QHBoxLayout()
        self.b_all = QPushButton("▶ 全ステップ実行")
        self.b_sel = QPushButton("▶ 選択ステップのみ")
        self.b_abort = QPushButton("■ 中断")
        self.b_all.clicked.connect(lambda: self.main.run_steps("all"))
        self.b_sel.clicked.connect(lambda: self.main.run_steps("selected"))
        self.b_abort.clicked.connect(self.main.abort_run)
        for b in (self.b_all, self.b_sel, self.b_abort):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.lbl_step = QLabel("待機中")
        self.pb_step = QProgressBar()
        self.lbl_frame = QLabel("―")
        self.pb_frame = QProgressBar()
        self.lbl_elapsed = QLabel("経過 0.0 s")
        for w in (self.lbl_step, self.pb_step, self.lbl_frame, self.pb_frame, self.lbl_elapsed):
            lay.addWidget(w)

        self.preview = ImagePanel("処理中フレーム（劣化後）", min_h=200)
        lay.addWidget(self.preview, 1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        lay.addWidget(self.log, 1)

        self.set_running(False)

    def set_running(self, on: bool):
        self.b_all.setEnabled(not on)
        self.b_sel.setEnabled(not on)
        self.b_abort.setEnabled(on)

    def append_log(self, msg: str):
        self.log.appendPlainText(msg)

    def on_run_started(self, nsteps: int):
        self.log.clear()
        self.pb_step.setRange(0, max(nsteps, 1))
        self.pb_step.setValue(0)
        self.pb_frame.setRange(0, 1)
        self.pb_frame.setValue(0)
        self.append_log(f"=== 実行開始（{nsteps} ステップ）===")

    def on_step(self, si: int, n: int, name: str):
        self.lbl_step.setText(f"ステップ {si + 1}/{n} : {name}")
        self.pb_step.setValue(si)

    def on_progress(self, si, n, f, ft, qimg):
        self.lbl_frame.setText(f"フレーム {f}/{ft}")
        self.pb_frame.setRange(0, max(ft, 1))
        self.pb_frame.setValue(f)
        if qimg is not None:
            self.preview.set_qimage(qimg)

    def on_elapsed(self, sec: float):
        self.lbl_elapsed.setText(f"経過 {sec:.1f} s")

    def on_finished(self, aborted: bool):
        self.pb_step.setValue(self.pb_step.maximum())
        self.lbl_step.setText("中断しました" if aborted else "完了")
        self.append_log("=== 中断 ===" if aborted else "=== 完了 ===")
        self.set_running(False)

    def on_error(self, msg: str):
        self.append_log(f"!! エラー: {msg}")
        self.lbl_step.setText("エラー終了")
        self.set_running(False)


# --------------------------------------------------------------------------- #
#  ⑤ 結果
# --------------------------------------------------------------------------- #
class _MapView(QWidget):
    """ 劣化率マップ / 累積ストレスマップ 共通ビュー """

    def __init__(self, main, kind: str):
        super().__init__()
        self.main = main
        self.kind = kind  # "deg" | "stat"
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.cmb_ch = QComboBox()
        self.cmb_ch.addItems(["R", "G", "B"])
        self.cmb_cmap = QComboBox()
        self.cmb_cmap.addItems(CMAPS)
        b_reload = QPushButton("再読込")
        self.cmb_ch.currentIndexChanged.connect(self.reload)
        self.cmb_cmap.currentIndexChanged.connect(self.reload)
        b_reload.clicked.connect(self.reload)
        top.addWidget(QLabel("チャンネル"))
        top.addWidget(self.cmb_ch)
        top.addWidget(QLabel("カラーマップ"))
        top.addWidget(self.cmb_cmap)
        top.addWidget(b_reload)
        top.addStretch(1)
        lay.addLayout(top)

        self.canvas = MplCanvas()
        self.canvas.set_hover_cb(self._hover)
        lay.addWidget(self.canvas, 1)

        self.lbl_hover = QLabel("カーソル値: ―")
        self.lbl_stats = QLabel("min/max/mean: ―")
        lay.addWidget(self.lbl_hover)
        lay.addWidget(self.lbl_stats)

    def _hover(self, x, y, v):
        self.lbl_hover.setText(f"カーソル値: (x={x}, y={y}) = {v:.4f}")

    def showEvent(self, e):  # noqa: N802 -- タブ表示時に初めて CSV を読む
        super().showEvent(e)
        self.reload()

    def reload(self):
        idx = self.main.results_tab.current_idx()
        if idx is None or idx not in self.main.results:
            self.canvas.clear_view("（結果なし）")
            self.lbl_stats.setText("min/max/mean: ―")
            return
        res = self.main.results[idx]
        ch = "rgb"[self.cmb_ch.currentIndex()]
        path = (res.deg_paths if self.kind == "deg" else res.stat_paths)[ch]
        try:
            arr = np.loadtxt(path, delimiter=",")
        except OSError:
            self.canvas.clear_view("（CSV読込失敗）")
            return
        label = "劣化率" if self.kind == "deg" else "累積ストレス"
        self.canvas.show_array(arr, self.cmb_cmap.currentText(),
                               f"#{idx} {label} ({ch.upper()})")
        self.lbl_stats.setText(
            f"min {np.nanmin(arr):.4g} / max {np.nanmax(arr):.4g} / mean {np.nanmean(arr):.4g}")


class ResultsTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.cmb_idx = QComboBox()
        self.cmb_idx.currentIndexChanged.connect(self._on_idx)
        top.addWidget(QLabel("表示するステップ (idx)"))
        top.addWidget(self.cmb_idx)
        top.addStretch(1)
        lay.addLayout(top)

        from PySide6.QtWidgets import QTabWidget
        self.sub = QTabWidget()
        lay.addWidget(self.sub, 1)

        # 劣化後プレビュー
        w_prev = QWidget()
        pl = QVBoxLayout(w_prev)
        self.pv = ImagePanel("劣化後", min_h=260)
        self.sld = QSlider(Qt.Orientation.Horizontal)
        self.sld.setEnabled(False)
        self.sld.valueChanged.connect(self._on_frame)
        pl.addWidget(self.pv, 1)
        pl.addWidget(self.sld)
        self.sub.addTab(w_prev, "劣化後プレビュー")

        self.view_deg = _MapView(main, "deg")
        self.view_stat = _MapView(main, "stat")
        self.sub.addTab(self.view_deg, "劣化率マップ")
        self.sub.addTab(self.view_stat, "累積ストレスマップ")

        # 時系列
        self._ts_page = QWidget()
        tl = QVBoxLayout(self._ts_page)
        b_ts = QPushButton("更新")
        b_ts.clicked.connect(self._plot_timeseries)
        self.canvas_ts = MplCanvas()
        tl.addWidget(b_ts)
        tl.addWidget(self.canvas_ts, 1)
        self.sub.addTab(self._ts_page, "時系列")

        # A/B比較（無効）
        w_ab = QWidget()
        al = QVBoxLayout(w_ab)
        al.addWidget(QLabel("補正あり / なし の A/B 比較 —— 将来拡張（現在は無効）"))
        al.addStretch(1)
        self.sub.addTab(w_ab, "A/B比較")

        self.sub.currentChanged.connect(self._on_subtab)
        self._cap = None

    # -- idx handling --
    def current_idx(self):
        t = self.cmb_idx.currentText()
        return int(t) if t.isdigit() else None

    def add_result(self, idx: int):
        if self.cmb_idx.findText(str(idx)) < 0:
            self.cmb_idx.addItem(str(idx))
        self.cmb_idx.setCurrentText(str(idx))
        self._on_idx()

    def clear_results(self):
        self.cmb_idx.clear()

    def _on_idx(self):
        idx = self.current_idx()
        self._load_preview(idx)
        cur = self.sub.currentWidget()
        if cur is self.view_deg:
            self.view_deg.reload()
        elif cur is self.view_stat:
            self.view_stat.reload()

    def _on_subtab(self, _i):
        cur = self.sub.currentWidget()
        if cur is self._ts_page:
            self._plot_timeseries()
        elif cur is self.view_deg:
            self.view_deg.reload()
        elif cur is self.view_stat:
            self.view_stat.reload()

    # -- preview --
    def _load_preview(self, idx):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if idx is None or idx not in self.main.results:
            self.pv.set_message("（結果なし）")
            self.sld.setEnabled(False)
            return
        res = self.main.results[idx]
        if res.is_mov:
            self._cap = cv2.VideoCapture(res.out_img)
            n = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.sld.setEnabled(True)
            self.sld.setRange(0, max(n - 1, 0))
            self.sld.setValue(0)
            self._show_frame(0)
        else:
            self.sld.setEnabled(False)
            self.pv.set_bgr(imio.imread(res.out_img))

    def _on_frame(self, v):
        self._show_frame(v)

    def _show_frame(self, v):
        if self._cap is None:
            return
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, v)
        ok, frame = self._cap.read()
        if ok:
            self.pv.set_bgr(frame)

    # -- timeseries --
    def _plot_timeseries(self):
        ax = self.canvas_ts.ax
        ax.clear()
        items = sorted(self.main.results.items())
        if items:
            xs = [i for i, _ in items]
            for c, color in zip("rgb", ["tab:red", "tab:green", "tab:blue"]):
                ax.plot(xs, [r.get_means()[c] for _, r in items], "o-", color=color, label=c.upper())
            ax.set_xlabel("step idx")
            ax.set_ylabel("平均劣化率 (mean deg)")
            ax.set_xticks(xs)
            ax.legend()
            ax.grid(alpha=0.3)
        else:
            ax.set_title("（結果なし）")
        self.canvas_ts.draw_idle()
