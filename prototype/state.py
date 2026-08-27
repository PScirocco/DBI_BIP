""" プロトタイプ用の状態・設定データ（使い捨てUX検証プロトタイプ）
    劣化モデル本体は source/ 側にあり、ここでは無改変で利用する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROTO_DIR = Path(__file__).resolve().parent
REPO_DIR = PROTO_DIR.parent
SOURCE_DIR = REPO_DIR / "source"

# 既存コードのフォルダ構成をデフォルト値にする
DEFAULT_FOLDERS: dict[str, Path] = {
    "input_image": SOURCE_DIR / "dbi_common",
    "heatmap":     SOURCE_DIR / "dbi_common",
    "bcset":       SOURCE_DIR / "dbi_input",
    "model":       SOURCE_DIR / "dbi_conf",
    "simconf":     SOURCE_DIR / "dbi_conf",
    "output":      SOURCE_DIR / "dbi_output",
}
FOLDER_LABELS: dict[str, str] = {
    "input_image": "入力画像フォルダ",
    "heatmap":     "ヒートマップフォルダ",
    "bcset":       "BC設定フォルダ",
    "model":       "モデルパラメータフォルダ",
    "simconf":     "Sim条件フォルダ",
    "output":      "出力フォルダ",
}

# CSV が読めなかった場合のフォールバック（dbi_conf の現行値）
DEFAULT_MODEL: dict[str, list[float]] = {
    "N":  [1.5, 1.3, 1.7],
    "K0": [500.0, 1000.0, 100.0],
    "Q":  [1000.0, 800.0, 600.0],
    "B0": [0.7, 0.8, 0.4],
    "A":  [0.0, 0.0, 0.0],
}
DEFAULT_SIMCONF: dict[str, float] = {
    "AGING_TIME": 10.0,     # 現状 未使用（表示のみ）
    "ACCEL_RATIO": 30000.0,
    "TMP_L": 25.0,
    "TMP_H": 60.0,
}
MODEL_ROWS = ["N", "K0", "Q", "B0", "A"]


@dataclass
class Step:
    name: str = "新規ステップ"
    input_image: str = ""              # ファイル名のみ（フォルダは FolderConfig 側）
    heatmap: str = ""
    init_stress: str = "none"          # none | prev | file
    stress_r: str = ""                 # init_stress == "file" のときの絶対パス
    stress_g: str = ""
    stress_b: str = ""
    model: dict = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_MODEL.items()})
    simconf: dict = field(default_factory=lambda: dict(DEFAULT_SIMCONF))
    status: str = "未実行"

    @property
    def kind(self) -> str:
        ext = Path(self.input_image).suffix.lower()
        if ext == ".mp4":
            return "aging"
        if ext == ".png":
            return "pq"
        return "unknown"

    @property
    def kind_label(self) -> str:
        return {"aging": "Aging", "pq": "PQ評価", "unknown": "―"}[self.kind]


@dataclass
class AppState:
    folders: dict = field(default_factory=lambda: {k: str(v) for k, v in DEFAULT_FOLDERS.items()})
    steps: list = field(default_factory=list)


def load_model_csv(path) -> dict | None:
    """ source/load_com_info.load_degparam_mm と同じ書式（N,r,g,b ...） """
    m = {k: list(v) for k, v in DEFAULT_MODEL.items()}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                p = line.strip().split(",")
                if p[0] in m and len(p) >= 4:
                    m[p[0]] = [float(p[1]), float(p[2]), float(p[3])]
    except OSError:
        return None
    return m


def load_simconf_csv(path) -> dict | None:
    s = dict(DEFAULT_SIMCONF)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                p = line.strip().split(",")
                if p[0] in s and len(p) >= 2:
                    s[p[0]] = float(p[1])
    except OSError:
        return None
    return s
