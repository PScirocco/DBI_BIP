"""パッケージング（T9 / フェーズE）の静的チェック。

PyInstaller の実ビルドは走らせない（社内ネットワーク必須・時間がかかる）。
spec / launcher が壊れていないこと、同梱対象が存在すること、
配布時の既定出力フォルダの切り替えだけを確認する。
"""
from __future__ import annotations

import sys
from pathlib import Path

from bisim import paths

_REPO = paths.REPO_DIR
_PKG = _REPO / "installer"


def test_packaging_files_present_and_compile():
    spec = _PKG / "bisim.spec"
    launcher = _PKG / "bisim_launcher.py"
    assert spec.exists() and launcher.exists()
    # 構文チェック（exec はしない: spec は PyInstaller 注入名に依存）
    compile(spec.read_text(encoding="utf-8"), str(spec), "exec")
    src = launcher.read_text(encoding="utf-8")
    compile(src, str(launcher), "exec")
    assert "bisim.__main__" in src and "freeze_support" in src
    # 劣化コアは datas 同梱＋ファイルパスロード。"main" を hiddenimports の要素に入れない
    spec_txt = spec.read_text(encoding="utf-8")
    assert 'str(SRC / "main.py")' in spec_txt          # datas に main.py
    assert 'str(SRC / "load_com_info.py")' in spec_txt
    _hi = spec_txt.split("hiddenimports = [", 1)[1].split("]", 1)[0]
    assert '"main"' not in _hi                          # リスト要素としての "main" は無い
    assert '"load_com_info"' in _hi


def test_engine_loads_core_by_file_path():
    """engine._load_core が source/main.py（新コア）を掴めること（frozen 相当の経路）。"""
    from bisim import engine
    engine._CORE_MOD = None
    mod = engine._load_core()
    assert mod.__file__ == str(paths.SOURCE_DIR / "main.py")
    assert mod.burn_in_core.__name__ == "burn_in_core"
    assert callable(mod.burn_in_band_extract) and callable(mod.com_info.load_degparam_sm)


def test_spec_bundles_existing_sample_inputs():
    """spec が挙げる同梱サンプルが実在すること（build_exe.ps1 の前提）。"""
    common = _REPO / "source" / "dbi_common"
    for f in ("mov_001_480x270.mp4", "mov_ht_001_480x270.mp4",
              "eval_img.png", "eval_img_ht.png"):
        assert (common / f).exists(), f"{f} が無い"
    assert (_REPO / "source" / "main.py").exists()
    assert (_REPO / "source" / "load_com_info.py").exists()
    # 新コアの標準ファイル（フェーズF）：パネル設定は dbi_conf、Sim 条件は dbi_input
    for f in ("bcsetting.csv", "degparam_mm.csv", "degparam_sm.csv"):
        assert (_REPO / "source" / "dbi_conf" / f).exists(), f
    assert (_REPO / "source" / "dbi_input" / "simconf.csv").exists()


def test_default_output_switches_when_frozen():
    assert paths._default_output() == paths.SOURCE_DIR / "dbi_output"
    had = hasattr(sys, "frozen")
    sys.frozen = True
    try:
        assert paths._default_output() == paths.APP_DIR / "bisim_output"
    finally:
        if had:
            pass
        else:
            del sys.frozen
