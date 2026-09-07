"""engine.py のテスト（実データ・実コアを使う統合テスト）"""
from __future__ import annotations

import tempfile
from pathlib import Path

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

        out = engine.write_recipe_outputs(result=res, folders=_folders(d),
                                          sequence_name="T", model=_model(),
                                          model_param=r.model_param,
                                          stopped_at="260904-1430")
        assert Path(out["stat_r"]).name == "T_01_aging01_stat_r_260904-1430.csv"


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
