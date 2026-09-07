"""paramio.py のテスト（CLI版 CSV との互換）"""
from __future__ import annotations

import tempfile
from pathlib import Path

from bisim import paramio
from bisim.model import DEFAULT_SIM
from bisim.paths import SOURCE_DIR


def test_read_real_model_csv():
    m = paramio.read_model_csv(SOURCE_DIR / "dbi_conf" / "degparam_mm.csv")
    assert m["N"] == [1.5, 1.3, 1.7]
    assert m["K0"] == [500.0, 1000.0, 100.0]
    assert m["B0"] == [0.7, 0.8, 0.4]
    assert m["A"] == [0.0, 0.0, 0.0]


def test_read_real_sim_csv():
    s = paramio.read_sim_csv(SOURCE_DIR / "dbi_conf" / "simconf.csv")
    assert s["ACCEL_RATIO"] == 30000.0
    assert s["TMP_L"] == 25.0 and s["TMP_H"] == 60.0
    assert s["AGING_TIME"] == 10.0


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
        assert lines[0] == "AGING_TIME,10"
        assert paramio.read_sim_csv(p) == dict(DEFAULT_SIM)


def test_to_mm_dict():
    d = paramio.to_mm_dict({"N": [1.5, 1.3, 1.7], "K0": [1, 2, 3],
                            "Q": [4, 5, 6], "B0": [0.7, 0.8, 0.4], "A": [0, 0, 0]})
    assert d["N_r"] == 1.5 and d["N_g"] == 1.3 and d["N_b"] == 1.7
    assert d["K0_b"] == 3.0
    assert set(d) == {f"{k}_{c}" for k in ("N", "K0", "Q", "B0", "A") for c in "rgb"}
