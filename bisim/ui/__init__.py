"""bisim.ui — 本番GUI（PySide6、5タブ）

`docs/GUI仕様.md` 2章の構成。エントリは :func:`run`（``python -m bisim`` から呼ばれる）。
UI シェルは :mod:`bisim.ui.main_window`、各タブは :mod:`bisim.ui.tabs`。
"""
from __future__ import annotations


def run(argv=None) -> int:
    """GUI を起動する。PySide6 が無い環境では説明を出して 1 を返す。"""
    try:
        from bisim.ui.main_window import run as _run
    except ImportError as e:  # PySide6 未インストール等
        print(f"GUI を起動できません（{type(e).__name__}: {e}）")
        print("  pip install -r bisim/requirements.txt を実行してください。")
        return 1
    return _run(argv)
