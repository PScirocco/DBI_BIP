"""tools 共通：シーケンスファイル（*.seq.json）からフォルダを決める。

シーケンスの ``folders`` に書く相対パスは、**bisim.exe のフォルダから見たパス**
（開発環境ではリポジトリ直下から見たパス）。bisim の ``Sequence.load`` と同じ規則。
例：``"eval_test/rgbcircle/input"`` → ``<bisim.exe のフォルダ>/eval_test/rgbcircle/input``

tools のスクリプトでは、相対パスの基準（＝bisim.exe のフォルダ）を ``--app-dir`` で指定できる。
指定しなければリポジトリ直下（開発環境の bisim と同じ）。

フォルダは次の順で決める。

1. コマンドで直接指定されたフォルダ（``--input-dir`` / ``--bisim-out`` など）
2. シーケンスの ``folders`` に書かれたパス（相対パスは ``--app-dir`` が基準）
3. 2 がそのPCに無ければ、シーケンスファイルの横の既定の名前（``input`` / ``output``）
   （別PCからシーケンスと結果をフォルダごと持ち帰ったとき用）
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

APP_DIR_HELP = ("相対パスの基準にするフォルダ＝bisim.exe のフォルダ"
                "（既定：リポジトリ直下。開発環境の python -m bisim と同じ）")


def load_sequence(path) -> tuple:
    """(シーケンスの dict, シーケンスファイルの絶対パス)。"""
    p = Path(path).resolve()
    if not p.is_file():
        raise SystemExit(f"シーケンスファイルが見つかりません: {p}")
    return json.loads(p.read_text(encoding="utf-8")), p


def app_dir(arg=None) -> Path:
    """相対パスの基準（``--app-dir`` の値。無ければリポジトリ直下）。"""
    return Path(arg).resolve() if arg else REPO


def resolve_folder(seq: dict, seq_path: Path, key: str, fallback: str, override=None,
                   app_dir_arg=None, quiet: bool = False) -> Path:
    """フォルダを決める（上の 1→2→3 の順）。見つからなければ 2 のパスをそのまま返す。"""
    if override:
        return Path(override).resolve()
    written = (seq.get("folders") or {}).get(key, "")
    cand = None
    if written:
        cand = Path(written)
        if not cand.is_absolute():
            cand = app_dir(app_dir_arg) / cand
        if cand.exists():
            return cand.resolve()
    fb = Path(seq_path).parent / fallback
    if fb.exists():
        if written and not quiet:
            print(f"  （{key}: シーケンスに書かれたフォルダ {written} が見つからないため、"
                  f"シーケンスの横の {fb} を使います）")
        return fb.resolve()
    return (cand or fb).resolve()


def to_app_relative(p: Path, app_dir_arg=None) -> str:
    """シーケンスに書く形：基準フォルダの下なら相対パス（/ 区切り）、外なら絶対パス。"""
    try:
        return Path(p).resolve().relative_to(app_dir(app_dir_arg)).as_posix()
    except ValueError:
        return str(Path(p).resolve())


def display_path(p: Path, repo: Path = REPO) -> str:
    """表示用：リポジトリ内ならリポジトリからの相対パス、外なら絶対パス。"""
    try:
        return Path(p).resolve().relative_to(Path(repo).resolve()).as_posix()
    except ValueError:
        return str(p)
