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

# アプリConfig をテスト用の一時ファイルに隔離（リポジトリ直下の bisim_app.json を汚さない、
# フォルダ編集テストの値が後続テストへ漏れない）
import tempfile as _tf  # noqa: E402

_TEST_APP_CFG = Path(_tf.mkdtemp(prefix="bisim_test_")) / "bisim_app.json"
try:
    import bisim.ui.main_window as _mw
    _mw.APP_CONFIG_PATH = _TEST_APP_CFG
except Exception:  # noqa: BLE001  (PySide6 なし)
    pass

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
    try:
        _TEST_APP_CFG.unlink()          # 各ウィンドウは既定値から始める（テスト間で漏らさない）
    except OSError:
        pass
    return MainWindow()


def _close(win):
    """ウィンドウを確実に破棄する（selftest は 1 プロセスで多数生成するため、
    Qt/cv2/i18n のリソースを溜めない）。"""
    import gc

    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    try:
        win.close()                       # closeEvent が i18n / logger listener を解除
        win.setParent(None)
        win.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        _app().processEvents()
        _app().processEvents()
    except Exception:  # noqa: BLE001
        pass
    gc.collect()


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
    _close(win)


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
    _close(win)


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
    assert cfg._collect_into_recipe()
    r = win.sequence.recipes[0]
    assert r.recipe_name == "aging_A"
    assert r.sim_param["ACCEL_RATIO"] == 12345.0
    assert not hasattr(cfg, "tbl_model")            # mm の表は①へ移した（フェーズF）
    _close(win)


def test_run_tab_shows_movie_info_for_selected_step():
    """評価メモ #1: ④Runタブに動画のフレーム数・ACCEL_RATIO換算の1周回時間を表示する。"""
    if not _pyside_ok():
        return
    win = _new_window()
    win.sequence.folders["input_image"] = str(_COMMON)
    win.sequence.folders["heatmap"] = str(_COMMON)
    win.sequence.recipes = [_movie_recipe("aging01")]
    win.sequence.recipes[0].sim_param["ACCEL_RATIO"] = 1.0
    win.steps_changed()
    win.run_tab.cmb_sel.setCurrentIndex(0)
    text = win.run_tab.lbl_movie_info.text()
    assert "405" in text        # mov_001_480x270.mp4 の総フレーム数
    assert "00h 00m 13s" in text or "00h 00m 14s" in text   # native長さ（fps由来で丸め差あり）
    assert "0 (unlimited)" in text and "unlimited" in text   # 既定 AGING_TIME=0

    # ③で AGING_TIME を変えて「この設定を適用」すると、④の表示（設定値・判定）が追従する
    cfg = win.config_tab
    win.steps_tab._select_row(0)
    cfg.sp_aging.setValue(5.0)      # 1周回(約13.5秒)より短い → 打切り
    cfg._apply()
    text = win.run_tab.lbl_movie_info.text()
    assert "00h 00m 05s" in text and "truncat" in text

    cfg.sp_aging.setValue(100.0)    # 1周回より十分長い → 周回
    cfg._apply()
    text = win.run_tab.lbl_movie_info.text()
    assert "00h 01m 40s" in text and "loop" in text

    # PQ評価ステップは「Aging しない」の表示（動画でも静止画でも）
    from bisim.model import Recipe
    from bisim.ui.i18n import t
    win.sequence.recipes = [Recipe(recipe_name="pq01", input_image=_STILL, heatmap=_STILL_HT)]
    win.steps_changed()
    win.run_tab.cmb_sel.setCurrentIndex(0)
    assert win.run_tab.lbl_movie_info.text() == t("run.movie_info_eval")
    win.sequence.recipes = [Recipe(recipe_name="pq02", input_image=_MOVIE, step_type="eval")]
    win.steps_changed()
    win.run_tab.cmb_sel.setCurrentIndex(0)
    assert win.run_tab.lbl_movie_info.text() == t("run.movie_info_eval")

    # 静止画 Aging は fps=1 の見積り（1フレーム = 1秒 × ACCEL_RATIO）
    r = Recipe(recipe_name="age01", input_image=_STILL, step_type="aging")
    r.sim_param["ACCEL_RATIO"] = 60.0
    r.sim_param["AGING_TIME"] = 600.0
    win.sequence.recipes = [r]
    win.steps_changed()
    win.run_tab.cmb_sel.setCurrentIndex(0)
    text = win.run_tab.lbl_movie_info.text()
    assert "00h 01m 00s" in text and "10" in text and "00h 10m 00s" in text
    _close(win)


def test_step_type_selector_switches_settings():
    """③ステップ種別を手動で選ぶ。PQ評価ではヒートマップ・Sim条件（Aging条件）を隠す。"""
    if not _pyside_ok():
        return
    from bisim.ui.i18n import t
    win = _new_window()
    win.steps_tab._add()
    cfg = win.config_tab
    r = win.sequence.recipes[0]
    assert r.step_type == "aging" and cfg.cmb_kind.currentIndex() == 0
    assert cfg.gb_sim.isVisibleTo(cfg) and cfg._f1.isRowVisible(cfg._row_ht)

    cfg.ed_name.setText("pq_A")             # 未適用の入力が種別変更で消えないこと
    cfg.cmb_kind.setCurrentIndex(1)         # → PQ評価（即時反映）
    assert r.step_type == "eval"
    # Sim条件のうち Aging 条件は隠し、表示条件（DBV_NIT・DPK_ON・GADJ）は出したまま（フェーズF）
    assert cfg.gb_sim.isVisibleTo(cfg)
    assert not any(cfg._f3.isRowVisible(w) for w in cfg._aging_rows)
    assert cfg._f3.isRowVisible(cfg.sp_dbv) and cfg._f3.isRowVisible(cfg.cb_dpk)
    assert not cfg._f1.isRowVisible(cfg._row_ht) and not cfg._f1.isRowVisible(cfg._row_ht_fixed)
    assert cfg.ed_name.text() == "pq_A"
    assert win.steps_tab.table.item(0, 3).text() == t("kind.eval")    # ②の Type 列
    assert cfg._collect_into_recipe() and r.step_type == "eval" and r.recipe_name == "pq_A"

    cfg.cmb_kind.setCurrentIndex(0)         # → Aging に戻すと欄が戻る
    assert r.step_type == "aging" and all(cfg._f3.isRowVisible(w) for w in cfg._aging_rows)
    assert win.steps_tab.table.item(0, 3).text() == t("kind.aging")
    _close(win)


