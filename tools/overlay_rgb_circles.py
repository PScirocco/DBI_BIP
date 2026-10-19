"""動画の各フレームに R/G/B 3色の円（加法混色）を重ねて MP4 に保存する。

円は R=上、G=左下、B=右下 の三角配置。重なり部分は色ごとの最大値（加法混色）：
  B+G=(B,G,R)=(255,255,0)、R+G=(0,255,255)、R+B=(255,0,255)、3色=白。
円の外は元動画のまま。縁はアンチエイリアスなし（画素値は 0/255 のみ）。

使い方:
  python tools/overlay_rgb_circles.py 入力.mp4 [出力.mp4] [--radius 0.18] [--png パターン.png]
    --radius : 円の半径（フレーム高さに対する比率、既定 0.18）
    --png    : パターンだけを黒背景で描いた静止画も保存する
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np


def make_pattern(w: int, h: int, radius_ratio: float = 0.18):
    """(pattern_bgr, mask) を返す。mask は円のいずれかに含まれる画素で True。"""
    r = int(round(h * radius_ratio))
    d = r                                   # 円の中心間距離（＝半径。3色の重なりができる）
    cx, cy = w // 2, h // 2                 # 3つの中心の重心を画面中央に置く
    k = d / np.sqrt(3)                      # 重心から各中心までの距離
    centers = {                             # BGR のチャンネル番号
        2: (cx, int(round(cy - k))),                            # R: 上
        1: (int(round(cx - d / 2)), int(round(cy + k / 2))),    # G: 左下
        0: (int(round(cx + d / 2)), int(round(cy + k / 2))),    # B: 右下
    }
    pattern = np.zeros((h, w, 3), np.uint8)
    for ch, c in centers.items():
        m = np.zeros((h, w), np.uint8)
        cv2.circle(m, c, r, 255, thickness=-1, lineType=cv2.LINE_8)
        pattern[:, :, ch] = np.maximum(pattern[:, :, ch], m)
    mask = pattern.any(axis=2)
    return pattern, mask


def overlay_video(src: Path, dst: Path, radius_ratio: float) -> None:
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        sys.exit(f"開けません: {src}")
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    pattern, mask = make_pattern(w, h, radius_ratio)

    # cv2.VideoWriter は日本語パスに書けないため ASCII の一時ファイル経由
    fd, tmp = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    wr = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame[mask] = pattern[mask]
        wr.write(frame)
        n += 1
    cap.release()
    wr.release()
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp, dst)
    print(f"{src.name} -> {dst}  ({w}x{h}, {fps:.3f}fps, {n} frames, 半径 {int(round(h * radius_ratio))}px)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path, nargs="?")
    ap.add_argument("--radius", type=float, default=0.18)
    ap.add_argument("--png", type=Path)
    a = ap.parse_args()
    dst = a.dst or a.src.with_name(f"{a.src.stem}_rgbcircle.mp4")
    overlay_video(a.src, dst, a.radius)
    if a.png:
        cap = cv2.VideoCapture(str(a.src))
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        pattern, _ = make_pattern(w, h, a.radius)
        ok, buf = cv2.imencode(".png", pattern)  # 日本語パス対策（imwrite を使わない）
        buf.tofile(str(a.png))
        print(f"パターン静止画 -> {a.png}")


if __name__ == "__main__":
    main()
