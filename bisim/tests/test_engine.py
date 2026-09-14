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
        deg = _model().deg_maps(res.state, res.temp_kelvin, r.model_param)
        assert np.allclose(deg["r"], 1.0)         # 初期ストレス0 → 劣化なし

        out = engine.write_recipe_outputs(result=res, folders=_folders(d),
                                          sequence_name="T", model=_model(),
                                          model_param=r.model_param)
        assert Path(out["image"]).name == "T_01_pq01_image.png"
        assert Path(out["deg_r"]).name == "T_01_pq01_deg_r.csv"
        assert all(Path(p).exists() for p in out.values())


def test_run_recipe_still_fixed_temp():
    """ヒートマップなし（固定温度）: IP設計者レビュー2 (2)。"""
    with tempfile.TemporaryDirectory() as d:
        r = Recipe(recipe_name="pq01", input_image=_STILL, heatmap="",
                  heatmap_mode="fixed", fixed_temp_c=40.0)
        res = engine.run_recipe(recipe=r, folders=_folders(d), sequence_name="T",
                                nn="01", model=_model())
        assert res.frames_done == 1 and not res.stopped
        assert np.allclose(res.temp_kelvin, 40.0 + 273.0)   # パネル全面が固定温度


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
        out = engine.write_recipe_outputs(result=res, folders=_folders(d),
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
    assert engine.format_aging(3600) == "1.00 h"
    assert engine.format_aging(0) == "0.00 h"
    assert "day" in engine.format_aging(3600 * 100)


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