def test_pick_file_rejects_different_image_size():
    """画像サイズ：シーケンスの基準（最初に選んだ画像）と違う画像は警告して選ばせない。"""
    if not _pyside_ok():
        return
    import cv2
    import numpy as np
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    win = _new_window()
    warned = []
    orig_o, orig_w = QFileDialog.getOpenFileName, QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[2] if len(a) > 2 else ""))
    try:
        with tempfile.TemporaryDirectory() as d:
            small = Path(d) / "small_240x512.png"
            cv2.imencode(".png", np.zeros((512, 240, 3), np.uint8))[1].tofile(str(small))
            win.sequence.folders["input_image"] = str(_COMMON)
            win.sequence.folders["heatmap"] = str(_COMMON)
            win.steps_tab._add()
            win.steps_tab._add()
            cfg = win.config_tab

            def pick(row, key, path):
                win.steps_tab._select_row(row)
                QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(path), ""))
                cfg._pick_file(key)

            pick(0, "input_image", _COMMON / _MOVIE)          # 最初の画像（480x270）＝基準
            assert win.sequence.recipes[0].input_image == _MOVIE and not warned
            pick(1, "input_image", _COMMON / _STILL)          # 静止画でも同サイズなら可
            assert win.sequence.recipes[1].input_image == _STILL and not warned
            pick(1, "input_image", small)                     # サイズ違い → 選択不可
            assert win.sequence.recipes[1].input_image == _STILL
            assert len(warned) == 1 and "240" in warned[0] and "480" in warned[0]
            assert win.sequence.folders["input_image"] == str(_COMMON)   # フォルダも変えない
            pick(0, "heatmap", small)                         # ヒートマップも同じ判定
            assert win.sequence.recipes[0].heatmap == "" and len(warned) == 2
            pick(0, "heatmap", _COMMON / _MOVIE_HT)
            assert win.sequence.recipes[0].heatmap == _MOVIE_HT and len(warned) == 2
            _close(win)
    finally:
        QFileDialog.getOpenFileName, QMessageBox.warning = orig_o, orig_w


def test_previous_step_preview_wording():
    """③プレビューの文言は「前ステップの画像」（議事録 261015 の指摘3）。"""
    from bisim.ui import i18n
    from bisim.ui.i18n import t
    old = i18n.LANG
    try:
        i18n.LANG = "ja"
        assert t("cfg.pv.prev") == "前ステップの画像"
        assert t("cfg.pv.prev_named", name="x.mp4") == "前ステップの画像（x.mp4）"
        i18n.LANG = "en"
        assert t("cfg.pv.prev") == "Previous step image"
    finally:
        i18n.LANG = old


def test_aging_time_field_via_config_tab():
    if not _pyside_ok():
        return
    win = _new_window()
    win.steps_tab._add()
    cfg = win.config_tab
    assert cfg.sp_aging.value() == 0.0 and cfg.sp_aging.decimals() == 0   # 既定=無制限・整数秒
    cfg.sp_aging.setValue(2500.0)
    assert cfg._collect_into_recipe()
    assert win.sequence.recipes[0].sim_param["AGING_TIME"] == 2500.0
    _close(win)


def test_fixed_heatmap_checkbox_via_config_tab():
    if not _pyside_ok():
        return
    win = _new_window()
    win.steps_tab._add()
    cfg = win.config_tab
    assert cfg.ed_ht.isEnabled() and not cfg.sp_fixed_temp.isEnabled()   # 既定は file モード
    cfg.cb_ht_fixed.setChecked(True)
    cfg.sp_fixed_temp.setValue(45.0)
    assert not cfg.ed_ht.isEnabled() and not cfg.b_ht.isEnabled()
    assert cfg.sp_fixed_temp.isEnabled()
    assert cfg._collect_into_recipe()
    r = win.sequence.recipes[0]
    assert r.heatmap_mode == "fixed" and r.fixed_temp_c == 45.0
    _close(win)


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
    _close(win)


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
    _close(win)


def test_save_sequence_name_matches_filename(monkey_qfd=None):
    if not _pyside_ok():
        return
    from PySide6.QtWidgets import QFileDialog
    win = _new_window()
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # Save As: 選んだファイル名 → シーケンス名
        orig = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(
            lambda *a, **k: (str(d / "My Seq A.seq.json"), ""))
        try:
            win.sequence.sequence_name = "sequence"
            win.sequence.recipes = [_movie_recipe("a")]
            win.save_sequence(as_new=True)
            assert win.sequence.sequence_name == "My-Seq-A"        # サニタイズ
            assert win._seq_path.name == "My-Seq-A.seq.json"
            assert win._seq_path.exists()
            # 保存: 名前を変えると旧ファイルをリネーム
            old = win._seq_path
            win.sequence.sequence_name = "renamed_B"
            win.save_sequence()
            assert win._seq_path.name == "renamed-B.seq.json"
            assert win._seq_path.exists() and not old.exists()
            # 名前を付けて保存：元のファイルは残す（評価メモ 261021B-1）
            prev = win._seq_path
            QFileDialog.getSaveFileName = staticmethod(
                lambda *a, **k: (str(d / "copy C.seq.json"), ""))
            win.save_sequence(as_new=True)
            assert win._seq_path.name == "copy-C.seq.json" and win._seq_path.exists()
            assert prev.exists()                                    # 元の renamed-B も残る
            assert win.sequence.sequence_name == "copy-C"
        finally:
            QFileDialog.getSaveFileName = orig
    _close(win)


def test_pick_file_keeps_unapplied_edits():
    """③で「参照…」からファイルを選んでも、未適用の入力（初期ストレス・レシピ名）が戻らない。
    評価メモ 261021B-3：「前ステップ継承」を選んだ直後に画像を選ぶと、前ステップの画像が消えていた。"""
    if not _pyside_ok():
        return
    from PySide6.QtWidgets import QFileDialog
    from bisim.ui.i18n import t
    win = _new_window()
    orig = QFileDialog.getOpenFileName
    try:
        with tempfile.TemporaryDirectory() as d:
            win.sequence.sequence_name = "PICK"
            win.sequence.folders["output"] = d
            win.sequence.folders["input_image"] = str(_COMMON)
            win.steps_tab._add()
            win.steps_tab._add()
            r1 = win.sequence.recipes[0]
            r1.input_image = _MOVIE
            # 前ステップの出力（動画）を置いておく → 「前ステップの画像」に出る
            import shutil
            from bisim import naming
            shutil.copy(_COMMON / _MOVIE,
                        Path(d) / naming.output_name("PICK", "01", r1.recipe_name, "movie", ext="mp4"))
            win.steps_tab._select_row(1)
            cfg = win.config_tab
            cfg.ed_name.setText("eval-A")                    # 未適用
            cfg.cmb_init.setCurrentIndex(1)                  # 前ステップ継承（未適用）
            assert cfg.pv_prev._pixmap is not None           # 前ステップの画像が出ている
            QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(_COMMON / _STILL), ""))
            cfg._pick_file("input_image")
            assert win.sequence.recipes[1].input_image == _STILL
            assert cfg.cmb_init.currentIndex() == 1          # 初期ストレスは戻らない
            assert cfg.ed_name.text() == "eval-A"            # レシピ名も戻らない
            assert cfg.pv_prev._pixmap is not None           # 前ステップの画像も消えない
            assert win.steps_tab.table.item(1, 4).text() == _STILL   # ②の一覧には反映
            _close(win)
    finally:
        QFileDialog.getOpenFileName = orig


