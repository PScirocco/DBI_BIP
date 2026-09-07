"""python -m bisim

フェーズA（現状）: データ層の存在確認のみ。UI はフェーズC（docs/実装計画.md）で実装。
"""
from __future__ import annotations

import sys

from bisim import __version__, naming, paths
from bisim.model import AppConfig, Sequence


def main() -> int:
    print(f"bisim {__version__} — phase A (data layer only)")
    print(f"  SOURCE_DIR : {paths.SOURCE_DIR}")
    print(f"  APP_DIR    : {paths.APP_DIR}")
    cfg = AppConfig.load_or_default(paths.APP_CONFIG_PATH)
    print(f"  AppConfig  : {paths.APP_CONFIG_PATH.name} "
          f"({'あり' if paths.APP_CONFIG_PATH.exists() else 'なし→既定'}) "
          f"log_max_mb={cfg.log_max_mb} language={cfg.language}")
    seq = Sequence()
    print(f"  Sequence   : recipes={len(seq.recipes)} folders={list(seq.folders)}")
    print(f"  例: 入力名 {naming.input_name('aging01', 'movie', ext='mp4')}")
    print(f"  例: 出力名 {naming.output_name('SEQ-A', 1, 'aging01', 'deg', 'r')}")
    print(f"  例: 停止保存 {naming.output_name('SEQ-A', 1, 'aging01', 'stat', 'r', stopped_at='260904-1430')}")
    print("UI は未実装（フェーズC）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
