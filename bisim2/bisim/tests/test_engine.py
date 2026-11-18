"""engine.py のテスト（実データ・実コアを使う統合テスト）"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

from bisim import engine, imio
from bisim.model import DEFAULT_MODEL, Recipe, Sequence
from bisim.paths import SOURCE_DIR, STD_BCSET, STD_DEGPARAM_SM

_COMMON = SOURCE_DIR / "dbi_common"
_MOVIE = "mov_001_480x270.mp4"
_MOVIE_HT = "mov_ht_001_480x270.mp4"
_STILL = "eval_img.png"
_STILL_HT = "eval_img_ht.png"


def _folders(out_dir) -> dict:
    return {"input_image": str(_COMMON), "heatmap": str(_COMMON),
            "bcset": str(SOURCE_DIR / "dbi_conf"),
            "model": str(SOURCE_DIR / "dbi_conf"),
            "simconf": str(SOURCE_DIR / "dbi_input"),
            "output": str(out_dir)}


_MODEL = None


def _mm() -> dict:
    """mm（マスターモデル）の既定値の複製。フェーズF からはシーケンスのパネル設定が持つ。"""
    return {k: list(v) for k, v in DEFAULT_MODEL.items()}


def _model():
    """新コアのモデル（パネル設定の読み込みを毎回しないよう1つを使い回す）。"""
    global _MODEL
    if _MODEL is None:
        _MODEL = engine.CoreModel()
    return _MODEL


def test_core_model_loads():
    m = engine.CoreModel()
    assert m.name == "core01"
    assert isinstance(m, engine.DegradationModel)   # Protocol 準拠
    assert m.bc_dict["BC_BAND_NUM"] == m.sm_dict["DEG_2D_BC_IxDEG_R"].shape[0]


def test_stress_state():
    s = engine.StressState.zeros(4, 5)
    assert s.shape == (4, 5)
    s.require_shape(4, 5)
    try:
        s.require_shape(4, 6)
    except engine.EngineError:
        pass
    else:
        raise AssertionError("shape 不一致で EngineError が出るべき")
    with tempfile.TemporaryDirectory() as d:
        paths = [Path(d) / f"stat_{c}.csv" for c in "rgb"]
        s.r[0, 0] = 1.25
        s.save(*paths)
        s2 = engine.StressState.load(*paths)
        assert s2.shape == (4, 5) and s2.r[0, 0] == 1.25


def test_run_recipe_still():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="pq01", input_image=_STILL, heatmap=_STILL_HT)
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model())
        assert res.frames_done == 1 and not res.is_movie and not res.stopped
        assert res.size == (480, 270)
        assert res.aging_seconds == 0.0            # 静止画は寄与ゼロ
        assert res.dt_accel == 0.0
        deg = _model().deg_maps(res.state, res.temp_kelvin, _mm())
        assert np.allclose(deg["r"], 1.0)         # 初期ストレス0 → 劣化なし

        out = engine.write_recipe_outputs(result=res, folders=_folders(d),
                                          sequence_name="T", model=_model(),
                                          model_param=_mm())
        assert Path(out["image"]).name == "T_01_pq01_image.png"
        assert Path(out["deg_r"]).name == "T_01_pq01_deg_r.csv"
        assert all(Path(p).exists() for p in out.values())


def test_run_recipe_still_fixed_temp():
    """ヒートマップなし（固定温度）: IP設計者レビュー2 (2)。静止画 Aging で確認。"""
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="age01", input_image=_STILL, heatmap="", step_type="aging",
                  heatmap_mode="fixed", fixed_temp_c=40.0)
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model())
        assert res.frames_done == 1 and not res.stopped
        assert np.allclose(res.temp_kelvin, 40.0 + 273.0)   # パネル全面が固定温度


# --------------------------------------------------------------------------- #
#  ステップ種別（Aging / PQ評価 を手動選択。2026-10-19 決定）
# --------------------------------------------------------------------------- #
def test_still_image_aging_accumulates_at_fps1():
    """静止画 Aging：同じ絵を fps=1 で繰り返す（1フレーム = 1秒×ACCEL_RATIO）。"""
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="age01", input_image=_STILL, step_type="aging",
                  heatmap_mode="fixed", fixed_temp_c=25.0)
        r.sim_param["ACCEL_RATIO"] = 100.0
        r.sim_param["AGING_TIME"] = 450.0          # 4.5フレーム分 → 5フレーム
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model())
        assert engine.STILL_AGING_FPS == 1.0
        assert res.dt_accel == 100.0 and res.frames_done == 5 and res.frames_total == 5
        assert res.aging_seconds == 500.0 and not res.is_movie
        assert float(np.nanmax(res.state.r)) > 0.0   # ストレスが貯まっている
        out = engine.write_recipe_outputs(result=res, folders=_folders(d), sequence_name="T",
                                          model=_model(), model_param=_mm())
        assert Path(out["image"]).name == "T_01_age01_image.png"   # 出力は最後の劣化画像

        # 新コアはストレスを「劣化前の画素電流」で貯めるので、同じ絵を5回処理した stat は
        # 1回分のちょうど5倍になる。1回分はコアの burn_in_core を直接呼んで求める
        m = _model()
        img = cv2.imdecode(np.fromfile(str(_COMMON / _STILL), np.uint8), cv2.IMREAD_COLOR)
        ht = np.zeros_like(img)
        sim = engine.core_sim_dict(dict(r.sim_param, TMP_L=25.0, TMP_H=25.0))
        one = engine.StressState.zeros(*img.shape[:2])
        rc = m._core.burn_in_core(1.0, img.copy(), ht, m.bc_dict,
                                  {f"{k}_{c}": v[i] for k, v in _mm().items()
                                   for i, c in enumerate("rgb")},
                                  m.sm_dict, sim, stat_r=one.r, stat_g=one.g, stat_b=one.b,
                                  **m.band_data(sim))
        assert rc == 0 and float(np.max(one.r)) > 0.0
        for c in "rgb":
            assert np.allclose(res.state.channel(c), 5.0 * one.channel(c), rtol=1e-12, atol=0)


def test_still_image_aging_zero_aging_time_is_one_frame():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="age01", input_image=_STILL, step_type="aging",
                  heatmap_mode="fixed")
        r.sim_param["ACCEL_RATIO"] = 50.0
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model())
        assert res.frames_done == 1 and res.aging_seconds == 50.0


def test_eval_movie_does_not_accumulate():
    """PQ評価 × 動画：ストレスを貯めずに全フレームを処理し、劣化後の見え方の動画を作る。"""
    with tempfile.TemporaryDirectory() as d:
        init = engine.StressState.zeros(270, 480)
        init.r[:] = 0.5
        before = init.r.copy()
        r = Recipe(recipe_name="pqmov", input_image=_MOVIE, heatmap=_MOVIE_HT,
                  step_type="eval", init_stress="prev")
        r.sim_param["AGING_TIME"] = 99999.0        # 評価では使わない
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T", nn="02",
                                model=_model(), initial_state=init, max_frames=4)
        assert res.is_movie and res.frames_done == 4
        assert res.aging_seconds == 0.0 and res.dt_accel == 0.0
        assert np.array_equal(res.state.r, before)     # 累積ストレスは変わらない
        out = engine.write_recipe_outputs(result=res, folders=_folders(d), sequence_name="T",
                                          model=_model(), model_param=_mm())
        assert _movie_count(out["movie"]) == 4


def test_eval_has_no_temperature_setting():
    """PQ評価は温度設定なし：ヒートマップ・固定温度の設定に関係なく EVAL_TEMP_C で計算する。"""
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="pq01", input_image=_STILL, heatmap="no_such_heatmap.png",
                  step_type="eval", heatmap_mode="file")
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model())     # ヒートマップが無くても動く
        assert np.allclose(res.temp_kelvin, engine.EVAL_TEMP_C + 273.0)
        r2 = Recipe(recipe_name="pq02", input_image=_STILL, step_type="eval",
                   heatmap_mode="fixed", fixed_temp_c=80.0)
        res2 = engine.run_recipe(recipe=r2, folders=_folders(d), sequence_name="T",
                                 nn="02", model=_model())
        assert np.allclose(res2.temp_kelvin, engine.EVAL_TEMP_C + 273.0)


def test_still_image_aging_stop_and_resume_matches_uninterrupted():
    """静止画 Aging も停止位置から再開でき、通しで実行した結果と一致する。"""
    with tempfile.TemporaryDirectory() as d:
        f = _folders(d)
        r = Recipe(recipe_name="age01", input_image=_STILL, step_type="aging",
                  heatmap_mode="fixed")
        r.sim_param["ACCEL_RATIO"] = 100.0
        r.sim_param["AGING_TIME"] = 600.0          # 6フレーム
        full = engine.run_recipe(recipe=r, folders=f, sequence_name="S", nn="01", model=_model())

        ctl = engine.RunControl()

        def cb(fd, ft, prev):
            if fd >= 2:
                ctl.request_stop()

        res1 = engine.run_recipe(recipe=r, folders=f, sequence_name="S", nn="01",
                                 model=_model(), control=ctl, progress_cb=cb)
        assert res1.stopped and res1.frames_done == 2
        st, out1 = engine.write_stop_checkpoint(result=res1, folders=f, sequence_name="S",
                                                model=_model(), model_param=_mm(),
                                                timestamp="261019-1200")
        assert not st.is_movie and Path(out1["image"]).exists()
        plan, err = engine.build_resume_plan(f, st)
        assert err is None and plan.video is None and plan.frames_done == 2
        res2 = engine.run_recipe(recipe=r, folders=f, sequence_name="S", nn="01",
                                 model=_model(), initial_state=plan.state,
                                 resume_from=plan.frames_done,
                                 resume_aging_seconds=plan.aging_seconds)
        assert not res2.stopped and res2.frames_done == 4 and res2.frames_absolute == 6
        assert res2.aging_seconds == full.aging_seconds == 600.0
        assert np.allclose(res2.state.r, full.state.r, rtol=1e-12, atol=0)


def test_remove_stop_checkpoint_reports_leftover_and_cleanup():
    """停止フォルダを消せなかったとき（ファイルが開かれている等）は False を返し、
    残った空フォルダは cleanup_empty_stop_dirs で後から消せる（評価 261021B B-6）。"""
    from bisim.model import StopState
    with tempfile.TemporaryDirectory() as d:
        f = _folders(d)
        st = StopState(recipe_name="a", frames_done=1, frames_total=2, aging_seconds=1.0,
                       is_movie=False, timestamp="261022-1000", dir="_stops/S_01_a")
        base = Path(d) / st.dir
        base.mkdir(parents=True)
        (base / "stat_r.csv").write_text("0")
        assert engine.remove_stop_checkpoint(f, st) is True and not base.exists()

        on_windows = sys.platform.startswith("win")
        base.mkdir(parents=True)
        locked = base / "stat_r.csv"
        fh = open(locked, "w")                      # Windows では開いているファイルは消せない
        try:
            ok = engine.remove_stop_checkpoint(f, st)
            if on_windows:
                assert ok is False and base.exists()          # 消せなかったことを返す
                assert engine.cleanup_empty_stop_dirs(f) == []  # 中身があるうちは触らない
        finally:
            fh.close()
        if locked.exists():
            locked.unlink()                         # ファイルが閉じられて中身が消えた状態
        keep = Path(d) / "_stops" / "S_02_b"
        keep.mkdir(parents=True)
        (keep / "stat_r.csv").write_text("0")       # 中身のあるフォルダは触らない
        removed = engine.cleanup_empty_stop_dirs(f)
        if on_windows:
            assert removed == ["S_01_a"]
        assert not base.exists() and keep.exists()
        import shutil
        shutil.rmtree(keep)
        engine.cleanup_empty_stop_dirs(f)
        assert not (Path(d) / "_stops").exists()   # 空になった _stops 自体も消える


def test_media_size_and_sequence_reference_size():
    """画像サイズの基準：シーケンス内で最初に見つかる画像（動画・静止画は問わない）。"""
    assert engine.media_size(_COMMON / _MOVIE) == (480, 270)
    assert engine.media_size(_COMMON / _STILL) == (480, 270)
    assert engine.media_size(_COMMON / "no_such.png") is None
    seq = Sequence(sequence_name="S", folders=_folders("."))
    assert engine.sequence_reference_size(seq) is None              # 画像がまだ無い
    seq.recipes = [Recipe(recipe_name="a", input_image="", heatmap=_MOVIE_HT),
                   Recipe(recipe_name="b", input_image=_STILL, step_type="eval")]
    ref = engine.sequence_reference_size(seq)
    assert ref.size == (480, 270) and (ref.index, ref.field, ref.name) == (0, "heatmap", _MOVIE_HT)
    # 選び直している欄そのものは基準から外す
    ref2 = engine.sequence_reference_size(seq, skip=(0, "heatmap"))
    assert (ref2.index, ref2.field) == (1, "input_image")
    assert engine.sequence_reference_size(seq, skip=(1, "input_image")).index == 0
    # 固定温度モード・評価ステップのヒートマップは使わないので基準にしない
    seq.recipes[0].heatmap_mode = "fixed"
    assert engine.sequence_reference_size(seq).index == 1


def test_run_recipe_movie_fixed_temp():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap="",
                  heatmap_mode="fixed", fixed_temp_c=50.0)
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model(), max_frames=3)
        assert res.is_movie and res.frames_done == 3 and not res.stopped
        assert np.allclose(res.temp_kelvin, 50.0 + 273.0)
        out = engine.write_recipe_outputs(result=res, folders=_folders(d),
                                          sequence_name="T", model=_model(),
                                          model_param=_mm())
        assert Path(out["movie"]).exists()


def test_run_recipe_movie_limited():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model(), max_frames=4)
        assert res.is_movie and res.frames_done == 4 and not res.stopped
        assert res.aging_seconds > 0 and np.isfinite(res.aging_seconds)
        # 1フレームあたりの加速込み時間（⑤結果タブのフレーム→Aging時間換算に使う）
        assert res.dt_accel > 0 and np.isclose(res.dt_accel * 4, res.aging_seconds)
        out =engine.write_recipe_outputs(result=res, folders=_folders(d),
                                          sequence_name="T", model=_model(),
                                          model_param=_mm())
        assert Path(out["movie"]).name == "T_01_aging01_movie.mp4"
        assert Path(out["movie"]).exists()
        assert res._tmp_video is not None and not Path(res._tmp_video).exists()  # 移動済み


def test_run_recipe_stop_midway():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)
        ctl = engine.RunControl()

        def cb(fd, ft, prev):
            if fd >= 2:
                ctl.request_stop()

        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model(), control=ctl, progress_cb=cb)
        assert res.stopped and res.frames_done == 2

        st, out = engine.write_stop_checkpoint(
            result=res, folders=_folders(d), sequence_name="T", model=_model(),
            model_param=_mm(), timestamp="260904-1430")
        assert st.dir == "_stops/T_01_aging01"
        assert st.frames_done == 2 and st.is_movie
        base = Path(d) / "_stops" / "T_01_aging01"
        assert Path(out["stat_r"]) == base / "stat_r.csv"
        assert (base / "stat_r.csv").exists() and (base / "deg_r.csv").exists()
        assert (base / "movie.mp4").exists()


def test_run_recipe_stop_discard():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)
        ctl = engine.RunControl()
        ctl.request_stop()
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model(), control=ctl)
        assert res.stopped and res.frames_done == 0
        engine.discard_recipe_outputs(res)
        assert res._tmp_video is None or not Path(res._tmp_video).exists()


def test_run_sequence_chains_prev():
    with tempfile.TemporaryDirectory() as d:
        seq = Sequence(sequence_name="SEQ", folders=_folders(d))
        seq.recipes = [
            Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT),
            Recipe(recipe_name="pq01", input_image=_STILL, heatmap=_STILL_HT,
                   init_stress="prev"),
        ]
        results = engine.run_sequence(sequence=seq, model=_model(), max_frames=3)
        assert len(results) == 2
        assert results[0].frames_done == 3
        assert results[1].frames_done == 1
        # 累積 Aging 時間: step1 のみ寄与、step2(静止画)で不変
        assert results[1].cumulative_aging_seconds == results[0].aging_seconds > 0
        # step2 は step1 の劣化を継承 → 白ベタでも劣化画像になる（stat != 0）
        assert float(np.nanmax(results[1].state.r)) > 0.0


def test_format_aging():
    assert engine.format_aging(3600) == "01h 00m 00s"
    assert engine.format_aging(0) == "00h 00m 00s"
    assert engine.format_aging(10) == "00h 00m 10s"          # 小さい値も見える（評価反映3 B-3）
    assert engine.format_aging(20) == "00h 00m 20s"
    assert "d " in engine.format_aging(3600 * 100)            # 100h = 4日4時間


def _movie_count(path) -> int:
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return n


def test_stop_then_resume_continuous_video():
    """停止 → チェックポイント保存 → 停止位置から再開（連続動画・Aging 積み増し）。"""
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)
        f = _folders(d)

        ctl = engine.RunControl()

        def cb(fd, ft, prev):
            if fd >= 3:
                ctl.request_stop()

        res1 = engine.run_recipe(recipe=r, folders=f, sequence_name="S", nn="01",
                                 model=_model(), control=ctl, progress_cb=cb)
        assert res1.stopped and res1.frames_done == 3 and res1.resumed_from == 0
        assert res1.frames_absolute == 3

        st, out1 = engine.write_stop_checkpoint(
            result=res1, folders=f, sequence_name="S", model=_model(),
            model_param=_mm(), timestamp="260904-1430")
        assert st.frames_done == 3 and st.is_movie and st.frames_total == 405
        assert st.aging_seconds > 0
        assert st.dir == "_stops/S_01_aging01"
        n1 = _movie_count(out1["movie"])

        # ---- 再開（build_resume_plan 経由）----
        plan, err = engine.build_resume_plan(f, st)
        assert err is None and plan.frames_done == 3 and plan.video is not None
        res2 = engine.run_recipe(
            recipe=r, folders=f, sequence_name="S", nn="01", model=_model(),
            initial_state=plan.state, resume_from=plan.frames_done,
            resume_video=plan.video, resume_aging_seconds=plan.aging_seconds,
            max_frames=4)
        assert res2.resumed_from == 3 and res2.frames_done == 4
        assert res2.aging_seconds > st.aging_seconds        # 積み増しされている
        out2 = engine.write_recipe_outputs(
            result=res2, folders=f, sequence_name="S", model=_model(),
            model_param=_mm())
        assert Path(out2["movie"]).name == "S_01_aging01_movie.mp4"   # 通常完了名
        n2 = _movie_count(out2["movie"])
        assert n2 >= n1 + 2                                  # 先頭連結ぶん + 新規

        # 再開完了後の後片付け
        engine.remove_stop_checkpoint(f, st)
        assert not (Path(d) / st.dir).exists()


# --------------------------------------------------------------------------- #
#  AGING_TIME（目標Aging時間。IP設計者レビュー2 (3)）
# --------------------------------------------------------------------------- #
def _movie_meta(path) -> tuple:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return fps, total


def _small_movie_folders(d, frames: int = 20, size: tuple = (96, 54)) -> dict:
    """周回連結のテスト用に、入力動画・ヒートマップ動画を小さくしたものを d に作る。

    新コアは 480×270 で1フレーム約0.2秒かかり、1周回（405フレーム）を超えるテストが
    1本 90 秒以上になるため。テストの目的（周回のつなぎ方）は画像の大きさに依らない。
    """
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    for name in (_MOVIE, _MOVIE_HT):
        cap = cv2.VideoCapture(str(_COMMON / name))
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = cv2.VideoWriter(str(Path(d) / name), fourcc, fps, size)
        for _ in range(frames):
            ok, frm = cap.read()
            assert ok
            w.write(cv2.resize(frm, size, interpolation=cv2.INTER_AREA))
        w.release()
        cap.release()
    f = _folders(d)
    f["input_image"] = f["heatmap"] = str(d)
    return f


def test_aging_time_zero_is_unlimited():
    """既定 AGING_TIME=0 は従来どおり無制限（1周回のみ、打ち切りなし）。"""
    r = Recipe()
    assert r.sim_param["AGING_TIME"] == 0.0


def test_aging_time_add_frames_matches_run_recipe():
    """engine.aging_time_add_frames() は run_recipe 本体と同じ見積りを返す
    （④実行タブの表示が内部計算と食い違わないことの保証）。"""
    fps, _ = _movie_meta(_COMMON / _MOVIE)
    dt_accel = (1.0 / fps) * 30000.0        # 既定 ACCEL_RATIO
    assert engine.aging_time_add_frames(dt_accel, 0.0) == 0          # 残り0=目標達成済み
    assert engine.aging_time_add_frames(dt_accel, 10.0) == 1         # 1フレーム未満でも最低1
    assert engine.aging_time_add_frames(dt_accel, dt_accel * 2.5) == 3


def test_aging_time_small_values_round_up_to_same_frame_count():
    """大きい ACCEL_RATIO では1フレームが千秒規模になり、小さい AGING_TIME は
    どれも『最低1フレーム』に丸められて区別できなくなる（評価メモ: 10秒と20秒を
    試して結果が同じに見えた、の原因。バグではなく既定 ACCEL_RATIO=30000 での
    1フレームあたりの粒度の問題）。"""
    with tempfile.TemporaryDirectory() as d:
        fps, native_total = _movie_meta(_COMMON / _MOVIE)
        dt_accel = (1.0 / fps) * 30000.0
        assert dt_accel > 20.0              # 1フレーム分の時間が 20 秒を上回ることを確認

        results = []
        for aging_time in (10.0, 20.0):
            r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap="",
                      heatmap_mode="fixed", fixed_temp_c=100.0)
            r.sim_param["AGING_TIME"] = aging_time
            res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                    nn="01", model=_model())
            results.append(res)

        assert results[0].frames_done == results[1].frames_done == 1   # どちらも1フレームのみ
        # 同じ1フレーム目を同じ条件で処理するので、劣化結果も一致する
        assert np.array_equal(results[0].state.r, results[1].state.r)


def test_run_recipe_aging_time_truncates():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)
        fps, native_total = _movie_meta(_COMMON / _MOVIE)
        dt_accel = (1.0 / fps) * r.sim_param["ACCEL_RATIO"]
        r.sim_param["AGING_TIME"] = dt_accel * 2.5     # 2.5フレーム分 → 3フレームで打ち切り

        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model())
        assert not res.stopped                          # 目標到達は「停止」ではなく正常完了
        assert res.frames_done == 3 and res.frames_done < native_total
        assert res.aging_seconds >= r.sim_param["AGING_TIME"]
        assert res.frames_total == res.frames_done       # 目標フレーム数=処理数（進捗バー用）


def test_run_recipe_aging_time_loops_past_movie_length():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)
        f = _small_movie_folders(d)
        fps, native_total = _movie_meta(Path(d) / _MOVIE)
        dt_accel = (1.0 / fps) * r.sim_param["ACCEL_RATIO"]
        r.sim_param["AGING_TIME"] = dt_accel * (native_total + 5)   # 1周回+5フレーム分

        res = engine.run_recipe(recipe=r, folders=f, sequence_name="T",
                                nn="01", model=_model())
        assert not res.stopped
        assert res.frames_done == native_total + 5       # 1周回を超えて周回連結された
        assert res.frames_total == res.frames_done

        out = engine.write_recipe_outputs(result=res, folders=f,
                                          sequence_name="T", model=_model(),
                                          model_param=_mm())
        assert _movie_count(out["movie"]) == res.frames_done   # 出力動画も周回ぶん連結済み


def test_run_recipe_aging_time_stop_and_resume_across_wrap():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)
        f = _small_movie_folders(d)
        fps, native_total = _movie_meta(Path(d) / _MOVIE)
        dt_accel = (1.0 / fps) * r.sim_param["ACCEL_RATIO"]
        r.sim_param["AGING_TIME"] = dt_accel * (native_total + 20)  # 1周回+20フレーム分

        ctl = engine.RunControl()
        stop_at = native_total + 3      # 周回をまたいだ直後で停止

        def cb(fd, ft, prev):
            if fd >= stop_at:
                ctl.request_stop()

        res1 = engine.run_recipe(recipe=r, folders=f, sequence_name="S", nn="01",
                                 model=_model(), control=ctl, progress_cb=cb)
        assert res1.stopped and res1.frames_done == stop_at

        st, out1 = engine.write_stop_checkpoint(
            result=res1, folders=f, sequence_name="S", model=_model(),
            model_param=_mm(), timestamp="260910-1200")
        assert st.frames_done == stop_at
        n1 = _movie_count(out1["movie"])
        assert n1 == stop_at

        plan, err = engine.build_resume_plan(f, st)
        assert err is None and plan.frames_done == stop_at

        res2 = engine.run_recipe(
            recipe=r, folders=f, sequence_name="S", nn="01", model=_model(),
            initial_state=plan.state, resume_from=plan.frames_done,
            resume_video=plan.video, resume_aging_seconds=plan.aging_seconds)
        assert not res2.stopped
        assert res2.resumed_from == stop_at and res2.frames_done > 0
        assert res2.aging_seconds >= r.sim_param["AGING_TIME"]
        assert res2.frames_total == res2.frames_absolute   # 目標到達=絶対フレーム数と一致

        out2 = engine.write_recipe_outputs(
            result=res2, folders=f, sequence_name="S", model=_model(),
            model_param=_mm())
        n2 = _movie_count(out2["movie"])
        assert n2 == res2.frames_absolute                  # 周回をまたいでも連続動画として出力


def test_run_sequence_continues_after_aging_time_truncation():
    """AGING_TIME による打ち切りは通常完了扱い＝シーケンスの次ステップへ継続する。"""
    with tempfile.TemporaryDirectory() as d:
        seq = Sequence(sequence_name="SEQ", folders=_folders(d))
        aging = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)
        fps, native_total = _movie_meta(_COMMON / _MOVIE)
        dt_accel = (1.0 / fps) * aging.sim_param["ACCEL_RATIO"]
        aging.sim_param["AGING_TIME"] = dt_accel * 2.5
        pq = Recipe(recipe_name="pq01", input_image=_STILL, heatmap=_STILL_HT,
                   init_stress="prev")
        seq.recipes = [aging, pq]

        results = engine.run_sequence(sequence=seq, model=_model())
        assert len(results) == 2
        assert not results[0].stopped and results[0].frames_done < native_total
        assert results[1].frames_done == 1
        assert float(np.nanmax(results[1].state.r)) > 0.0   # 前ステップの劣化を継承


def test_run_sequence_resume_plan():
    with tempfile.TemporaryDirectory() as d:
        seq = Sequence(sequence_name="SEQ", folders=_folders(d))
        seq.recipes = [Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)]
        ctl = engine.RunControl()
        r1 = engine.run_recipe(recipe=seq.recipes[0], folders=seq.folders,
                               sequence_name="SEQ", nn="01", model=_model(),
                               control=ctl, max_frames=3)
        st, _ = engine.write_stop_checkpoint(
            result=r1, folders=seq.folders, sequence_name="SEQ", model=_model(),
            model_param=seq.panel.model_param, timestamp="260904-1430")
        plan, err = engine.build_resume_plan(seq.folders, st)
        assert err is None
        results = engine.run_sequence(sequence=seq, model=_model(), only_index=0,
                                      resume=plan, max_frames=3)
        assert results[0].resumed_from == 3
        assert results[0].cumulative_aging_seconds == results[0].aging_seconds > st.aging_seconds


# --------------------------------------------------------------------------- #
#  新コア（フェーズF。松井さん Burn_in_sim_core_01）
# --------------------------------------------------------------------------- #
_REF_CORE = Path(__file__).resolve().parent / "data" / "core01_case1-2.npz"


def test_core_matches_matsui_reference_case1_2():
    """松井さんのケース1→2 の切り出し（16×16。作り方は tool/phaseF/make_selftest_core_data.py）を
    bisim のエンジン（run_recipe → write_recipe_outputs）で計算し、stat・deg・deg2・出力画像が一致する。

    ケース1 = Aging（初期ストレス0）、ケース2 = ケース1 の stat を引き継ぐテストステップ
    （bisim では「Aging・静止画（fps=1）」で流すと松井さんの 1 秒分と同じ条件になる）。"""
    ref = np.load(_REF_CORE)
    mp = {k: list(ref[f"mm_{k}"]) for k in ("N", "K0", "Q", "B0", "A")}
    with tempfile.TemporaryDirectory() as d:
        f = _folders(d)
        f["input_image"] = f["heatmap"] = str(d)
        state = None
        for idx in (1, 2):
            cv2.imwrite(str(Path(d) / f"in{idx}.png"), ref[f"c{idx}_img"])
            cv2.imwrite(str(Path(d) / f"ht{idx}.png"), ref[f"c{idx}_ht"])
            sim = {k: float(ref[f"c{idx}_sim_{k}"]) for k in
                   ("ACCEL_RATIO", "TMP_L", "TMP_H", "DBV_NIT", "DPK_ON", "GADJ_R", "GADJ_G", "GADJ_B")}
            sim["AGING_TIME"] = 0.0                  # 静止画は1フレーム（1秒×ACCEL_RATIO）
            r = Recipe(recipe_name=f"c{idx}", input_image=f"in{idx}.png", heatmap=f"ht{idx}.png",
                       sim_param=sim, step_type="aging")
            res = engine.run_recipe(recipe=r, folders=f, sequence_name="M", nn=f"{idx:02d}",
                                    model=_model(), initial_state=state, model_param=mp)
            out = engine.write_recipe_outputs(result=res, folders=f, sequence_name="M",
                                              model=_model(), model_param=mp)
            for c in "rgb":
                for kind in ("stat", "deg", "deg2"):
                    got = np.loadtxt(out[f"{kind}_{c}"], delimiter=",")
                    assert np.array_equal(got, ref[f"c{idx}_{kind}_{c}"]), f"case{idx} {kind}_{c}"
            assert np.array_equal(cv2.imread(str(out["image"])), ref[f"c{idx}_out"]), f"case{idx} 画像"
            state = res.state


def test_deg_maps_is_exp_minus_stat_pow_b0():
    """出力の deg（deg1）は新コアの出力と同じ exp(-stat^B0)。温度・A は使わない。"""
    s = engine.StressState.zeros(2, 3)
    s.r[:] = 0.5
    s.g[:] = 2.0
    mp = _mm()
    mp["A"] = [0.01, 0.01, 0.01]                    # A を入れても deg1 には効かない
    deg = _model().deg_maps(s, np.full((2, 3), 350.0), mp)
    assert np.allclose(deg["r"], np.exp(-(0.5 ** mp["B0"][0])))
    assert np.allclose(deg["g"], np.exp(-(2.0 ** mp["B0"][1])))
    assert np.allclose(deg["b"], 1.0)


def test_deg2_written_to_outputs_and_checkpoint():
    with tempfile.TemporaryDirectory() as d:
        f = _folders(d)
        r = Recipe(recipe_name="age01", input_image=_STILL, step_type="aging", heatmap_mode="fixed")
        r.sim_param["ACCEL_RATIO"] = 100.0
        r.sim_param["AGING_TIME"] = 300.0          # 3フレーム
        res = engine.run_recipe(recipe=r, folders=f, sequence_name="T", nn="01", model=_model())
        assert res.deg2 is not None and res.deg2.shape == (270, 480)
        # コアが deg2 を書き込んでいる（初期値 1.0 から変わる。サブモデルの表によっては 1 を少し超える）
        assert np.all(res.deg2.r != 1.0)
        # 最後に処理した入力フレームの黒の画素（⑤の deg2 表示で除く。5-4）。コアが書き換える前の入力で判定
        src = imio.imread(Path(f["input_image"]) / _STILL)
        assert res.input_black["r"].shape == (270, 480)
        for c, k in (("r", 2), ("g", 1), ("b", 0)):
            assert np.array_equal(res.input_black[c], src[..., k] == 0)
        assert engine.black_mask_bgr(np.zeros((2, 2), dtype=np.uint8))["g"].all()
        out = engine.write_recipe_outputs(result=res, folders=f, sequence_name="T",
                                          model=_model(), model_param=_mm())
        assert Path(out["deg2_g"]).name == "T_01_age01_deg2_g.csv"
        assert np.array_equal(np.loadtxt(out["deg2_g"], delimiter=","), res.deg2.g)

        ctl = engine.RunControl()

        def cb(fd, ft, prev):
            if fd >= 2:
                ctl.request_stop()

        res1 = engine.run_recipe(recipe=r, folders=f, sequence_name="S", nn="01",
                                 model=_model(), control=ctl, progress_cb=cb)
        st, out1 = engine.write_stop_checkpoint(result=res1, folders=f, sequence_name="S",
                                                model=_model(), model_param=_mm(),
                                                timestamp="261118-1200")
        base = Path(d) / st.dir
        assert out1["deg2_b"] == base / "deg2_b.csv" and out1["deg2_b"].exists()
        assert engine.stop_checkpoint_outputs(f, st)["deg2_r"] == base / "deg2_r.csv"
        # deg2 の無い停止（フェーズF より前）でも ⑤ 用の outputs は作れる
        for c in "rgb":
            (base / f"deg2_{c}.csv").unlink()
        assert "deg2_r" not in engine.stop_checkpoint_outputs(f, st)


def test_core_sim_dict_defaults_and_gadj():
    d = engine.core_sim_dict({"ACCEL_RATIO": 1.0, "TMP_L": 25.0, "TMP_H": 60.0, "AGING_TIME": 0.0})
    assert d["DBV_NIT"] == 2000.0 and d["DPK_ON"] == 0                  # 決定済みの既定値
    assert (d["GADJ_R"], d["GADJ_G"], d["GADJ_B"]) == (1.0, 1.0, 1.0)
    d2 = engine.core_sim_dict({"DBV_NIT": 6500, "DPK_ON": 1.0, "GADJ": [1.1, 1.2, 1.3]})
    assert d2["DPK_ON"] == 1 and isinstance(d2["DPK_ON"], int)
    assert (d2["GADJ_R"], d2["GADJ_G"], d2["GADJ_B"]) == (1.1, 1.2, 1.3) and "GADJ" not in d2


def test_band_data_cached_per_dbv_and_dpk():
    m = engine.CoreModel()
    calls = []
    orig = m._core.burn_in_band_extract

    def spy(*a):
        calls.append(1)
        return orig(*a)

    m._core.burn_in_band_extract = spy
    try:
        sim = engine.core_sim_dict({})
        b1 = m.band_data(sim)
        assert m.band_data(dict(sim, GADJ_R=1.5)) is b1        # GADJ は Band 選択に関係しない
        assert len(calls) == 1
        m.band_data(dict(sim, DBV_NIT=500.0))
        m.band_data(dict(sim, DPK_ON=1))
        assert len(calls) == 3
    finally:
        m._core.burn_in_band_extract = orig


def test_core_model_reports_bad_panel_files():
    with tempfile.TemporaryDirectory() as d:
        try:
            engine.CoreModel(sm_path=Path(d) / "no_such_sm.csv")
        except engine.EngineError as e:
            assert "no_such_sm.csv" in str(e)
        else:
            raise AssertionError("読めないサブモデルで EngineError が出るべき")


# --------------------------------------------------------------------------- #
#  パネル設定（フェーズF 手順5-1）：ファイルの検査・sm の差し替え・シーケンスの mm
# --------------------------------------------------------------------------- #
def _edit_csv(src: Path, dst: Path, key: str = None, values=None, drop: str = None, scale_lut=None):
    """CSV を書き換えた複製を作る。key の行の値を values に／drop の行を削除／キーの無い数値行（表）を scale_lut 倍。"""
    out = []
    for line in src.read_text(encoding="utf-8-sig").splitlines():
        head = line.split(",", 1)[0].strip()
        if drop and head == drop:
            continue
        if key and head == key:
            line = ",".join([key] + [f"{v:g}" for v in values])
        elif scale_lut is not None and head and head[0] in "0123456789.-":
            line = ",".join(f"{float(x) * scale_lut:g}" if x.strip() else x for x in line.split(","))
        out.append(line)
    dst.write_text("\n".join(out) + "\n", encoding="utf-8")
    return dst


def test_check_panel_files_standard_ok():
    bc = engine.check_bcset(STD_BCSET)
    assert bc.ok and bc.band_num == 15
    sm = engine.check_sm(STD_DEGPARAM_SM, bc.band_num)
    assert sm.ok and sm.band_num == 15
    assert not engine.check_sm(STD_DEGPARAM_SM, 14).ok              # Band 数の不一致
    assert "BC_BAND_NUM=14" in engine.check_sm(STD_DEGPARAM_SM, 14).problems[0]


def test_check_panel_files_reports_problems():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        assert "ファイルがありません" in engine.check_bcset(d / "none.csv").problems[0]
        # 取り違え（sm を bcsetting の欄に）→ キーの行が無い
        assert "キーの行がありません" in engine.check_bcset(STD_DEGPARAM_SM).problems[0]
        p = _edit_csv(STD_DEGPARAM_SM, d / "a.csv", drop="DEG_2D_I_G")
        assert "DEG_2D_I_G" in engine.check_sm(p).problems[0]
        sm = engine.check_sm(STD_DEGPARAM_SM).data
        # 値の並び順・軸の端の値は見ない（2026-11-18 担当者判断：キー名と行数・列数だけ）
        deg = list(sm["DEG_2D_DEG_R"])
        p = _edit_csv(STD_DEGPARAM_SM, d / "b.csv", key="DEG_2D_DEG_R", values=[0.995] + deg[1:])
        assert engine.check_sm(p).ok
        i_ax = list(sm["DEG_2D_I_B"])
        i_ax[0], i_ax[1] = i_ax[1], i_ax[0]
        p = _edit_csv(STD_DEGPARAM_SM, d / "c.csv", key="DEG_2D_I_B", values=i_ax)
        assert engine.check_sm(p).ok
        # 軸の値の数が DEG_2D_WRD_I と合わない → 読み込みに失敗（列数の検査）
        p = _edit_csv(STD_DEGPARAM_SM, d / "c2.csv", key="DEG_2D_I_B", values=list(sm["DEG_2D_I_B"])[:-1])
        assert any("読み込みに失敗" in x for x in engine.check_sm(p).problems)
        bc = engine.check_bcset(STD_BCSET).data
        dbv = list(bc["DBV_NIT_BC"])
        dbv[2], dbv[3] = dbv[3], dbv[2]
        p = _edit_csv(STD_BCSET, d / "d.csv", key="DBV_NIT_BC", values=dbv)
        assert engine.check_bcset(p).ok
        p = _edit_csv(STD_BCSET, d / "e.csv", key="DUTY_BC", values=list(bc["DUTY_BC"])[:-1])
        assert any("DUTY_BC の値の数 14" in x for x in engine.check_bcset(p).problems)
        try:
            engine.CoreModel(bcset_path=p)
        except engine.EngineError as e:
            assert "DUTY_BC" in str(e)
        else:
            raise AssertionError("使えない bcsetting で EngineError が出るべき")


def test_panel_key_changes_when_file_is_saved_again():
    import os
    import shutil
    with tempfile.TemporaryDirectory() as d:
        bc, sm = Path(d) / "bc.csv", Path(d) / "sm.csv"
        shutil.copyfile(STD_BCSET, bc)
        shutil.copyfile(STD_DEGPARAM_SM, sm)
        m = engine.CoreModel(bcset_path=bc, sm_path=sm)
        assert m.panel_key == engine.panel_key(bc, sm)
        st = sm.stat()
        os.utime(sm, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))   # Excel で保存し直した
        assert m.panel_key != engine.panel_key(bc, sm)


def _small_still(d: Path, name="small.png") -> str:
    rng = np.random.default_rng(0)
    cv2.imwrite(str(d / name), rng.integers(0, 256, (18, 32, 3), dtype=np.uint8))
    return name


def test_sm_override_changes_deg2_only():
    """ステップごとのサブモデルの差し替え：deg2（表示）だけが変わり、stat・deg1 は変わらない。"""
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        f = _folders(d)
        f["input_image"] = str(dd)
        img = _small_still(dd)
        alt = _edit_csv(STD_DEGPARAM_SM, dd / "sm_alt.csv", scale_lut=0.9)
        assert engine.check_sm(alt, 15).ok
        m = engine.CoreModel()
        r = Recipe(recipe_name="a", input_image=img, step_type="aging", heatmap_mode="fixed")
        r.sim_param.update(ACCEL_RATIO=1000.0, AGING_TIME=2000.0)         # 2フレーム
        res0 = engine.run_recipe(recipe=r, folders=f, sequence_name="T", nn="01", model=m)
        res1 = engine.run_recipe(recipe=r, folders=f, sequence_name="T", nn="01", model=m,
                                 sm_path=alt)
        assert m.sm_path == alt
        assert np.array_equal(res0.state.r, res1.state.r)               # stat は同じ
        assert not np.allclose(res0.deg2.r, res1.deg2.r)                 # deg2 は違う
        res2 = engine.run_recipe(recipe=r, folders=f, sequence_name="T", nn="01", model=m)
        assert m.sm_path == m.base_sm_path                               # None＝シーケンスの sm に戻る
        assert np.array_equal(res0.deg2.r, res2.deg2.r)


def test_run_sequence_uses_panel_mm_and_step_sm():
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        img = _small_still(dd)
        _edit_csv(STD_DEGPARAM_SM, dd / "sm_alt.csv", scale_lut=0.9)
        import shutil
        shutil.copyfile(STD_DEGPARAM_SM, dd / STD_DEGPARAM_SM.name)
        seq = Sequence(sequence_name="P", folders=_folders(d))
        seq.folders["input_image"] = seq.folders["model"] = str(dd)   # sm（差し替えも）はモデルフォルダ
        r1 = Recipe(recipe_name="age", input_image=img, step_type="aging", heatmap_mode="fixed")
        r1.sim_param.update(ACCEL_RATIO=1000.0, AGING_TIME=1000.0)
        r2 = Recipe(recipe_name="pq", input_image=img, step_type="eval", init_stress="prev")
        seq.recipes = [r1, r2]
        res_a = engine.run_sequence(sequence=seq, model=_model())
        seq.panel.model_param["K0"] = [k * 2 for k in seq.panel.model_param["K0"]]
        r2.sm_override = "sm_alt.csv"
        res_b = engine.run_sequence(sequence=seq, model=_model())
        # mm（K0 を2倍）→ stat は半分
        assert np.allclose(res_b[0].state.r, res_a[0].state.r / 2)
        # 2ステップ目（PQ評価）だけ sm を差し替え → deg2 が違う。1ステップ目は同じ sm
        assert not np.allclose(res_a[1].deg2.g, res_b[1].deg2.g)
        assert _model().sm_path == seq.sm_path(1)


def test_eval_step_uses_display_conditions():
    """PQ評価（dt=0）でも表示条件（DBV_NIT・DPK_ON・GADJ）はコアに渡る：deg2・画像は変わり、stat は貯まらない。"""
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        f = _folders(d)
        f["input_image"] = str(dd)
        img = _small_still(dd)
        age = Recipe(recipe_name="age", input_image=img, step_type="aging", heatmap_mode="fixed")
        age.sim_param.update(ACCEL_RATIO=1e5, AGING_TIME=3e5)
        st = engine.run_recipe(recipe=age, folders=f, sequence_name="T", nn="01", model=_model()).state
        out = {}
        for dbv in (2000.0, 600.0):
            pq = Recipe(recipe_name="pq", input_image=img, step_type="eval")
            pq.sim_param["DBV_NIT"] = dbv
            init = engine.StressState(st.r.copy(), st.g.copy(), st.b.copy())
            res = engine.run_recipe(recipe=pq, folders=f, sequence_name="T", nn="02", model=_model(),
                                    initial_state=init)
            assert np.array_equal(res.state.r, st.r)            # PQ評価はストレスを貯めない
            out[dbv] = res
        assert not np.allclose(out[2000.0].deg2.g, out[600.0].deg2.g)
