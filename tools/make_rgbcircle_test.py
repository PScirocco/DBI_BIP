"""理論確認テスト用の入力一式を作る（黒背景＋R/G/B 3色円）。

作るもの（既定の出力先 ``eval_test/rgbcircle/``）:
  input/rgbcircle-aging_movie.mp4   Aging 用。全フレーム同じ絵の静止画を MP4 化（mp4v, 30fps, 30フレーム=1秒）
  input/rgbcircle-eval_image.png    評価用。全面白（255,255,255）
  input/rgbcircle-pattern.png       参考：MP4 化する前の理想パターン（画素値は 0/255 のみ）
  input/rgbcircle-regions.png       参考：領域番号マップ（0=背景, 1..7 = B,G,G+B,R,R+B,R+G,白）
  rgbcircle.seq.json                bisim でそのまま開けるシーケンス（Aging→評価 を Aging時間ごとに連結）
                                    フォルダは相対パス（input / output）なので、出力先フォルダごと
                                    別PCへコピーしても、そのまま開いて実行できる

パネルは 横240 × 縦512 画素。円は R=上、G=左下、B=右下 の三角配置で、
中心間距離＝半径（3円が互いに重なり、中央が白になる）。

シーケンスの考え方（ACCEL_RATIO=3600、30fps → 1フレーム=120秒、動画1周回=1時間）:
  01 Aging（初期ストレス none）  累積 0.5h まで（動画の途中で打ち切り）
  02 評価（白・前ステップ継承）
  03 Aging（前ステップ継承）     累積 1h まで  …… 以下 2h, 5h, 10h, 20h, 50h
評価ステップは Aging しない（静止画は dt=0）ので、次の Aging は評価ステップの累積ストレスをそのまま引き継ぐ。

使い方:
  python tools/make_rgbcircle_test.py [--out eval_test/rgbcircle] [--radius 70] [--app-dir <bisim.exe のフォルダ>]

シーケンスに書くフォルダは、bisim.exe のフォルダ（既定はリポジトリ直下）から見た相対パス
（例 eval_test/rgbcircle/input）。別PCでは bisim.exe のフォルダの下に eval_test/rgbcircle を
コピーすれば、そのまま開いて実行できる。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO))
from overlay_rgb_circles import make_pattern  # noqa: E402
from _seqpaths import APP_DIR_HELP, to_app_relative  # noqa: E402

W, H = 240, 512                  # パネルサイズ（横×縦）
FPS = 30.0
FRAMES = 30                      # 1秒分。AGING_TIME で周回連結される
ACCEL_RATIO = 3600.0             # 1フレーム = (1/30)×3600 = 120秒 → 1周回(30フレーム) = 1時間
TEMP_C = 25.0                    # 固定温度（ヒートマップなし）
CUM_HOURS = [0.5, 1, 2, 5, 10, 20, 50]       # 評価する累積 Aging 時間 [h]（暫定パラメータでは 50h でほぼ黒）

SEQ_NAME = "rgbcircle"
MOVIE = "rgbcircle-aging_movie.mp4"
WHITE = "rgbcircle-eval_image.png"
PATTERN = "rgbcircle-pattern.png"
REGIONS = "rgbcircle-regions.png"


def region_map(pattern_bgr: np.ndarray) -> np.ndarray:
    """領域番号 = R×4 + G×2 + B×1（0=背景, 7=白）。"""
    on = pattern_bgr > 127
    return (on[:, :, 2] * 4 + on[:, :, 1] * 2 + on[:, :, 0] * 1).astype(np.uint8)


def write_png(path: Path, img: np.ndarray) -> None:
    ok, buf = cv2.imencode(".png", img)       # 日本語パス対策（imwrite を使わない）
    if not ok:
        sys.exit(f"PNG エンコード失敗: {path}")
    buf.tofile(str(path))


def write_movie(path: Path, frame: np.ndarray) -> None:
    # cv2.VideoWriter は日本語パスに書けないため ASCII の一時ファイル経由（bisim と同じ）
    fd, tmp = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    wr = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    if not wr.isOpened():
        sys.exit("VideoWriter を開けません（mp4v）")
    for _ in range(FRAMES):
        wr.write(frame)
    wr.release()
    shutil.move(tmp, str(path))


def hours_label(h: float) -> str:
    """レシピ名用の時間表記（ファイル名に '.' を入れない）: 0.5 → '0h30m'、2 → '2h'。"""
    hh, mm = int(h), int(round((h - int(h)) * 60))
    return f"{hh}h{mm:02d}m" if mm else f"{hh}h"


def recipe(name: str, step_type: str, image: str, aging_time: float, init: str) -> dict:
    from bisim.model import DEFAULT_MODEL, DEFAULT_SIM
    sim = dict(DEFAULT_SIM)
    sim.update(AGING_TIME=float(aging_time), ACCEL_RATIO=ACCEL_RATIO)
    return {
        "recipe_name": name,
        "step_type": step_type,
        "input_image": image,
        "heatmap": "",
        "heatmap_mode": "fixed",
        "fixed_temp_c": TEMP_C,
        "model_param": {k: list(v) for k, v in DEFAULT_MODEL.items()},
        "model_param_csv": "",
        "sim_param": sim,
        "sim_param_csv": "",
        "init_stress": init,
        "init_stress_files": {"r": "", "g": "", "b": ""},
    }


def build_sequence(in_dir: Path, out_dir: Path, app_dir_arg=None) -> dict:
    recipes, prev_h = [], 0
    for i, h in enumerate(CUM_HOURS):
        recipes.append(recipe(f"aging-{hours_label(h)}", "aging", MOVIE, (h - prev_h) * 3600.0,
                              "none" if i == 0 else "prev"))
        recipes.append(recipe(f"eval-{hours_label(h)}", "eval", WHITE, 0.0, "prev"))
        prev_h = h
    # フォルダは bisim.exe のフォルダ（開発環境ではリポジトリ直下）から見た相対パスで書く。
    # 例: "eval_test/rgbcircle/input"。別PCでも bisim.exe のフォルダの下に同じ構成で置けば、
    # パスを書き換えずに開ける（bisim の Sequence.load が APP_DIR 基準で読み替える）。
    # 基準の外に作った場合は絶対パスになる。
    # BC設定・モデル・Sim のフォルダは書かない → 各PC（EXE）の既定フォルダが使われる
    inp = to_app_relative(in_dir, app_dir_arg)
    folders = {"input_image": inp, "heatmap": inp, "output": to_app_relative(out_dir, app_dir_arg)}
    return {"sequence_name": SEQ_NAME, "folders": folders, "recipes": recipes}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "eval_test" / "rgbcircle")
    ap.add_argument("--radius", type=int, default=70, help="円の半径 [px]（既定 70）")
    ap.add_argument("--app-dir", type=Path, help=APP_DIR_HELP)
    a = ap.parse_args()

    base = a.out.resolve()
    in_dir, out_dir = base / "input", base / "output"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    pattern, _ = make_pattern(W, H, a.radius / H)
    write_png(in_dir / PATTERN, pattern)
    write_png(in_dir / REGIONS, region_map(pattern))
    write_png(in_dir / WHITE, np.full((H, W, 3), 255, np.uint8))
    write_movie(in_dir / MOVIE, pattern)

    seq = build_sequence(in_dir, out_dir, a.app_dir)
    (base / f"{SEQ_NAME}.seq.json").write_text(
        json.dumps(seq, ensure_ascii=False, indent=2), encoding="utf-8")

    cap = cv2.VideoCapture(str(in_dir / MOVIE))
    info = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    cap.release()
    print(f"出力先: {base}")
    print(f"  動画 {MOVIE}: {info[0]}x{info[1]}, {info[2]:g}fps, {info[3]} frames, 半径 {a.radius}px")
    print(f"  評価 {WHITE}: {W}x{H} 全面白")
    print(f"  シーケンス {SEQ_NAME}.seq.json: {len(seq['recipes'])} ステップ"
          f"（累積 {', '.join(hours_label(h) for h in CUM_HOURS)}、ACCEL_RATIO={ACCEL_RATIO:g}、固定 {TEMP_C:g}℃）")


if __name__ == "__main__":
    main()
