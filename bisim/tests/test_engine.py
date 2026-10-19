"""engine.py のテスト（実データ・実コアを使う統合テスト）"""
from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np

from bisim import engine
from bisim.model import Recipe, Sequence
from bisim.paths import SOURCE_DIR

_COMMON = SOURCE_DIR / "dbi_common"
_MOVIE = "mov_001_480x270.mp4"
_MOVIE_HT = "mov_ht_001_480x270.mp4"
_STILL = "eval_img.png"
_STILL_HT = "eval_img_ht.png"


def _folders(out_dir) -> dict:
    return {"input_image": str(_COMMON), "heatmap": str(_COMMON),
            "bcset": str(SOURCE_DIR / "dbi_input"),
            "model": str(SOURCE_DIR / "dbi_conf"),
            "simconf": str(SOURCE_DIR / "dbi_conf"),
            "output": str(out_dir)}


def _model():
    return engine.MasterModel()


def test_master_model_loads():
    m = _model()
    assert m.name == "master"
    assert isinstance(m, engine.DegradationModel)   # Protocol 準拠


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
        deg = _model().deg_maps(res.state, res.temp_kelvin, r.model_param)
        assert np.allclose(deg["r"], 1.0)         # 初期ストレス0 → 劣化なし

        out = engine.write_recipe_outputs(result=res, folders=_folders(d),
                                          sequence_name="T", model=_model(),
                                          model_param=r.model_param)
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
                                          model=_model(), model_param=r.model_param)
        assert Path(out["image"]).name == "T_01_age01_image.png"   # 出力は最後の劣化画像

        # 1フレームずつの手計算と一致する（劣化した後の明るさでストレスを貯める）
        img = cv2.imdecode(np.fromfile(str(_COMMON / _STILL), np.uint8), cv2.IMREAD_COLOR)
        mm = {k: v for k, v in r.model_param.items()}
        n, k0, q, b0 = mm["N"][0], mm["K0"][0], mm["Q"][0], mm["B0"][0]
        lum0 = (img[:, :, 2] / 255) ** 2.2
        s = np.zeros(lum0.shape)
        for _ in range(5):
            lum = lum0 * np.exp(-1.0 * s ** b0)
            s += 1.0 * 100.0 * lum ** n / (k0 * np.exp(q / 298.0))
        assert np.allclose(res.state.r, s, rtol=1e-12, atol=0)


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
                                          model=_model(), model_param=r.model_param)
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
                                                model=_model(), model_param=r.model_param,
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
                                          model_param=r.model_param)
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
                                          model_param=r.model_param)
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
            model_param=r.model_param, timestamp="260904-1430")
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
            model_param=r.model_param, timestamp="260904-1430")
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
            model_param=r.model_param)
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
        fps, native_total = _movie_meta(_COMMON / _MOVIE)
        dt_accel = (1.0 / fps) * r.sim_param["ACCEL_RATIO"]
        r.sim_param["AGING_TIME"] = dt_accel * (native_total + 5)   # 1周回+5フレーム分

        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model())
        assert not res.stopped
        assert res.frames_done == native_total + 5       # 1周回を超えて周回連結された
        assert res.frames_total == res.frames_done

        out = engine.write_recipe_outputs(result=res, folders=_folders(d),
                                          sequence_name="T", model=_model(),
                                          model_param=r.model_param)
        assert _movie_count(out["movie"]) == res.frames_done   # 出力動画も周回ぶん連結済み


def test_run_recipe_aging_time_stop_and_resume_across_wrap():
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="aging01", input_image=_MOVIE, heatmap=_MOVIE_HT)
        f = _folders(d)
        fps, native_total = _movie_meta(_COMMON / _MOVIE)
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
            model_param=r.model_param, timestamp="260910-1200")
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
            model_param=r.model_param)
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
            model_param=seq.recipes[0].model_param, timestamp="260904-1430")
        plan, err = engine.build_resume_plan(seq.folders, st)
        assert err is None
        results = engine.run_sequence(sequence=seq, model=_model(), only_index=0,
                                      resume=plan, max_frames=3)
        assert results[0].resumed_from == 3
        assert results[0].cumulative_aging_seconds == results[0].aging_seconds > st.aging_seconds
