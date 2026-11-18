"""eval_exec_debug.bat の11ケースを (a) burn_in(CLI) と (b) burn_in_band_extract + burn_in_core で実行し、松井さんの出力と比較"""
import sys, os, subprocess, re
import numpy as np, cv2
core, ref, py = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, core); os.chdir(core)
import main as m, load_com_info as ci
bat = open(os.path.join(ref, "..", "eval_exec_debug.bat"), encoding="utf-8").read()
cases = [l.split()[2:] for l in bat.splitlines() if l.startswith("python ./main.py")]
worst = {"a": 0.0, "b": 0.0, "b_img": 0}
for a in cases:
    img_f, ht_f, bc_f, mm_f, sm_f, sc_f, sr, sg, sb, ini, oe, idx = a
    # (a) CLI
    subprocess.run([py, "main.py", *a], check=True, capture_output=True)
    # (b) 切り出した関数 + burn_in_core
    _, bc = ci.load_bcset(f"dbi_conf/{bc_f}"); _, mm = ci.load_degparam_mm(f"dbi_conf/{mm_f}")
    _, sm = ci.load_degparam_sm(f"dbi_conf/{sm_f}"); _, sc = ci.load_simconf(f"dbi_input/{sc_f}")
    rc, band, log_b = m.burn_in_band_extract(bc, sm, sc); assert rc == 0, log_b
    img = cv2.imread(f"dbi_common/{img_f}"); ht = cv2.imread(f"dbi_common/{ht_f}")
    h, w = img.shape[:2]
    stat = {c: (np.loadtxt(os.path.join(ref, f), delimiter=",") if ini == "1" else np.zeros((h, w)))
            for c, f in zip("rgb", (sr, sg, sb))}
    rc = m.burn_in_core(1.0, img, ht, bc, mm, sm, sc, stat_r=stat["r"], stat_g=stat["g"], stat_b=stat["b"], **band); assert rc == 0
    # log の Band 抽出部分が burn_in の log と同じか
    log_a = open(f"dbi_output/{idx}_log.txt").read()
    seg = log_a[log_a.index("---- Target DBV check"):log_a.index("Deg 2D_Lut extraction finished.")]
    assert seg == log_b[:log_b.index("Deg 2D_Lut extraction finished.")], f"log mismatch case {idx}"
    for c in "rgb":
        r_stat = np.loadtxt(os.path.join(ref, f"{idx}_stat_{c}.csv"), delimiter=",")
        r_deg = np.loadtxt(os.path.join(ref, f"{idx}_deg_{c}.csv"), delimiter=",")
        a_stat = np.loadtxt(f"dbi_output/{idx}_stat_{c}.csv", delimiter=",")
        worst["a"] = max(worst["a"], np.abs(a_stat - r_stat).max())
        b_deg = np.exp(-1.0 * stat[c] ** mm[f"B0_{c}"])
        worst["b"] = max(worst["b"], np.abs(stat[c] - r_stat).max(), np.abs(b_deg - r_deg).max())
    r_img = cv2.imread(os.path.join(ref, f"{idx}_out_img.png"))
    worst["b_img"] = max(worst["b_img"], int(np.abs(img.astype(int) - r_img.astype(int)).max()))
    print(f"case {idx:>2}: DBV={sc['DBV_NIT']:>6g} DPK={sc['DPK_ON']} ini={ini}  "
          f"{re.search(r'Extracted Band.*', log_b).group(0)}")
print("max|diff| (a) burn_in CLI vs 松井:", worst["a"])
print("max|diff| (b) 切り出し関数+burn_in_core vs 松井 (stat/deg):", worst["b"], " 画像:", worst["b_img"])
