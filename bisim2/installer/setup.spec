# -*- mode: python ; coding: utf-8 -*-
"""BI-sim セットアップ（インストーラ）の PyInstaller spec。PyInstaller 6.x 用。onefile（1つの EXE）。

    build_exe.ps1 が、dist/BI-sim をビルドしたあと
      dist/BI-sim_payload.zip（dist/BI-sim の中身）と dist/payload_info.txt（バージョン）を作り、
      pyinstaller installer/setup.spec を実行する  →  dist/BI-sim_setup.exe
    （build_exe.ps1 が日付付きの名前 dist/BI-sim_setup_YYMMDD.exe に変える）

インストールするPCに Python は要らない（EXE の中に入る）。画面は tkinter。
"""
from pathlib import Path

REPO = Path(SPECPATH).parent          # SPECPATH = installer/
DIST = REPO / "dist"

datas = [
    (str(DIST / "BI-sim_payload.zip"), "."),
    (str(DIST / "payload_info.txt"), "."),
]

# BI-sim 本体の重いモジュールは要らない（セットアップは標準ライブラリと tkinter だけ）
excludes = [
    "PySide6", "numpy", "cv2", "matplotlib", "pandas", "openpyxl", "pptx", "PIL", "pytest",
    "IPython", "PyQt5", "PyQt6",
]

a = Analysis(
    [str(Path(SPECPATH) / "setup_main.py")],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox", "winreg"],
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BI-sim_setup",
    console=False,                     # 黒い画面を出さない
    upx=False,                         # ウイルス対策ソフトの誤検知を減らす
    runtime_tmpdir=None,
)
