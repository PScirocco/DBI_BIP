# -*- mode: python ; coding: utf-8 -*-
"""BI-sim（bisim GUI）の PyInstaller spec。PyInstaller 6.x 用。

    pyinstaller installer/bisim.spec           # リポジトリ直下から
    →  dist/BI-sim/BI-sim.exe                   （onedir。フォルダごと配布）

onefile（単一 .exe）にしたい場合は下部のコメント参照。
IP設計者へは onedir + zip を推奨（起動が速い／AV 誤検知が少ない）。
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

REPO = Path(SPECPATH).parent          # SPECPATH = installer/
SRC = REPO / "source"

# ---- 同梱データ（実行時に SOURCE_DIR=<_MEIPASS>/source から参照される）----
datas = [
    # 劣化コア（暫定モデル）。engine._load_burn_fn がこの main.py をファイルパスで直接ロードする。
    (str(SRC / "main.py"), "source"),
    (str(SRC / "load_com_info.py"), "source"),
    (str(SRC / "dbi_conf"), "source/dbi_conf"),          # degparam_mm.csv / simconf.csv
    (str(SRC / "dbi_input"), "source/dbi_input"),         # bcsetting.csv
]
# 小さいサンプル入力だけ同梱（大きい原寸動画 input.* / mov_001.mp4 は入れない）
for _f in ("mov_001_480x270.mp4", "mov_ht_001_480x270.mp4", "eval_img.png", "eval_img_ht.png"):
    _p = SRC / "dbi_common" / _f
    if _p.exists():
        datas.append((str(_p), "source/dbi_common"))
datas += collect_data_files("matplotlib")               # mpl-data（フォント等）

# ---- 隠れ import ----
# 劣化コアは datas 同梱＋ファイルパスロードなので "main" は hiddenimports に入れない
# （"main" はありふれた名前で frozen のモジュール解決が別物を掴む事故の元）。
# load_com_info は main.py が `import load_com_info` するので保険で入れておく。
hiddenimports = [
    "load_com_info",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_agg",
]

# ---- 使わない重量モジュールを除外（サイズ削減）----
excludes = [
    "tkinter", "PyQt5", "PyQt6", "IPython", "pytest", "pandas",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtDesigner",
    "PySide6.QtSensors", "PySide6.QtPositioning", "PySide6.QtWebSockets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSql", "PySide6.QtTest",
]

a = Analysis(
    [str(REPO / "installer" / "bisim_launcher.py")],
    pathex=[str(REPO)],                     # `import bisim` 用（source/ は datas 経由なので不要）
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BI-sim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # Qt DLL と相性が悪く AV 誤検知も増えるため無効
    console=False,             # GUI アプリ（コンソール窓を出さない）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon=str(REPO / "installer" / "bisim.ico"),   # アイコンを用意したら有効化
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BI-sim",
)

# --- onefile（単一 .exe）にする場合 ---
# 上の EXE(...) の引数を  EXE(pyz, a.scripts, a.binaries, a.datas, [], name="BI-sim",
#   console=False, upx=False, ...)  に変え、exclude_binaries を外し、COLLECT を削除する。
