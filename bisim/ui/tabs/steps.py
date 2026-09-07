"""② 実行ステップ（仕様 5-②）

レシピの一覧・追加/複製/削除・並べ替えのみ。**ファイル指定は不可**（詳細は③）。
NN（2桁通し番号）はリスト内位置から算出（``Sequence.recipe_number``）。
"""
from __future__ import annotations

import copy

from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from bisim.model import Recipe, Sequence
from bisim.ui.i18n import t
from bisim.ui.tabs._common import init_label, kind_label, recipe_status, set_recipe_status


class StepsTab(QWidget):
    H_KEYS = ["steps.h.num", "steps.h.nn", "steps.h.name", "steps.h.type", "steps.h.input",
              "steps.h.heatmap", "steps.h.init", "steps.h.status"]

    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.lbl_seq = QLabel(t("steps.seq_name"))
        self.ed_seq = QLineEdit()
        self.ed_seq.editingFinished.connect(self._on_seq_name)
        top.addWidget(self.lbl_seq)
        top.addWidget(self.ed_seq, 1)
        lay.addLayout(top)

        self.lbl_note = QLabel(t("steps.note"))
        self.lbl_note.setWordWrap(True)
        lay.addWidget(self.lbl_note)

        self.table = QTableWidget(0, len(self.H_KEYS))
        self.table.setHorizontalHeaderLabels([t(k) for k in self.H_KEYS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
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

    # -- helpers --
    def _recipes(self) -> list:
        return self.main.sequence.recipes

    def _unique_name(self, base: str) -> str:
        names = {r.recipe_name for r in self._recipes()}
        if base not in names:
            return base
        i = 2
        while f"{base}{i}" in names:
            i += 1
        return f"{base}{i}"

    # -- data ops --
    def _on_seq_name(self):
        self.main.sequence.sequence_name = self.ed_seq.text().strip() or "sequence"

    def _add(self):
        n = len(self._recipes()) + 1
        name = self._unique_name(t("steps.nth", n=n))
        self._recipes().append(Recipe(recipe_name=name))
        self.main.steps_changed()
        self._select_row(len(self._recipes()) - 1)

    def _dup(self):
        r = self.current_row()
        if r is None:
            return
        s = copy.deepcopy(self._recipes()[r])
        s.recipe_name = self._unique_name(s.recipe_name + t("steps.copy_suffix"))
        set_recipe_status(s, "pending")
        self._recipes().insert(r + 1, s)
        self.main.steps_changed()
        self._select_row(r + 1)

    def _del(self):
        r = self.current_row()
        if r is None:
            return
        del self._recipes()[r]
        self.main.steps_changed()

    def _move(self, d):
        r = self.current_row()
        if r is None:
            return
        j = r + d
        rs = self._recipes()
        if 0 <= j < len(rs):
            rs[r], rs[j] = rs[j], rs[r]
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
        rs = self._recipes()
        if self.ed_seq.text() != self.main.sequence.sequence_name:
            self.ed_seq.setText(self.main.sequence.sequence_name)
        self.table.blockSignals(True)
        self.table.setRowCount(len(rs))
        dash = t("kind.unknown")
        for i, r in enumerate(rs):
            values = [str(i + 1), Sequence.recipe_number(i), r.recipe_name,
                      kind_label(r), r.input_image or dash, r.heatmap or dash,
                      init_label(r), t(f"status.{_status_key(r)}")]
            for c, v in enumerate(values):
                self.table.setItem(i, c, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)
        if self.main.current_row is not None and self.main.current_row < len(rs):
            self._select_row(self.main.current_row)

    def retranslate(self):
        self.lbl_seq.setText(t("steps.seq_name"))
        self.lbl_note.setText(t("steps.note"))
        self.table.setHorizontalHeaderLabels([t(k) for k in self.H_KEYS])
        for key, (b, _slot) in self._btns.items():
            b.setText(t(key))
        self.refresh()


def _status_key(recipe) -> str:
    s = recipe_status(recipe)
    return {"pending": "pending", "running": "running",
            "done": "done", "stopped": "stopped_row"}.get(s, "pending")
