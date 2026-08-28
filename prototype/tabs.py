""" 5つのタブ（プロトタイプ用 UX 検証）。文字列は i18n.t() 経由（JP/EN 切替対応）。 """
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

import imio
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSlider, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from i18n import t
from state import FOLDER_KEYS, MODEL_ROWS, Step, folder_label, load_model_csv
from widgets import ImagePanel, MplCanvas, read_first_frame

IMG_FILTER = "画像・動画 / images & movies (*.png *.mp4);;すべて / all (*)"
INIT_KEYS = ["none", "prev", "file"]
CH_KEYS = ["r", "g", "b", "rgb"]


def _with_btn(edit, btn):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(edit, 1)
    h.addWidget(btn)
    return w


# --------------------------------------------------------------------------- #
#  ① フォルダ設定
# --------------------------------------------------------------------------- #
class FoldersTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.edits: dict[str, QLineEdit] = {}
        self.row_labels: dict[str, QLabel] = {}
        self.browse_btns: dict[str, QPushButton] = {}

        lay = QVBoxLayout(self)
        self.lbl_desc = QLabel(t("folders.desc"))
        self.lbl_desc.setWordWrap(True)
        lay.addWidget(self.lbl_desc)

        self.form = QFormLayout()
        for key in FOLDER_KEYS:
            edit = QLineEdit(self.main.state.folders[key])
            edit.editingFinished.connect(lambda k=key: self._on_edit(k))
            btn = QPushButton(t("btn.browse"))
            btn.clicked.connect(lambda _=False, k=key: self._browse(k))
            lbl = QLabel(folder_label(key))
            self.form.addRow(lbl, _with_btn(edit, btn))
            self.edits[key] = edit
            self.row_labels[key] = lbl
            self.browse_btns[key] = btn
        lay.addLayout(self.form)
        lay.addStretch(1)

    def _on_edit(self, key):
        self.main.state.folders[key] = self.edits[key].text().strip()

    def _browse(self, key):
        d = QFileDialog.getExistingDirectory(self, folder_label(key), self.main.state.folders[key])
        if d:
            self.main.state.folders[key] = d
            self.edits[key].setText(d)

    def refresh(self):
        for key, edit in self.edits.items():
            if edit.text() != self.main.state.folders[key]:
                edit.setText(self.main.state.folders[key])

    def retranslate(self):
        self.lbl_desc.setText(t("folders.desc"))
        for key in FOLDER_KEYS:
            self.row_labels[key].setText(folder_label(key))
            self.browse_btns[key].setText(t("btn.browse"))


