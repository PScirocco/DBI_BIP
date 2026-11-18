"""③ ステップ設定（仕様 5-③）

選択中レシピを編集する。プレビュー3面（入力 / ヒートマップ / 前ステップの画像）、
Sim条件＋CSV、初期ストレス（なし / 前ステップ継承 / ファイル指定）。
モデルパラメータ（mm）はフェーズF からシーケンスのパネル設定（①）に移した。
ステップ種別（Aging / PQ評価）は手動で選ぶ。PQ評価ではヒートマップと Sim条件のうち Aging 条件
（ACCEL_RATIO・TMP_L/H・AGING_TIME）の欄を隠す（ストレスを貯めない・温度設定なし。2026-10-19 決定）。
表示条件（DBV_NIT・DPK_ON・GADJ）は PQ評価でも設定する（フェーズF）。
サブモデルの差し替え（任意）：このステップだけ別の degparam_sm を使う（表示＝deg2 だけに効く）。
入力画像・ヒートマップは選んだ時点でシーケンスの基準サイズと比べ、違えば警告して選ばせない。
処理パイプライン・A/B は将来枠（無効表示）。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from bisim import engine, naming, paramio
from bisim.model import STEP_TYPES, Recipe, Sequence
from bisim.ui.i18n import t
from bisim.ui.tabs._common import FileWatch, with_btn
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

        # ステップ種別（手動選択。入力が動画か静止画かとは独立）
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItems([t(f"kind.{k}") for k in STEP_TYPES])
        self.cmb_kind.currentIndexChanged.connect(self._on_kind_changed)
        self.l_kind = QLabel(t("cfg.kind"))
        f1.addRow(self.l_kind, self.cmb_kind)
        self.lbl_kind_note = QLabel("")
        self.lbl_kind_note.setWordWrap(True)
        self.lbl_kind_note.setStyleSheet("color:#555;")
        f1.addRow(self.lbl_kind_note)

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
        self._row_ht = with_btn(self.ed_ht, self.b_ht)
        f1.addRow(self.l_ht, self._row_ht)

        # ヒートマップなし＝パネル全面を固定温度で計算（IP設計者レビュー2 (1)）
        ht_fixed_host = QWidget()
        ht_fixed_lay = QHBoxLayout(ht_fixed_host)
        ht_fixed_lay.setContentsMargins(0, 0, 0, 0)
        self.cb_ht_fixed = QCheckBox(t("cfg.heatmap.fixed_cb"))
        self.cb_ht_fixed.toggled.connect(self._on_heatmap_mode_changed)
        self.sp_fixed_temp = self._dspin(-50.0, 200.0, 1.0)
        self.l_ht_fixed_unit = QLabel(t("cfg.heatmap.fixed_unit"))
        ht_fixed_lay.addWidget(self.cb_ht_fixed)
        ht_fixed_lay.addWidget(self.sp_fixed_temp)
        ht_fixed_lay.addWidget(self.l_ht_fixed_unit)
        ht_fixed_lay.addStretch(1)
        self._row_ht_fixed = ht_fixed_host
        f1.addRow(ht_fixed_host)
        self._f1 = f1
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

        # ---- Sim条件 ----
        self.gb_sim = QGroupBox(t("cfg.grp.sim"))
        f3 = QFormLayout(self.gb_sim)
        self.sp_accel = self._dspin(1.0, 1e12, 1000.0)
        self.sp_tl = self._dspin(-50.0, 200.0, 1.0)
        self.sp_th = self._dspin(-50.0, 300.0, 1.0)
        self.sp_aging = self._dspin(0.0, 1e9, 1.0, decimals=0)   # 秒。整数精度でよい（担当者確認済み）
        self.l_accel = QLabel(t("cfg.accel"))
        self.l_tl = QLabel(t("cfg.tmp_l"))
        self.l_th = QLabel(t("cfg.tmp_h"))
        self.l_aging = QLabel(t("cfg.aging_time"))
        f3.addRow(self.l_accel, self.sp_accel)
        f3.addRow(self.l_tl, self.sp_tl)
        f3.addRow(self.l_th, self.sp_th)
        f3.addRow(self.l_aging, self.sp_aging)
        # 表示条件（新コア。フェーズF）：PQ評価のステップでも使う
        self.sp_dbv = self._dspin(0.0, 1e6, 100.0, decimals=2)
        self.cb_dpk = QCheckBox(t("cfg.dpk_on.cb"))
        self.sp_gadj = [self._dspin(0.0, 100.0, 0.01, decimals=4) for _ in range(3)]
        gadj_host = QWidget()
        gl = QHBoxLayout(gadj_host)
        gl.setContentsMargins(0, 0, 0, 0)
        for c, sp in zip("RGB", self.sp_gadj):
            gl.addWidget(QLabel(c))
            gl.addWidget(sp, 1)
        self.l_dbv = QLabel(t("cfg.dbv_nit"))
        self.l_dpk = QLabel(t("cfg.dpk_on"))
        self.l_gadj = QLabel(t("cfg.gadj"))
        f3.addRow(self.l_dbv, self.sp_dbv)
        f3.addRow(self.l_dpk, self.cb_dpk)
        f3.addRow(self.l_gadj, gadj_host)
        self._f3 = f3
        self._aging_rows = (self.sp_accel, self.sp_tl, self.sp_th, self.sp_aging)  # PQ評価では隠す
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

        # ---- サブモデルの差し替え（任意。2026-11-18 決定：表示＝deg2 だけに効く）----
        self.gb_sm = QGroupBox(t("cfg.grp.sm"))
        gs = QVBoxLayout(self.gb_sm)
        self.cb_sm = QCheckBox(t("cfg.sm.cb"))
        self.cb_sm.toggled.connect(self._on_sm_toggled)
        gs.addWidget(self.cb_sm)
        self.ed_sm = QLineEdit()
        self.ed_sm.setReadOnly(True)
        self.b_sm = QPushButton(t("btn.browse"))
        self.b_sm.clicked.connect(self._pick_sm)
        self.b_sm_open = QPushButton(t("panel.btn.open_excel"))
        self.b_sm_open.clicked.connect(self._open_sm)
        # 差し替えのファイル（と①の bcsetting）を Excel で保存したら検査し直す（2026-11-18）
        self._sm_watch = FileWatch(self, self._on_sm_file_changed)
        row_sm = QHBoxLayout()
        row_sm.addWidget(self.ed_sm, 1)
        row_sm.addWidget(self.b_sm)
        row_sm.addWidget(self.b_sm_open)
        gs.addLayout(row_sm)
        self.lbl_sm_status = QLabel("")
        self.lbl_sm_status.setWordWrap(True)
        gs.addWidget(self.lbl_sm_status)
        form.addWidget(self.gb_sm)

        # ---- 将来拡張 ----
        self.gb_future = QGroupBox(t("cfg.grp.future"))
        g4 = QVBoxLayout(self.gb_future)
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
    def _dspin(lo, hi, step, decimals=3):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(decimals)
        s.setSingleStep(step)
        return s

    def _folders(self) -> dict:
        return self.main.sequence.folders

    def set_enabled(self, on: bool):
        for w in (self.ed_name, self.cmb_kind, self.ed_img, self.cmb_init,
                  self.sp_accel, self.sp_tl, self.sp_th, self.sp_aging, self.btn_apply,
                  self.b_img, self.cb_ht_fixed, self.b_load_sim, self.b_save_sim,
                  self.sp_dbv, self.cb_dpk, *self.sp_gadj, self.cb_sm):
            w.setEnabled(on)
        self._sync_heatmap_widgets(on)
        self._sync_sm_widgets()

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
        self.cb_ht_fixed.blockSignals(True)
        self.cb_ht_fixed.setChecked(recipe.heatmap_mode == "fixed")
        self.cb_ht_fixed.blockSignals(False)
        self.sp_fixed_temp.setValue(recipe.fixed_temp_c)
        self._sync_heatmap_widgets(True)
        self.cmb_kind.blockSignals(True)
        self.cmb_kind.setCurrentIndex(STEP_TYPES.index(recipe.step_type))
        self.cmb_kind.blockSignals(False)
        self._sync_kind_widgets(refresh=False)       # プレビューは load の最後でまとめて更新
        self.cmb_init.blockSignals(True)
        self.cmb_init.setCurrentIndex(INIT_KEYS.index(recipe.init_stress))
        self.cmb_init.blockSignals(False)
        f = recipe.init_stress_files
        self.ed_sr.setText(f.get("r", ""))
        self.ed_sg.setText(f.get("g", ""))
        self.ed_sb.setText(f.get("b", ""))
        self._set_csv_labels()
        self.sp_accel.setValue(recipe.sim_param["ACCEL_RATIO"])
        self.sp_tl.setValue(recipe.sim_param["TMP_L"])
        self.sp_th.setValue(recipe.sim_param["TMP_H"])
        self.sp_aging.setValue(recipe.sim_param["AGING_TIME"])
        self._set_display_fields(recipe.sim_param)
        self.cb_sm.blockSignals(True)
        self.cb_sm.setChecked(bool(recipe.sm_override))
        self.cb_sm.blockSignals(False)
        self._sync_sm_widgets()
        self._on_init_changed()
        self._refresh_previews()

    def _set_display_fields(self, sim: dict):
        """表示条件（DBV_NIT・DPK_ON・GADJ）の欄に値を入れる。"""
        self.sp_dbv.setValue(float(sim["DBV_NIT"]))
        self.cb_dpk.setChecked(int(sim["DPK_ON"]) == 1)
        for sp, v in zip(self.sp_gadj, sim["GADJ"]):
            sp.setValue(float(v))

    def _set_csv_labels(self):
        r = self.recipe
        self.lbl_sim_csv.setText(
            t("cfg.sim_csv", name=r.sim_param_csv) if r.sim_param_csv
            else t("cfg.sim_csv_none"))

    def _collect_into_recipe(self) -> bool:
        r = self.recipe
        name = self.ed_name.text().strip()
        if name:
            r.recipe_name = name
        r.step_type = STEP_TYPES[self.cmb_kind.currentIndex()]
        r.init_stress = INIT_KEYS[self.cmb_init.currentIndex()]
        r.heatmap_mode = "fixed" if self.cb_ht_fixed.isChecked() else "file"
        r.fixed_temp_c = self.sp_fixed_temp.value()
        r.init_stress_files = {
            "r": self.ed_sr.text().strip(), "g": self.ed_sg.text().strip(),
            "b": self.ed_sb.text().strip()}
        r.sim_param["ACCEL_RATIO"] = self.sp_accel.value()
        r.sim_param["TMP_L"] = self.sp_tl.value()
        r.sim_param["TMP_H"] = self.sp_th.value()
        r.sim_param["AGING_TIME"] = self.sp_aging.value()
        r.sim_param["DBV_NIT"] = self.sp_dbv.value()
        r.sim_param["DPK_ON"] = 1 if self.cb_dpk.isChecked() else 0
        r.sim_param["GADJ"] = [sp.value() for sp in self.sp_gadj]
        return True

    # -- サブモデルの差し替え（選んだ・外した時点でレシピに反映。入力画像の選択と同じ）--
    def _on_sm_toggled(self, checked: bool):
        if self.recipe is not None and not checked and self.recipe.sm_override:
            self.recipe.sm_override = ""             # チェックを外した → シーケンスの sm に戻す
            self.main.logger.action(f"レシピ '{self.recipe.recipe_name}' のサブモデルの差し替えを解除")
        self._sync_sm_widgets()

    def _sync_sm_widgets(self):
        """欄の有効・無効と状態表示だけ（レシピは変えない）。"""
        on = self.recipe is not None and self.cb_sm.isChecked()
        for w in (self.ed_sm, self.b_sm, self.b_sm_open):
            w.setEnabled(on)
        if self.recipe is None:
            self.ed_sm.setText("")
            self.lbl_sm_status.setText("")
            self._sm_watch.set_paths([])
            return
        self._show_sm_status()

    def _show_sm_status(self):
        seq, r = self.main.sequence, self.recipe
        if not r.sm_override:
            self.ed_sm.setText("")
            self.lbl_sm_status.setStyleSheet("color:#555;")
            self.lbl_sm_status.setText(t("cfg.sm.base", name=seq.panel.degparam_sm))
            self._sm_watch.set_paths([])
            return
        self.ed_sm.setText(Path(r.sm_override).name)
        path = Path(self._folders()["model"]) / r.sm_override      # 絶対パスならそのまま
        self.ed_sm.setToolTip(str(path))
        band = engine.check_bcset(seq.bcset_path()).band_num
        chk = engine.check_sm(path, band)
        if chk.ok:
            self.lbl_sm_status.setStyleSheet("color:#1b6e20;")
            self.lbl_sm_status.setText(t("panel.ok", n=chk.band_num))
        else:
            self.lbl_sm_status.setStyleSheet("color:#b00020;")
            self.lbl_sm_status.setText(t("panel.ng", problems="\n".join(chk.problems)))
        self._sm_watch.set_paths([path, seq.bcset_path()])
        return chk

    def _on_sm_file_changed(self, changed: list):
        """差し替えのファイル（または bcsetting）が変わった（Excel で保存した）→ 検査し直す。"""
        if self.recipe is None or not self.recipe.sm_override:
            return
        names = ", ".join(p.name for p in changed)
        self.main.logger.action(f"サブモデルの差し替えのファイルが変わったため検査し直しました: {names}")
        self._show_sm_status()
        self.main.statusBar().showMessage(t("panel.recheck.auto", names=names), 8000)

    def _set_sm_override(self, p: Path, warn: bool = True):
        """差し替えのファイルを設定する。モデルフォルダ内ならファイル名、外なら絶対パスで持つ
        （①のモデルフォルダを動かすとシーケンスの sm の場所が変わってしまうため）。"""
        model_dir = Path(self._folders()["model"]).resolve()
        r = self.recipe
        r.sm_override = p.name if p.parent.resolve() == model_dir else str(p.resolve())
        self.main.logger.action(f"レシピ '{r.recipe_name}' のサブモデルを差し替え: {p}")
        chk = self._show_sm_status()
        if warn and chk is not None and not chk.ok:
            QMessageBox.warning(self, t("panel.check.title"),
                                t("panel.check.msg", name=p.name, problems="\n".join(chk.problems)))

    def _pick_sm(self):
        if self.recipe is None:
            return
        cur = Path(self._folders()["model"]) / (self.recipe.sm_override or "")
        start = str(cur.parent if self.recipe.sm_override else self._folders()["model"])
        path, _ = QFileDialog.getOpenFileName(self, t("panel.sm"), start, "CSV (*.csv)")
        if path:
            self._set_sm_override(Path(path))

    def _open_sm(self):
        """差し替えのファイルを Excel で開く（複製はしない。保存すると自動で検査し直す）。"""
        if self.recipe is None or not self.recipe.sm_override:
            return
        from bisim.ui.tabs.folders import open_in_excel
        path = self.main.sequence.sm_path(self.row)
        if open_in_excel(self, path, self.main.logger):
            self.main.statusBar().showMessage(t("panel.open.done", path=str(path)), 8000)

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
        if not self._check_size(p, folder_key):
            return                      # 基準サイズと違う → 選ばせない（フォルダも変えない）
        self._folders()[folder_key] = str(p.parent)
        if folder_key == "input_image":
            self.recipe.input_image = p.name
            self.ed_img.setText(p.name)
        else:
            self.recipe.heatmap = p.name
            self.ed_ht.setText(p.name)
        self.main.folders_changed()
        # ②の一覧・④の表示だけ更新する。③をレシピから読み直す（main.steps_changed）と、
        # まだ「適用」していない入力（初期ストレス・レシピ名など）が元に戻ってしまう
        # （評価メモ 261021B-3：「前ステップ継承」を選んだ直後に参照…で画像を選ぶとプレビューが消える）
        self.main.steps_tab.refresh()
        self.main.run_tab.refresh_steps()
        self._refresh_previews()

    def _check_size(self, path: Path, folder_key: str) -> bool:
        """選んだ画像がシーケンスの基準サイズと同じか（2026-10-19 決定）。違えば警告して False。

        基準＝シーケンス内で最初に見つかる画像（ステップ順に入力画像→ヒートマップ）。
        動画・静止画の別は問わない。選び直している欄そのものは基準から除く。
        """
        size = engine.media_size(path)
        if size is None:
            QMessageBox.warning(self, t("cfg.size.title"), t("cfg.size.unreadable", name=path.name))
            return False
        ref = engine.sequence_reference_size(self.main.sequence, skip=(self.row, folder_key))
        if ref is None or ref.size == size:
            return True
        ref_recipe = self.main.sequence.recipes[ref.index]
        QMessageBox.warning(self, t("cfg.size.title"), t(
            "cfg.size.msg", sel=path.name, w=size[0], h=size[1],
            rw=ref.size[0], rh=ref.size[1], n=ref.index + 1, recipe=ref_recipe.recipe_name,
            field=t("cfg.input") if ref.field == "input_image" else t("cfg.heatmap"),
            name=ref.name))
        return False

    # -- ステップ種別 --
    def _on_kind_changed(self, _idx: int):
        if self.recipe is None:
            return
        # 種別は即時反映（②の一覧・④の表示を更新。③の他の未適用の入力は残す）
        self.recipe.step_type = STEP_TYPES[self.cmb_kind.currentIndex()]
        self._sync_kind_widgets()
        self.main.steps_tab.refresh()
        self.main.run_tab.refresh_steps()

    def _sync_kind_widgets(self, refresh: bool = True):
        """PQ評価ではヒートマップ（温度）と Sim条件のうち Aging 条件の欄を隠す。

        表示条件（DBV_NIT・DPK_ON・GADJ）は PQ評価でも使うので出したまま（フェーズF。2026-11-17 決定）。
        """
        is_eval = STEP_TYPES[self.cmb_kind.currentIndex()] == "eval"
        self._f1.setRowVisible(self._row_ht, not is_eval)
        self._f1.setRowVisible(self._row_ht_fixed, not is_eval)
        for w in self._aging_rows:
            self._f3.setRowVisible(w, not is_eval)
        self.lbl_kind_note.setText(
            t("cfg.kind.note_eval", v=engine.EVAL_TEMP_C) if is_eval else t("cfg.kind.note_aging"))
        if refresh and self.recipe is not None:
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

    # -- ヒートマップなし（固定温度）--
    def _sync_heatmap_widgets(self, tab_enabled: bool):
        fixed = self.cb_ht_fixed.isChecked()
        self.ed_ht.setEnabled(tab_enabled and not fixed)
        self.b_ht.setEnabled(tab_enabled and not fixed)
        self.sp_fixed_temp.setEnabled(tab_enabled and fixed)

    def _on_heatmap_mode_changed(self, _checked: bool):
        self._sync_heatmap_widgets(self.recipe is not None)
        self._refresh_previews()

    # -- previews --
    def refresh_prev_preview(self):
        """「前ステップの画像」だけを描き直す（③タブに切り替えたときに MainWindow から呼ぶ）。

        ④で前ステップを実行した後に③へ切り替えても「未実行です」のまま残っていた（2026-10-22 修正）。
        フォーム全体は読み直さない（未適用の入力を消さないため）。
        """
        if self.recipe is not None and self.row is not None:
            self._refresh_prev_preview(INIT_KEYS[self.cmb_init.currentIndex()])

    def _refresh_previews(self):
        r = self.recipe
        fi = self._folders()["input_image"]
        fh = self._folders()["heatmap"]
        self.pv_img.set_bgr(
            read_first_frame(str(Path(fi) / r.input_image)) if r.input_image else None)
        if STEP_TYPES[self.cmb_kind.currentIndex()] == "eval":
            self.pv_ht.set_message(t("cfg.pv.heatmap_eval"))
        elif self.cb_ht_fixed.isChecked():
            self.pv_ht.set_message(t("cfg.pv.heatmap_fixed", v=self.sp_fixed_temp.value()))
        else:
            self.pv_ht.set_bgr(
                read_first_frame(str(Path(fh) / r.heatmap)) if r.heatmap else None)
        # 前ステップの画像は、画面で選んでいる初期ストレス（未適用でも）に合わせて出す
        self._refresh_prev_preview(INIT_KEYS[self.cmb_init.currentIndex()])

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

    # -- sim csv --
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
        self._set_display_fields(s)
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
        self.cb_ht_fixed.setText(t("cfg.heatmap.fixed_cb"))
        self.l_ht_fixed_unit.setText(t("cfg.heatmap.fixed_unit"))
        self.l_kind.setText(t("cfg.kind"))
        cur_kind = self.cmb_kind.currentIndex()
        self.cmb_kind.blockSignals(True)
        self.cmb_kind.clear()
        self.cmb_kind.addItems([t(f"kind.{k}") for k in STEP_TYPES])
        self.cmb_kind.setCurrentIndex(max(cur_kind, 0))
        self.cmb_kind.blockSignals(False)
        self.b_img.setText(t("btn.browse"))
        self.b_ht.setText(t("btn.browse"))
        self.gb_init.setTitle(t("cfg.grp.init"))
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
        self.b_load_sim.setText(t("cfg.btn.load_csv"))
        self.b_save_sim.setText(t("cfg.btn.save_csv"))
        self.l_accel.setText(t("cfg.accel"))
        self.l_tl.setText(t("cfg.tmp_l"))
        self.l_th.setText(t("cfg.tmp_h"))
        self.l_aging.setText(t("cfg.aging_time"))
        self.l_dbv.setText(t("cfg.dbv_nit"))
        self.l_dpk.setText(t("cfg.dpk_on"))
        self.cb_dpk.setText(t("cfg.dpk_on.cb"))
        self.l_gadj.setText(t("cfg.gadj"))
        self.gb_sm.setTitle(t("cfg.grp.sm"))
        self.cb_sm.setText(t("cfg.sm.cb"))
        self.b_sm.setText(t("btn.browse"))
        self.b_sm_open.setText(t("panel.btn.open_excel"))
        for key, cb in self._future_cbs.items():
            cb.setText(t(key))
        self.btn_apply.setText(t("cfg.btn.apply"))
        self.pv_img.set_title(t("cfg.pv.input"))
        self.pv_ht.set_title(t("cfg.pv.heatmap"))
        self.load(self.recipe, self.row)
