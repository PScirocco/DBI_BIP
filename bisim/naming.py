"""ファイル命名規則（仕様 4）

- 入力 : ``レシピ名_種別[_色].拡張子``
- 出力 : ``シーケンス名_NN_レシピ名_種別[_色][_YYMMDD-HHMM].拡張子``
  （NN = シーケンス内通し番号 2桁、末尾の日時は「停止保存」時のみ）

レシピ名・シーケンス名は ``sanitize_name`` でファイル安全化する。
``_`` は区切り文字専用なので名前から除去する（``-`` に置換）ため、
パースは一意に行える。

種別トークンについて:
- ``deg`` / ``stat`` は色別（r/g/b）。
- ``model-param`` / ``sim-param`` は CLI 版（source/load_com_info.py）と互換の
  単一ファイル（色なし）を想定。※仕様 4 の例 ``_model-param_r`` は要確認。
"""
from __future__ import annotations

import re
from datetime import datetime

KINDS = ("deg", "stat", "movie", "image", "model-param", "sim-param")
COLORS = ("r", "g", "b")

_TS_FMT = "%y%m%d-%H%M"
_TS_RE = re.compile(r"\d{6}-\d{4}")
_NN_RE = re.compile(r"\d{2}")
_UNSAFE_RE = re.compile(r'[_/\\:*?"<>|\s]+')


def sanitize_name(name: str) -> str:
    """ファイル名の一部として安全な文字列にする。

    ``_`` ・空白・Windows で使えない文字を ``-`` に。Unicode（日本語等）は許可。
    """
    s = _UNSAFE_RE.sub("-", (name or "").strip())
    s = re.sub(r"-{2,}", "-", s).strip("-. ")
    return s or "unnamed"


def timestamp(dt: datetime | None = None) -> str:
    """停止保存用の日時トークン ``YYMMDD-HHMM``。"""
    return (dt or datetime.now()).strftime(_TS_FMT)


def _nn(value) -> str:
    if isinstance(value, str):
        if not _NN_RE.fullmatch(value):
            raise ValueError(f"NN は2桁の数字文字列: {value!r}")
        return value
    return f"{int(value):02d}"


def _join(*bits: str | None) -> str:
    return "_".join(b for b in bits if b)


def _ext(ext: str) -> str:
    return ext.lstrip(".")


def input_name(recipe_name: str, kind: str, color: str | None = None,
               ext: str = "csv") -> str:
    if kind not in KINDS:
        raise ValueError(f"未知の種別: {kind!r}")
    if color is not None and color not in COLORS:
        raise ValueError(f"未知の色: {color!r}")
    return f"{_join(sanitize_name(recipe_name), kind, color)}.{_ext(ext)}"


def output_name(sequence_name: str, nn, recipe_name: str, kind: str,
                color: str | None = None, ext: str = "csv",
                stopped_at: datetime | str | None = None) -> str:
    if kind not in KINDS:
        raise ValueError(f"未知の種別: {kind!r}")
    if color is not None and color not in COLORS:
        raise ValueError(f"未知の色: {color!r}")
    ts = None
    if stopped_at is not None:
        ts = stopped_at if isinstance(stopped_at, str) else timestamp(stopped_at)
        if not _TS_RE.fullmatch(ts):
            raise ValueError(f"日時トークンの書式が不正: {ts!r}")
    return (f"{_join(sanitize_name(sequence_name), _nn(nn), sanitize_name(recipe_name), kind, color, ts)}"
            f".{_ext(ext)}")


def _split_stem(filename: str) -> tuple[str, str]:
    stem, dot, ext = filename.rpartition(".")
    return (stem, ext) if dot else (filename, "")


def parse_output(filename: str) -> dict | None:
    """出力ファイル名を分解。想定外なら None。"""
    stem, ext = _split_stem(filename)
    toks = stem.split("_")
    ts = color = kind = None
    if toks and _TS_RE.fullmatch(toks[-1]):
        ts = toks.pop()
    if toks and toks[-1] in COLORS:
        color = toks.pop()
    if toks and toks[-1] in KINDS:
        kind = toks.pop()
    else:
        return None
    if len(toks) != 3 or not _NN_RE.fullmatch(toks[1]):
        return None
    return {"sequence": toks[0], "nn": toks[1], "recipe": toks[2],
            "kind": kind, "color": color, "timestamp": ts, "ext": ext}


def parse_input(filename: str) -> dict | None:
    """入力ファイル名を分解。想定外なら None。"""
    stem, ext = _split_stem(filename)
    toks = stem.split("_")
    color = kind = None
    if toks and toks[-1] in COLORS:
        color = toks.pop()
    if toks and toks[-1] in KINDS:
        kind = toks.pop()
    else:
        return None
    if len(toks) != 1:
        return None
    return {"recipe": toks[0], "kind": kind, "color": color, "ext": ext}
