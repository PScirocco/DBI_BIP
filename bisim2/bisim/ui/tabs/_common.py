"""タブ共通の小物。"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from bisim.model import Recipe
from bisim.ui.i18n import t


def with_btn(edit, btn) -> QWidget:
    """行エディット＋「参照…」ボタンを横並びにした 1 セル。"""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(edit, 1)
    h.addWidget(btn)
    return w


def kind_label(recipe: Recipe) -> str:
    return t(f"kind.{recipe.kind}")


def folder_label(key: str) -> str:
    return t(f"folder.{key}")


def init_label(recipe: Recipe) -> str:
    return t(f"init.{recipe.init_stress}")


# -- 実行状態はランタイムのみ（Config には保存しない。仕様 3.2）--
def recipe_status(recipe: Recipe) -> str:
    """"pending" | "running" | "done" | "stopped"。"""
    return getattr(recipe, "_status", "pending")


def set_recipe_status(recipe: Recipe, status: str) -> None:
    recipe._status = status
