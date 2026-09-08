"""PyInstaller 用エントリスクリプト。

``python -m bisim`` 相当。PyInstaller は ``-m`` を直接扱えないため、
実体のあるスクリプトから :func:`bisim.__main__.main` を呼ぶ。
"""
from __future__ import annotations

import multiprocessing
import sys


def _run() -> int:
    from bisim.__main__ import main
    return main(sys.argv)


if __name__ == "__main__":
    multiprocessing.freeze_support()   # numpy / cv2 がプロセスを起こす場合の保険
    sys.exit(_run())
