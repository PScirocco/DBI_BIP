"""① フォルダ設定（仕様 5-①）

6種のフォルダをパス欄＋「参照…」で変更。③でファイルを選ぶと親フォルダがここへ反映される。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from bisim.paths import FOLDER_KEYS
from bisim.ui.i18n import t
from bisim.ui.tabs._common import folder_label, with_btn


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
        lay.addStretch(1)

    def _folders(self) -> dict:
        return self.main.sequence.folders

    def _on_edit(self, key):
        self._folders()[key] = self.edits[key].text().strip()

    def _browse(self, key):
        d = QFileDialog.getExistingDirectory(self, folder_label(key), self._folders()[key])
        if d:
            self._folders()[key] = d
            self.edits[key].setText(d)

    def refresh(self):
        for key, edit in self.edits.items():
            if edit.text() != self._folders()[key]:
                edit.setText(self._folders()[key])

    def retranslate(self):
        self.lbl_desc.setText(t("folders.desc"))
        for key in FOLDER_KEYS:
            self.row_labels[key].setText(folder_label(key))
            self.browse_btns[key].setText(t("btn.browse"))
