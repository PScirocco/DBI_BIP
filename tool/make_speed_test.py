"""計算時間の体験用テスト一式を作る（実機サイズ 2848×1320 の静止画。2026-11-24）。

作るもの（既定の出力先 ``bisim2/eval_test/speedtest_phone/``。Git 管理外）:
  input/phone-aging_image.png   Aging 用（mov_001.mp4 の先頭フレームを 2848×1320 に拡大した静止画）
  input/phone-eval_image.png    PQ評価用（全面白）
  conf/                         パネル設定（bcsetting.csv・degparam_mm.csv・degparam_sm.csv。標準ファイルのコピー）
  simconf/                      Sim 条件 CSV（シーケンスのステップと同じ値）
  speed-10f.seq.json            Aging 10 フレーム（ACCEL_RATIO 3000・AGING_TIME 30000 秒）→ PQ評価
  speed-1month.seq.json         Aging 1か月（ACCEL_RATIO 3000・AGING_TIME 2592000 秒 ＝ 864 フレーム）→ PQ評価
  README.md                     手順と、開発PCでの計算時間

フォルダはシーケンスファイルから見た相対パス（"folders_base": "sequence"）なので、
このフォルダごと、どこへ・別PCへコピーしても、シーケンスを開くだけで動く。
共通：固定温度 25℃（ヒートマップなし）、DBV_NIT 2000・DPK_ON 0・GADJ 1,1,1。

使い方（Burn-In_Simv2 直下で）:
  bisim2\\.venv\\Scripts\\python tool\\make_speed_test.py [--out <出力先>]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent / "bisim2"
sys.path.insert(0, str(REPO))
from bisim import imio, paramio  # noqa: E402
from bisim.model import DEFAULT_SIM, PanelConfig, Recipe, Sequence  # noqa: E402

W, H = 2848, 1320
ACCEL = 3000.0
AGING_IMG, EVAL_IMG = "phone-aging_image.png", "phone-eval_image.png"
CASES = {                                     # シーケンス名 → (Aging のレシピ名, AGING_TIME[秒])
    "speed-10f": ("aging-10f", 10 * ACCEL),
    "speed-1month": ("aging-1month", 30 * 24 * 3600.0),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "eval_test" / "speedtest_phone")
    a = ap.parse_args()
    base = a.out.resolve()
    for d in ("input", "conf", "simconf", "output"):
        (base / d).mkdir(parents=True, exist_ok=True)

    # 入力画像：実際の映像の1コマを実機サイズに拡大（静止画）＋全面白
    src = REPO / "source" / "dbi_common" / "mov_001.mp4"
    cap = cv2.VideoCapture(str(src))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit(f"動画を読めません: {src}")
    imio.imwrite(base / "input" / AGING_IMG, cv2.resize(frame, (W, H), interpolation=cv2.INTER_CUBIC))
    imio.imwrite(base / "input" / EVAL_IMG, np.full((H, W, 3), 255, np.uint8))

    # パネル設定（標準ファイルのコピー）
    for n in ("bcsetting.csv", "degparam_mm.csv", "degparam_sm.csv"):
        shutil.copy2(REPO / "source" / "dbi_conf" / n, base / "conf" / n)
    panel = PanelConfig(model_param=paramio.read_model_csv(base / "conf" / "degparam_mm.csv"),
                        model_param_csv="degparam_mm.csv")

    for seq_name, (aging_name, aging_time) in CASES.items():
        sim = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_SIM.items()}
        sim.update(AGING_TIME=aging_time, ACCEL_RATIO=ACCEL, TMP_L=25.0, TMP_H=25.0)
        csv_name = f"{aging_name}_sim-param.csv"
        paramio.write_sim_csv(base / "simconf" / csv_name, sim)
        seq = Sequence(sequence_name=seq_name, panel=panel)
        seq.folders.update(input_image=str(base / "input"), heatmap=str(base / "input"),
                           bcset=str(base / "conf"), model=str(base / "conf"),
                           simconf=str(base / "simconf"), output=str(base / "output" / seq_name))
        seq.recipes = [
            Recipe(recipe_name=aging_name, step_type="aging", input_image=AGING_IMG,
                   heatmap_mode="fixed", fixed_temp_c=25.0, sim_param=sim, sim_param_csv=csv_name),
            Recipe(recipe_name="eval", step_type="eval", input_image=EVAL_IMG,
                   heatmap_mode="fixed", fixed_temp_c=25.0, sim_param=dict(sim), init_stress="prev"),
        ]
        seq.save(base / f"{seq_name}.seq.json")              # フォルダはシーケンスファイルからの相対パスで保存される
        print(f"{seq_name}.seq.json: Aging {aging_time / ACCEL:g} フレーム → PQ評価")
    print(f"出力先: {base}")


if __name__ == "__main__":
    main()
