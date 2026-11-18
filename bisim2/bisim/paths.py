"""パス・既定フォルダの定義（仕様 3, 5-①, 6）"""
from __future__ import annotations

import sys
from pathlib import Path

BISIM_DIR = Path(__file__).resolve().parent
REPO_DIR = BISIM_DIR.parent
SOURCE_DIR = REPO_DIR / "source"


def app_dir() -> Path:
    """アプリのあるフォルダ。配布(PyInstaller)時は実行ファイルのフォルダ、
    開発時はリポジトリ直下。ログ・アプリConfig の基準（仕様 3.1 / 6）。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return REPO_DIR


APP_DIR = app_dir()
LOG_DIR = APP_DIR / "_log_BISim"
APP_CONFIG_PATH = APP_DIR / "bisim_app.json"


def _default_output() -> Path:
    """既定の出力フォルダ。

    配布（PyInstaller）時は読み取り専用の同梱データではなく、実行ファイル横の
    書き込み可能な ``bisim_output/`` を既定にする。開発時は従来どおり
    ``source/dbi_output``。
    """
    if getattr(sys, "frozen", False):
        return APP_DIR / "bisim_output"
    return SOURCE_DIR / "dbi_output"


# 実行シーケンスが持つ 6 種のフォルダ（仕様 3.2 / 5-①）
FOLDER_KEYS = ["input_image", "heatmap", "bcset", "model", "simconf", "output"]

DEFAULT_FOLDERS: dict[str, Path] = {
    "input_image": SOURCE_DIR / "dbi_common",
    "heatmap":     SOURCE_DIR / "dbi_common",
    "bcset":       SOURCE_DIR / "dbi_conf",     # 新コア（フェーズF）の置き方：パネル設定は dbi_conf
    "model":       SOURCE_DIR / "dbi_conf",
    "simconf":     SOURCE_DIR / "dbi_input",    # Sim 条件は dbi_input
    "output":      _default_output(),
}

# パネル設定の標準ファイル（新コア。手順5 でシーケンスに持たせるまでは常にこれを使う）
STD_BCSET = SOURCE_DIR / "dbi_conf" / "bcsetting.csv"
STD_DEGPARAM_MM = SOURCE_DIR / "dbi_conf" / "degparam_mm.csv"
STD_DEGPARAM_SM = SOURCE_DIR / "dbi_conf" / "degparam_sm.csv"
