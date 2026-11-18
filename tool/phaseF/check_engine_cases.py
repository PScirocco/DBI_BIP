r"""手順4の確認（2026-11-18）: 松井さんの11ケースを bisim のエンジン（run_recipe → write_recipe_outputs）で実行し、
松井さんの dbi_output と stat・deg・出力画像を比べる。deg2 の CSV が出ていることも確認する。
テストステップは「Aging・静止画（fps=1 → 1フレーム=1秒×ACCEL_RATIO）」で流す（松井さんの1秒分と同じ条件）。

実行（Burn-In_Simv2 直下）:
  bisim2\.venv\Scripts\python -I tool\phaseF\check_engine_cases.py bisim2 receive\Burn_in_sim_core_01 <出力フォルダ>
receive/ には書き込まない（出力は <出力フォルダ> に P4_NN_cNN_*.csv/png）。
"""
import sys, re, time
from pathlib import Path
import numpy as np
bisim2, recv, out = map(Path, sys.argv[1:4])
sys.path.insert(0, str(bisim2))
from bisim import engine, imio
from bisim.model import Recipe
model = engine.CoreModel(bcset_path=recv/"dbi_conf/bcsetting.csv", sm_path=recv/"dbi_conf/degparam_sm.csv")
ci = model._core.com_info
_, mm = ci.load_degparam_mm(str(recv/"dbi_conf/degparam_mm.csv"))
model_param = {k: [mm[f"{k}_{c}"] for c in "rgb"] for k in ["N","K0","Q","B0","A"]}
folders = {"input_image": str(recv/"dbi_common"), "heatmap": str(recv/"dbi_common"), "output": str(out)}
cases = []
for line in (recv/"eval_exec_debug.bat").read_text().splitlines():
    if line.startswith("python"):
        a = line.split()[2:]
        cases.append(dict(img=a[0], ht=a[1], sim=a[5], ini=a[6:9], ini_en=a[9], idx=a[11]))
ok_all = True
for cs in cases:
    _, sim = ci.load_simconf(str(recv/"dbi_input"/cs["sim"]))
    sim["AGING_TIME"] = 0.0
    r = Recipe(recipe_name=f"c{cs['idx']}", input_image=cs["img"], heatmap=cs["ht"],
               model_param=model_param, sim_param=sim, step_type="aging")
    init = None
    if cs["ini_en"] == "1":
        pre = [out / f"P4_{int(cs['ini'][0].split('_')[0]):02d}_c{cs['ini'][0].split('_')[0]}_stat_{c}.csv" for c in "rgb"]
        init = engine.StressState.load(*pre)
    t = time.time()
    res = engine.run_recipe(recipe=r, folders=folders, sequence_name="P4", nn=f"{int(cs['idx']):02d}", model=model, initial_state=init)
    o = engine.write_recipe_outputs(result=res, folders=folders, sequence_name="P4", model=model, model_param=model_param)
    ref = recv/"dbi_output"
    d = {}
    for c in "rgb":
        d[f"stat_{c}"] = np.max(np.abs(np.loadtxt(o[f"stat_{c}"], delimiter=",") - np.loadtxt(ref/f"{cs['idx']}_stat_{c}.csv", delimiter=",")))
        d[f"deg_{c}"] = np.max(np.abs(np.loadtxt(o[f"deg_{c}"], delimiter=",") - np.loadtxt(ref/f"{cs['idx']}_deg_{c}.csv", delimiter=",")))
    im = np.max(np.abs(imio.imread(o["image"]).astype(int) - imio.imread(ref/f"{cs['idx']}_out_img.png").astype(int)))
    worst = max(d.values())
    ok = worst == 0 and im == 0 and "deg2_r" in o
    ok_all &= ok
    print(f"case {cs['idx']:>2} {cs['sim']:<28} stat/deg 最大差={worst:.3g} 画像 最大差={im} deg2出力={'deg2_r' in o} {time.time()-t:.1f}s {'OK' if ok else 'NG'}")
print("ALL OK" if ok_all else "NG あり")
