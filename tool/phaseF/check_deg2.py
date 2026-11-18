import sys, os, numpy as np, cv2
core, ref = sys.argv[1], sys.argv[2]; os.chdir(core)
L = lambda p: np.loadtxt(p, delimiter=",")
_mm = {l.split(",")[0]: [float(x) for x in l.strip().split(",")[1:4]] for l in open("dbi_conf/degparam_mm.csv", encoding="utf-8-sig")}
B0 = dict(zip("rgb", _mm["B0"])); A = dict(zip("rgb", _mm["A"]))
bat = open(os.path.join(ref, "..", "eval_exec_debug.bat"), encoding="utf-8").read()
cases = [l.split()[2:] for l in bat.splitlines() if l.startswith("python ./main.py")]
worst = 0; lo = 1.0
for a in cases:
    img_f, ht_f, bc_f, mm_f, sm_f, sc_f, sr, sg, sb, ini, oe, idx = a
    tmpl = [float(l.split(",")[1]) for l in open(f"dbi_input/{sc_f}") if l.startswith("TMP_L")][0] + 273.0
    inp = cv2.imread(f"dbi_common/{img_f}").astype(float); out = cv2.imread(f"dbi_output/{idx}_out_img.png")
    rec = np.zeros_like(out)
    for ch, c, f in ((0, "b", sb), (1, "g", sg), (2, "r", sr)):
        stat0 = L(os.path.join(ref, f)) if ini == "1" else np.zeros(inp.shape[:2])
        deg = np.exp(-1.0 * stat0 ** (B0[c] + A[c] * tmpl))          # burn_in_core 内の deg_c（フレーム処理前）
        deg2 = L(f"dbi_output/{idx}_deg2_{c}.csv"); lo = min(lo, deg2.min())
        rec[:, :, ch] = (255 * (((inp[:, :, ch] / 255) ** 2.2 * deg * deg2) ** (1 / 2.2))).astype(np.uint8)
    worst = max(worst, int(np.abs(rec.astype(int) - out.astype(int)).max()))
print(f"入力画像 × deg × deg2(CSV) で出力画像を再現: 11ケースの最大差 = {worst} 階調 / deg2 の最小値 = {lo:.4f}")
