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
    cfg.tbl_model.item(0, 0).setText("1.9")
    assert cfg._collect_into_recipe()
    r = win.sequence.recipes[0]
    assert r.recipe_name == "aging_A"
    assert r.sim_param["ACCEL_RATIO"] == 12345.0
    assert r.model_param["N"][0] == 1.9
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
    assert not cfg.gb_sim.isVisibleTo(cfg)
    assert not cfg._f1.isRowVisible(cfg._row_ht) and not cfg._f1.isRowVisible(cfg._row_ht_fixed)
    assert cfg.ed_name.text() == "pq_A"
    assert win.steps_tab.table.item(0, 3).text() == t("kind.eval")    # ②の Type 列
    assert cfg._collect_into_recipe() and r.step_type == "eval" and r.recipe_name == "pq_A"

    cfg.cmb_kind.setCurrentIndex(0)         # → Aging に戻すと欄が戻る
    assert r.step_type == "aging" and cfg.gb_sim.isVisibleTo(cfg)
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
        finally:
            QFileDialog.getSaveFileName = orig
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