def test_prev_step_preview_refreshes_when_config_tab_shown():
    """前ステップを実行した後、③タブに切り替えると「前ステップの画像」が表示される
    （以前は「未実行です」のまま残っていた）。未適用の入力は消えない。"""
    if not _pyside_ok():
        return
    import shutil
    from bisim import naming
    from bisim.ui.i18n import t
    win = _new_window()
    with tempfile.TemporaryDirectory() as d:
        win.sequence.sequence_name = "SHOW"
        win.sequence.folders["output"] = d
        win.sequence.folders["input_image"] = str(_COMMON)
        win.steps_tab._add()
        win.steps_tab._add()
        r1 = win.sequence.recipes[0]
        win.steps_tab._select_row(1)
        cfg = win.config_tab
        cfg.cmb_init.setCurrentIndex(1)                          # 前ステップ継承（未適用）
        cfg.ed_name.setText("eval-B")                            # 未適用
        assert cfg.pv_prev._pixmap is None                       # 前ステップ未実行
        win.tabs.setCurrentWidget(win.run_tab)
        _app().processEvents()
        # 前ステップの実行が終わって出力ができた状態
        shutil.copy(_COMMON / _MOVIE,
                    Path(d) / naming.output_name("SHOW", "01", r1.recipe_name, "movie", ext="mp4"))
        win.tabs.setCurrentWidget(win.config_tab)                # ③へ切り替えるだけ
        _app().processEvents()
        assert cfg.pv_prev._pixmap is not None                   # 表示される
        assert cfg.cmb_init.currentIndex() == 1 and cfg.ed_name.text() == "eval-B"
        _close(win)


def test_stat_map_scale_minmax_toggle():
    """累積時間マップは「0〜面内最大」（従来・既定）と「面内最小〜面内最大」を切り替えられる
    （Excel No.9／10/15 MTG 指摘4。2026-10-23）。輝度残存率マップは「0〜1」と「面内最小〜最大」（フェーズF 5-4）。"""
    if not _pyside_ok():
        return
    import numpy as np
    from bisim.ui.i18n import t
    from bisim.ui.main_window import ResultEntry
    win = _new_window()
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # 前ステップから引き継いで全面が 2.0 底上げされ、その上に 2.0〜3.0 のムラがある想定
            a = np.array([[2.0, 2.5], [3.0, 2.0]])
            outputs = {}
            for c in "rgb":
                np.savetxt(d / f"stat_{c}.csv", a, delimiter=",")
                np.savetxt(d / f"deg_{c}.csv", np.array([[1.0, 0.5], [1.0, 1.0]]), delimiter=",")
                outputs[f"stat_{c}"], outputs[f"deg_{c}"] = d / f"stat_{c}.csv", d / f"deg_{c}.csv"
            win.results[1] = ResultEntry(nn=1, recipe_name="x", is_movie=False, outputs=outputs)
            win.results_tab.add_result(1)
            vs, vd = win.results_tab.view_stat, win.results_tab.view_deg
            assert vd.scale_key() == "unit"                      # 輝度残存率マップは 0〜1 が既定
            assert vs.scale_key() == "zero"                      # 既定は従来どおり
            cap = {}
            vs.canvas.show_channel = lambda arr, ch, title="": cap.update(arr=arr.copy(), title=title)
            vs.cmb_ch.setCurrentIndex(0)
            vs.reload()
            assert np.allclose(cap["arr"], 1.0 - a / 3.0)        # 0〜最大：最小の画素も暗め（1-2/3）
            vs.cmb_scale.setCurrentIndex(1)                      # 面内最小〜最大に切替（自動で再描画）
            assert vs.scale_key() == "minmax"
            assert np.allclose(cap["arr"], 1.0 - (a - 2.0) / 1.0)  # 最小→白(1)、最大→黒(0)
            assert cap["arr"][0, 0] == 1.0 and cap["arr"][1, 0] == 0.0
            assert "2" in cap["title"] and "3" in cap["title"]
            # 面内が一様なら全面白（0 割りしない）
            assert np.all(vs._norm(np.full((2, 2), 5.0), 5.0, 5.0) == 1.0)
            # RGB 合成も各色ごとの面内最小〜最大
            vs.cmb_ch.setCurrentIndex(3)
            vs.canvas.show_rgb = lambda rgb, title="": cap.update(rgb=rgb.copy(), title=title)
            vs.reload()
            assert cap["rgb"][0, 0, 0] == 1.0 and cap["rgb"][1, 0, 2] == 0.0
            assert cap["title"].count("2–3") == 3
            # 言語を切り替えても選択は保たれる
            from bisim.ui import i18n
            i18n.set_lang("ja")
            assert vs.scale_key() == "minmax" and vs.cmb_scale.currentText() == t("map.scale.minmax")
            i18n.set_lang("en")
    finally:
        _close(win)


def test_editing_locked_while_running():
    """実行中（一時停止中を含む）は ①②③タブとファイル操作が使えない。終われば戻る（2026-10-22）。"""
    if not _pyside_ok():
        return
    win = _new_window()
    win._max_frames = 3
    with tempfile.TemporaryDirectory() as d:
        win.sequence.sequence_name = "LOCK"
        win.sequence.folders.update(output=d, input_image=str(_COMMON), heatmap=str(_COMMON))
        win.sequence.recipes = [_movie_recipe("aging01")]
        win.steps_changed()
        tabs = win.tabs
        idx = [tabs.indexOf(w) for w in (win.folders_tab, win.steps_tab, win.config_tab)]
        acts = (win.act_open, win.act_save, win.act_save_as, win.act_recipe_load, win.act_recipe_save)
        assert all(tabs.isTabEnabled(i) for i in idx) and all(a.isEnabled() for a in acts)
        win.run_steps("all")
        # 終了の通知はイベントループで届くので、ここではまだ実行中扱い
        assert not any(tabs.isTabEnabled(i) for i in idx)
        assert not any(a.isEnabled() for a in acts)
        assert tabs.isTabEnabled(tabs.indexOf(win.run_tab))
        assert tabs.isTabEnabled(tabs.indexOf(win.results_tab))
        _wait_idle(win)
        assert all(tabs.isTabEnabled(i) for i in idx) and all(a.isEnabled() for a in acts)
        _close(win)


