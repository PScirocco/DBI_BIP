r"""手順6（結合試験）の準備（2026-11-18）: 松井さんの動作確認（11 ケース、
`material/Core Part in simulator_brief confirmation result.pptx`）を bisim のシーケンスとして作る。

作るもの（`<bisim2>/eval_test/phaseF_integ/`。Git 管理外）:
  input/      テスト画像・ヒートマップ・動画（受領物 dbi_common からコピー）
  conf/       bcsetting.csv・degparam_mm.csv・degparam_sm.csv（受領物 dbi_conf からコピー）
  simconf/    使う simconf_*.csv（受領物 dbi_input からコピー）
  reference/matsui_dbi_output/  松井さんの結果（受領物 dbi_output の 1〜11）
  reference/pptx/               スライドの画像と、どのケースの結果か（pptx_map.json）
  reference/movie_cli/          動画を CLI（burn_in）で実行した結果（--cli-ref のとき作る。idx=20）
  integ-cases.seq.json     11 ケース（テストステップは「Aging・ACCEL_RATIO=1」＝1フレーム1秒）
  integ-cases-pq.seq.json  同じ（テストステップを PQ評価＝ストレスを貯めない）。参考
  integ-movie.seq.json     動画 480×270・405 フレーム（DBV 2000・AGING_TIME=0＝1周回）
  integ-timing.seq.json    計算時間用：動画 1920×1080 を 30 フレーム（AGING_TIME=3000 秒）

ケース3 はケース1 の stat から分かれる（ケース2 からではない）。シーケンスは一本道なので、
ケース1 の Aging をもう一度実行してから（同じ計算なので同じ stat）ケース3 を「前ステップ継承」で流す。
→ ステップは 12 個。フォルダはシーケンスファイルから見た相対パス（このフォルダごと、どこへ・別PCへコピーしても開ける）。

実行（Burn-In_Simv2 直下）:
  bisim2\.venv\Scripts\python -I tool\phaseF\make_integ_seq.py bisim2 receive\Burn_in_sim_core_01 ^
      "material\Core Part in simulator_brief confirmation result.pptx" [--cli-ref]
receive/ には書き込まない（CLI は一時フォルダにコピーして実行）。
"""
import io, json, shutil, subprocess, sys, tempfile
from pathlib import Path

import numpy as np

args = [a for a in sys.argv[1:] if not a.startswith("--")]
bisim2, recv, pptx_path = Path(args[0]).resolve(), Path(args[1]).resolve(), Path(args[2]).resolve()
cli_ref = "--cli-ref" in sys.argv
sys.path.insert(0, str(bisim2))
from bisim import imio, paramio
from bisim.model import PanelConfig, Recipe, Sequence

REL = "eval_test/phaseF_integ"
root = bisim2 / REL
for d in ("input", "conf", "simconf", "reference/matsui_dbi_output", "reference/pptx"):
    (root / d).mkdir(parents=True, exist_ok=True)

# ---- 松井さんの 11 ケース（eval_exec_debug.bat）----
cases = []
for line in (recv / "eval_exec_debug.bat").read_text().splitlines():
    if line.startswith("python"):
        a = line.split()[2:]
        cases.append(dict(img=a[0], ht=a[1], sim=a[5], ini=a[6], ini_en=a[9] == "1", idx=int(a[11])))
assert len(cases) == 11, cases

# ---- コピー ----
movies = ["mov_001_480x270.mp4", "mov_ht_001_480x270.mp4", "mov_001.mp4", "mov_ht_001.mp4"]
for name in sorted({c["img"] for c in cases} | {c["ht"] for c in cases} | set(movies)):
    shutil.copy2(recv / "dbi_common" / name, root / "input" / name)
for name in ("bcsetting.csv", "degparam_mm.csv", "degparam_sm.csv"):
    shutil.copy2(recv / "dbi_conf" / name, root / "conf" / name)
for name in sorted({c["sim"] for c in cases}):
    shutil.copy2(recv / "dbi_input" / name, root / "simconf" / name)
for c in cases:
    for f in (recv / "dbi_output").glob(f"{c['idx']}_*"):
        shutil.copy2(f, root / "reference/matsui_dbi_output" / f.name)

# ---- スライドの画像：どのケースの結果か（画素が完全に一致するもの）----
from pptx import Presentation
from PIL import Image
outs = {c["idx"]: imio.imread(recv / "dbi_output" / f"{c['idx']}_out_img.png") for c in cases}
test_idx = [c["idx"] for c in cases if c["ini_en"]]          # テストステップ（結果がスライドに載っている）
pmap = []
for si, slide in enumerate(Presentation(str(pptx_path)).slides, 1):
    for sh in slide.shapes:
        if sh.shape_type != 13:
            continue
        rgb = np.array(Image.open(io.BytesIO(sh.image.blob)).convert("RGB"))
        bgr = rgb[:, :, ::-1]
        hit = [i for i in test_idx if outs[i].shape == bgr.shape and np.array_equal(outs[i], bgr)]
        if not hit:
            continue                                         # 入力パターン（Aging/Test pattern）の画像
        name = f"slide{si}_{sh.name.replace(' ', '')}.png"
        imio.imwrite(root / "reference/pptx" / name, bgr)
        pmap.append(dict(file=name, slide=si, case=hit[0]))
