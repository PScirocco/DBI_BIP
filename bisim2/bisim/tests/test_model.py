"""model.py のテスト（仕様 3）"""
from __future__ import annotations

import tempfile
from pathlib import Path

from bisim.model import (
    DEFAULT_MODEL, DEFAULT_SIM, SIM_KEYS, AppConfig, PanelConfig, Recipe, Sequence,
    StopState,
)
from bisim.paths import STD_BCSET, STD_DEGPARAM_SM


def test_recipe_defaults():
    r = Recipe()
    assert not hasattr(r, "model_param")       # mm はシーケンスのパネル設定へ（フェーズF）
    assert set(r.sim_param) == set(SIM_KEYS)
    assert r.sim_param["DBV_NIT"] == 2000.0 and r.sim_param["DPK_ON"] == 0
    assert r.sim_param["GADJ"] == [1.0, 1.0, 1.0]
    assert r.sm_override == ""
    assert r.init_stress == "none"
    assert r.heatmap_mode == "file" and r.fixed_temp_c == 25.0
    assert r.validate() == []
    # 既定はインスタンス間で共有されない（GADJ のリストも）
    r2 = Recipe()
    r.sim_param["GADJ"][0] = 9.0
    assert r2.sim_param["GADJ"][0] == 1.0 and DEFAULT_SIM["GADJ"][0] == 1.0


def test_recipe_fixed_heatmap_roundtrip():
    r = Recipe(recipe_name="pq01", input_image="a.png", heatmap="",
              heatmap_mode="fixed", fixed_temp_c=40.0)
    r2 = Recipe.from_dict(r.to_dict())
    assert r2.to_dict() == r.to_dict()
    assert r2.heatmap_mode == "fixed" and r2.fixed_temp_c == 40.0
    assert r.validate() == []


def test_recipe_from_dict_lenient_heatmap_mode():
    r = Recipe.from_dict({"recipe_name": "r", "heatmap_mode": "bogus",
                          "fixed_temp_c": "not-a-number"})
    assert r.heatmap_mode == "file"          # 不正値は既定にフォールバック
    assert r.fixed_temp_c == 25.0


def test_recipe_kind_defaults_from_extension():
    """種別を指定しないと拡張子から決める（旧仕様の自動判定と同じ）。"""
    assert Recipe(input_image="a.mp4").kind == "aging"
    assert Recipe(input_image="a.png").kind == "eval"
    assert Recipe(input_image="").kind == "aging"
    assert Recipe(input_image="a.MP4").kind == "aging"
    assert Recipe(input_image="a.PNG").is_eval


def test_recipe_step_type_is_manual():
    """種別は手動で決められ、入力ファイルの種類とは独立（2026-10-19 決定）。"""
    still_aging = Recipe(input_image="logo.png", step_type="aging")
    movie_eval = Recipe(input_image="clip.mp4", step_type="eval")
    assert still_aging.kind == "aging" and not still_aging.is_eval
    assert movie_eval.kind == "eval" and movie_eval.is_eval
    # 保存・読込で種別が保たれる（拡張子に引きずられない）
    assert Recipe.from_dict(still_aging.to_dict()).step_type == "aging"
    assert Recipe.from_dict(movie_eval.to_dict()).step_type == "eval"
    assert still_aging.to_dict()["step_type"] == "aging"
    # 後から入力ファイルを差し替えても種別は変わらない
    still_aging.input_image = "other.png"
    assert still_aging.step_type == "aging"
    bad = Recipe(input_image="a.mp4")
    bad.step_type = "bogus"
    assert any("step_type" in p for p in bad.validate())