def test_reordering_steps_with_stop_state_asks_and_discards():
    """停止中のステップがあるときに②で削除・複製・並べ替えをすると確認が出る。
    「いいえ」なら何もしない。「はい」なら停止状態（と _stops/ の実体）を破棄して続ける（2026-10-22）。"""
    if not _pyside_ok():
        return
    from PySide6.QtWidgets import QMessageBox
    from bisim.model import Recipe, StopState
    win = _new_window()
    orig_q = QMessageBox.question
    try:
        with tempfile.TemporaryDirectory() as d:
            seq_path = Path(d) / "S.seq.json"
            win._seq_path = seq_path
            win.sequence.folders["output"] = d
            win.sequence.recipes = [Recipe(recipe_name="first", input_image=_MOVIE),
                                    Recipe(recipe_name="second", input_image=_MOVIE)]
            win.steps_changed()
            ckpt = Path(d) / "_stops" / "S_02_second"
            ckpt.mkdir(parents=True)
            (ckpt / "stat_r.csv").write_text("0")
            win._set_stop(2, StopState(recipe_name="second", frames_done=3, frames_total=10,
                                       aging_seconds=1.0, is_movie=True, timestamp="261022-1000",
                                       dir="_stops/S_02_second"))
            win.steps_tab._select_row(0)

            QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
            win.steps_tab._del()
            assert [r.recipe_name for r in win.sequence.recipes] == ["first", "second"]   # 何もしない
            assert 2 in win._stopped_states and ckpt.exists()
            win.steps_tab._move(1)
            assert [r.recipe_name for r in win.sequence.recipes] == ["first", "second"]

            QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
            win.steps_tab._select_row(0)
            win.steps_tab._del()
            assert [r.recipe_name for r in win.sequence.recipes] == ["second"]
            assert not win._stopped_states and not win.sequence.stops        # 停止状態は破棄
            assert not ckpt.exists()                                         # 途中結果も削除
            assert seq_path.exists()                                         # シーケンスにも反映
            # 停止状態が無ければ確認は出ない
            QMessageBox.question = staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("確認が出た")))
            win.steps_tab._select_row(0)
            win.steps_tab._dup()
            assert len(win.sequence.recipes) == 2
            # 末尾への追加は既存ステップの番号を変えないので、停止中でも確認しない
            win._set_stop(1, StopState(recipe_name="second", frames_done=1, frames_total=2,
                                       aging_seconds=1.0, is_movie=True, timestamp="261022-1000",
                                       dir="_stops/none"))
            win.steps_tab._add()
            assert len(win.sequence.recipes) == 3 and 1 in win._stopped_states
            _close(win)
    finally:
        QMessageBox.question = orig_q


def test_run_tab_time_labels_follow_language_switch():
    """④の「計算時間」「Aging時間」も言語切替で描き直される。"""
    if not _pyside_ok():
        return
    from bisim.ui import i18n
    from bisim.ui.i18n import t
    win = _new_window()
    try:
        win.run_tab.on_calc_time(12.5)
        win.run_tab.on_aging_time("01h 00m 00s")
        i18n.set_lang("ja")
        assert win.run_tab.lbl_calc.text() == t("run.calc_time", s=12.5)
        assert win.run_tab.lbl_aging.text() == t("run.aging_time", v="01h 00m 00s")
        i18n.set_lang("en")
        assert win.run_tab.lbl_calc.text() == t("run.calc_time", s=12.5)
        assert "01h 00m 00s" in win.run_tab.lbl_aging.text()
    finally:
        i18n.set_lang("en")
        _close(win)


def test_sim_param_csv_roundtrip_via_config_tab():
    if not _pyside_ok():
        return
    from PySide6.QtWidgets import QFileDialog
    win = _new_window()
    win.steps_tab._add()
    cfg = win.config_tab
    cfg.sp_accel.setValue(4242.0)
    cfg.sp_th.setValue(71.0)
    with tempfile.TemporaryDirectory() as d:
        p = str(Path(d) / "aging_sim.csv")
        orig_s, orig_o = QFileDialog.getSaveFileName, QFileDialog.getOpenFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (p, ""))
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (p, ""))
        try:
            cfg._save_sim_csv()
            assert Path(p).exists()
            assert win.sequence.recipes[0].sim_param_csv == "aging_sim.csv"
            cfg.sp_accel.setValue(1.0)
            cfg._load_sim_csv()
            assert cfg.sp_accel.value() == 4242.0 and cfg.sp_th.value() == 71.0
        finally:
            QFileDialog.getSaveFileName, QFileDialog.getOpenFileName = orig_s, orig_o
    _close(win)


def test_folders_persist_to_app_config():
    if not _pyside_ok():
        return
    win = _new_window()
    win.folders_tab.edits["input_image"].setText(r"D:\my\inputs")
    win.folders_tab._on_edit("input_image")
    assert win.app_config.default_folders.get("input_image") == r"D:\my\inputs"
    _close(win)


def test_run_small_sequence_end_to_end():
    if not _pyside_ok():
        return
    win = _new_window()
    win._max_frames = 3
    with tempfile.TemporaryDirectory() as d:
        win.sequence.sequence_name = "SEQ_E2E"
        win.sequence.folders["output"] = d
        win.sequence.folders["input_image"] = str(_COMMON)
        win.sequence.folders["heatmap"] = str(_COMMON)
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
        # 累積時間マップは明暗反転（IP設計者レビュー3 変更6）: 累積が大きい画素ほど暗い。
        # 輝度残存率マップは従来どおり（明=劣化少）
        import numpy as np
        vs, vd = win.results_tab.view_stat, win.results_tab.view_deg
        raw = vs._raw["r"]
        vmax = float(np.nanmax(raw))
        assert vmax > 0
        shown = vs._norm(raw, vmax)
        assert np.allclose(shown, 1.0 - raw / vmax)
        assert shown[np.unravel_index(np.nanargmax(raw), raw.shape)] == 0.0
        assert np.allclose(vd._norm(vd._raw["r"], 1.0), np.clip(vd._raw["r"], 0.0, 1.0))
        # 輝度残存率マップの deg1×deg2（フェーズF 5-4）：実行結果の CSV の積。黒の画素は出力動画の最後のフレームで判定
        assert vd.rb_mode["deg12"].isEnabled()
        vd.rb_mode["deg12"].setChecked(True)
        want12 = (np.loadtxt(entry.outputs["deg_r"], delimiter=",")
                  * np.loadtxt(entry.outputs["deg2_r"], delimiter=","))
        assert np.allclose(vd._raw["r"], want12)
        assert vd._mask is not None and vd._mask["r"].shape == want12.shape
        vd.rb_mode["deg1"].setChecked(True)
        # フレームスライダに Aging 時間を併記（IP設計者レビュー3 変更7）
        from bisim import engine
        from bisim.ui.i18n import t
        rt = win.results_tab
        assert entry.seconds_per_frame > 0 and entry.base_aging_seconds == 0.0
        rt.sld.setValue(2)
        want = engine.format_aging(2 * entry.seconds_per_frame)
        assert rt.lbl_frame.text() == t("res.frame_aging", v=2, aging=want)
        _close(win)   # tempdir を消す前に VideoCapture を解放


