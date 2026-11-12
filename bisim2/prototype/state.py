""" プロトタイプ用の状態・設定データ（使い捨てUX検証プロトタイプ）
    劣化モデル本体は source/ 側にあり、ここでは無改変で利用する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from i18n import t

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
FOLDER_KEYS = ["input_image", "heatmap", "bcset", "model", "simconf", "output"]


def folder_label(key: str) -> str:
    return t(f"folder.{key}")

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
    name: str = ""                     # ユーザー入力の名前（空なら name_key / 既定）
    name_key: str = ""                 # サンプル用の i18n キー（name 未設定時に使う）
    input_image: str = ""              # ファイル名のみ（フォルダは FolderConfig 側）
    heatmap: str = ""
    init_stress: str = "none"          # none | prev | file
    stress_r: str = ""                 # init_stress == "file" のときの絶対パス
    stress_g: str = ""
    stress_b: str = ""
    model: dict = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_MODEL.items()})
    simconf: dict = field(default_factory=lambda: dict(DEFAULT_SIMCONF))
    status: str = "pending"            # pending | running | done | done_existing

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
        return t(f"kind.{self.kind}")

    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.name_key:
            return t(self.name_key)
        return t("steps.new")


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
