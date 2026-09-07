"""logio.py のテスト（仕様 6）"""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from bisim.logio import Logger


def test_writes_dated_file():
    with tempfile.TemporaryDirectory() as d:
        lg = Logger(log_dir=d, max_mb=10)
        lg.action("開始")
        lg.io("in", "aging01_movie.mp4")
        lg.param_change("ACCEL_RATIO", 30000, 40000)
        fname = f"BISim_{datetime.now().strftime('%y%m%d')}.log"
        p = Path(d) / fname
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "[action] 開始" in text
        assert "[io/in] aging01_movie.mp4" in text
        assert "[param] ACCEL_RATIO: 30000 -> 40000" in text


def test_listener():
    with tempfile.TemporaryDirectory() as d:
        lg = Logger(log_dir=d, max_mb=10)
        got: list[str] = []
        lg.add_listener(got.append)
        lg.action("hello")
        assert len(got) == 1 and "[action] hello" in got[0]
        lg.remove_listener(got.append)


def test_rotation_deletes_oldest():
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        # 過去日の大きめログを2つ用意
        old1 = dd / "BISim_250101.log"
        old2 = dd / "BISim_250102.log"
        old1.write_bytes(b"x" * 300_000)
        old2.write_bytes(b"y" * 300_000)
        lg = Logger(log_dir=dd, max_mb=0.5)   # 上限 ~524288 bytes
        lg.action("今日のログ")               # 書き込み → rotate 発火
        remaining = sorted(p.name for p in dd.glob("BISim_*.log"))
        assert "BISim_250101.log" not in remaining   # 最古が削除
        assert f"BISim_{datetime.now().strftime('%y%m%d')}.log" in remaining
