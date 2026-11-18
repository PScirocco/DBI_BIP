r"""手順6（結合試験）の比較（2026-11-18）。先に make_integ_seq.py で準備し、
run_seq_headless.py（または GUI）でシーケンスを実行しておく。

  cases     integ-cases の出力を、松井さんの dbi_output（stat・deg・出力画像）とスライドの画像と比べる。
            deg2 は「入力画像 × deg × deg2 → 出力画像」が再現できるか（CSV の deg2 が画像に使われた値か）
  pq        integ-cases-pq（テストステップ＝PQ評価）を同じ相手と比べる。参考（合否なし、差の大きさだけ）
  movie     integ-movie の stat・deg・deg2 を CLI（burn_in）の結果と比べる（mp4 は圧縮で値が変わるので比べない）

実行（Burn-In_Simv2 直下）:
  bisim2\.venv\Scripts\python -I tool\phaseF\check_integ.py bisim2 cases|pq|movie [<出力フォルダ>]
<出力フォルダ> を省くとシーケンスに書いた出力先（eval_test/phaseF_integ/output/<シーケンス名>）。
GUI や別PCで実行した結果を比べるときは、その出力フォルダを指定する。
"""
import json, sys
from pathlib import Path

import numpy as np

bisim2, mode = Path(sys.argv[1]).resolve(), sys.argv[2]
sys.path.insert(0, str(bisim2))
from bisim import imio

root = bisim2 / "eval_test/phaseF_integ"
seq_name = {"cases": "integ-cases", "pq": "integ-cases-pq", "movie": "integ-movie"}[mode]
out = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else root / "output" / seq_name
seq = json.loads((root / f"{seq_name}.seq.json").read_text(encoding="utf-8"))
steps = json.loads((root / f"{seq_name}.steps.json").read_text(encoding="utf-8"))


def find(nn, recipe, kind, color=None, ext="csv"):
    name = f"{seq_name}_{nn:02d}_{recipe}_{kind}" + (f"_{color}" if color else "") + f".{ext}"
    p = out / name
    if not p.is_file():
        raise SystemExit(f"出力がありません: {p}")
    return p


def csv(p):
    return np.loadtxt(p, delimiter=",")


def maxdiff(a, b):
    return float(np.max(np.abs(a - b)))


ok_all = True
if mode in ("cases", "pq"):
    ref = root / "reference/matsui_dbi_output"
    pmap = {p["case"]: p for p in json.loads((root / "reference/pptx/pptx_map.json").read_text(encoding="utf-8"))}
    print(f"出力: {out}")
    print("NN ケース 種別   stat最大差  deg最大差(R/G/B)                 画像最大差 スライド  deg2再現  判定")
    for st in steps:
        nn, case = st["nn"], st["case"]
        r = seq["recipes"][nn - 1]
        name = r["recipe_name"]
        d_stat = max(maxdiff(csv(find(nn, name, "stat", c)), csv(ref / f"{case}_stat_{c}.csv")) for c in "rgb")
        d_deg = [maxdiff(csv(find(nn, name, "deg", c)), csv(ref / f"{case}_deg_{c}.csv")) for c in "rgb"]
        img = imio.imread(find(nn, name, "image", ext="png")).astype(int)
        d_img = int(np.max(np.abs(img - imio.imread(ref / f"{case}_out_img.png").astype(int))))
        if case in pmap and not st["again"]:
            d_ppt = int(np.max(np.abs(img - imio.imread(root / "reference/pptx" / pmap[case]["file"]).astype(int))))
            s_ppt = f"{d_ppt}"
        else:
            d_ppt, s_ppt = 0, "-"
        # deg2 の再現（tool/phaseF/check_deg2.py と同じ式）：輝度（ガンマ 2.2）で 入力 × deg × deg2 → 切り捨て。
        # deg は burn_in_core の中と同じく「このステップを処理する前の stat」から β＝B0+A·(TMP_L+273) で計算
        mm = seq["panel"]["model_param"]
        tmpl = float(r["sim_param"]["TMP_L"]) + 273.0
        inp = imio.imread(root / "input" / r["input_image"]).astype(np.float64)
        rec = np.empty(inp.shape, dtype=np.uint8)
        for ch, k, c in ((2, 0, "r"), (1, 1, "g"), (0, 2, "b")):          # BGR
            if r["init_stress"] == "prev":
                prev = seq["recipes"][nn - 2]["recipe_name"]
                stat0 = csv(find(nn - 1, prev, "stat", c))
            else:
                stat0 = np.zeros(inp.shape[:2])
            deg0 = np.exp(-1.0 * stat0 ** (mm["B0"][k] + mm["A"][k] * tmpl))
            deg2 = csv(find(nn, name, "deg2", c))
            rec[:, :, ch] = (255 * (((inp[:, :, ch] / 255) ** 2.2 * deg0 * deg2) ** (1 / 2.2))).astype(np.uint8)
        d_rec = int(np.max(np.abs(rec.astype(int) - img)))
        if mode == "cases":
            ok = d_stat == 0 and max(d_deg) == 0 and d_img == 0 and d_ppt == 0 and d_rec == 0
            ok_all &= ok
            verdict = "OK" if ok else "NG"
        else:
            verdict = "（参考）"
        kind = "PQ評価" if r["step_type"] == "eval" else "Aging"
        print(f"{nn:02d} {case:>4}{'再' if st['again'] else ' '} {kind:<5} {d_stat:10.3g}  "
              f"{d_deg[0]:9.3g} {d_deg[1]:9.3g} {d_deg[2]:9.3g}   {d_img:8d} {s_ppt:>8} {d_rec:8d}  {verdict}")
else:
    ref = root / "reference/movie_cli"
    r = seq["recipes"][0]
    name = r["recipe_name"]
    print(f"出力: {out}")
    for kind in ("stat", "deg", "deg2"):
        d = [maxdiff(csv(find(1, name, kind, c)), csv(ref / f"20_{kind}_{c}.csv")) for c in "rgb"]
        ok = max(d) == 0
        ok_all &= ok
        print(f"{kind:<5} 最大差 R={d[0]:.3g} G={d[1]:.3g} B={d[2]:.3g}  {'OK' if ok else 'NG'}")
if mode != "pq":
    print("ALL OK" if ok_all else "NG あり")
