"""モデル/Sim パラメータ CSV の読み書き（CLI版と完全互換）

書式は ``source/load_com_info.py`` に合わせる:
- model-param (``degparam_mm.csv``): 1行 ``KEY,r,g,b``（KEY ∈ N/K0/Q/B0/A）
- sim-param  (``simconf.csv``)     : 1行 ``KEY,値``（KEY ∈ AGING_TIME/ACCEL_RATIO/TMP_L/TMP_H/DBV_NIT/DPK_ON）、
  ``GADJ`` だけ ``GADJ,r,g,b``

読み込みは ``utf-8-sig``（BOM 許容）、書き込みは ``utf-8``（BOM なし）。
"""
from __future__ import annotations

from pathlib import Path

from bisim.model import (
    DEFAULT_MODEL, MODEL_KEYS, SIM_KEYS, SIM_RGB_KEYS, _fresh_sim, parse_sim_value,
)


def read_model_csv(path) -> dict:
    """``{"N":[r,g,b], "K0":[...], ...}`` を返す。欠けは既定値で補完。"""
    out = {k: list(v) for k, v in DEFAULT_MODEL.items()}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        p = line.strip().split(",")
        if len(p) >= 4 and p[0] in MODEL_KEYS:
            out[p[0]] = [float(p[1]), float(p[2]), float(p[3])]
    return out


def write_model_csv(path, model: dict) -> None:
    lines = [f"{k}," + ",".join(f"{float(v):g}" for v in model[k]) for k in MODEL_KEYS]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_sim_csv(path) -> dict:
    """Sim 条件 CSV を読む。無い項目は既定値（旧形式の4項目だけの CSV も読める）。

    値を読めない行は ``ValueError``（画面は「読み込めない」と表示する）。
    """
    out = _fresh_sim()
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        p = line.strip().split(",")
        if not p or p[0] not in SIM_KEYS:
            continue
        key = p[0]
        if key in SIM_RGB_KEYS:
            if len(p) < 4:
                raise ValueError(f"{key} は R,G,B の3つの値が必要: {line!r}")
            out[key] = parse_sim_value(key, p[1:4])
        elif len(p) >= 2:
            out[key] = parse_sim_value(key, p[1])
    return out


def _fmt(v) -> str:
    return str(v) if isinstance(v, int) else f"{float(v):g}"


def write_sim_csv(path, sim: dict) -> None:
    lines = []
    for k in SIM_KEYS:
        v = parse_sim_value(k, sim[k])
        lines.append(f"{k}," + (",".join(_fmt(x) for x in v) if k in SIM_RGB_KEYS else _fmt(v)))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def to_mm_dict(model: dict) -> dict:
    """``{"N":[r,g,b],...}`` → ``{"N_r":.., "N_g":.., "N_b":.., ...}``

    ``source/main.py`` の ``burn_in_core`` が要求する形式。
    """
    d = {}
    for k in MODEL_KEYS:
        r, g, b = model[k]
        d[f"{k}_r"], d[f"{k}_g"], d[f"{k}_b"] = float(r), float(g), float(b)
    return d