def test_stat_rgb_composite_normalizes_each_channel_independently():
    """評価反映3 B-2: R/G/Bの最大値の桁が大きく違っても、RGB合成はチャンネルごとに
    自分の最大値で正規化する（共通の最大値だと小さい方が常に明るいまま埋もれていた）。
    """
    if not _pyside_ok():
        return
    import numpy as np
    from bisim.ui.main_window import ResultEntry
    win = _new_window()
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # 2行以上にする（1行だと np.loadtxt が1次元配列として読み込んでしまうため）
            arrs = {"r": np.array([[0.0, 1.0], [0.0, 0.0]]),
                   "g": np.array([[0.0, 10.0], [0.0, 0.0]]),
                   "b": np.array([[0.0, 100.0], [0.0, 0.0]])}
            outputs = {}
            for c, a in arrs.items():
                p = d / f"stat_{c}.csv"
                np.savetxt(p, a, delimiter=",")
                outputs[f"stat_{c}"] = p
                dp = d / f"deg_{c}.csv"
                np.savetxt(dp, np.array([[1.0, 0.5], [1.0, 1.0]]), delimiter=",")
                outputs[f"deg_{c}"] = dp
            win.results[1] = ResultEntry(nn=1, recipe_name="x", is_movie=False, outputs=outputs)
            win.results_tab.add_result(1)
            vs = win.results_tab.view_stat
            vs.cmb_ch.setCurrentIndex(3)   # RGB合成

            captured = {}
            vs.canvas.show_rgb = lambda rgb, title="": captured.update(rgb=rgb.copy(), title=title)
            vs.reload()

            rgb = captured["rgb"]
            # 各色「自分の最大値」の画素(列1)で、その色成分が暗(0)になっている＝各色独立正規化
            assert rgb[0, 1, 0] == 0.0   # R: 自分の最大値(1.0)の画素でRが暗
            assert rgb[0, 1, 1] == 0.0   # G: 自分の最大値(10.0)の画素でGが暗
            assert rgb[0, 1, 2] == 0.0   # B: 自分の最大値(100.0)の画素でBが暗
            assert "R=1" in captured["title"] and "G=10" in captured["title"] and "B=100" in captured["title"]
    finally:
        _close(win)


def _deg_map_entry(d: Path, nn: int, with_deg2: bool):
    """輝度残存率マップのテスト用の結果（2×2、静止画）。

    deg   = [[1.0, 0.5], [0.8, 1.0]]
    deg2  = [[1.02, 0.9], [0.05, 0.98]]（1 を少し超える値と、黒の画素の意味のない小さな値を含む）
    黒の画素（最後に処理した入力フレームでその色が 0）：(y=1, x=0) は全色、(y=0, x=1) は B だけ
    """
    import numpy as np
    from bisim import engine
    from bisim.ui.main_window import ResultEntry
    deg = np.array([[1.0, 0.5], [0.8, 1.0]])
    deg2 = np.array([[1.02, 0.9], [0.05, 0.98]])
    outputs = {}
    for c in "rgb":
        for kind, a in (("deg", deg), ("stat", np.ones((2, 2)))) + ((("deg2", deg2),) if with_deg2 else ()):
            p = d / f"{nn}_{kind}_{c}.csv"
            np.savetxt(p, a, delimiter=",")
            outputs[f"{kind}_{c}"] = p
    img = np.full((2, 2, 3), 128, dtype=np.uint8)
    img[1, 0, :] = 0
    img[0, 1, 0] = 0                       # BGR の B
    return (ResultEntry(nn=nn, recipe_name="x", is_movie=False, outputs=outputs,
                        input_black=engine.black_mask_bgr(img)), deg, deg2)


def test_deg_map_mode_buttons_disabled_without_deg2():
    """deg2 の無い結果（フェーズF より前の停止結果）では deg2・deg1×deg2 のボタンを押せず、deg1 で表示する（5-4）。"""
    if not _pyside_ok():
        return
    from bisim.ui.i18n import t
    win = _new_window()
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            win.results[1], deg, _ = _deg_map_entry(d, 1, with_deg2=False)
            win.results[2], _, _ = _deg_map_entry(d, 2, with_deg2=True)
            rt = win.results_tab
            vd = rt.view_deg
            rt.add_result(2)
            vd.rb_mode["deg2"].setChecked(True)
            assert vd.mode_key() == "deg2"
            rt.add_result(1)                                     # deg2 の無い結果へ
            vd.reload()
            assert not vd.rb_mode["deg2"].isEnabled() and not vd.rb_mode["deg12"].isEnabled()
            assert vd.rb_mode["deg2"].toolTip() == t("map.deg.no_deg2")
            assert vd.mode_key() == "deg1"                       # deg1 に戻る
            assert (vd._raw["r"] == deg).all()
            assert t("map.deg.no_deg2") in vd.lbl_note.text()
            vd.rb_mode["deg12"].setChecked(True)                 # プログラムから選んでも deg1 に戻す
            assert vd.mode_key() == "deg1" and (vd._raw["g"] == deg).all()
            rt.cmb_idx.setCurrentText("2")                       # deg2 のある結果に戻すと押せる
            vd.reload()
            assert vd.rb_mode["deg2"].isEnabled() and vd.rb_mode["deg12"].isEnabled()
            assert t("map.deg.no_deg2") not in vd.lbl_note.text()
    finally:
        _close(win)


