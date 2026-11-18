import sys, os, numpy as np, cv2
core = sys.argv[1]; sys.path.insert(0, core); os.chdir(core)
import main as m, load_com_info as ci
_, bc = ci.load_bcset("dbi_conf/bcsetting.csv"); _, mm = ci.load_degparam_mm("dbi_conf/degparam_mm.csv")
_, sm = ci.load_degparam_sm("dbi_conf/degparam_sm.csv"); _, sc = ci.load_simconf("dbi_input/simconf_2000_aging.csv")
_, band, _ = m.burn_in_band_extract(bc, sm, sc)
ci_, ch = cv2.VideoCapture("dbi_common/mov_001_480x270.mp4"), cv2.VideoCapture("dbi_common/mov_ht_001_480x270.mp4")
n, fps = int(ci_.get(7)), ci_.get(5)
st = {c: np.zeros((270, 480)) for c in "rgb"}; d2 = {c: np.ones((270, 480)) for c in "rgb"}; prev = None
for i in range(n):
    _, img = ci_.read(); _, ht = ch.read()
    if i == n - 1: prev = {c: d2[c].copy() for c in "rgb"}
    assert m.burn_in_core(1.0 / fps, img, ht, bc, mm, sm, sc, stat_r=st["r"], stat_g=st["g"], stat_b=st["b"], deg2_r=d2["r"], deg2_g=d2["g"], deg2_b=d2["b"], **band) == 0
for c in "rgb":
    csv = np.loadtxt(f"dbi_output/20_deg2_{c}.csv", delimiter=",")
    print(c, "CSV と最終フレームの差=", np.abs(csv - d2[c]).max(), " CSV と1つ前のフレームの差=", round(float(np.abs(csv - prev[c]).max()), 4),
          " stat の差=", np.abs(np.loadtxt(f"dbi_output/20_stat_{c}.csv", delimiter=",") - st[c]).max())
