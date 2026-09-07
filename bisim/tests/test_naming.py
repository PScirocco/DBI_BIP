"""naming.py のテスト（仕様 4）"""
from __future__ import annotations

from datetime import datetime

from bisim import naming


def test_sanitize_name():
    assert naming.sanitize_name("aging_01") == "aging-01"
    assert naming.sanitize_name("PQ 評価") == "PQ-評価"
    assert naming.sanitize_name('a/b:c*d') == "a-b-c-d"
    assert naming.sanitize_name("  --x--  ") == "x"
    assert naming.sanitize_name("") == "unnamed"
    assert naming.sanitize_name("日本語レシピ") == "日本語レシピ"


def test_timestamp_format():
    ts = naming.timestamp(datetime(2026, 9, 4, 14, 30))
    assert ts == "260904-1430"
    assert naming._TS_RE.fullmatch(ts)


def test_stop_state_name():
    n = naming.stop_state_name("SEQ A", 1, "aging_01", "260904-1430")
    assert n == "SEQ-A_01_aging-01_resume_260904-1430.json"
    # 再開サイドカーは出力ファイルと取り違えない
    assert naming.parse_output(n) is None
    try:
        naming.stop_state_name("S", 1, "r", "bad-ts")
    except ValueError:
        pass
    else:
        raise AssertionError("不正な日時トークンで ValueError が出るべき")


def test_input_name():
    assert naming.input_name("aging01", "movie", ext="mp4") == "aging01_movie.mp4"
    assert naming.input_name("aging01", "model-param") == "aging01_model-param.csv"
    assert naming.input_name("r01", "deg", "r") == "r01_deg_r.csv"
    assert naming.input_name("pq eval", "image", ext=".png") == "pq-eval_image.png"


def test_output_name():
    assert naming.output_name("SEQ-A", 1, "aging01", "deg", "r") == "SEQ-A_01_aging01_deg_r.csv"
    assert naming.output_name("SEQ-A", 3, "aging01", "movie", ext="mp4") == "SEQ-A_03_aging01_movie.mp4"
    assert naming.output_name("SEQ-A", "07", "aging01", "stat", "b") == "SEQ-A_07_aging01_stat_b.csv"


def test_output_name_stopped():
    got = naming.output_name("SEQ-A", 1, "aging01", "stat", "r", stopped_at="260904-1430")
    assert got == "SEQ-A_01_aging01_stat_r_260904-1430.csv"
    got2 = naming.output_name("SEQ-A", 2, "pq01", "deg", "g",
                              stopped_at=datetime(2026, 9, 4, 9, 5))
    assert got2 == "SEQ-A_02_pq01_deg_g_260904-0905.csv"


def test_output_name_rejects_bad():
    for bad in [lambda: naming.output_name("S", 1, "r", "bogus"),
                lambda: naming.output_name("S", 1, "r", "deg", "x"),
                lambda: naming.output_name("S", 1, "r", "deg", stopped_at="2026-09-04")]:
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("ValueError が出るべき")


def test_parse_output():
    assert naming.parse_output("SEQ-A_01_aging01_deg_r.csv") == {
        "sequence": "SEQ-A", "nn": "01", "recipe": "aging01",
        "kind": "deg", "color": "r", "timestamp": None, "ext": "csv"}
    assert naming.parse_output("SEQ-A_03_aging01_movie.mp4") == {
        "sequence": "SEQ-A", "nn": "03", "recipe": "aging01",
        "kind": "movie", "color": None, "timestamp": None, "ext": "mp4"}
    assert naming.parse_output("SEQ-A_01_aging01_stat_r_260904-1430.csv") == {
        "sequence": "SEQ-A", "nn": "01", "recipe": "aging01",
        "kind": "stat", "color": "r", "timestamp": "260904-1430", "ext": "csv"}
    assert naming.parse_output("aging01_movie.mp4") is None       # 入力名
    assert naming.parse_output("garbage.txt") is None
    assert naming.parse_output("SEQ_01_r_kimchi_x.csv") is None   # 未知種別


def test_parse_input():
    assert naming.parse_input("aging01_movie.mp4") == {
        "recipe": "aging01", "kind": "movie", "color": None, "ext": "mp4"}
    assert naming.parse_input("r01_deg_r.csv") == {
        "recipe": "r01", "kind": "deg", "color": "r", "ext": "csv"}
    assert naming.parse_input("SEQ-A_01_aging01_deg_r.csv") is None   # 出力名


def test_roundtrip_output():
    for name in ["SEQ-A_01_aging01_deg_r.csv",
                 "SEQ-A_12_pq-eval_stat_b_260904-1430.csv",
                 "myseq_05_recipeX_movie.mp4"]:
        p = naming.parse_output(name)
        rebuilt = naming.output_name(p["sequence"], p["nn"], p["recipe"], p["kind"],
                                     p["color"], ext=p["ext"], stopped_at=p["timestamp"])
        assert rebuilt == name, (name, rebuilt)