(root / "reference/pptx/pptx_map.json").write_text(json.dumps(pmap, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"スライドの結果画像: {len(pmap)} 枚 → ケース {sorted(p['case'] for p in pmap)}")

# ---- シーケンス ----
# フォルダはシーケンスファイル（phaseF_integ/）から見た相対パス（2026-11-19〜。"folders_base": "sequence"）
folders = {"input_image": "input", "heatmap": "input", "bcset": "conf", "model": "conf", "simconf": "simconf"}
panel = PanelConfig(bcsetting="bcsetting.csv", degparam_sm="degparam_sm.csv",
                    model_param=paramio.read_model_csv(root / "conf/degparam_mm.csv"),
                    model_param_csv="degparam_mm.csv")


def recipe(name, img, ht, sim_csv, init, step_type, aging_time=None):
    sim = paramio.read_sim_csv(root / "simconf" / sim_csv)
    if aging_time is not None:
        sim["AGING_TIME"] = float(aging_time)
    return Recipe(recipe_name=name, input_image=img, heatmap=ht, heatmap_mode="file",
                  sim_param=sim, sim_param_csv=sim_csv, init_stress=init, step_type=step_type)


def save(seq_name, recipes, steps_info):
    seq = Sequence(sequence_name=seq_name, recipes=recipes, panel=panel)
    d = seq.to_dict()
    d["folders"] = dict(folders, output=f"output/{seq_name}")           # 相対パスのまま保存
    d["folders_base"] = "sequence"
    (root / f"{seq_name}.seq.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / f"{seq_name}.steps.json").write_text(json.dumps(steps_info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{seq_name}.seq.json: {len(recipes)} ステップ")


def case_name(c):
    kind = "test" if c["ini_en"] else "aging"
    return f"c{c['idx']:02d}-{kind}" + c["sim"].replace("simconf_", "").replace(".csv", "").replace(
        "_aging", "").replace("_test", "").replace("_", "-")


by_idx = {c["idx"]: c for c in cases}
for seq_name, test_type in (("integ-cases", "aging"), ("integ-cases-pq", "eval")):
    recipes, info = [], []
    for c in cases:
        if c["ini_en"]:
            src = int(c["ini"].split("_")[0])                # 初期ストレスにするケース
            if info[-1]["case"] != src:                      # 直前がそのケースでなければ、もう一度実行
                s = by_idx[src]
                recipes.append(recipe(case_name(s) + "-again", s["img"], s["ht"], s["sim"], "none", "aging"))
                info.append(dict(nn=len(recipes), case=src, again=True))
            recipes.append(recipe(case_name(c), c["img"], c["ht"], c["sim"], "prev", test_type))
        else:
            recipes.append(recipe(case_name(c), c["img"], c["ht"], c["sim"], "none", "aging"))
        info.append(dict(nn=len(recipes), case=c["idx"], again=False))
    save(seq_name, recipes, info)

save("integ-movie", [recipe("mov480-aging2000", "mov_001_480x270.mp4", "mov_ht_001_480x270.mp4",
                            "simconf_2000_aging.csv", "none", "aging", aging_time=0)],
     [dict(nn=1, case=20, again=False)])
save("integ-timing", [recipe("movFHD-aging2000-30f", "mov_001.mp4", "mov_ht_001.mp4",
                             "simconf_2000_aging.csv", "none", "aging", aging_time=3000)],
     [dict(nn=1, case=None, again=False)])

# ---- 動画を CLI（burn_in）で実行した結果（比べる相手）----
if cli_ref:
    work = Path(tempfile.mkdtemp(prefix="integ_cli_"))
    for n in ("main.py", "load_com_info.py"):
        shutil.copy2(bisim2 / "source" / n, work / n)      # bisim が使うコア（受領物＋bisim 側の追加）
    for d in ("dbi_common", "dbi_conf", "dbi_input", "dbi_output"):
        (work / d).mkdir()
    for n in movies[:2]:
        shutil.copy2(root / "input" / n, work / "dbi_common" / n)
    for n in ("bcsetting.csv", "degparam_mm.csv", "degparam_sm.csv"):
        shutil.copy2(root / "conf" / n, work / "dbi_conf" / n)
    shutil.copy2(root / "simconf/simconf_2000_aging.csv", work / "dbi_input/simconf_2000_aging.csv")
    cmd = [sys.executable, "main.py", movies[0], movies[1], "bcsetting.csv", "degparam_mm.csv",
           "degparam_sm.csv", "simconf_2000_aging.csv", "0", "0", "0", "0", "0", "20"]
    import time
    t = time.time()
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    print(f"CLI: 終了コード {r.returncode}、{time.time() - t:.0f} 秒")
    dst = root / "reference/movie_cli"
    dst.mkdir(parents=True, exist_ok=True)
    for f in (work / "dbi_output").glob("20_*"):
        shutil.copy2(f, dst / f.name)
    print("CLI の出力:", sorted(f.name for f in dst.iterdir()))
    shutil.rmtree(work, ignore_errors=True)