# --------------------------------------------------------------------------- #
#  ② 実行ステップ
# --------------------------------------------------------------------------- #
class StepsTab(QWidget):
    H_KEYS = ["steps.h.num", "steps.h.name", "steps.h.type", "steps.h.input",
              "steps.h.heatmap", "steps.h.init", "steps.h.status"]

    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)

        self.table = QTableWidget(0, len(self.H_KEYS))
        self.table.setHorizontalHeaderLabels([t(k) for k in self.H_KEYS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.cellDoubleClicked.connect(lambda *_: self.main.goto_config())
        lay.addWidget(self.table, 1)

        btns = QHBoxLayout()
        self._btns = {
            "steps.btn.add": (QPushButton(), self._add),
            "steps.btn.dup": (QPushButton(), self._dup),
            "steps.btn.del": (QPushButton(), self._del),
            "steps.btn.up": (QPushButton(), lambda: self._move(-1)),
            "steps.btn.down": (QPushButton(), lambda: self._move(1)),
            "steps.btn.edit": (QPushButton(), self.main.goto_config),
        }
        for key, (b, slot) in self._btns.items():
            b.setText(t(key))
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

    # -- data ops --
    def _add(self):
        n = len(self.main.state.steps) + 1
        self.main.state.steps.append(Step(name=t("steps.nth", n=n)))
        self.main.steps_changed()
        self._select_row(len(self.main.state.steps) - 1)

    def _dup(self):
        r = self.current_row()
        if r is None:
            return
        import copy
        s = copy.deepcopy(self.main.state.steps[r])
        s.name = s.display_name() + t("steps.copy_suffix")
        s.status = "pending"
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
            init = {"none": t("init.zero"),
                    "prev": t("init.inherit_n", i=i),
                    "file": t("init.file")}[s.init_stress]
            dash = t("kind.unknown")
            values = [str(i + 1), s.display_name(), s.kind_label, s.input_image or dash,
                      s.heatmap or dash, init, t(f"status.{s.status}")]
            for c, v in enumerate(values):
                self.table.setItem(i, c, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)
        if self.main.current_row is not None and self.main.current_row < len(steps):
            self._select_row(self.main.current_row)

    def retranslate(self):
        self.table.setHorizontalHeaderLabels([t(k) for k in self.H_KEYS])
        for key, (b, _slot) in self._btns.items():
            b.setText(t(key))
        self.refresh()


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
        form_host = QWidget()
        form = QVBoxLayout(form_host)

        self.lbl_head = QLabel(t("cfg.none"))
        self.lbl_head.setStyleSheet("font-size:15px; font-weight:600;")
        form.addWidget(self.lbl_head)

        f1 = QFormLayout()
        self.ed_name = QLineEdit()
        self.l_name = QLabel(t("cfg.name"))
        f1.addRow(self.l_name, self.ed_name)

        self.ed_img = QLineEdit()
        self.ed_img.setReadOnly(True)
        self.b_img = QPushButton(t("btn.browse"))
        self.b_img.clicked.connect(lambda: self._pick_file("input_image"))
        self.l_img = QLabel(t("cfg.input"))
        f1.addRow(self.l_img, _with_btn(self.ed_img, self.b_img))

        self.ed_ht = QLineEdit()
        self.ed_ht.setReadOnly(True)
        self.b_ht = QPushButton(t("btn.browse"))
        self.b_ht.clicked.connect(lambda: self._pick_file("heatmap"))
        self.l_ht = QLabel(t("cfg.heatmap"))
        f1.addRow(self.l_ht, _with_btn(self.ed_ht, self.b_ht))

        self.lbl_kind = QLabel(t("kind.unknown"))
        self.l_kind = QLabel(t("cfg.kind"))
        f1.addRow(self.l_kind, self.lbl_kind)
        form.addLayout(f1)

        # 初期ストレス
        self.gb_init = QGroupBox(t("cfg.grp.init"))
        g = QVBoxLayout(self.gb_init)
        self.cmb_init = QComboBox()
        self.cmb_init.addItems([t(f"initsel.{k}") for k in INIT_KEYS])
        self.cmb_init.currentIndexChanged.connect(self._on_init_changed)
        g.addWidget(self.cmb_init)
        self.file_host = QWidget()
        fg = QFormLayout(self.file_host)
        self.ed_sr, self.ed_sg, self.ed_sb = QLineEdit(), QLineEdit(), QLineEdit()
        self._stat_btns = []
        for lab, ed in [("stat_r", self.ed_sr), ("stat_g", self.ed_sg), ("stat_b", self.ed_sb)]:
            bb = QPushButton(t("btn.browse"))
            bb.clicked.connect(lambda _=False, e=ed: self._pick_stat(e))
            fg.addRow(lab, _with_btn(ed, bb))
            self._stat_btns.append(bb)
        g.addWidget(self.file_host)
        form.addWidget(self.gb_init)

        # モデルパラメータ
        self.gb_model = QGroupBox(t("cfg.grp.model"))
        g2 = QVBoxLayout(self.gb_model)
        self.tbl_model = QTableWidget(len(MODEL_ROWS), 3)
        self.tbl_model.setHorizontalHeaderLabels(["R", "G", "B"])
        self.tbl_model.setVerticalHeaderLabels(MODEL_ROWS)
        self.tbl_model.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_model.setMaximumHeight(190)
        g2.addWidget(self.tbl_model)
        hb = QHBoxLayout()
        self.b_load = QPushButton(t("cfg.btn.load_csv"))
        self.b_load.clicked.connect(self._load_model_csv)
        self.b_save = QPushButton(t("cfg.btn.save_csv"))
        self.b_save.clicked.connect(self._save_model_csv)
        hb.addWidget(self.b_load)
        hb.addWidget(self.b_save)
        hb.addStretch(1)
        g2.addLayout(hb)
        form.addWidget(self.gb_model)

        # Sim条件
        self.gb_sim = QGroupBox(t("cfg.grp.sim"))
        f3 = QFormLayout(self.gb_sim)
        self.sp_accel = self._dspin(1.0, 1e9, 100.0)
        self.sp_tl = self._dspin(-50.0, 200.0, 1.0)
        self.sp_th = self._dspin(-50.0, 300.0, 1.0)
        self.sp_aging = self._dspin(0.0, 1e6, 1.0)
        self.l_accel = QLabel("ACCEL_RATIO")
        self.l_tl = QLabel(t("cfg.tmp_l"))
        self.l_th = QLabel(t("cfg.tmp_h"))
        self.l_aging = QLabel(t("cfg.aging_time"))
        f3.addRow(self.l_accel, self.sp_accel)
        f3.addRow(self.l_tl, self.sp_tl)
        f3.addRow(self.l_th, self.sp_th)
        f3.addRow(self.l_aging, self.sp_aging)
        form.addWidget(self.gb_sim)

        # 将来拡張
        self.gb_future = QGroupBox(t("cfg.grp.future"))
        g4 = QVBoxLayout(self.gb_future)
        self.lbl_bc = QLabel(t("cfg.bc_note"))
        g4.addWidget(self.lbl_bc)
        self.cb_bip = QCheckBox(t("cfg.pipe.bip"))
        self.cb_dbi = QCheckBox(t("cfg.pipe.dbi"))
        self.cb_peak = QCheckBox(t("cfg.pipe.peak"))
        self.cb_ab = QCheckBox(t("cfg.pipe.ab"))
        for cb in (self.cb_bip, self.cb_dbi, self.cb_peak, self.cb_ab):
            cb.setEnabled(False)
            g4.addWidget(cb)
        form.addWidget(self.gb_future)

        self.btn_apply = QPushButton(t("cfg.btn.apply"))
        self.btn_apply.clicked.connect(self._apply)
        form.addWidget(self.btn_apply)
        form.addStretch(1)

        # プレビュー
        prev_host = QWidget()
        pv = QVBoxLayout(prev_host)
        self.pv_img = ImagePanel(t("cfg.pv.input"))
        self.pv_ht = ImagePanel(t("cfg.pv.heatmap"))
        self.pv_prev = ImagePanel(t("cfg.pv.prev"))
        pv.addWidget(self.pv_img, 1)
        pv.addWidget(self.pv_ht, 1)
        pv.addWidget(self.pv_prev, 1)

        root.addWidget(form_host, 3)
        root.addWidget(prev_host, 2)
        self.set_enabled(False)

    @staticmethod
    def _dspin(lo, hi, step):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(3)
        s.setSingleStep(step)
        return s

    def set_enabled(self, on: bool):
        for w in (self.ed_name, self.ed_img, self.ed_ht, self.cmb_init, self.tbl_model,
                  self.sp_accel, self.sp_tl, self.sp_th, self.sp_aging, self.btn_apply,
                  self.b_img, self.b_ht, self.b_load, self.b_save):
            w.setEnabled(on)

    # -- load / collect --
    def load(self, step: Step | None, row: int | None):
        self.step, self.row = step, row
        if step is None:
            self.lbl_head.setText(t("cfg.none"))
            self.set_enabled(False)
            for p in (self.pv_img, self.pv_ht, self.pv_prev):
                p.set_message(t("cfg.pv.none"))
            return
        self.set_enabled(True)
        self.lbl_head.setText(t("cfg.head", n=row + 1))
        self.ed_name.setText(step.display_name())
        self.ed_img.setText(step.input_image)
        self.ed_ht.setText(step.heatmap)
        self.lbl_kind.setText(step.kind_label)
        self.cmb_init.setCurrentIndex(INIT_KEYS.index(step.init_stress))
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
        typed = self.ed_name.text().strip()
        if typed and typed != s.display_name():   # サンプル名のままなら i18n 追従を維持
            s.name, s.name_key = typed, ""
        s.init_stress = INIT_KEYS[self.cmb_init.currentIndex()]
        s.stress_r, s.stress_g, s.stress_b = (
            self.ed_sr.text().strip(), self.ed_sg.text().strip(), self.ed_sb.text().strip())
        try:
            for r, key in enumerate(MODEL_ROWS):
                s.model[key] = [float(self.tbl_model.item(r, c).text()) for c in range(3)]
        except (ValueError, AttributeError):
            QMessageBox.warning(self, t("cfg.err.title"), t("cfg.err.model"))
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
        self.main.statusBar().showMessage(t("status.applied"), 3000)

    # -- file pickers --
    def _pick_file(self, folder_key: str):
        if self.step is None:
            return
        start = self.main.state.folders[folder_key]
        path, _ = QFileDialog.getOpenFileName(self, folder_label(folder_key), start, IMG_FILTER)
        if not path:
            return
        p = Path(path)
        self.main.state.folders[folder_key] = str(p.parent)
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
        path, _ = QFileDialog.getOpenFileName(self, t("cfg.dlg.stress_csv"), start, "CSV (*.csv)")
        if path:
            edit.setText(path)

    def _on_init_changed(self):
        key = INIT_KEYS[self.cmb_init.currentIndex()]
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
            self.pv_prev.set_title(t("cfg.pv.prev"))
            self.pv_prev.set_message(t("cfg.pv.first"))
            return
        prev_idx = self.row
        out = Path(self.main.state.folders["output"])
        for ext in (".png", ".mp4"):
            cand = out / f"{prev_idx}_out_img{ext}"
            if cand.exists():
                self.pv_prev.set_title(t("cfg.pv.prev_named", n=prev_idx, ext=ext))
                self.pv_prev.set_bgr(read_first_frame(str(cand)))
                return
        self.pv_prev.set_title(t("cfg.pv.prev"))
        self.pv_prev.set_message(t("cfg.pv.prev_notrun", n=prev_idx))

    # -- model csv --
    def _load_model_csv(self):
        start = self.main.state.folders["model"]
        path, _ = QFileDialog.getOpenFileName(self, t("cfg.dlg.model_csv"), start, "CSV (*.csv)")
        if not path:
            return
        m = load_model_csv(path)
        if m is None:
            QMessageBox.warning(self, t("cfg.load_fail.title"), t("cfg.load_fail.msg"))
            return
        self.main.state.folders["model"] = str(Path(path).parent)
        self.step.model = m
        self._fill_model_table(m)
        self.main.folders_changed()

    def _save_model_csv(self):
        if self.step is None or not self._collect_into_step():
            return
        start = str(Path(self.main.state.folders["model"]) / "degparam_mm.csv")
        path, _ = QFileDialog.getSaveFileName(self, t("cfg.dlg.model_csv"), start, "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            for key in MODEL_ROWS:
                f.write(",".join([key] + [f"{v:g}" for v in self.step.model[key]]) + "\n")
        self.main.statusBar().showMessage(t("status.saved", path=path), 3000)

    def retranslate(self):
        self.l_name.setText(t("cfg.name"))
        self.l_img.setText(t("cfg.input"))
        self.l_ht.setText(t("cfg.heatmap"))
        self.l_kind.setText(t("cfg.kind"))
        self.b_img.setText(t("btn.browse"))
        self.b_ht.setText(t("btn.browse"))
        self.gb_init.setTitle(t("cfg.grp.init"))
        self.gb_model.setTitle(t("cfg.grp.model"))
        self.gb_sim.setTitle(t("cfg.grp.sim"))
        self.gb_future.setTitle(t("cfg.grp.future"))
        for bb in self._stat_btns:
            bb.setText(t("btn.browse"))
        cur = self.cmb_init.currentIndex()
        self.cmb_init.blockSignals(True)
        self.cmb_init.clear()
        self.cmb_init.addItems([t(f"initsel.{k}") for k in INIT_KEYS])
        self.cmb_init.setCurrentIndex(max(cur, 0))
        self.cmb_init.blockSignals(False)
        self.b_load.setText(t("cfg.btn.load_csv"))
        self.b_save.setText(t("cfg.btn.save_csv"))
        self.l_tl.setText(t("cfg.tmp_l"))
        self.l_th.setText(t("cfg.tmp_h"))
        self.l_aging.setText(t("cfg.aging_time"))
        self.lbl_bc.setText(t("cfg.bc_note"))
        self.cb_bip.setText(t("cfg.pipe.bip"))
        self.cb_dbi.setText(t("cfg.pipe.dbi"))
        self.cb_peak.setText(t("cfg.pipe.peak"))
        self.cb_ab.setText(t("cfg.pipe.ab"))
        self.btn_apply.setText(t("cfg.btn.apply"))
        self.pv_img.set_title(t("cfg.pv.input"))
        self.pv_ht.set_title(t("cfg.pv.heatmap"))
        self.load(self.step, self.row)


# --------------------------------------------------------------------------- #
#  ④ 実行
# --------------------------------------------------------------------------- #
class RunTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._running = False
        lay = QVBoxLayout(self)

        btns = QHBoxLayout()
        self.b_all = QPushButton(t("run.btn.all"))
        self.b_sel = QPushButton(t("run.btn.sel"))
        self.b_abort = QPushButton(t("run.btn.abort"))
        self.b_all.clicked.connect(lambda: self.main.run_steps("all"))
        self.b_sel.clicked.connect(lambda: self.main.run_steps("selected"))
        self.b_abort.clicked.connect(self.main.abort_run)
        for b in (self.b_all, self.b_sel, self.b_abort):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.lbl_step = QLabel(t("run.idle"))
        self.pb_step = QProgressBar()
        self.lbl_frame = QLabel(t("run.dash"))
        self.pb_frame = QProgressBar()
        self.lbl_elapsed = QLabel(t("run.elapsed", s=0.0))
        for w in (self.lbl_step, self.pb_step, self.lbl_frame, self.pb_frame, self.lbl_elapsed):
            lay.addWidget(w)

        self.preview = ImagePanel(t("run.preview"), min_h=200)
        lay.addWidget(self.preview, 1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        lay.addWidget(self.log, 1)
        self.set_running(False)

    def set_running(self, on: bool):
        self._running = on
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
        self.append_log(t("run.log.start", n=nsteps))

    def on_step(self, si: int, n: int, name: str):
        self.lbl_step.setText(t("run.step", i=si + 1, n=n, name=name))
        self.pb_step.setValue(si)

    def on_progress(self, si, n, f, ft, qimg):
        self.lbl_frame.setText(t("run.frame", f=f, ft=ft))
        self.pb_frame.setRange(0, max(ft, 1))
        self.pb_frame.setValue(f)
        if qimg is not None:
            self.preview.set_qimage(qimg)

    def on_elapsed(self, sec: float):
        self.lbl_elapsed.setText(t("run.elapsed", s=sec))

    def on_finished(self, aborted: bool):
        self.pb_step.setValue(self.pb_step.maximum())
        self.lbl_step.setText(t("run.state.aborted") if aborted else t("run.state.done"))
        self.append_log(t("run.log.aborted") if aborted else t("run.log.done"))
        self.set_running(False)

    def on_error(self, msg: str):
        self.append_log(t("run.log.err", msg=msg))
        self.lbl_step.setText(t("run.state.err"))
        self.set_running(False)

    def retranslate(self):
        self.b_all.setText(t("run.btn.all"))
        self.b_sel.setText(t("run.btn.sel"))
        self.b_abort.setText(t("run.btn.abort"))
        self.preview.set_title(t("run.preview"))
        if not self._running:
            self.lbl_step.setText(t("run.idle"))
            self.lbl_frame.setText(t("run.dash"))


# --------------------------------------------------------------------------- #
#  ⑤ 結果
# --------------------------------------------------------------------------- #
class _MapView(QWidget):
    """ 劣化率マップ / 累積ストレスマップ 共通ビュー
        各チャネルはそのチャネル色の輝度で表示（黒=劣化大 / 明=劣化小）。RGB合成も可。
    """

    def __init__(self, main, kind: str):
        super().__init__()
        self.main = main
        self.kind = kind  # "deg" | "stat"
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
            self.lbl_hover.setText(t("map.hover.ch", x=x, y=y, ch=c.upper(), v=self._raw[c][y, x]))
        else:
            vals = "  ".join(f"{c.upper()}={self._raw[c][y, x]:.4f}" for c in "rgb")
            self.lbl_hover.setText(t("map.hover.rgb", x=x, y=y, vals=vals))

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self.reload()

    def reload(self):
        idx = self.main.results_tab.current_idx()
        if idx is None or idx not in self.main.results:
            self.canvas.clear_view(t("map.none"))
            self.lbl_stats.setText(t("map.stats.none"))
            self._raw = None
            return
        res = self.main.results[idx]
        paths = res.deg_paths if self.kind == "deg" else res.stat_paths
        try:
            raw = {c: np.loadtxt(paths[c], delimiter=",") for c in "rgb"}
        except OSError:
            self.canvas.clear_view(t("map.csv_fail"))
            self._raw = None
            return
        self._raw = raw
        label = t("map.label.deg") if self.kind == "deg" else t("map.label.stat")

        if self.kind == "deg":
            vmax = 1.0
            rng = t("map.range01")
        else:
            vmax = max(float(np.nanmax(raw[c])) for c in "rgb") or 1.0
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
            parts = " / ".join(f"{c.upper()} mean {np.nanmean(raw[c]):.4g}" for c in "rgb")
            self.lbl_stats.setText(parts)

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

        w_prev = QWidget()
        pl = QVBoxLayout(w_prev)
        self.pv = ImagePanel(t("res.preview.title"), min_h=260)
        self.sld = QSlider(Qt.Orientation.Horizontal)
        self.sld.setEnabled(False)
        self.sld.valueChanged.connect(self._on_frame)
        pl.addWidget(self.pv, 1)
        pl.addWidget(self.sld)
        self.sub.addTab(w_prev, t("res.sub.preview"))

        self.view_deg = _MapView(main, "deg")
        self.view_stat = _MapView(main, "stat")
        self.sub.addTab(self.view_deg, t("res.sub.deg"))
        self.sub.addTab(self.view_stat, t("res.sub.stat"))

        self._ts_page = QWidget()
        tl = QVBoxLayout(self._ts_page)
        self.b_ts = QPushButton(t("res.ts.update"))
        self.b_ts.clicked.connect(self._plot_timeseries)
        self.canvas_ts = MplCanvas()
        tl.addWidget(self.b_ts)
        tl.addWidget(self.canvas_ts, 1)
        self.sub.addTab(self._ts_page, t("res.sub.ts"))

        w_ab = QWidget()
        al = QVBoxLayout(w_ab)
        self.lbl_ab = QLabel(t("res.ab.note"))
        al.addWidget(self.lbl_ab)
        al.addStretch(1)
        self.sub.addTab(w_ab, t("res.sub.ab"))

        self.sub.currentChanged.connect(self._on_subtab)
        self._cap = None

    def current_idx(self):
        txt = self.cmb_idx.currentText()
        return int(txt) if txt.isdigit() else None

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

    def _load_preview(self, idx):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if idx is None or idx not in self.main.results:
            self.pv.set_message(t("map.none"))
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

    def _plot_timeseries(self):
        ax = self.canvas_ts.ax
        ax.clear()
        items = sorted(self.main.results.items())
        if items:
            xs = [i for i, _ in items]
            for c, color in zip("rgb", ["tab:red", "tab:green", "tab:blue"]):
                ax.plot(xs, [r.get_means()[c] for _, r in items], "o-", color=color, label=c.upper())
            ax.set_xlabel(t("res.ts.x"))
            ax.set_ylabel(t("res.ts.y"))
            ax.set_xticks(xs)
            ax.legend()
            ax.grid(alpha=0.3)
        else:
            ax.set_title(t("res.ts.none"))
        self.canvas_ts.draw_idle()

    def retranslate(self):
        self.lbl_idx.setText(t("res.idx"))
        titles = ["res.sub.preview", "res.sub.deg", "res.sub.stat", "res.sub.ts", "res.sub.ab"]
        for i, key in enumerate(titles):
            self.sub.setTabText(i, t(key))
        self.pv.set_title(t("res.preview.title"))
        self.lbl_ab.setText(t("res.ab.note"))
        self.b_ts.setText(t("res.ts.update"))
        self.view_deg.retranslate()
        self.view_stat.retranslate()
        self._plot_timeseries()
