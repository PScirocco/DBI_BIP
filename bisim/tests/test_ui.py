"""UI（フェーズC / T6〜T7）の headless テスト。

``QT_QPA_PLATFORM=offscreen`` で MainWindow を生成し、タブ構成・言語切替・
シーケンス I/O・エンジン結線（小さな実データ実行）を確認する。
PySide6 が無い環境ではスキップ（pass 扱い）。
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from bisim.paths import SOURCE_DIR

_COMMON = SOURCE_DIR / "dbi_common"
_MOVIE, _MOVIE_HT = "mov_001_480x270.mp4", "mov_ht_001_480x270.mp4"
_STILL, _STILL_HT = "eval_img.png", "eval_img_ht.png"


def _pyside_ok() -> bool:
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        return False


_APP = None


def _app():
    global _APP
    from PySide6.QtWidgets import QApplication
    from bisim.ui.theme import setup_matplotlib
    if _APP is None:
        setup_matplotlib()
        _APP = QApplication.instance() or QApplication([])
    return _APP


def _new_window():
    from bisim.ui.main_window import MainWindow
    _app()
    return MainWindow()


def _movie_recipe(name="aging01"):
    from bisim.model import Recipe
    return Recipe(recipe_name=name, input_image=_MOVIE, heatmap=_MOVIE_HT)


# --------------------------------------------------------------------------- #
def test_window_builds_five_tabs():
    if not _pyside_ok():
        return
    win = _new_window()
    assert win.tabs.count() == 5
    # 既定は英語（仕様 2）
    assert win.tabs.tabText(0).strip().startswith("1")
    win.close()


def test_language_switch_retranslates():
    if not _pyside_ok():
        return
    from bisim.ui import i18n
    win = _new_window()
    win._set_lang("ja")
    assert "フォルダ" in win.tabs.tabText(0)
    win._set_lang("en")
    assert "Folders" in win.tabs.tabText(0)
    i18n.LANG = "en"
    win.close()


def test_add_edit_recipe_via_tabs():
    if not _pyside_ok():
        return
    win = _new_window()
    win.steps_tab._add()
    assert len(win.sequence.recipes) == 1
    assert win.current_row == 0
    cfg = win.config_tab
    cfg.ed_name.setText("aging_A")
    cfg.sp_accel.setValue(12345.0)
    cfg.tbl_model.item(0, 0).setText("1.9")
    assert cfg._collect_into_recipe()
    r = win.sequence.recipes[0]
    assert r.recipe_name == "aging_A"
    assert r.sim_param["ACCEL_RATIO"] == 12345.0
    assert r.model_param["N"][0] == 1.9
    win.close()


def test_folders_tab_reflects_sequence():
    if not _pyside_ok():
        return
    win = _new_window()
    win.sequence.folders["output"] = r"C:\tmp\out"
    win.folders_changed()
    assert win.folders_tab.edits["output"].text() == r"C:\tmp\out"
    win.folders_tab.edits["model"].setText(r"C:\tmp\model")
    win.folders_tab._on_edit("model")
    assert win.sequence.folders["model"] == r"C:\tmp\model"
    win.close()


def test_sequence_save_load_roundtrip_via_window():
    if not _pyside_ok():
        return
    win = _new_window()
    win.sequence.sequence_name = "SEQ_T"
    win.sequence.recipes = [_movie_recipe("a"), _movie_recipe("b")]
    win.sequence.recipes[1].init_stress = "prev"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.seq.json"
        win.sequence.save(p)
        win._seq_path = None
        from bisim.model import Sequence
        win.sequence = Sequence.load(p)
        win.steps_changed()
        assert [r.recipe_name for r in win.sequence.recipes] == ["a", "b"]
        assert win.steps_tab.table.rowCount() == 2
        assert win.run_tab.cmb_sel.count() == 2
    win.close()


def test_run_small_sequence_end_to_end():
    if not _pyside_ok():
        return
    win = _new_window()
    win._max_frames = 3
    with tempfile.TemporaryDirectory() as d:
        win.sequence.sequence_name = "SEQ_E2E"
        win.sequence.folders["output"] = d
        win.sequence.recipes = [_movie_recipe("aging01")]
        win.steps_changed()
        win.run_steps("all")
        deadline = time.time() + 90
        while win.worker is not None and time.time() < deadline:
            _app().processEvents()
            time.sleep(0.02)
        assert win.worker is None, "worker が終了しなかった"
        assert 1 in win.results
        entry = win.results[1]
        assert Path(entry.outputs["movie"]).exists()
        assert Path(entry.outputs["deg_r"]).exists()
        # 結果タブ: 選択 → プレビュー/マップが例外なく描ける
        win.results_tab.add_result(1)
        win.results_tab.view_deg.reload()
        win.results_tab.view_stat.reload()
        win.close()   # tempdir を消す前に VideoCapture を解放
