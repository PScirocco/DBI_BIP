"""paramio.py のテスト（CLI版 CSV との互換）"""
from __future__ import annotations

import tempfile
from pathlib import Path

from bisim import paramio
from bisim.model import DEFAULT_SIM, _fresh_sim
from bisim.paths import SOURCE_DIR


def test_read_real_model_csv():
    m = paramio.read_model_csv(SOURCE_DIR / "dbi_conf" / "degparam_mm.csv")
    assert m["N"] == [1.5, 1.3, 1.7]
    assert m["K0"] == [500.0, 1000.0, 100.0]
    assert m["B0"] == [0.7, 0.8, 0.4]
    assert m["A"] == [0.0, 0.0, 0.0]


def test_read_real_sim_csv():
    # 新コア（フェーズF）の標準ファイル（DPK_ON・GADJ は決定済みの既定値に書き換えたもの。2026-11-18）
    s = paramio.read_sim_csv(SOURCE_DIR / "dbi_input" / "simconf.csv")
    assert s["ACCEL_RATIO"] == 30000.0
    assert s["TMP_L"] == 25.0 and s["TMP_H"] == 60.0
    assert s["AGING_TIME"] == 10.0
    assert s["DBV_NIT"] == 2000.0 and s["DPK_ON"] == 0 and s["GADJ"] == [1.0, 1.0, 1.0]


def test_model_csv_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "aging01_model-param.csv"
        src = {"N": [1.5, 1.3, 1.7], "K0": [500.0, 1000.0, 100.0],
               "Q": [1000.0, 800.0, 600.0], "B0": [0.7, 0.8, 0.4], "A": [0.0, 0.0, 0.0]}
        paramio.write_model_csv(p, src)
        text = p.read_text(encoding="utf-8")
        assert text.splitlines()[0] == "N,1.5,1.3,1.7"
        assert paramio.read_model_csv(p) == src


def test_sim_csv_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "aging01_sim-param.csv"
        paramio.write_sim_csv(p, dict(DEFAULT_SIM))
        lines = p.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "AGING_TIME,0"
        assert lines[-3:] == ["DBV_NIT,2000", "DPK_ON,0", "GADJ,1,1,1"]
        assert paramio.read_sim_csv(p) == dict(DEFAULT_SIM)
        sim = _fresh_sim()
        sim.update(DBV_NIT=600.0, DPK_ON=1, GADJ=[1.1, 1.0, 0.95])
        paramio.write_sim_csv(p, sim)
        assert paramio.read_sim_csv(p) == sim


def test_sim_csv_compatible_with_core_loader():
    """bisim が書いた Sim 条件 CSV を、新コアの load_simconf がそのまま読めること（simconf.csv 互換）。"""
    from bisim import engine
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sim.csv"
        sim = _fresh_sim()
        sim.update(DBV_NIT=600.0, DPK_ON=1, GADJ=[1.1, 1.0, 0.95], ACCEL_RATIO=3600.0)
        paramio.write_sim_csv(p, sim)
        rc, core = engine._load_core().com_info.load_simconf(str(p))
        assert rc == 0
        assert core == engine.core_sim_dict(sim)


def test_sim_csv_old_format_and_errors():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "old.csv"
        p.write_text("AGING_TIME,5\nACCEL_RATIO,100\nTMP_L,20\nTMP_H,50\n", encoding="utf-8")
        s = paramio.read_sim_csv(p)                  # 旧形式（4項目）：新3項目は既定値
        assert s["ACCEL_RATIO"] == 100.0 and s["GADJ"] == [1.0, 1.0, 1.0] and s["DPK_ON"] == 0
        p.write_text("GADJ,1.1,1.0\n", encoding="utf-8")
        try:
            paramio.read_sim_csv(p)
        except ValueError:
            pass
        else:
            raise AssertionError("GADJ の値が3つでなければ ValueError")


def test_to_mm_dict():
    d = paramio.to_mm_dict({"N": [1.5, 1.3, 1.7], "K0": [1, 2, 3],
                            "Q": [4, 5, 6], "B0": [0.7, 0.8, 0.4], "A": [0, 0, 0]})
    assert d["N_r"] == 1.5 and d["N_g"] == 1.3 and d["N_b"] == 1.7
    assert d["K0_b"] == 3.0
    assert set(d) == {f"{k}_{c}" for k in ("N", "K0", "Q", "B0", "A") for c in "rgb"}
