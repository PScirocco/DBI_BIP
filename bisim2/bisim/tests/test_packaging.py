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


def test_engine_loads_master_by_file_path():
    """engine._load_burn_fn が source/main.py を掴めること（frozen 相当の経路）。"""
    from bisim import engine
    engine._BURN_FN = None
    fn = engine._load_burn_fn()
    assert callable(fn)
    assert fn.__name__ == "temp_update_stat_and_burn_img"


def test_spec_bundles_existing_sample_inputs():
    """spec が挙げる同梱サンプルが実在すること（build_exe.ps1 の前提）。"""
    common = _REPO / "source" / "dbi_common"
    for f in ("mov_001_480x270.mp4", "mov_ht_001_480x270.mp4",
              "eval_img.png", "eval_img_ht.png"):
        assert (common / f).exists(), f"{f} が無い"
    assert (_REPO / "source" / "main.py").exists()
    assert (_REPO / "source" / "load_com_info.py").exists()
    assert (_REPO / "source" / "dbi_conf" / "degparam_mm.csv").exists()
    assert (_REPO / "source" / "dbi_input" / "bcsetting.csv").exists()


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
