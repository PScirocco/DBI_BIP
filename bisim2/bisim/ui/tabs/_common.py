"""タブ共通の小物。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer
from PySide6.QtWidgets import QHBoxLayout, QWidget

from bisim import engine
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


class FileWatch(QObject):
    """指定したファイルが変わったら（Excel で保存したら）``callback(変わったパスのリスト)`` を呼ぶ（2026-11-18）。

    パネル設定のファイル（①）・サブモデルの差し替え（③）を、保存した時点で検査し直すのに使う。
    Excel は「一時ファイルに書いて元のファイルと入れ替える」ので、ファイルだけを見ていると監視が外れる。
    そのためファイルの入ったフォルダも見て、少し待ってから（連続する通知をまとめて）更新時刻・大きさを比べる。
    """

    def __init__(self, parent, callback, delay_ms: int = 400):
        super().__init__(parent)
        self._cb = callback
        self._paths: list = []
        self._keys: dict = {}
        self._w = QFileSystemWatcher(self)
        self._w.fileChanged.connect(self._kick)
        self._w.directoryChanged.connect(self._kick)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._fire)

    def set_paths(self, paths) -> None:
        """見るファイルを決め直す（今の更新時刻・大きさを基準にする）。"""
        new = [Path(p) for p in paths if p]
        if new != self._paths:
            self._paths = new
            self._keys = {p: engine.file_key(p) for p in new}
        self._rewatch()

    def _rewatch(self) -> None:
        old = self._w.files() + self._w.directories()
        if old:
            self._w.removePaths(old)
        want = set()
        for p in self._paths:
            if p.is_file():
                want.add(str(p))
            if p.parent.is_dir():
                want.add(str(p.parent))
        if want:
            self._w.addPaths(sorted(want))

    def _kick(self, _path) -> None:
        self._timer.start()

    def check_now(self) -> list:
        """変わったファイルを調べて、あれば callback を呼ぶ（テスト・通知の後の処理）。"""
        changed = [p for p in self._paths if engine.file_key(p) != self._keys.get(p)]
        for p in changed:
            self._keys[p] = engine.file_key(p)
        self._rewatch()                      # 入れ替えで外れた監視を付け直す
        if changed:
            self._cb(changed)
        return changed

    def _fire(self) -> None:
        self.check_now()
