"""新コアで「一気に N フレーム」と「k フレームで止めて stat を CSV に保存→読み戻して残りを実行」を比べる"""
import sys, os
import numpy as np, cv2
core = sys.argv[1]; sys.path.insert(0, core); os.chdir(core)
import main as m, load_com_info as ci
_, bc = ci.load_bcset("dbi_conf/bcsetting.csv"); _, mm = ci.load_degparam_mm("dbi_conf/degparam_mm.csv")
_, sm = ci.load_degparam_sm("dbi_conf/degparam_sm.csv")
N, K, ST = 40, 17, os.path.join(sys.argv[2], "stop")
os.makedirs(ST, exist_ok=True)
for sc_f in ("simconf_2000_aging_tmp60.csv", "simconf_6500_aging.csv"):   # 通常 / DPK=ON
    _, sc = ci.load_simconf(f"dbi_input/{sc_f}"); sc["ACCEL_RATIO"] = 3000.0   # 劣化を進めて deg2 を効かせる
    _, band, _ = m.burn_in_band_extract(bc, sm, sc)
    def run(frames, stat, start):
        ci_, ch = cv2.VideoCapture("dbi_common/mov_001_480x270.mp4"), cv2.VideoCapture("dbi_common/mov_ht_001_480x270.mp4")
        ci_.set(cv2.CAP_PROP_POS_FRAMES, start); ch.set(cv2.CAP_PROP_POS_FRAMES, start)
        fps = ci_.get(cv2.CAP_PROP_FPS); imgs = []
        for _ in range(frames):
            _, img = ci_.read(); _, ht = ch.read()
            assert m.burn_in_core(1.0 / fps, img, ht, bc, mm, sm, sc, stat_r=stat["r"], stat_g=stat["g"], stat_b=stat["b"], **band) == 0
            imgs.append(img.copy())
        return imgs
    h, w = 270, 480
    s_a = {c: np.zeros((h, w)) for c in "rgb"}; img_a = run(N, s_a, 0)                   # 一気に
    s_b = {c: np.zeros((h, w)) for c in "rgb"}; img_b = run(K, s_b, 0)                   # K で停止
    for c in "rgb": np.savetxt(f"{ST}/stat_{c}.csv", s_b[c], delimiter=",")             # stat だけ保存（bisim と同じ savetxt）
    s_b = {c: np.loadtxt(f"{ST}/stat_{c}.csv", delimiter=",") for c in "rgb"}           # 読み戻して再開
    img_b += run(N - K, s_b, K)
    d_stat = max(np.abs(s_a[c] - s_b[c]).max() for c in "rgb")
    d_img = max(int(np.abs(a.astype(int) - b.astype(int)).max()) for a, b in zip(img_a, img_b))
    deg_min = min(np.exp(-s_a[c] ** mm[f"B0_{c}"]).min() for c in "rgb"); deg_max = max(np.exp(-s_a[c][s_a[c]>0] ** mm[f"B0_{c}"]).max() for c in "rgb")
    print(f"{sc_f}: DPK={sc['DPK_ON']}  {N}フレーム（{K}で停止→再開）  stat の差={d_stat:.1e}  全フレーム画像の差={d_img}  （最終 deg の範囲 {deg_min:.3f}〜{deg_max:.3f}）")
