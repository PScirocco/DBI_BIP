"""selftest の基準データ（新コア）を作る：松井さんのケース1→2 から 16×16 画素を切り出す。

ケース1（eval_img1・simconf_2000_aging・初期ストレス0）→ ケース2（eval_img2・simconf_2000_test・ケース1 の stat を引き継ぐ）。
どちらも DPK_ON=0 なので、画素どうしは影響し合わない（DPK は画面全体の APL を使うが、OFF なら使わない）。
入力の白い四角（eval_img1）と4階調の象限（eval_img2）が離れているため、1か所の切り出しでは両方の階調がそろわない。
そこで各象限から白い四角の右下の角を含む 8×8 を1つずつ取り、2×2 に並べて 16×16 にする（期待値も同じ並べ方）。

期待値：stat・deg・出力画像は松井さんの dbi_output。deg2 は松井さんの出力に無いので、bisim 側で追加した
deg2 出力（2026-11-17。入力×deg×deg2 で出力画像を差0で再現できることを確認済み）で全画面を計算し、同じ並べ方で切り出す。

実行（Burn-In_Simv2 直下）:
  bisim2\\.venv\\Scripts\\python -I tool\\phaseF\\make_selftest_core_data.py bisim2 receive\\Burn_in_sim_core_01
出力: bisim2/bisim/tests/data/core01_case1-2.npz
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

# 各象限の 8×8（行の先頭, 列の先頭）。白い四角は行 45-89 / 180-224、列 80-159 / 320-399
PATCHES = [(86, 156), (86, 396), (221, 156), (221, 396)]
P = 8


def mosaic(arr: np.ndarray) -> np.ndarray:
    """(h, w[, c]) の全画面から 4 か所の 8×8 を取り、2×2 に並べた 16×16 を返す。"""
    tiles = [arr[y:y + P, x:x + P] for y, x in PATCHES]
    return np.concatenate([np.concatenate(tiles[:2], axis=1),
                           np.concatenate(tiles[2:], axis=1)], axis=0)


def main() -> int:
    bisim2, recv = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    sys.path.insert(0, str(bisim2))
    from bisim import engine

    common, ref = recv / "dbi_common", recv / "dbi_output"
    model = engine.CoreModel(bcset_path=recv / "dbi_conf" / "bcsetting.csv",
                             sm_path=recv / "dbi_conf" / "degparam_sm.csv")
    ci = model._core.com_info
    _, mm = ci.load_degparam_mm(str(recv / "dbi_conf" / "degparam_mm.csv"))
    mp = {k: [mm[f"{k}_{c}"] for c in "rgb"] for k in ("N", "K0", "Q", "B0", "A")}

    data = {}
    stat = engine.StressState.zeros(270, 480)
    for idx, img_name, ht_name, sim_name in ((1, "eval_img1.png", "eval_img_ht1.png", "simconf_2000_aging.csv"),
                                             (2, "eval_img2.png", "eval_img_ht2.png", "simconf_2000_test.csv")):
        img = cv2.imread(str(common / img_name))
        ht = cv2.imread(str(common / ht_name))
        _, sim = ci.load_simconf(str(recv / "dbi_input" / sim_name))
        # 全画面で deg2 を計算（stat・画像は松井さんの出力と照合）
        deg2 = engine.RGBMaps.full(270, 480, 1.0)
        work = img.copy()
        model.update(1.0, work, ht, stat, mp, sim, deg2=deg2)
        out_ref = cv2.imread(str(ref / f"{idx}_out_img.png"))
        assert np.array_equal(work, out_ref), f"case {idx}: 画像が松井さんの出力と一致しない"
        for c in "rgb":
            s_ref = np.loadtxt(ref / f"{idx}_stat_{c}.csv", delimiter=",")
            assert np.array_equal(stat.channel(c), s_ref), f"case {idx}: stat_{c} 不一致"
            data[f"c{idx}_stat_{c}"] = mosaic(s_ref)
            data[f"c{idx}_deg_{c}"] = mosaic(np.loadtxt(ref / f"{idx}_deg_{c}.csv", delimiter=","))
            data[f"c{idx}_deg2_{c}"] = mosaic(deg2.channel(c))
        data[f"c{idx}_img"] = mosaic(img)
        data[f"c{idx}_ht"] = mosaic(ht)
        data[f"c{idx}_out"] = mosaic(out_ref)
        for k in ("AGING_TIME", "ACCEL_RATIO", "TMP_L", "TMP_H", "DBV_NIT", "DPK_ON",
                  "GADJ_R", "GADJ_G", "GADJ_B"):
            data[f"c{idx}_sim_{k}"] = np.array(float(sim[k]))
    for k, v in mp.items():
        data[f"mm_{k}"] = np.array(v, dtype=float)

    dst = bisim2 / "bisim" / "tests" / "data" / "core01_case1-2.npz"
    dst.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dst, **data)
    print(f"保存: {dst}（{dst.stat().st_size} バイト、{len(data)} 配列）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
