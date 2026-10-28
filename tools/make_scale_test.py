"""累積時間マップの表示スケール（「0〜面内最大」と「面内最小〜面内最大」）の違いを確かめるテスト一式を作る。

最初に全面白で長めに Aging して画面全体に累積時間を貯め（＝面内の最小が 0 より大きくなる）、
そのあと3色円を短く Aging する。⑤の累積時間マップでスケールを切り替えると、
  - 0 〜 面内最大      : 背景（白の Aging 分）まで暗く沈み、円との差が小さい
  - 面内最小 〜 面内最大: 背景が白になり、3色円で増えた分だけが暗く浮かび上がる

作るもの（既定の出力先 ``eval_test/scaletest/``）:
  input/                       Aging 用の3色円の動画・全面白の画像（3色円テストと同じもの）
  scaletest.seq.json           bisim でそのまま開けるシーケンス（3ステップ）
  expected/                    期待される見え方（ステップ3の累積時間マップ、両スケール）と数値
  README.md                    手順と期待値

シーケンス:
  01 white-2h       Aging  全面白（静止画）  初期ストレス なし          AGING_TIME 7200秒（2時間）
  02 circles-0h30m  Aging  3色円の動画       前ステップ継承             AGING_TIME 1800秒（30分）
  03 eval           PQ評価 全面白            前ステップ継承
  共通: ACCEL_RATIO=3600、固定温度 25℃、モデルパラメータ既定値

フォルダは bisim.exe のフォルダ（開発環境ではリポジトリ直下）から見た相対パスで書く（tools/README.md）。

使い方:
  python tools/make_scale_test.py [--out eval_test/scaletest] [--app-dir <bisim.exe のフォルダ>]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO))
from make_rgbcircle_test import (  # noqa: E402
    H, MOVIE, W, WHITE, recipe, write_movie, write_png,
)
from overlay_rgb_circles import make_pattern  # noqa: E402
from _seqpaths import APP_DIR_HELP, to_app_relative  # noqa: E402

SEQ_NAME = "scaletest"
WHITE_AGING_S = 7200.0      # 白で 2時間
CIRCLE_AGING_S = 1800.0     # 3色円で 30分


def build_sequence(in_dir: Path, out_dir: Path, app_dir_arg=None) -> dict:
    inp = to_app_relative(in_dir, app_dir_arg)
    folders = {"input_image": inp, "heatmap": inp, "output": to_app_relative(out_dir, app_dir_arg)}
    recipes = [
        recipe("white-2h", "aging", WHITE, WHITE_AGING_S, "none"),
        recipe("circles-0h30m", "aging", MOVIE, CIRCLE_AGING_S, "prev"),
        recipe("eval", "eval", WHITE, 0.0, "prev"),
    ]
    return {"sequence_name": SEQ_NAME, "folders": folders, "recipes": recipes}


def expected(seq: dict, in_dir: Path, exp_dir: Path) -> dict:
    """bisim のエンジンで流して、ステップ3の累積時間マップを両スケールで画像にする（⑤と同じ描き方）。"""
    from bisim import engine
    from bisim.model import Sequence
    s = Sequence.from_dict(seq)
    s.folders["input_image"] = s.folders["heatmap"] = str(in_dir)
    with tempfile.TemporaryDirectory() as d:
        s.folders["output"] = d
        res = engine.run_sequence(sequence=s, model=engine.MasterModel())
    st = res[-1].state
    stats = {c: (float(st.channel(c).min()), float(st.channel(c).max())) for c in "rgb"}
    for key in ("zero", "minmax"):
        chans = []
        for c in "rgb":
            a = st.channel(c)
            lo, hi = (stats[c][0] if key == "minmax" else 0.0), stats[c][1]
            v = np.clip((a - lo) / (hi - lo), 0, 1) if hi > lo else np.zeros_like(a)
            chans.append(1.0 - v)                       # 明暗反転（暗＝累積大）
        rgb = (np.stack(chans, axis=-1) * 255).astype(np.uint8)
        write_png(exp_dir / f"expected_stat_rgb_{key}.png", rgb[:, :, ::-1])   # BGR で保存
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "eval_test" / "scaletest")
    ap.add_argument("--app-dir", type=Path, help=APP_DIR_HELP)
    a = ap.parse_args()

    base = a.out.resolve()
    in_dir, out_dir, exp_dir = base / "input", base / "output", base / "expected"
    for p in (in_dir, out_dir, exp_dir):
        p.mkdir(parents=True, exist_ok=True)
    pattern, _ = make_pattern(W, H, 70 / H)
    write_png(in_dir / WHITE, np.full((H, W, 3), 255, np.uint8))
    write_movie(in_dir / MOVIE, pattern)

    seq = build_sequence(in_dir, out_dir, a.app_dir)
    (base / f"{SEQ_NAME}.seq.json").write_text(json.dumps(seq, ensure_ascii=False, indent=2), encoding="utf-8")

    stats = expected(seq, in_dir, exp_dir)
    lines = ["ステップ3（eval）の累積時間（面内の最小 / 最大）"]
    lines += [f"  {c.upper()}: min {lo:.4f} / max {hi:.4f}" for c, (lo, hi) in stats.items()]
    (exp_dir / "expected_values.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"出力先: {base}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
