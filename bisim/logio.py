"""ログ（T5 / 仕様 6）

- 出力先: アプリのあるフォルダ直下 ``_log_BISim/``（無ければ作成）
- **セッションローテーション**（IP設計者レビュー2 (1)）: アプリ起動ごとに新しいファイル
  ``BISim_YYMMDD-HHMMSS.log``。1ファイルの大きさ感は従来の日次ログと同程度に保つため、
  同一セッション中でもファイルが上限(MB)に達したら ``..._02.log`` ``..._03.log`` … と続ける
- 総容量が上限(MB)を超えたら古いファイルから削除（従来どおり）
- 画面表示用に listener を登録できる
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from bisim.paths import LOG_DIR

_GLOB = "BISim_*.log"


class Logger:
    def __init__(self, log_dir=LOG_DIR, max_mb: float = 50.0) -> None:
        self.dir = Path(log_dir)
        self.max_mb = float(max_mb)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._listeners: list[Callable[[str], None]] = []
        self._session = datetime.now().strftime("%y%m%d-%H%M%S")   # 起動(セッション)ごとに固定
        self._part = 1

    # -- 購読（画面表示用）--
    def add_listener(self, cb: Callable[[str], None]) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def remove_listener(self, cb) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    # -- 公開 API --
    def action(self, msg: str) -> None:
        self._emit(f"[action] {msg}")

    def io(self, direction: str, name: str) -> None:      # direction: "in" / "out"
        self._emit(f"[io/{direction}] {name}")

    def param_change(self, what: str, old, new) -> None:
        self._emit(f"[param] {what}: {old} -> {new}")

    def error(self, msg: str) -> None:
        self._emit(f"[error] {msg}")

    # -- 内部 --
    def _session_path(self) -> Path:
        suffix = "" if self._part == 1 else f"_{self._part:02d}"
        return self.dir / f"BISim_{self._session}{suffix}.log"

    def _advance_part_if_full(self, line: str) -> None:
        """同一セッション中でも1ファイルが上限(MB)を超えないよう、パートを進める。"""
        limit = self.max_mb * 1024 * 1024
        p = self._session_path()
        try:
            size = p.stat().st_size if p.exists() else 0
        except OSError:
            size = 0
        if size and size + len(line.encode("utf-8")) + 1 > limit:
            self._part += 1

    def _emit(self, body: str) -> None:
        line = f"{datetime.now().strftime('%y-%m-%d %H:%M:%S')}  {body}"
        self._advance_part_if_full(line)
        try:
            with open(self._session_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        for cb in list(self._listeners):
            try:
                cb(line)
            except Exception:  # noqa: BLE001  リスナーの失敗でログを止めない
                pass
        self._rotate()

    def _rotate(self) -> None:
        files = sorted(self.dir.glob(_GLOB))
        limit = self.max_mb * 1024 * 1024
        total = sum(f.stat().st_size for f in files if f.exists())
        while total > limit and len(files) > 1:
            oldest = files.pop(0)
            try:
                total -= oldest.stat().st_size
                oldest.unlink()
            except OSError:
                break


def make_logger(max_mb: float = 50.0, log_dir=LOG_DIR) -> Logger:
    return Logger(log_dir=log_dir, max_mb=max_mb)
