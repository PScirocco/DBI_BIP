"""python -m bisim — 本番GUI（5タブ）を起動する。

データ層のみの確認は ``python -m bisim.selftest`` / ``python -m bisim --info``。
"""
from __future__ import annotations

import sys


def _info() -> int:
    from bisim import __version__, naming, paths
    from bisim.model import AppConfig, Sequence

    print(f"bisim {__version__}")
    print(f"  SOURCE_DIR : {paths.SOURCE_DIR}")
    print(f"  APP_DIR    : {paths.APP_DIR}")
    print(f"  LOG_DIR    : {paths.LOG_DIR}")
    cfg = AppConfig.load_or_default(paths.APP_CONFIG_PATH)
    print(f"  AppConfig  : {paths.APP_CONFIG_PATH.name} "
          f"({'あり' if paths.APP_CONFIG_PATH.exists() else 'なし→既定'}) "
          f"log_max_mb={cfg.log_max_mb} language={cfg.language}")
    print(f"  Sequence   : recipes={len(Sequence().recipes)}")
    print(f"  例 出力名   : {naming.output_name('SEQ-A', 1, 'aging01', 'deg', 'r')}")
    try:
        from bisim.engine import MasterModel
        print(f"  Engine     : DegradationModel='{MasterModel().name}'（source/ ラップOK）")
    except Exception as e:  # noqa: BLE001
        print(f"  Engine     : ロード失敗 — {type(e).__name__}: {e}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--info" in argv:
        return _info()
    from bisim.ui import run
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
