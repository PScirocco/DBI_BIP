"""model.py のテスト（仕様 3）"""
from __future__ import annotations

import tempfile
from pathlib import Path

from bisim.model import (
    DEFAULT_MODEL, MODEL_KEYS, SIM_KEYS, AppConfig, Recipe, Sequence,
)


def test_recipe_defaults():
    r = Recipe()
    assert set(r.model_param) == set(MODEL_KEYS)
    assert all(len(r.model_param[k]) == 3 for k in MODEL_KEYS)
    assert set(r.sim_param) == set(SIM_KEYS)
    assert r.init_stress == "none"
    # 既定はインスタンス間で共有されない
    r2 = Recipe()
    r.model_param["N"][0] = 99.0
    assert r2.model_param["N"][0] == DEFAULT_MODEL["N"][0]


def test_recipe_kind():
    assert Recipe(input_image="a.mp4").kind == "aging"
    assert Recipe(input_image="a.png").kind == "pq"
    assert Recipe(input_image="").kind == "unknown"
    assert Recipe(input_image="a.MP4").kind == "aging"


def test_recipe_roundtrip():
    r = Recipe(recipe_name="日本語01", input_image="x.mp4", heatmap="x_ht.mp4",
               model_param_csv="x_model-param.csv", init_stress="prev")
    r.model_param["K0"] = [1.0, 2.0, 3.0]
    r2 = Recipe.from_dict(r.to_dict())
    assert r2.to_dict() == r.to_dict()
    assert r2.recipe_name == "日本語01"
    assert r2.model_param["K0"] == [1.0, 2.0, 3.0]


def test_recipe_from_dict_lenient():
    r = Recipe.from_dict({"recipe_name": "r", "model_param": {"N": [1, 2, 3]},
                          "init_stress": "bogus", "sim_param": {"TMP_H": 70}})
    assert r.model_param["N"] == [1.0, 2.0, 3.0]
    assert r.model_param["K0"] == DEFAULT_MODEL["K0"]      # 欠けは既定で補完
    assert r.init_stress == "none"                          # 不正値は none
    assert r.sim_param["TMP_H"] == 70.0
    assert "AGING_TIME" in r.sim_param


def test_recipe_validate():
    assert Recipe(recipe_name="ok").validate() == []
    bad = Recipe(recipe_name="", init_stress="file")
    probs = bad.validate()
    assert any("recipe_name" in p for p in probs)
    assert any("init_stress_files" in p for p in probs)


def test_recipe_save_load():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.recipe.json"
        r = Recipe(recipe_name="レシピA", input_image="m.mp4")
        r.save(p)
        assert "レシピA" in p.read_text(encoding="utf-8")   # ensure_ascii=False
        assert Recipe.load(p).to_dict() == r.to_dict()


def test_sequence_recipe_number():
    assert Sequence.recipe_number(0) == "01"
    assert Sequence.recipe_number(9) == "10"
    assert Sequence.recipe_number(98) == "99"


def test_sequence_roundtrip():
    s = Sequence(sequence_name="SEQ-A")
    s.recipes = [Recipe(recipe_name="a", input_image="a.mp4"),
                 Recipe(recipe_name="b", input_image="b.png", init_stress="prev")]
    s.folders["output"] = r"C:\out"
    s2 = Sequence.from_dict(s.to_dict())
    assert s2.to_dict() == s.to_dict()
    assert len(s2.recipes) == 2
    assert s2.recipes[1].init_stress == "prev"
    assert s2.folders["output"] == r"C:\out"


def test_sequence_save_load():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.seq.json"
        s = Sequence(sequence_name="連番シーケンス")
        s.recipes = [Recipe(recipe_name="r1", input_image="r1.mp4")]
        s.save(p)
        assert Sequence.load(p).to_dict() == s.to_dict()


def test_appconfig_default_folders():
    c = AppConfig()
    assert c.default_folders == {} and "default_folders" not in c.to_dict()
    c.default_folders = {"output": r"C:\out", "bogus": "x"}
    d = c.to_dict()
    assert d["default_folders"] == {"output": r"C:\out"}      # 未知キーは落ちる
    assert AppConfig.from_dict(d).default_folders == {"output": r"C:\out"}


def test_appconfig():
    c = AppConfig()
    assert c.log_max_mb == 50.0 and c.language == "en"
    c2 = AppConfig.from_dict({"log_max_mb": "120", "language": "ja"})
    assert c2.log_max_mb == 120.0 and c2.language == "ja"
    c3 = AppConfig.from_dict({"language": "fr", "log_max_mb": "x"})
    assert c3.language == "en" and c3.log_max_mb == 50.0     # 不正値は既定


def test_appconfig_save_load():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bisim_app.json"
        assert AppConfig.load_or_default(p).to_dict() == AppConfig().to_dict()
        AppConfig(log_max_mb=200.0).save(p)
        assert AppConfig.load_or_default(p).log_max_mb == 200.0
