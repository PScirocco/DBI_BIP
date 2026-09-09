"""③ ステップ設定（仕様 5-③）

選択中レシピを編集する。プレビュー3面（入力 / ヒートマップ / 前回Aging結果）、
モデルパラメータ表＋CSV、Sim条件＋CSV、初期ストレス（なし / 前ステップ継承 / ファイル指定）。
BC設定・処理パイプライン・A/B は将来枠（無効表示）。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from bisim import naming, paramio
from bisim.model import MODEL_KEYS, Recipe, Sequence
from bisim.ui.i18n import t
from bisim.ui.tabs._common import kind_label, with_btn
from bisim.ui.widgets import ImagePanel, read_first_frame

IMG_FILTER = "画像・動画 / images & movies (*.png *.mp4);;すべて / all (*)"
INIT_KEYS = ["none", "prev", "file"]


class StepConfigTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.recipe: Recipe | None = None
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
        f1.addRow(self.l_img, with_btn(self.ed_img, self.b_img))

        self.ed_ht = QLineEdit()
        self.ed_ht.setReadOnly(True)
        self.b_ht = QPushButton(t("btn.browse"))
        self.b_ht.clicked.connect(lambda: self._pick_file("heatmap"))
        self.l_ht = QLabel(t("cfg.heatmap"))
        f1.addRow(self.l_ht, with_btn(self.ed_ht, self.b_ht))

        self.lbl_kind = QLabel(t("kind.unknown"))
        self.l_kind = QLabel(t("cfg.kind"))
        f1.addRow(self.l_kind, self.lbl_kind)
        form.addLayout(f1)

        # ---- 初期ストレス ----
        self.gb_init = QGroupBox(t("cfg.grp.init"))
        g = QVBoxLayout(self.gb_init)
        self.cmb_init = QComboBox()
        self.cmb_init.addItems([t(f"init.{k}") for k in INIT_KEYS])
        self.cmb_init.currentIndexChanged.connect(self._on_init_changed)
        g.addWidget(self.cmb_init)
        self.file_host = QWidget()
        fg = QFormLayout(self.file_host)
        self.ed_sr, self.ed_sg, self.ed_sb = QLineEdit(), QLineEdit(), QLineEdit()
        self._stat_btns = []
        self._stat_labels = []
        for ckey, ed in [("cfg.init.file_r", self.ed_sr), ("cfg.init.file_g", self.ed_sg),
                         ("cfg.init.file_b", self.ed_sb)]:
            bb = QPushButton(t("btn.browse"))
            bb.clicked.connect(lambda _=False, e=ed: self._pick_stat(e))
            lab = QLabel(t(ckey))
            fg.addRow(lab, with_btn(ed, bb))
            self._stat_btns.append(bb)
            self._stat_labels.append((ckey, lab))
        g.addWidget(self.file_host)
        form.addWidget(self.gb_init)

        # ---- モデルパラメータ ----
        self.gb_model = QGroupBox(t("cfg.grp.model"))
        g2 = QVBoxLayout(self.gb_model)
        self.tbl_model = QTableWidget(len(MODEL_KEYS), 3)
        self.tbl_model.setHorizontalHeaderLabels(["R", "G", "B"])
        self.tbl_model.setVerticalHeaderLabels(MODEL_KEYS)
        self.tbl_model.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_model.setMaximumHeight(190)
        g2.addWidget(self.tbl_model)
        self.lbl_model_csv = QLabel(t("cfg.model_csv_none"))
        g2.addWidget(self.lbl_model_csv)
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

        # ---- Sim条件 ----
        self.gb_sim = QGroupBox(t("cfg.grp.sim"))
        f3 = QFormLayout(self.gb_sim)
        self.sp_accel = self._dspin(1.0, 1e12, 1000.0)
        self.sp_tl = self._dspin(-50.0, 200.0, 1.0)
        self.sp_th = self._dspin(-50.0, 300.0, 1.0)
        self.sp_aging = self._dspin(0.0, 1e9, 1.0)
        self.l_accel = QLabel(t("cfg.accel"))
        self.l_tl = QLabel(t("cfg.tmp_l"))
        self.l_th = QLabel(t("cfg.tmp_h"))
        self.l_aging = QLabel(t("cfg.aging_time"))
        f3.addRow(self.l_accel, self.sp_accel)
        f3.addRow(self.l_tl, self.sp_tl)
        f3.addRow(self.l_th, self.sp_th)
        f3.addRow(self.l_aging, self.sp_aging)
        self.lbl_sim_csv = QLabel(t("cfg.sim_csv_none"))
        f3.addRow(self.lbl_sim_csv)
        hb_sim = QHBoxLayout()
        self.b_load_sim = QPushButton(t("cfg.btn.load_csv"))
        self.b_load_sim.clicked.connect(self._load_sim_csv)
        self.b_save_sim = QPushButton(t("cfg.btn.save_csv"))
        self.b_save_sim.clicked.connect(self._save_sim_csv)
        hb_sim.addWidget(self.b_load_sim)
        hb_sim.addWidget(self.b_save_sim)
        hb_sim.addStretch(1)
        f3.addRow(hb_sim)
        form.addWidget(self.gb_sim)

        # ---- 将来拡張 ----
        self.gb_future = QGroupBox(t("cfg.grp.future"))
        g4 = QVBoxLayout(self.gb_future)
        self.lbl_bc = QLabel(t("cfg.bc_note"))
        g4.addWidget(self.lbl_bc)
        self._future_cbs = {
            "cfg.pipe.bip": QCheckBox(), "cfg.pipe.dbi": QCheckBox(),
            "cfg.pipe.peak": QCheckBox(), "cfg.pipe.ab": QCheckBox(),
        }
        for key, cb in self._future_cbs.items():
            cb.setText(t(key))
            cb.setEnabled(False)
            g4.addWidget(cb)
        form.addWidget(self.gb_future)

        self.btn_apply = QPushButton(t("cfg.btn.apply"))
        self.btn_apply.clicked.connect(self._apply)
        form.addWidget(self.btn_apply)
        form.addStretch(1)

        # 左カラムはスクロール可（ウィンドウを縦に小さくしても畳める。
        # これが無いと全タブの最小高さがこのフォーム分まで押し上げられる）
        form_scroll = QScrollArea()
        form_scroll.setWidget(form_host)
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.Shape.NoFrame)

        # ---- プレビュー ----
        prev_host = QWidget()
        pv = QVBoxLayout(prev_host)
        self.pv_img = ImagePanel(t("cfg.pv.input"), min_h=100)
        self.pv_ht = ImagePanel(t("cfg.pv.heatmap"), min_h=100)
        self.pv_prev = ImagePanel(t("cfg.pv.prev"), min_h=100)
        pv.addWidget(self.pv_img, 1)
        pv.addWidget(self.pv_ht, 1)
        pv.addWidget(self.pv_prev, 1)

        root.addWidget(form_scroll, 3)
        root.addWidget(prev_host, 2)
        self.set_enabled(False)

    @staticmethod
    def _dspin(lo, hi, step):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(3)
        s.setSingleStep(step)
        return s

    def _folders(self) -> dict:
        return self.main.sequence.folders

    def set_enabled(self, on: bool):
        for w in (self.ed_name, self.ed_img, self.ed_ht, self.cmb_init, self.tbl_model,
                  self.sp_accel, self.sp_tl, self.sp_th, self.sp_aging, self.btn_apply,
                  self.b_img, self.b_ht, self.b_load, self.b_save,
                  self.b_load_sim, self.b_save_sim):
            w.setEnabled(on)

    # -- load / collect --
    def load(self, recipe: Recipe | None, row: int | None):
        self.recipe, self.row = recipe, row
        if recipe is None:
            self.lbl_head.setText(t("cfg.none"))
            self.set_enabled(False)
            for p in (self.pv_img, self.pv_ht, self.pv_prev):
                p.set_message(t("cfg.pv.none"))
            return
        self.set_enabled(True)
        self.lbl_head.setText(t("cfg.head", n=row + 1, nn=Sequence.recipe_number(row)))
        self.ed_name.setText(recipe.recipe_name)
        self.ed_img.setText(recipe.input_image)
        self.ed_ht.setText(recipe.heatmap)
        self.lbl_kind.setText(kind_label(recipe))
        self.cmb_init.blockSignals(True)
        self.cmb_init.setCurrentIndex(INIT_KEYS.index(recipe.init_stress))
        self.cmb_init.blockSignals(False)
        f = recipe.init_stress_files
        self.ed_sr.setText(f.get("r", ""))
        self.ed_sg.setText(f.get("g", ""))
        self.ed_sb.setText(f.get("b", ""))
        self._fill_model_table(recipe.model_param)
        self._set_csv_labels()
        self.sp_accel.setValue(recipe.sim_param["ACCEL_RATIO"])
        self.sp_tl.setValue(recipe.sim_param["TMP_L"])
        self.sp_th.setValue(recipe.sim_param["TMP_H"])
        self.sp_aging.setValue(recipe.sim_param["AGING_TIME"])
        self._on_init_changed()
        self._refresh_previews()

    def _set_csv_labels(self):
        r = self.recipe
        self.lbl_model_csv.setText(
            t("cfg.model_csv", name=r.model_param_csv) if r.model_param_csv
            else t("cfg.model_csv_none"))
        self.lbl_sim_csv.setText(
            t("cfg.sim_csv", name=r.sim_param_csv) if r.sim_param_csv
            else t("cfg.sim_csv_none"))

    def _fill_model_table(self, model: dict):
        for row, key in enumerate(MODEL_KEYS):
            for c in range(3):
                self.tbl_model.setItem(row, c, QTableWidgetItem(f"{model[key][c]:g}"))

    def _collect_into_recipe(self) -> bool:
        r = self.recipe
        name = self.ed_name.text().strip()
        if name:
            r.recipe_name = name
        r.init_stress = INIT_KEYS[self.cmb_init.currentIndex()]
        r.init_stress_files = {
            "r": self.ed_sr.text().strip(), "g": self.ed_sg.text().strip(),
            "b": self.ed_sb.text().strip()}
        try:
            for row, key in enumerate(MODEL_KEYS):
                r.model_param[key] = [float(self.tbl_model.item(row, c).text())
                                      for c in range(3)]
        except (ValueError, AttributeError):
            QMessageBox.warning(self, t("cfg.err.title"), t("cfg.err.model"))
            return False
        r.sim_param["ACCEL_RATIO"] = self.sp_accel.value()
        r.sim_param["TMP_L"] = self.sp_tl.value()
        r.sim_param["TMP_H"] = self.sp_th.value()
        r.sim_param["AGING_TIME"] = self.sp_aging.value()
        return True

    def _apply(self):
        if self.recipe is None or not self._collect_into_recipe():
            return
        self.main.log_param_apply(self.recipe)
        self.main.steps_changed()
        self.main.statusBar().showMessage(t("status.applied"), 3000)

    # -- file pickers --
    def _pick_file(self, folder_key: str):
        if self.recipe is None:
            return
        start = self._folders()[folder_key]
        path, _ = QFileDialog.getOpenFileName(self, t(f"folder.{folder_key}"), start, IMG_FILTER)
        if not path:
            return
        p = Path(path)
        self._folders()[folder_key] = str(p.parent)
        if folder_key == "input_image":
            self.recipe.input_image = p.name
            self.ed_img.setText(p.name)
            self.lbl_kind.setText(kind_label(self.recipe))
        else:
            self.recipe.heatmap = p.name
            self.ed_ht.setText(p.name)
        self.main.folders_changed()
        self.main.steps_changed()
        self._refresh_previews()

    def _pick_stat(self, edit: QLineEdit):
        start = self._folders()["output"]
        path, _ = QFileDialog.getOpenFileName(self, t("cfg.dlg.stress_csv"), start, "CSV (*.csv)")
        if path:
            edit.setText(path)

    def _on_init_changed(self):
        key = INIT_KEYS[self.cmb_init.currentIndex()]
        self.file_host.setVisible(key == "file")
        self._refresh_prev_preview(key)

    # -- previews --
    def _refresh_previews(self):
        r = self.recipe
        fi = self._folders()["input_image"]
        fh = self._folders()["heatmap"]
        self.pv_img.set_bgr(
            read_first_frame(str(Path(fi) / r.input_image)) if r.input_image else None)
        self.pv_ht.set_bgr(
            read_first_frame(str(Path(fh) / r.heatmap)) if r.heatmap else None)
        self._refresh_prev_preview(r.init_stress)

    def _refresh_prev_preview(self, key: str):
        self.pv_prev.set_title(t("cfg.pv.prev"))
        if key != "prev" or self.row is None or self.row == 0:
            self.pv_prev.set_message(t("cfg.pv.first"))
            return
        seq = self.main.sequence
        pidx = self.row - 1
        prev = seq.recipes[pidx]
        nn = Sequence.recipe_number(pidx)
        out = Path(self._folders()["output"])
        for kind, ext in (("movie", "mp4"), ("image", "png")):
            cand = out / naming.output_name(seq.sequence_name, nn, prev.recipe_name, kind, ext=ext)
            if cand.exists():
                self.pv_prev.set_title(t("cfg.pv.prev_named", name=cand.name))
                self.pv_prev.set_bgr(read_first_frame(str(cand)))
                return
        self.pv_prev.set_message(t("cfg.pv.prev_notrun", n=pidx + 1))

    # -- model / sim csv --
    def _load_model_csv(self):
        start = self._folders()["model"]
        path, _ = QFileDialog.getOpenFileName(self, t("cfg.dlg.model_csv"), start, "CSV (*.csv)")
        if not path:
            return
        try:
            m = paramio.read_model_csv(path)
        except (OSError, ValueError):
            QMessageBox.warning(self, t("cfg.load_fail.title"), t("cfg.load_fail.msg"))
            return
        self._folders()["model"] = str(Path(path).parent)
        self.recipe.model_param = m
        self.recipe.model_param_csv = Path(path).name
        self._fill_model_table(m)
        self._set_csv_labels()
        self.main.folders_changed()

    def _save_model_csv(self):
        if self.recipe is None or not self._collect_into_recipe():
            return
        start = str(Path(self._folders()["model"]) /
                    naming.input_name(self.recipe.recipe_name, "model-param"))
        path, _ = QFileDialog.getSaveFileName(self, t("cfg.dlg.model_csv"), start, "CSV (*.csv)")
        if not path:
            return
        paramio.write_model_csv(path, self.recipe.model_param)
        self.recipe.model_param_csv = Path(path).name
        self._folders()["model"] = str(Path(path).parent)
        self._set_csv_labels()
        self.main.folders_changed()
        self.main.statusBar().showMessage(t("status.saved", path=path), 3000)

    def _load_sim_csv(self):
        start = self._folders()["simconf"]
        path, _ = QFileDialog.getOpenFileName(self, t("cfg.dlg.sim_csv"), start, "CSV (*.csv)")
        if not path:
            return
        try:
            s = paramio.read_sim_csv(path)
        except (OSError, ValueError):
            QMessageBox.warning(self, t("cfg.load_fail.title"), t("cfg.load_fail.msg"))
            return
        self._folders()["simconf"] = str(Path(path).parent)
        self.recipe.sim_param = s
        self.recipe.sim_param_csv = Path(path).name
        self.sp_accel.setValue(s["ACCEL_RATIO"])
        self.sp_tl.setValue(s["TMP_L"])
        self.sp_th.setValue(s["TMP_H"])
        self.sp_aging.setValue(s["AGING_TIME"])
        self._set_csv_labels()
        self.main.folders_changed()

    def _save_sim_csv(self):
        if self.recipe is None or not self._collect_into_recipe():
            return
        start = str(Path(self._folders()["simconf"]) /
                    naming.input_name(self.recipe.recipe_name, "sim-param"))
        path, _ = QFileDialog.getSaveFileName(self, t("cfg.dlg.sim_csv"), start, "CSV (*.csv)")
        if not path:
            return
        paramio.write_sim_csv(path, self.recipe.sim_param)
        self.recipe.sim_param_csv = Path(path).name
        self._folders()["simconf"] = str(Path(path).parent)
        self._set_csv_labels()
        self.main.folders_changed()
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
        for ckey, lab in self._stat_labels:
            lab.setText(t(ckey))
        cur = self.cmb_init.currentIndex()
        self.cmb_init.blockSignals(True)
        self.cmb_init.clear()
        self.cmb_init.addItems([t(f"init.{k}") for k in INIT_KEYS])
        self.cmb_init.setCurrentIndex(max(cur, 0))
        self.cmb_init.blockSignals(False)
        self.b_load.setText(t("cfg.btn.load_csv"))
        self.b_save.setText(t("cfg.btn.save_csv"))
        self.b_load_sim.setText(t("cfg.btn.load_csv"))
        self.b_save_sim.setText(t("cfg.btn.save_csv"))
        self.l_accel.setText(t("cfg.accel"))
        self.l_tl.setText(t("cfg.tmp_l"))
        self.l_th.setText(t("cfg.tmp_h"))
        self.l_aging.setText(t("cfg.aging_time"))
        self.lbl_bc.setText(t("cfg.bc_note"))
        for key, cb in self._future_cbs.items():
            cb.setText(t(key))
        self.btn_apply.setText(t("cfg.btn.apply"))
        self.pv_img.set_title(t("cfg.pv.input"))
        self.pv_ht.set_title(t("cfg.pv.heatmap"))
        self.load(self.recipe, self.row)
