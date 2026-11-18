"""① フォルダ設定・パネル設定（仕様 5-①、フェーズF 手順5-2）

- 6種のフォルダをパス欄＋「参照…」で変更。③でファイルを選ぶと親フォルダがここへ反映される。
- パネル設定（シーケンスに1組。2026-11-17・11-18 決定）
  - 機種（劣化モデル）：サブモデル ``degparam_sm.csv``（モデルフォルダ）、マスターモデル mm の表（CSV 読込・保存）
  - 個体（BC設定）：``bcsetting.csv``（BC設定フォルダ）
  - ファイルを選ぶと検査し、結果を欄の下に出す（問題があっても選択は残す）。検査はキー名と行数・列数だけ
  - 「Excel で開く」：選んでいるファイルをそのまま既定のアプリ（Excel）で開く。
    複製はしない（ファイルの複製・名前はユーザーが決める。2026-11-18 担当者判断で「複製して Excel で開く」をやめた）
  - ファイルが変わったら（Excel で保存したら）自動で検査し直す（``FileWatch``）。「再検査」ボタンも残す
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from bisim import engine, naming, paramio
from bisim.model import MODEL_KEYS
from bisim.paths import FOLDER_KEYS
from bisim.ui.i18n import t
from bisim.ui.tabs._common import FileWatch, folder_label, with_btn

# パネル設定のファイル欄：種類 → (PanelConfig の属性名, フォルダのキー)
PANEL_FILES = {"sm": ("degparam_sm", "model"), "bcset": ("bcsetting", "bcset")}


def open_external(path) -> bool:
    """ファイルを Windows の既定のアプリ（CSV なら Excel）で開く。テストでは差し替える。"""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_in_excel(parent: QWidget, path: Path, logger) -> bool:
    """「Excel で開く」：ファイルをそのまま既定のアプリで開く（複製はしない。2026-11-18）。

    ①のパネル設定欄と③のサブモデルの差し替え欄で使う。開けたら True。
    """
    if not path.is_file():
        QMessageBox.warning(parent, t("panel.open.title"), t("panel.open.missing", path=str(path)))
        return False
    logger.action(f"パネル設定のファイルを開く: {path}")
    if not open_external(path):
        QMessageBox.warning(parent, t("panel.open.title"), t("panel.open.fail", path=str(path)))
        return False
    return True


class FoldersTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.edits: dict[str, QLineEdit] = {}
        self.row_labels: dict[str, QLabel] = {}
        self.browse_btns: dict[str, QPushButton] = {}
        self._check_cache: dict = {}          # (種類, file_key, band) -> PanelCheck
        self._watch = FileWatch(self, self._on_panel_files_changed)   # Excel で保存したら検査し直す

        host = QWidget()
        lay = QVBoxLayout(host)
        self.lbl_desc = QLabel(t("folders.desc"))
        self.lbl_desc.setWordWrap(True)
        lay.addWidget(self.lbl_desc)

        self.form = QFormLayout()
        for key in FOLDER_KEYS:
            edit = QLineEdit(self._folders()[key])
            edit.editingFinished.connect(lambda k=key: self._on_edit(k))
            btn = QPushButton(t("btn.browse"))
            btn.clicked.connect(lambda _=False, k=key: self._browse(k))
            lbl = QLabel(folder_label(key))
            self.form.addRow(lbl, with_btn(edit, btn))
            self.edits[key] = edit
            self.row_labels[key] = lbl
            self.browse_btns[key] = btn
        lay.addLayout(self.form)

        lay.addWidget(self._build_panel())
        lay.addStretch(1)

        # 縦に長くなったのでスクロール可にする（③と同じ。全タブの最小高さを押し上げないため）
        scroll = QScrollArea()
        scroll.setWidget(host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.refresh()

    # ------------------------------------------------------------------ #
    #  パネル設定の欄
    # ------------------------------------------------------------------ #
    def _build_panel(self) -> QWidget:
        self.gb_panel = QGroupBox(t("panel.grp"))
        v = QVBoxLayout(self.gb_panel)
        self.lbl_panel_desc = QLabel(t("panel.desc"))
        self.lbl_panel_desc.setWordWrap(True)
        self.lbl_panel_desc.setStyleSheet("color:#555;")
        v.addWidget(self.lbl_panel_desc)

        self.file_edits: dict[str, QLineEdit] = {}
        self.file_labels: dict[str, QLabel] = {}
        self.file_status: dict[str, QLabel] = {}
        self.file_browse: dict[str, QPushButton] = {}
        self.file_open: dict[str, QPushButton] = {}

        # ---- 機種（劣化モデル）----
        self.gb_type = QGroupBox(t("panel.grp.type"))
        tv = QVBoxLayout(self.gb_type)
        tv.addLayout(self._file_row("sm"))
        self.lbl_mm = QLabel(t("panel.mm"))
        tv.addWidget(self.lbl_mm)
        self.tbl_mm = QTableWidget(len(MODEL_KEYS), 3)
        self.tbl_mm.setHorizontalHeaderLabels(["R", "G", "B"])
        self.tbl_mm.setVerticalHeaderLabels(MODEL_KEYS)
        self.tbl_mm.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_mm.setMinimumHeight(170)
        self.tbl_mm.setMaximumHeight(190)
        self.tbl_mm.itemChanged.connect(self._on_mm_item_changed)
        tv.addWidget(self.tbl_mm)
        self.lbl_mm_csv = QLabel("")
        tv.addWidget(self.lbl_mm_csv)
        hb = QHBoxLayout()
        self.b_mm_load = QPushButton(t("cfg.btn.load_csv"))
        self.b_mm_load.clicked.connect(self._load_mm_csv)
        self.b_mm_save = QPushButton(t("cfg.btn.save_csv"))
        self.b_mm_save.clicked.connect(self._save_mm_csv)
        hb.addWidget(self.b_mm_load)
        hb.addWidget(self.b_mm_save)
        hb.addStretch(1)
        tv.addLayout(hb)
        v.addWidget(self.gb_type)

        # ---- 個体（BC設定）----
        self.gb_unit = QGroupBox(t("panel.grp.unit"))
        uv = QVBoxLayout(self.gb_unit)
        uv.addLayout(self._file_row("bcset"))
        v.addWidget(self.gb_unit)

        hb2 = QHBoxLayout()
        self.b_recheck = QPushButton(t("panel.btn.recheck"))
        self.b_recheck.clicked.connect(lambda: self.refresh_panel(force=True))
        hb2.addWidget(self.b_recheck)
        hb2.addStretch(1)
        v.addLayout(hb2)
        return self.gb_panel

    def _file_row(self, kind: str) -> QVBoxLayout:
        box = QVBoxLayout()
        row = QHBoxLayout()
        lbl = QLabel(t(f"panel.{kind}"))
        ed = QLineEdit()
        ed.setReadOnly(True)
        b = QPushButton(t("btn.browse"))
        b.clicked.connect(lambda _=False, k=kind: self._pick_panel_file(k))
        d = QPushButton(t("panel.btn.open_excel"))
        d.clicked.connect(lambda _=False, k=kind: self._open_in_excel(k))
        row.addWidget(lbl)
        row.addWidget(ed, 1)
        row.addWidget(b)
        row.addWidget(d)
        box.addLayout(row)
        st = QLabel("")
        st.setWordWrap(True)
        box.addWidget(st)
        self.file_labels[kind], self.file_edits[kind], self.file_status[kind] = lbl, ed, st
        self.file_browse[kind], self.file_open[kind] = b, d
        return box

    def _panel(self):
        return self.main.sequence.panel

    def _panel_path(self, kind: str) -> Path:
        attr, folder_key = PANEL_FILES[kind]
        return Path(self._folders()[folder_key]) / getattr(self._panel(), attr)

    def _check(self, kind: str, band_num=None, force=False) -> engine.PanelCheck:
        """ファイルの検査（同じファイル・同じ更新時刻なら前回の結果を使う）。"""
        path = self._panel_path(kind)
        key = (kind, engine.file_key(path), band_num)
        if force or key not in self._check_cache:
            try:
                chk = engine.check_bcset(path) if kind == "bcset" else engine.check_sm(path, band_num)
            except engine.EngineError as e:          # コア（source/main.py）を読めない
                chk = engine.PanelCheck(problems=[str(e)])
            self._check_cache[key] = chk
        return self._check_cache[key]

    def refresh_panel(self, force: bool = False) -> dict:
        """パネル設定の欄をシーケンスの内容で描き直し、ファイルを検査して結果を出す。

        戻り値 ``{"bcset": PanelCheck, "sm": PanelCheck}``。
        """
        if force:
            self._check_cache.clear()
        panel = self._panel()
        for kind, (attr, _fk) in PANEL_FILES.items():
            name = getattr(panel, attr)
            if self.file_edits[kind].text() != name:
                self.file_edits[kind].setText(name)
        bc = self._check("bcset")
        sm = self._check("sm", bc.band_num)
        for kind, chk in (("bcset", bc), ("sm", sm)):
            lab = self.file_status[kind]
            if chk.ok:
                lab.setText(t("panel.ok", n=chk.band_num))
                lab.setStyleSheet("color:#1b6e20;")
            else:
                lab.setText(t("panel.ng", problems="\n".join(chk.problems)))
                lab.setStyleSheet("color:#b00020;")
            lab.setToolTip(str(self._panel_path(kind)))
        self._fill_mm_table()
        self._watch.set_paths([self._panel_path(k) for k in PANEL_FILES])
        return {"bcset": bc, "sm": sm}

    def _on_panel_files_changed(self, changed: list):
        """パネル設定のファイルが変わった（Excel で保存した）→ 検査し直す。"""
        names = ", ".join(p.name for p in changed)
        self.main.logger.action(f"パネル設定のファイルが変わったため検査し直しました: {names}")
        self.refresh_panel()
        self.main.statusBar().showMessage(t("panel.recheck.auto", names=names), 8000)

    def _fill_mm_table(self):
        mm = self._panel().model_param
        self.tbl_mm.blockSignals(True)
        for row, key in enumerate(MODEL_KEYS):
            for c in range(3):
                self.tbl_mm.setItem(row, c, QTableWidgetItem(f"{mm[key][c]:g}"))
        self.tbl_mm.blockSignals(False)
        name = self._panel().model_param_csv
        self.lbl_mm_csv.setText(t("cfg.model_csv", name=name) if name else t("cfg.model_csv_none"))

    def _on_mm_item_changed(self, item: QTableWidgetItem):
        """mm の表は入力したらすぐシーケンスに反映（①のフォルダ欄と同じ。「適用」ボタンは無い）。"""
        key, c = MODEL_KEYS[item.row()], item.column()
        mm = self._panel().model_param
        try:
            val = float(item.text())
        except ValueError:
            QMessageBox.warning(self, t("cfg.err.title"), t("cfg.err.model"))
            self.tbl_mm.blockSignals(True)
            item.setText(f"{mm[key][c]:g}")
            self.tbl_mm.blockSignals(False)
            return
        if val != mm[key][c]:
            self.main.logger.param_change(f"mm {key}[{'RGB'[c]}]", mm[key][c], val)
            mm[key][c] = val

    def _pick_panel_file(self, kind: str):
        attr, folder_key = PANEL_FILES[kind]
        path, _ = QFileDialog.getOpenFileName(
            self, t(f"panel.{kind}"), self._folders()[folder_key], "CSV (*.csv)")
        if path:
            self._set_panel_file(kind, Path(path))

    def _set_panel_file(self, kind: str, p: Path, warn: bool = True):
        attr, folder_key = PANEL_FILES[kind]
        self._folders()[folder_key] = str(p.parent)
        setattr(self._panel(), attr, p.name)
        self.main.logger.action(f"パネル設定: {t(f'panel.{kind}')} = {p}")
        self.main.folders_changed()                    # フォルダ欄・パネル欄の描き直しと検査
        chk = self._check(kind, self._check("bcset").band_num if kind == "sm" else None)
        if warn and not chk.ok:
            QMessageBox.warning(self, t("panel.check.title"),
                                t("panel.check.msg", name=p.name, problems="\n".join(chk.problems)))

    def _open_in_excel(self, kind: str):
        """選んでいるファイルを Excel で開く（保存すると自動で検査し直す）。"""
        path = self._panel_path(kind)
        if open_in_excel(self, path, self.main.logger):
            self.main.statusBar().showMessage(t("panel.open.done", path=str(path)), 8000)

    def _load_mm_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("cfg.dlg.model_csv"), self._folders()["model"], "CSV (*.csv)")
        if not path:
            return
        try:
            m = paramio.read_model_csv(path)
        except (OSError, ValueError):
            QMessageBox.warning(self, t("cfg.load_fail.title"), t("cfg.load_fail.msg"))
            return
        self._folders()["model"] = str(Path(path).parent)
        self._panel().model_param = m
        self._panel().model_param_csv = Path(path).name
        self.main.logger.io("in", Path(path).name)
        self.main.folders_changed()

    def _save_mm_csv(self):
        start = str(Path(self._folders()["model"]) /
                    naming.input_name(self.main.sequence.sequence_name, "model-param"))
        path, _ = QFileDialog.getSaveFileName(self, t("cfg.dlg.model_csv"), start, "CSV (*.csv)")
        if not path:
            return
        paramio.write_model_csv(path, self._panel().model_param)
        self._panel().model_param_csv = Path(path).name
        self._folders()["model"] = str(Path(path).parent)
        self.main.logger.io("out", Path(path).name)
        self.main.folders_changed()
        self.main.statusBar().showMessage(t("status.saved", path=path), 3000)

    # ------------------------------------------------------------------ #
    #  フォルダ
    # ------------------------------------------------------------------ #
    def _folders(self) -> dict:
        return self.main.sequence.folders

    def _on_edit(self, key):
        self._folders()[key] = self.edits[key].text().strip()
        self.main.persist_folders()
        if key in ("bcset", "model"):
            self.refresh_panel()

    def _browse(self, key):
        d = QFileDialog.getExistingDirectory(self, folder_label(key), self._folders()[key])
        if d:
            self._folders()[key] = d
            self.edits[key].setText(d)
            self.main.persist_folders()
            if key in ("bcset", "model"):
                self.refresh_panel()

    def refresh(self):
        for key, edit in self.edits.items():
            if edit.text() != self._folders()[key]:
                edit.setText(self._folders()[key])
        self.refresh_panel()

    def retranslate(self):
        self.lbl_desc.setText(t("folders.desc"))
        for key in FOLDER_KEYS:
            self.row_labels[key].setText(folder_label(key))
            self.browse_btns[key].setText(t("btn.browse"))
        self.gb_panel.setTitle(t("panel.grp"))
        self.lbl_panel_desc.setText(t("panel.desc"))
        self.gb_type.setTitle(t("panel.grp.type"))
        self.gb_unit.setTitle(t("panel.grp.unit"))
        for kind in PANEL_FILES:
            self.file_labels[kind].setText(t(f"panel.{kind}"))
            self.file_browse[kind].setText(t("btn.browse"))
            self.file_open[kind].setText(t("panel.btn.open_excel"))
        self.lbl_mm.setText(t("panel.mm"))
        self.b_mm_load.setText(t("cfg.btn.load_csv"))
        self.b_mm_save.setText(t("cfg.btn.save_csv"))
        self.b_recheck.setText(t("panel.btn.recheck"))
        self.refresh_panel()