def test_deg_map_deg2_product_scale_and_black_pixels():
    """⑤ 輝度残存率マップ（5-4）：deg2・deg1×deg2 の値、0〜1／面内最小〜最大、黒の画素の扱い、2行の見出し。"""
    if not _pyside_ok():
        return
    import numpy as np
    from bisim.ui import i18n
    from bisim.ui.i18n import t
    from bisim.ui.tabs.results import BLACK_GRAY
    win = _new_window()
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            win.results[1], deg, deg2 = _deg_map_entry(d, 1, with_deg2=True)
            rt = win.results_tab
            rt.add_result(1)
            vd = rt.view_deg
            cap = {}
            vd.canvas.show_rgb = lambda rgb, title="": cap.update(rgb=rgb.copy(), title=title)
            vd.canvas.show_channel = lambda arr, ch, title="": cap.update(arr=arr.copy(), title=title)

            # deg1：黒の画素は除かない（deg1 は意味のある値）。見出しは2行
            vd.cmb_ch.setCurrentIndex(0)
            vd.reload()
            assert vd._mask is None and np.allclose(cap["arr"], deg)
            assert t("map.label.deg1") in cap["title"] and "\n" in cap["title"]

            # deg2（R）：0〜1 では 1 を超える値は 1、黒の画素は灰色、統計は黒の画素を除く
            vd.rb_mode["deg2"].setChecked(True)
            assert np.allclose(vd._raw["r"], deg2)
            assert vd._mask is not None and vd._mask["r"].tolist() == [[False, False], [True, False]]
            rgb = cap["rgb"]
            assert rgb[0, 0, 0] == 1.0 and abs(rgb[0, 1, 0] - 0.9) < 1e-12
            assert (rgb[1, 0] == BLACK_GRAY).all()
            assert t("map.label.deg2") in cap["title"]
            assert t("map.stats.black", n=1) in vd.lbl_stats.text() and "min 0.9 " in vd.lbl_stats.text()
            assert t("map.note.black", n=1 + 1 + 2) in vd.lbl_note.text()   # R 1・G 1・B 2
            vd._hover(0, 1)
            assert t("map.hover.black") in vd.lbl_hover.text()

            # deg1×deg2・面内最小〜最大（黒の画素を除いた範囲：R は 0.45〜1.02）
            vd.rb_mode["deg12"].setChecked(True)
            vd.cmb_scale.setCurrentIndex(1)
            assert vd.scale_key() == "minmax"
            assert np.allclose(vd._raw["r"], deg * deg2)
            rgb = cap["rgb"]
            assert rgb[0, 1, 0] == 0.0 and rgb[0, 0, 0] == 1.0     # 最小 0.45 → 0、最大 1.02 → 1
            assert (rgb[1, 0] == BLACK_GRAY).all()
            assert "0.45" in cap["title"] and "1.02" in cap["title"]
            assert t("map.note.deg12") in vd.lbl_note.text()

            # RGB合成（0〜1）：B だけ黒の画素は、光っている R・G の平均で B を埋める。全色黒は灰色
            vd.cmb_scale.setCurrentIndex(0)
            vd.cmb_ch.setCurrentIndex(3)
            rgb = cap["rgb"]
            assert np.allclose(rgb[0, 1], [0.45, 0.45, 0.45])
            assert (rgb[1, 0] == BLACK_GRAY).all()
            assert rgb[0, 0, 0] == 1.0                              # 1.02 は 1 として表示
            vd._hover(1, 0)
            assert vd.lbl_hover.text().count(t("map.hover.black")) == 1   # B だけ

            # 言語を切り替えても、選んだ量とスケールは保たれる
            i18n.set_lang("ja")
            assert vd.mode_key() == "deg12" and vd.scale_key() == "unit"
            assert vd.rb_mode["deg12"].text() == t("map.deg.deg12")
            i18n.set_lang("en")
    finally:
        _close(win)


def test_run_sequence_with_fixed_heatmap_end_to_end():
    """ヒートマップなし（固定温度）: IP設計者レビュー2 (2)。ヒートマップファイル無しで実行できる。"""
    if not _pyside_ok():
        return
    from bisim.model import Recipe
    win = _new_window()
    win._max_frames = 3
    with tempfile.TemporaryDirectory() as d:
        win.sequence.sequence_name = "SEQ_FIXEDHT"
        win.sequence.folders["output"] = d
        win.sequence.folders["input_image"] = str(_COMMON)
        win.sequence.folders["heatmap"] = str(_COMMON)
        win.sequence.recipes = [Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap="",
                                       heatmap_mode="fixed", fixed_temp_c=35.0)]
        win.steps_changed()
        win.run_steps("all")
        _wait_idle(win)
        assert 1 in win.results
        assert Path(win.results[1].outputs["movie"]).exists()
        _close(win)


def _wait_idle(win, timeout=90):
    end = time.time() + timeout
    while win.worker is not None and time.time() < end:
        _app().processEvents()
        time.sleep(0.02)
    assert win.worker is None, "worker が終了しなかった"


def test_stop_then_resume_same_session():
    if not _pyside_ok():
        return
    from PySide6.QtWidgets import QMessageBox
    win = _new_window()
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    try:
        with tempfile.TemporaryDirectory() as d:
            win.sequence.sequence_name = "RSM"
            win.sequence.folders["output"] = d
            win.sequence.folders["input_image"] = str(_COMMON)
            win.sequence.folders["heatmap"] = str(_COMMON)
            win.sequence.recipes = [_movie_recipe("aging01")]
            win._seq_path = Path(d) / "RSM.seq.json"      # 停止時の自動保存先（ダイアログを出さない）
            win.steps_changed()
            win.run_tab.cmb_sel.setCurrentIndex(0)

            # 1回目: 数フレームで停止（保存Yes → チェックポイント生成＋シーケンス自動保存）
            win.run_steps("selected")
            win.worker.sig_progress.connect(
                lambda pos, n, f, ft, q: win.stop_run() if f >= 1 else None)
            _wait_idle(win)
            assert 1 in win._stopped_states
            st = win._stopped_states[1]
            assert st.is_movie and st.frames_done >= 1
            assert win.resumable_nn_for_selected() == 1
            # 停止状態がシーケンス JSON に内包されている
            assert win._seq_path.exists()
            from bisim.model import Sequence as _Seq
            assert "01" in _Seq.load(win._seq_path).stops
            assert (Path(d) / st.dir).is_dir()

            # 2回目: 停止位置から再開（confirm Yes）。max_frames で早期に完了扱い
            win._max_frames = 4
            win.run_tab.cmb_sel.setCurrentIndex(0)
            win.run_steps("resume")
            _wait_idle(win)
            assert 1 in win.results
            mv = win.results[1].outputs["movie"]
            assert Path(mv).name == "RSM_01_aging01_movie.mp4"      # 通常完了名
            # 再開完了 → 停止状態が消えている（メモリ・JSON・実体とも）
            assert 1 not in win._stopped_states
            assert "01" not in _Seq.load(win._seq_path).stops
            assert not (Path(d) / st.dir).exists()
            import cv2
            cap = cv2.VideoCapture(str(mv))
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            assert n >= st.frames_done + 2                          # 連続動画
            _close(win)
    finally:
        QMessageBox.question = orig_q