def test_sequence_relative_folders_resolve_against_app_dir():
    """シーケンスの folders は相対パスでもよい。基準は APP_DIR（EXE では bisim.exe のフォルダ、
    開発時はリポジトリ直下）。シーケンスファイル自体はどこに置いてもよい。"""
    import json
    import tempfile
    from bisim.paths import APP_DIR, DEFAULT_FOLDERS
    with tempfile.TemporaryDirectory() as d:
        absdir = str(Path(d).resolve() / "abs_out")
        (Path(d) / "t.seq.json").write_text(json.dumps({
            "sequence_name": "t",
            "folders": {"input_image": "eval_test/rgbcircle/input", "heatmap": "eval_test/../ht",
                        "output": absdir},
            "recipes": []}), encoding="utf-8")
        s = Sequence.load(Path(d) / "t.seq.json")
        assert Path(s.folders["input_image"]) == (APP_DIR / "eval_test" / "rgbcircle" / "input").resolve()
        assert Path(s.folders["heatmap"]) == (APP_DIR / "ht").resolve()
        assert s.folders["output"] == absdir                      # 絶対パスはそのまま
        assert s.folders["model"] == str(DEFAULT_FOLDERS["model"])  # 書かれていない欄はそのPCの既定


def test_recipe_from_old_json_without_step_type():
    """種別の欄が無い旧シーケンス JSON は拡張子から決める（従来と同じ動作）。"""
    assert Recipe.from_dict({"recipe_name": "a", "input_image": "x.mp4"}).step_type == "aging"
    assert Recipe.from_dict({"recipe_name": "p", "input_image": "x.png"}).step_type == "eval"
    assert Recipe.from_dict({"recipe_name": "p", "input_image": "x.png",
                             "step_type": "bogus"}).step_type == "eval"


def test_recipe_roundtrip():
    r = Recipe(recipe_name="日本語01", input_image="x.mp4", heatmap="x_ht.mp4",
               init_stress="prev", sm_override="sm_alt.csv")
    r.sim_param.update(DBV_NIT=600.0, DPK_ON=1, GADJ=[1.1, 1.0, 0.9])
    r2 = Recipe.from_dict(r.to_dict())
    assert r2.to_dict() == r.to_dict()
    assert r2.recipe_name == "日本語01" and r2.sm_override == "sm_alt.csv"
    assert r2.sim_param["DPK_ON"] == 1 and r2.sim_param["GADJ"] == [1.1, 1.0, 0.9]


def test_recipe_from_dict_lenient():
    r = Recipe.from_dict({"recipe_name": "r", "model_param": {"N": [1, 2, 3]},
                          "init_stress": "bogus",
                          "sim_param": {"TMP_H": 70, "DPK_ON": 5, "GADJ": [1, 2]}})
    assert "model_param" not in r.to_dict()                 # 旧 JSON の mm はレシピには残らない
    assert r.init_stress == "none"                          # 不正値は none
    assert r.sim_param["TMP_H"] == 70.0
    assert r.sim_param["DPK_ON"] == 0                       # 不正値（0/1 以外）は既定値
    assert r.sim_param["GADJ"] == [1.0, 1.0, 1.0]           # 3つでない → 既定値
    assert "AGING_TIME" in r.sim_param and "DBV_NIT" in r.sim_param   # 旧 JSON（4項目）も補完


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


def test_stopstate_roundtrip():
    st = StopState(recipe_name="日本語01", frames_done=42, frames_total=405,
                   aging_seconds=12345.6, is_movie=True, timestamp="260909-1030",
                   dir="_stops/SEQ_01_aging01")
    assert StopState.from_dict(st.to_dict()).to_dict() == st.to_dict()
    assert StopState.from_dict(st.to_dict()) == st


def test_sequence_stops_roundtrip():
    s = Sequence(sequence_name="SEQ")
    s.recipes = [Recipe(recipe_name="aging01", input_image="a.mp4")]
    assert "stops" not in s.to_dict()                     # 空なら JSON に出さない
    s.stops["01"] = StopState(recipe_name="aging01", frames_done=3, frames_total=405,
                              aging_seconds=9.0, is_movie=True, timestamp="260909-1030",
                              dir="_stops/SEQ_01_aging01")
    d = s.to_dict()
    assert list(d["stops"]) == ["01"]
    s2 = Sequence.from_dict(d)
    assert s2.to_dict() == d
    assert s2.stops["01"].frames_done == 3 and s2.stops["01"].is_movie


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


