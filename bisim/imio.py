"""Unicode パス対応の画像 I/O（prototype/imio.py から移植）

OpenCV の cv2.imread / cv2.imwrite は Windows で非ASCIIパス（例: C:\\ユーザー\\...）を
扱えないため、np.fromfile / imdecode / imencode / tofile 経由に置き換える。
動画 I/O（VideoCapture / VideoWriter）は Unicode パスでも動作するのでそのまま cv2 を使う。
"""
from __future__ import annotations

import os

import cv2
import numpy as np


def imread(path) -> np.ndarray | None:
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def imwrite(path, img: np.ndarray) -> bool:
    path = str(path)
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        return False
    try:
        buf.tofile(path)
    except OSError:
        return False
    return True