# --------------------------------------------------------------------------- #
#  ① パネル設定（フェーズF 手順5-2）
# --------------------------------------------------------------------------- #
def _stub_dialogs(open_path=None, save_path=None):
    """QFileDialog・QMessageBox を差し替える。戻り値 (warned, restore)。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    orig = (QFileDialog.getOpenFileName, QFileDialog.getSaveFileName,
            QMessageBox.warning, QMessageBox.critical)
    warned = []
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(open_path or ""), ""))
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(save_path or ""), ""))
    QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[2] if len(a) > 2 else ""))
    QMessageBox.critical = staticmethod(lambda *a, **k: warned.append(a[2] if len(a) > 2 else ""))

    def restore():
        (QFileDialog.getOpenFileName, QFileDialog.getSaveFileName,
         QMessageBox.warning, QMessageBox.critical) = orig
    return warned, restore


def test_folders_tab_shows_panel_settings():
    if not _pyside_ok():
        return
    from bisim.paths import STD_BCSET, STD_DEGPARAM_SM
    win = _new_window()
    ft = win.folders_tab
    assert ft.file_edits["bcset"].text() == STD_BCSET.name
    assert ft.file_edits["sm"].text() == STD_DEGPARAM_SM.name
    assert "OK" in ft.file_status["bcset"].text() and "15" in ft.file_status["sm"].text()
    # mm の表は入力したらすぐシーケンスへ。数値でなければ警告して元に戻す
    ft.tbl_mm.item(0, 0).setText("1.9")
    assert win.sequence.panel.model_param["N"][0] == 1.9
    warned, restore = _stub_dialogs()
    try:
        ft.tbl_mm.item(1, 2).setText("abc")
    finally:
        restore()
    assert warned and ft.tbl_mm.item(1, 2).text() == "100"
    assert win.sequence.panel.model_param["K0"][2] == 100.0
    _close(win)


def test_pick_panel_file_checks_and_keeps_selection():
    if not _pyside_ok():
        return
    import shutil
    from bisim.paths import STD_DEGPARAM_SM
    win = _new_window()
    ft = win.folders_tab
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        bad = d / "sm_bad.csv"
        bad.write_text("DEG_2D_WRD_DEG,3\n", encoding="utf-8")
        warned, restore = _stub_dialogs(open_path=bad)
        try:
            ft._pick_panel_file("sm")
        finally:
            restore()
        assert win.sequence.panel.degparam_sm == "sm_bad.csv"            # 選択は残す
        assert win.sequence.folders["model"] == str(d)
        assert warned and "sm_bad.csv" in warned[0]
        assert "✗" in ft.file_status["sm"].text()
        # 実行前の検査でも止まる
        warned, restore = _stub_dialogs()
        try:
            assert not win._ensure_model([])
        finally:
            restore()
        assert warned and win.model is None
        # 直したら「再検査」で OK に
        shutil.copyfile(STD_DEGPARAM_SM, bad)
        ft.refresh_panel(force=True)
        assert "✓" in ft.file_status["sm"].text()
        assert win._ensure_model([])
    _close(win)


def test_open_panel_file_in_excel_and_auto_recheck():
    """「Excel で開く」は選んでいるファイルをそのまま開く（複製しない）。Excel で保存したら自動で検査し直す（2026-11-18）。"""
    if not _pyside_ok():
        return
    import shutil
    from bisim.paths import STD_BCSET, STD_DEGPARAM_SM
    from bisim.ui.tabs import folders as folders_mod
    win = _new_window()
    ft = win.folders_tab
    opened = []
    orig_open = folders_mod.open_external
    folders_mod.open_external = lambda p: opened.append(Path(p)) or True
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        sm = d / "sm_unit.csv"
        shutil.copyfile(STD_DEGPARAM_SM, sm)
        shutil.copyfile(STD_BCSET, d / "bcsetting.csv")
        win.sequence.folders["model"] = win.sequence.folders["bcset"] = str(d)
        win.sequence.panel.degparam_sm, win.sequence.panel.bcsetting = "sm_unit.csv", "bcsetting.csv"
        warned, restore = _stub_dialogs()
        try:
            ft.refresh_panel()
            assert t_ok(ft, "sm")
            files_before = sorted(p.name for p in d.iterdir())
            ft._open_in_excel("sm")
            assert opened == [sm] and not warned
            assert sorted(p.name for p in d.iterdir()) == files_before     # 複製しない
            # Excel で保存した（軸の行を消した）→ 自動で検査し直す（通知を待つ。来なければ直接確かめる）
            lines = [ln for ln in sm.read_text(encoding="utf-8").splitlines() if not ln.startswith("DEG_2D_I_R,")]
            sm.write_text("\n".join(lines) + "\n", encoding="utf-8")
            deadline = time.time() + 5
            while t_ok(ft, "sm") and time.time() < deadline:
                _app().processEvents()
                time.sleep(0.05)
            ft._watch.check_now()
            assert not t_ok(ft, "sm") and "DEG_2D_I_R" in ft.file_status["sm"].text()
            # 直して保存 → ✓ に戻る
            shutil.copyfile(STD_DEGPARAM_SM, sm)
            ft._watch.check_now()
            assert t_ok(ft, "sm")
            # ファイルが無ければ警告して開かない
            win.sequence.panel.bcsetting = "none.csv"
            ft._open_in_excel("bcset")
            assert warned and opened == [sm]
        finally:
            restore()
            folders_mod.open_external = orig_open
            _close(win)


def t_ok(ft, kind: str) -> bool:
    """①のパネル設定欄の検査結果が ✓ か。"""
    return ft.file_status[kind].text().startswith("✓")


def test_model_rebuilt_when_panel_changes():
    if not _pyside_ok():
        return
    import os
    import shutil
    from bisim.paths import STD_BCSET
    win = _new_window()
    assert win._ensure_model([])
    m1 = win.model
    assert win._ensure_model([]) and win.model is m1                 # 変わらなければ使い回す
    with tempfile.TemporaryDirectory() as d:
        bc = Path(d) / "bc2.csv"
        shutil.copyfile(STD_BCSET, bc)
        win.sequence.folders["bcset"] = d
        win.sequence.panel.bcsetting = bc.name
        assert win._ensure_model([]) and win.model is not m1             # 別のファイル → 作り直す
        m2 = win.model
        st = bc.stat()
        os.utime(bc, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))  # 保存し直した
        assert win._ensure_model([]) and win.model is not m2
    _close(win)


def test_open_old_sequence_logs_panel_migration():
    if not _pyside_ok():
        return
    import json
    from PySide6.QtWidgets import QFileDialog
    win = _new_window()
    logged = []
    win.logger.add_listener(logged.append)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "old.seq.json"
        mm = {"N": [1.5, 1.3, 1.7], "K0": [500, 1000, 100], "Q": [1000, 800, 600],
              "B0": [0.7, 0.8, 0.4], "A": [0, 0, 0]}
        p.write_text(json.dumps({"sequence_name": "old", "recipes": [
            {"recipe_name": "a", "model_param": dict(mm, N=[2, 2, 2])},
            {"recipe_name": "b", "model_param": mm}]}), encoding="utf-8")
        orig = QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(p), ""))
        try:
            win.open_sequence()
        finally:
            QFileDialog.getOpenFileName = orig
    assert win.sequence.panel.model_param["N"] == [2.0, 2.0, 2.0]
    assert win.folders_tab.tbl_mm.item(0, 0).text() == "2"
    assert sum("シーケンス読込の注意" in x for x in logged) == 2
    _close(win)


# --------------------------------------------------------------------------- #
#  ③ 表示条件・サブモデルの差し替え（フェーズF 手順5-3）
# --------------------------------------------------------------------------- #
def test_display_conditions_via_config_tab():
    if not _pyside_ok():
        return
    from PySide6.QtWidgets import QFileDialog
    win = _new_window()
    win.steps_tab._add()
    cfg = win.config_tab
    r = win.sequence.recipes[0]
    assert cfg.sp_dbv.value() == 2000.0 and not cfg.cb_dpk.isChecked()
    assert [sp.value() for sp in cfg.sp_gadj] == [1.0, 1.0, 1.0]
    cfg.cmb_kind.setCurrentIndex(1)                     # PQ評価でも設定できる
    cfg.sp_dbv.setValue(600.0)
    cfg.cb_dpk.setChecked(True)
    for sp, v in zip(cfg.sp_gadj, (1.1, 1.0, 0.95)):
        sp.setValue(v)
    assert cfg._collect_into_recipe()
    assert r.sim_param["DBV_NIT"] == 600.0 and r.sim_param["DPK_ON"] == 1
    assert r.sim_param["GADJ"] == [1.1, 1.0, 0.95]
    with tempfile.TemporaryDirectory() as d:
        p = str(Path(d) / "pq_sim.csv")
        orig_s, orig_o = QFileDialog.getSaveFileName, QFileDialog.getOpenFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (p, ""))
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (p, ""))
        try:
            cfg._save_sim_csv()
            cfg.sp_dbv.setValue(1.0)
            cfg.cb_dpk.setChecked(False)
            cfg._load_sim_csv()                         # CSV から読むと表示条件も入る
        finally:
            QFileDialog.getSaveFileName, QFileDialog.getOpenFileName = orig_s, orig_o
    assert cfg.sp_dbv.value() == 600.0 and cfg.cb_dpk.isChecked()
    assert abs(cfg.sp_gadj[2].value() - 0.95) < 1e-9
    _close(win)


def test_bcset_override_via_config_tab():
    """③ BC設定（個体）の差し替え（2026-11-25）：選ぶ・検査・Excel で開く・自動の再検査・前ステップ継承の決まり。"""
    if not _pyside_ok():
        return
    import shutil
    from bisim.paths import STD_BCSET
    from bisim.ui.tabs import folders as folders_mod
    win = _new_window()
    win.steps_tab._add()
    win.steps_tab._add()
    cfg = win.config_tab
    win.select_step(0)
    r0, r1 = win.sequence.recipes
    assert not hasattr(cfg, "cb_sm")                       # サブモデルの差し替え欄は廃止
    assert not cfg.cb_bc.isChecked() and not cfg.b_bc.isEnabled()
    assert STD_BCSET.name in cfg.lbl_bc_status.text()
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        alt = d / "bc_unitB.csv"
        shutil.copyfile(STD_BCSET, alt)
        cfg.cb_bc.setChecked(True)
        assert cfg.b_bc.isEnabled()
        warned, restore = _stub_dialogs(open_path=alt)
        try:
            cfg._pick_bc()                                  # BC設定フォルダの外 → 絶対パスで持つ
        finally:
            restore()
        assert not warned and r0.bcset_override == str(alt.resolve())
        assert win.sequence.bcset_path(0) == alt.resolve()
        assert "OK" in cfg.lbl_bc_status.text() and cfg.ed_bc.text() == "bc_unitB.csv"
        assert win.sequence.folders["bcset"] != str(d)     # ①の BC設定フォルダは動かさない
        # 別のステップを選んで戻っても消えない
        win.select_step(1)
        assert not cfg.cb_bc.isChecked() and r1.bcset_override == ""
        win.select_step(0)
        assert cfg.cb_bc.isChecked() and r0.bcset_override == str(alt.resolve())
        # 実行前の検査：ステップ02 は初期ストレス なし → 通る
        assert win._ensure_model([0, 1])
        # ステップ02 を前ステップ継承にすると、個体B → 個体A になるので実行させない
        r1.init_stress = "prev"
        errs = []
        from PySide6.QtWidgets import QMessageBox
        orig_crit = QMessageBox.critical
        QMessageBox.critical = staticmethod(lambda *a, **k: errs.append(a[2]))
        try:
            assert not win._ensure_model([0, 1])
        finally:
            QMessageBox.critical = orig_crit
        assert errs and "#2" in errs[0] and "bc_unitB.csv" in errs[0]
        r1.init_stress = "none"
        # Excel で開く → 差し替えのファイルをそのまま開く（複製しない）。保存したら自動で検査し直す
        opened = []
        orig_open = folders_mod.open_external
        folders_mod.open_external = lambda p: opened.append(Path(p)) or True
        try:
            cfg._open_bc()
        finally:
            folders_mod.open_external = orig_open
        assert opened == [alt.resolve()] and sorted(p.name for p in d.iterdir()) == ["bc_unitB.csv"]
        lines = [ln for ln in alt.read_text(encoding="utf-8").splitlines() if not ln.startswith("DUTY_BC,")]
        alt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cfg._bc_watch.check_now()
        assert "DUTY_BC" in cfg.lbl_bc_status.text()
        shutil.copyfile(STD_BCSET, alt)
        cfg._bc_watch.check_now()
        assert "OK" in cfg.lbl_bc_status.text()
        # チェックを外すと差し替えを解除
        cfg.cb_bc.setChecked(False)
        assert r0.bcset_override == "" and STD_BCSET.name in cfg.lbl_bc_status.text()
    _close(win)