# --------------------------------------------------------------------------- #
#  パネル設定（フェーズF 手順5-1）
# --------------------------------------------------------------------------- #
def test_panel_defaults_and_roundtrip():
    seq = Sequence()
    assert seq.panel.bcsetting == STD_BCSET.name and seq.panel.degparam_sm == STD_DEGPARAM_SM.name
    assert seq.panel.model_param == DEFAULT_MODEL
    seq.panel.model_param["K0"] = [1.0, 2.0, 3.0]
    assert Sequence().panel.model_param["K0"] == DEFAULT_MODEL["K0"]    # 共有されない
    seq.panel.bcsetting = "bc_unit7.csv"
    seq.panel.model_param_csv = "mm_typeA.csv"
    seq.recipes = [Recipe(recipe_name="a", input_image="a.mp4")]
    d = seq.to_dict()
    assert d["panel"]["bcsetting"] == "bc_unit7.csv"
    assert "model_param" not in d["recipes"][0]
    seq2 = Sequence.from_dict(d)
    assert seq2.panel == seq.panel and seq2.load_warnings == []
    assert PanelConfig.from_dict({}) == PanelConfig()


def test_sequence_panel_paths_and_sm_override():
    seq = Sequence(folders={"bcset": "C:/bc", "model": "C:/mdl"})
    seq.recipes = [Recipe(recipe_name="a"), Recipe(recipe_name="b", sm_override="sm_b.csv")]
    assert seq.bcset_path() == Path("C:/bc") / STD_BCSET.name
    assert seq.sm_path() == Path("C:/mdl") / STD_DEGPARAM_SM.name
    assert seq.sm_path(0) == seq.sm_path()                       # 差し替えなし
    assert seq.sm_path(1) == Path("C:/mdl") / "sm_b.csv"


def test_old_sequence_json_gets_standard_panel():
    """パネル設定の無い旧 JSON：標準ファイル・標準フォルダ、mm は1番目のステップ（違えば警告）。"""
    mm1 = {k: list(v) for k, v in DEFAULT_MODEL.items()}
    mm2 = dict(mm1, K0=[1.0, 2.0, 3.0])
    old = {"sequence_name": "old",
           "folders": {"bcset": "C:/old/bc", "model": "C:/old/model", "output": "C:/old/out"},
           "recipes": [{"recipe_name": "a", "model_param": mm2, "model_param_csv": "x.csv"},
                       {"recipe_name": "b", "model_param": mm1}]}
    seq = Sequence.from_dict(old)
    assert seq.panel.model_param["K0"] == [1.0, 2.0, 3.0]        # 1番目のステップの値
    assert seq.panel.model_param_csv == "x.csv"
    assert seq.panel.bcsetting == STD_BCSET.name
    assert seq.folders["bcset"] == str(STD_BCSET.parent)
    assert seq.folders["model"] == str(STD_DEGPARAM_SM.parent)
    assert seq.folders["output"] == "C:/old/out"                  # ほかのフォルダはそのまま
    assert len(seq.load_warnings) == 2 and "02" in seq.load_warnings[1]
    # 同じ mm なら警告は1件（標準ファイルを割り当てた旨）だけ
    old["recipes"][0]["model_param"] = mm1
    assert len(Sequence.from_dict(old).load_warnings) == 1


def test_use_standard_panel_folders_if_missing():
    with tempfile.TemporaryDirectory() as d:
        seq = Sequence(folders={"bcset": d, "model": d})
        msgs = seq.use_standard_panel_folders_if_missing()
        assert len(msgs) == 2
        assert seq.folders["bcset"] == str(STD_BCSET.parent)
        assert seq.folders["model"] == str(STD_DEGPARAM_SM.parent)
        # 標準と違う名前のファイルは勝手に切り替えない（無いことは①の検査で表示する）
        seq2 = Sequence(folders={"bcset": d, "model": d})
        seq2.panel.bcsetting = "bc_unit7.csv"
        seq2.use_standard_panel_folders_if_missing()
        assert seq2.folders["bcset"] == d and seq2.folders["model"] == str(STD_DEGPARAM_SM.parent)
