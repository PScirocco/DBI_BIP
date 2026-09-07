"""python -m bisim

現状（フェーズB まで）: データ層＋エンジン＋ログの存在確認のみ。UI はフェーズC（docs/実装計画.md）で実装。
"""
from __future__ import annotations

import sys

from bisim import __version__, naming, paths
from bisim.model import AppConfig, Sequence


def main() -> int:
    print(f"bisim {__version__} — phases A+B (data / engine / log)")
    print(f"  SOURCE_DIR : {paths.SOURCE_DIR}")
    print(f"  APP_DIR    : {paths.APP_DIR}")
    print(f"  LOG_DIR    : {paths.LOG_DIR}")
    cfg = AppConfig.load_or_default(paths.APP_CONFIG_PATH)
    print(f"  AppConfig  : {paths.APP_CONFIG_PATH.name} "
          f"({'あり' if paths.APP_CONFIG_PATH.exists() else 'なし→既定'}) "
          f"log_max_mb={cfg.log_max_mb}")
    print(f"  Sequence   : recipes={len(Sequence().recipes)}")
    print(f"  例 出力名   : {naming.output_name('SEQ-A', 1, 'aging01', 'deg', 'r')}")

    try:
        from bisim.engine import MasterModel
        m = MasterModel()
        print(f"  Engine     : DegradationModel='{m.name}'（source/ ラップOK）")
    except Exception as e:  # noqa: BLE001
        print(f"  Engine     : ロード失敗 — {type(e).__name__}: {e}")

    print("UI は未実装（フェーズC）。動作確認: python -m bisim.selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
