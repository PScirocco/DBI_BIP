"""logio.py のテスト（仕様 6）"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from bisim.logio import Logger

_SESSION_RE = re.compile(r"BISim_\d{6}-\d{6}\.log")


def test_writes_session_file():
    with tempfile.TemporaryDirectory() as d:
        lg = Logger(log_dir=d, max_mb=10)
        lg.action("開始")
        lg.io("in", "aging01_movie.mp4")
        lg.param_change("ACCEL_RATIO", 30000, 40000)
        p = lg._session_path()
        assert _SESSION_RE.fullmatch(p.name)
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "[action] 開始" in text
        assert "[io/in] aging01_movie.mp4" in text
        assert "[param] ACCEL_RATIO: 30000 -> 40000" in text


def test_different_sessions_use_different_files():
    with tempfile.TemporaryDirectory() as d:
        lg1 = Logger(log_dir=d, max_mb=10)
        lg1._session = "260909-090000"       # 起動時刻が異なる2セッションを再現
        lg1.action("セッション1")
        lg2 = Logger(log_dir=d, max_mb=10)
        lg2._session = "260909-100000"
        lg2.action("セッション2")
        assert lg1._session_path() != lg2._session_path()
        files = sorted(p.name for p in Path(d).glob("BISim_*.log"))
        assert files == ["BISim_260909-090000.log", "BISim_260909-100000.log"]


def test_session_rolls_to_new_part_when_full():
    with tempfile.TemporaryDirectory() as d:
        lg = Logger(log_dir=d, max_mb=10)
        lg.max_mb = 100 / (1024 * 1024)     # 上限を極端に小さく（約100バイト）
        p1 = lg._session_path()
        p1.write_bytes(b"x" * 90)            # 事前に上限近くまで埋めておく（決定的にするため）
        assert lg._part == 1
        lg.action("この行で1ファイル目の上限を超えて2本目のパートへ")
        assert lg._part == 2
        p2 = lg._session_path()
        assert p2.name == p1.name.replace(".log", "_02.log")
        assert p2.exists()
        assert "この行で1ファイル目の上限を超えて2本目のパートへ" in p2.read_text(encoding="utf-8")


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
        lg.action("今回のログ")               # 書き込み → rotate 発火
        remaining = sorted(p.name for p in dd.glob("BISim_*.log"))
        assert "BISim_250101.log" not in remaining   # 最古が削除
        assert lg._session_path().name in remaining  # 今回のセッションログは残る
