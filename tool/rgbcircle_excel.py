"""理論確認テスト（3色円）の理論値を Excel の数式で計算し、bisim の出力と比べるブックを作る（新コア）。

Python の理論計算（tool/rgbcircle_theory.py）とは別に、劣化モデル（新コア：松井さん Burn_in_sim_core_01）の式を
Excel の数式だけで計算する。比較には、30フレームすべてで画素値が理想どおり（その色＝255、ほかの色＝0）
の画素を使う（MP4 の非可逆圧縮の影響を受けない画素なので、Excel 側の入力を 255 の定数にできる）。

新コアではストレスが「劣化前の電流」で貯まるので、累積時間は フレーム数 × 1フレームの増分 の掛け算になる
（旧コアのように1フレームずつ順に計算する必要がない）。そのため「計算」シートは 1行＝評価時点（7行）。

シート:
  説明        理論式（文字）、記号の意味、数値例、比較に使う画素、判定基準、使い方
  パラメータ  モデルパラメータ・Sim条件・Band のデータ（青字が入力。書き換えると全体が再計算される）と、そこから求める値
  サブモデル  degparam_sm.csv のうち、使う2つの Band の表（R/G/B）。青字が入力
  計算        1行＝評価時点。累積時間 → deg → サブモデルの表の補間（deg2）→ 評価画像の画素値
  比較        7つの評価時点 × R/G/B で、Excel の値と bisim の値（CSV・評価画像）を並べて判定

使い方（Burn-In_Simv2 直下で）:
  bisim2\\.venv\\Scripts\\python tool\\rgbcircle_excel.py [--seq <シーケンス>] [--bisim-out <bisimの出力フォルダ>] [--out <xlsx>]
  例）別PCからフォルダごとコピーした結果で作る：
      bisim2\\.venv\\Scripts\\python tool\\rgbcircle_excel.py --seq bisim2\\eval_test_other-PC\\rgbcircle\\rgbcircle.seq.json
  フォルダ・パネル設定ファイルの決め方は tool/rgbcircle_theory.py と同じ
  作成後、Excel で開くと計算される（このスクリプトは Excel があれば開いて計算・保存まで行う）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# bisim 本体（bisim/・source/・eval_test/）は tool/ の横の bisim2/ にある
REPO = Path(__file__).resolve().parent.parent / "bisim2"
TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))
from _seqpaths import APP_DIR_HELP, display_path, load_sequence, resolve_folder  # noqa: E402
from rgbcircle_theory import SIM_DEFAULTS, Panel, panel_files  # noqa: E402  （CSV の読み込みと Band の選び方だけ使う）
FONT = "Meiryo UI"

SEQ = "rgbcircle"
EVALS = [("02", "eval-0h30m", 0.5), ("04", "eval-1h", 1), ("06", "eval-2h", 2), ("08", "eval-5h", 5),
         ("10", "eval-10h", 10), ("12", "eval-20h", 20), ("14", "eval-50h", 50)]
# 30フレームすべてで画素値が理想どおりの画素（円の中心に近いもの）。(x, y)
PIXELS = {"R": (120, 159), "G": (64, 285), "B": (175, 287)}
COLORS = ["R", "G", "B"]
BGR = {"R": 2, "G": 1, "B": 0}
MODEL_KEYS = ["N", "K0", "Q", "B0", "A"]

thin = Side(style="thin", color="999999")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
HEAD_FILL = PatternFill("solid", fgColor="D9E1F2")
SUB_FILL = PatternFill("solid", fgColor="F2F2F2")
OK_FILL = PatternFill("solid", fgColor="E2EFDA")
NUM = "0.000000000000000"


def f(bold=False, color="000000", size=10, italic=False):
    return Font(name=FONT, bold=bold, color=color, size=size, italic=italic)


INPUT = f(color="0000FF")


def cell(ws, ref, value, font=None, fill=None, fmt=None, align=None, border=True):
    c = ws[ref]
    c.value = value
    c.font = font or f()
    if fill:
        c.fill = fill
    if fmt:
        c.number_format = fmt
    if align:
        c.alignment = align
    if border:
        c.border = BORDER
    return c


P = "パラメータ"
PCOL = {"R": "B", "G": "C", "B": "D"}          # パラメータシートの列 B/C/D = R/G/B
ROW = {}                                        # 項目名 → パラメータシートの行（sheet_params が埋める）


def pref(key, color=None):
    """パラメータシートのセル参照。color を渡すと色の列、渡さなければ B 列。"""
    return f"{P}!${PCOL[color] if color else 'B'}${ROW[key]}"


# --------------------------------------------------------------------------- #
def sheet_params(wb, mm: dict, sim: dict, panel: Panel, bands: tuple):
    eff, b1, b2 = bands
    ws = wb.create_sheet(P)
    ws.column_dimensions["A"].width = 34
    for col in "BCD":
        ws.column_dimensions[col].width = 17
    ws.column_dimensions["E"].width = 8
    ws.column_dimensions["F"].width = 80
    cell(ws, "A1", "パラメータ（青字が入力。書き換えると「計算」「比較」シートが再計算される）", f(bold=True, size=11), border=False)

    def head(r, title):
        cell(ws, f"A{r}", title, f(bold=True, size=11), border=False)
        for col, h in zip("ABCDEF", ["項目", "R", "G", "B", "単位", "説明"]):
            cell(ws, f"{col}{r + 1}", h, f(bold=True), HEAD_FILL, align=Alignment(horizontal="center"))
        return r + 2

    def row(r, key, label, values, unit, note, fmt="General", is_input=True):
        ROW[key] = r
        cell(ws, f"A{r}", label, f(bold=True))
        if isinstance(values, (list, tuple)):
            for col, v in zip("BCD", values):
                cell(ws, f"{col}{r}", v, INPUT if is_input else f(), fmt=fmt)
        else:
            cell(ws, f"B{r}", values, INPUT if is_input else f(), fmt=fmt)
        cell(ws, f"E{r}", unit, align=Alignment(horizontal="center"))
        cell(ws, f"F{r}", note, align=Alignment(wrap_text=True))
        return r + 1

    r = head(3, "■ マスターモデル（degparam_mm＝シーケンスのパネル設定の mm）")
    notes = {"N": ("−", "加速係数（電流に対するストレスの効き方）。電流^N"),
             "K0": ("−", "τ（寿命の目安）に相当する係数。大きいほどストレスが貯まりにくい"),
             "Q": ("K", "温度依存の係数（アレニウス型）。exp(Q÷T)"),
             "B0": ("−", "劣化カーブの形 β の基準値"),
             "A": ("1/K", "β の温度依存（β = B0 + A×T）。既定 0")}
    for k in MODEL_KEYS:
        r = row(r, k, k, [float(x) for x in mm[k]], *notes[k])
    cols = "BCD"

    r = head(r + 1, "■ Sim 条件（シーケンスのステップの値）")
    r = row(r, "accel", "ACCEL_RATIO", float(sim["ACCEL_RATIO"]), "倍", "1秒の表示を何秒分の Aging とみなすか", "0")
    r = row(r, "fps", "fps", 30, "1/s", "動画のフレームレート（rgbcircle-aging_movie.mp4）", "0")
    r = row(r, "temp", "固定温度", 25.0, "℃", "ヒートマップなし（パネル全面が同じ温度）。PQ評価も 25℃", "0.0")
    r = row(r, "T", "T（絶対温度）", f"=B{ROW['temp']}+273", "K", "T = 温度 + 273", "0.0", False)
    r = row(r, "dt", "Δt（1フレームの時間）", f"=1/B{ROW['fps']}", "s", "Δt = 1 ÷ fps", "0.0000000", False)
    r = row(r, "dtacc", "1フレームの加速込み時間", f"=B{ROW['dt']}*B{ROW['accel']}", "s", "Δt × ACCEL_RATIO（= 120 秒）", "0.0", False)
    r = row(r, "dbv", "DBV_NIT", float(sim["DBV_NIT"]), "nit", "パネルの輝度設定（ピーク輝度）。DPK_ON=0", "0")
    r = row(r, "gadj", "GADJ", [float(x) for x in sim["GADJ"]], "倍", "電流調整（GI_LUT の電流を何倍にするか）", "0.000")
    r = row(r, "v", "画素値 v", 255, "−", "比較に使う画素の値（その色の円の中＝255。評価画像も白＝255）", "0")
    r = row(r, "gamma", "ガンマ γ", 2.2, "−", "画素値→輝度の変換 (v/255)^γ", "0.0")
    r = row(r, "beta", "β（= B0 + A×T）", [f"={c}{ROW['B0']}+{c}{ROW['A']}*$B${ROW['T']}" for c in cols], "−",
            "コアの中で画像に使う deg の β（T は固定温度）。出力の deg CSV は β = B0（11/12 決定）", "0.000", False)

    r = head(r + 1, f"■ Band のデータ（bcsetting.csv から。DBV_NIT={sim['DBV_NIT']:g} をはさむ2つの Band）")
    cell(ws, f"A{r}", f"使う Band：BC1＝Band{b1}（{panel.dbv[b1]:g} nit）、BC2＝Band{b2}（{panel.dbv[b2]:g} nit）。"
                      f"DBV_NIT を通常の Band の範囲（{panel.dbv[-1]:g}〜{panel.dbv[panel.n_dpk]:g} nit）に収めた値（DBV_eff）をはさむ2つ。"
                      "Band の選び方はこのブックでは計算していない（Python で選んだ Band の値を入力している）",
         f(size=9), border=False)
    ws.merge_cells(f"A{r}:F{r}")
    ws.row_dimensions[r].height = 28
    ws[f"A{r}"].alignment = Alignment(wrap_text=True, vertical="top")
    r += 1
    r = row(r, "dbveff", "DBV_eff", f"=MIN(MAX(B{ROW['dbv']},{panel.dbv[-1]:g}),{panel.dbv[panel.n_dpk]:g})", "nit",
            "DBV_NIT を通常の Band の範囲に収めた値", "0.0", False)
    r = row(r, "dbv1", "DBV_NIT_BC（BC1）", float(panel.dbv[b1]), "nit", f"Band{b1} のピーク輝度", "0")
    r = row(r, "dbv2", "DBV_NIT_BC（BC2）", float(panel.dbv[b2]), "nit", f"Band{b2} のピーク輝度", "0")
    r = row(r, "duty1", "DUTY_BC（BC1）", float(panel.duty[b1]), "−", f"Band{b1} の Duty（発光している時間の割合）", "0.000")
    r = row(r, "duty2", "DUTY_BC（BC2）", float(panel.duty[b2]), "−", f"Band{b2} の Duty", "0.000")
    r = row(r, "c1", "CURR_BC（BC1）", [float(panel.curr[c][b1]) for c in "rgb"], "−",
            f"Band{b1} のピーク電流（Band 間で規格化した値）", "0.00000")
    r = row(r, "c2", "CURR_BC（BC2）", [float(panel.curr[c][b2]) for c in "rgb"], "−", f"Band{b2} のピーク電流", "0.00000")
    r = row(r, "gi1", "GI_LUT[v]（BC1）", [float(panel.gi[c][255, b1]) for c in "rgb"], "−",
            f"Band{b1} の GI_LUT の v=255 の値（その Band のピーク電流を 1 とした電流）", "0.000000000")
    r = row(r, "gi2", "GI_LUT[v]（BC2）", [float(panel.gi[c][255, b2]) for c in "rgb"], "−",
            f"Band{b2} の GI_LUT の v=255 の値", "0.000000000")

    r = head(r + 1, "■ 求める値（数式）")
    D = lambda k: f"$B${ROW[k]}"                                           # noqa: E731
    r = row(r, "t", "t（Band 間の位置）", f"=({D('dbveff')}-{D('dbv2')})/({D('dbv1')}-{D('dbv2')})", "−",
            "t = (DBV_eff − DBV2) ÷ (DBV1 − DBV2)。1 なら BC1、0 なら BC2", "0.000000", False)
    r = row(r, "duty", "duty（補間）", f"={D('duty2')}+({D('duty1')}-{D('duty2')})*{D('t')}", "−",
            "duty = duty2 + (duty1 − duty2) × t", "0.000000", False)
    r = row(r, "ipix", "画素電流 ipix",
            [f"={c}{ROW['gi2']}*{c}{ROW['c2']}/{c}{ROW['c1']}+({c}{ROW['gi1']}-{c}{ROW['gi2']}*{c}{ROW['c2']}/{c}{ROW['c1']})*{D('t')}"
             for c in cols], "−",
            "ipix = GI2×C2/C1 + (GI1 − GI2×C2/C1) × t（BC2 の電流を BC1 の単位にそろえて補間）", NUM, False)
    r = row(r, "ie1", "発光電流 iemit（BC1 の単位）", [f"={c}{ROW['ipix']}/{D('duty')}*{c}{ROW['gadj']}" for c in cols], "−",
            "iemit = ipix ÷ duty × GADJ。サブモデルの BC1 の表はこの値で引く", NUM, False)
    r = row(r, "ie2", "発光電流（BC2 の単位）", [f"={c}{ROW['ie1']}*{c}{ROW['c1']}/{c}{ROW['c2']}" for c in cols], "−",
            "BC2 の表はこの値で引く（× C1/C2）", NUM, False)
    r = row(r, "rate", "1フレームの stat の増分",
            [f"={D('dt')}*{D('duty')}*{D('accel')}*({c}{ROW['ie1']}*{c}{ROW['c1']})^{c}{ROW['N']}"
             f"/({c}{ROW['K0']}*EXP({c}{ROW['Q']}/{D('T')}))*({c}{ROW['B0']}+{c}{ROW['A']}*{D('T')})/{c}{ROW['B0']}"
             for c in cols], "−",
            "Δt × duty × ACCEL_RATIO × (iemit × C1)^N ÷ (K0 × exp(Q÷T)) × (B0 + A×T) ÷ B0", NUM, False)
    r = row(r, "L1", "発光輝度 L1", f"={D('dbv1')}/{D('duty1')}", "nit", "L = DBV ÷ duty（Band 間で deg2 を補間する位置を決める）", "0.000", False)
    r = row(r, "L2", "発光輝度 L2", f"={D('dbv2')}/{D('duty2')}", "nit", "", "0.000", False)
    r = row(r, "Le", "発光輝度 L_eff", f"={D('dbveff')}/{D('duty')}", "nit", "", "0.000", False)
    r = row(r, "s", "s（deg2 の Band 間の位置）", f"=({D('Le')}-{D('L2')})/({D('L1')}-{D('L2')})", "−",
            "deg2 = deg2_BC2 + (deg2_BC1 − deg2_BC2) × s", "0.000000", False)
    return ws


# --------------------------------------------------------------------------- #
SM = "サブモデル"
SM_POS = {}                                     # (色, "1"/"2") → (表の左上の行, 列番号)、電流軸・劣化軸の範囲


def sheet_submodel(wb, panel: Panel, bands: tuple):
    _eff, b1, b2 = bands
    ws = wb.create_sheet(SM)
    cell(ws, "A1", "サブモデル（degparam_sm.csv）のうち、使う2つの Band の表。行＝電流（昇順）、列＝劣化（1 から降順）。値は deg2",
         f(bold=True, size=11), border=False)
    ws.column_dimensions["A"].width = 12
    r = 3
    for c in COLORS:
        lc = c.lower()
        iax, dax = panel.i_axis[lc], panel.d_axis[lc]
        for tag, b in (("1", b1), ("2", b2)):
            cell(ws, f"A{r}", f"{c}・BC{tag}（Band{b}）", f(bold=True), border=False)
            cell(ws, f"A{r + 1}", "電流＼劣化", f(bold=True, size=9), HEAD_FILL)
            for j, d in enumerate(dax):
                cell(ws, f"{get_column_letter(2 + j)}{r + 1}", float(d), INPUT, HEAD_FILL, fmt="0.00")
            for i, iv in enumerate(iax):
                cell(ws, f"A{r + 2 + i}", float(iv), INPUT, HEAD_FILL, fmt="0.000")
                for j in range(len(dax)):
                    cell(ws, f"{get_column_letter(2 + j)}{r + 2 + i}", float(panel.lut[lc][b, i, j]), INPUT, fmt="0.000000")
            last_col = get_column_letter(1 + len(dax))
            SM_POS[(c, tag)] = dict(
                table=f"{SM}!$B${r + 2}:${last_col}${r + 1 + len(iax)}",
                iax=f"{SM}!$A${r + 2}:$A${r + 1 + len(iax)}",
                dax=f"{SM}!$B${r + 1}:${last_col}${r + 1}",
                ni=len(iax), nd=len(dax))
            r += len(iax) + 4
    for j in range(2, 14):
        ws.column_dimensions[get_column_letter(j)].width = 11
    return ws


# --------------------------------------------------------------------------- #
CALC_COLS = ["stat", "deg", "degc", "lo", "wd", "hi1", "a1", "b1", "x1", "hi2", "a2", "b2", "x2", "deg2", "val"]
CALC_NAMES = {
    "stat": "累積時間 stat", "deg": "deg（出力）", "degc": "deg（コアの中）", "lo": "劣化軸の位置",
    "wd": "劣化方向の重み", "hi1": "BC1 電流軸の位置", "a1": "BC1 電流 下の行", "b1": "BC1 電流 上の行", "x1": "deg2_BC1",
    "hi2": "BC2 電流軸の位置", "a2": "BC2 電流 下の行", "b2": "BC2 電流 上の行", "x2": "deg2_BC2",
    "deg2": "deg2", "val": "評価画像の画素値"}
CALC_MEAN = {
    "stat": "フレーム数 × 1フレームの増分", "deg": "exp(−stat^B0)", "degc": "exp(−stat^β)",
    "lo": "劣化軸で deg 以下になる最初の列（2〜末尾に制限）", "wd": "(deg − 下の点) ÷ (上の点 − 下の点)",
    "hi1": "電流軸で iemit 以上になる最初の行（2〜末尾に制限）", "a1": "表の hi−1 行を劣化方向に補間（0 未満は 0）",
    "b1": "表の hi 行を劣化方向に補間（0 未満は 0）", "x1": "a + (b − a) × (iemit − 下の電流) ÷ (上の電流 − 下の電流)",
    "hi2": "（BC2 の電流で同じ）", "a2": "", "b2": "", "x2": "",
    "deg2": "MAX(deg2_BC2 + (deg2_BC1 − deg2_BC2) × s, 0)", "val": "INT(255 × ((v/255)^γ × deg × deg2)^(1/γ))"}


def sheet_calc(wb):
    ws = wb.create_sheet("計算")
    first = 6
    ws.freeze_panes = f"C{first}"
    cols = {}
    for ci, c in enumerate(COLORS):
        cols[c] = {k: get_column_letter(3 + ci * len(CALC_COLS) + j) for j, k in enumerate(CALC_COLS)}
    ws.column_dimensions["A"].width = 9
    ws.column_dimensions["B"].width = 9
    for c in COLORS:
        for k, col in cols[c].items():
            ws.column_dimensions[col].width = 20 if k in ("stat", "deg", "degc", "x1", "x2", "deg2", "a1", "b1", "a2", "b2") else 11
    cell(ws, "A1", "共通", f(bold=True), HEAD_FILL, align=Alignment(horizontal="center"))
    ws.merge_cells("A1:B1")
    for c in COLORS:
        a, b = cols[c][CALC_COLS[0]], cols[c][CALC_COLS[-1]]
        cell(ws, f"{a}1", f"{c}（画素 x={PIXELS[c][0]}, y={PIXELS[c][1]}。v＝255）", f(bold=True), HEAD_FILL,
             align=Alignment(horizontal="center"))
        ws.merge_cells(f"{a}1:{b}1")
    for col, h in [("A", "時点 [h]"), ("B", "フレーム数")]:
        cell(ws, f"{col}2", h, f(bold=True), HEAD_FILL, align=Alignment(horizontal="center", wrap_text=True))
    for c in COLORS:
        for k, col in cols[c].items():
            cell(ws, f"{col}2", CALC_NAMES[k], f(bold=True), HEAD_FILL, align=Alignment(horizontal="center", wrap_text=True))
            cell(ws, f"{col}3", f"=_xlfn.FORMULATEXT({col}{first})", f(color="7F7F7F", size=8, italic=True), SUB_FILL,
                 align=Alignment(wrap_text=True, vertical="top"))
            cell(ws, f"{col}4", CALC_MEAN[k], f(size=8), SUB_FILL, align=Alignment(wrap_text=True, vertical="top"))
    cell(ws, "A3", "数式", f(bold=True, size=8), SUB_FILL, align=Alignment(vertical="top"))
    cell(ws, "A4", "意味", f(bold=True, size=8), SUB_FILL, align=Alignment(vertical="top"))
    cell(ws, "B3", "", fill=SUB_FILL)
    cell(ws, "B4", "時点 × 3600 ÷ 1フレームの加速込み時間", f(size=8), SUB_FILL, align=Alignment(wrap_text=True, vertical="top"))
    ws.row_dimensions[2].height = 30
    ws.row_dimensions[3].height = 110
    ws.row_dimensions[4].height = 44

    for i, (_nn, _name, hours) in enumerate(EVALS):
        r = first + i
        cell(ws, f"A{r}", hours, fmt="0.0")
        cell(ws, f"B{r}", f"=ROUND(A{r}*3600/{pref('dtacc')},0)", fmt="0")
        for c in COLORS:
            k = cols[c]
            cell(ws, f"{k['stat']}{r}", f"=B{r}*{pref('rate', c)}", fmt=NUM)
            cell(ws, f"{k['deg']}{r}", f"=EXP(-1*{k['stat']}{r}^{pref('B0', c)})", fmt=NUM)
            cell(ws, f"{k['degc']}{r}", f"=EXP(-1*{k['stat']}{r}^{pref('beta', c)})", fmt=NUM)
            pos1, pos2 = SM_POS[(c, "1")], SM_POS[(c, "2")]
            dax, nd = pos1["dax"], pos1["nd"]
            d = f"{k['degc']}{r}"
            # 劣化軸（降順）で d 以下になる最初の列：MATCH(d, 軸, -1) は d 以上の最後の列 → 等しければその列、違えば次の列
            cell(ws, f"{k['lo']}{r}",
                 f"=MIN(MAX(IFERROR(IF(INDEX({dax},MATCH({d},{dax},-1))={d},MATCH({d},{dax},-1),MATCH({d},{dax},-1)+1),1),2),{nd})")
            lo = f"{k['lo']}{r}"
            cell(ws, f"{k['wd']}{r}", f"=({d}-INDEX({dax},{lo}))/(INDEX({dax},{lo}-1)-INDEX({dax},{lo}))", fmt=NUM)
            wd = f"{k['wd']}{r}"
            for tag, pos, ie in (("1", pos1, pref("ie1", c)), ("2", pos2, pref("ie2", c))):
                iax, tb, ni = pos["iax"], pos["table"], pos["ni"]
                hi = f"{k['hi' + tag]}{r}"
                # 電流軸（昇順）で iemit 以上になる最初の行：MATCH(i, 軸, 1) は i 以下の最後の行
                cell(ws, hi, f"=MIN(MAX(IFERROR(IF(INDEX({iax},MATCH({ie},{iax},1))={ie},MATCH({ie},{iax},1),"
                             f"MATCH({ie},{iax},1)+1),1),2),{ni})")
                cell(ws, f"{k['a' + tag]}{r}",
                     f"=MAX(INDEX({tb},{hi}-1,{lo})+(INDEX({tb},{hi}-1,{lo}-1)-INDEX({tb},{hi}-1,{lo}))*{wd},0)", fmt=NUM)
                cell(ws, f"{k['b' + tag]}{r}",
                     f"=MAX(INDEX({tb},{hi},{lo})+(INDEX({tb},{hi},{lo}-1)-INDEX({tb},{hi},{lo}))*{wd},0)", fmt=NUM)
                a_, b_ = f"{k['a' + tag]}{r}", f"{k['b' + tag]}{r}"
                cell(ws, f"{k['x' + tag]}{r}",
                     f"=MAX({a_}+({b_}-{a_})*({ie}-INDEX({iax},{hi}-1))/(INDEX({iax},{hi})-INDEX({iax},{hi}-1)),0)", fmt=NUM)
            x1, x2 = f"{k['x1']}{r}", f"{k['x2']}{r}"
            cell(ws, f"{k['deg2']}{r}", f"=MAX({x2}+({x1}-{x2})*{pref('s')},0)", fmt=NUM)
            cell(ws, f"{k['val']}{r}",
                 f"=INT(255*((({pref('v')}/255)^{pref('gamma')})*{d}*{k['deg2']}{r})^(1/{pref('gamma')}))")
    return ws, cols, first


# --------------------------------------------------------------------------- #
def load_bisim(bisim_out: Path) -> dict:
    """比較画素の bisim 値 {(nn, color): (stat, deg, deg2, 評価画素値)}。"""
    vals = {}
    for nn, name, _h in EVALS:
        img = cv2.imdecode(np.fromfile(str(bisim_out / f"{SEQ}_{nn}_{name}_image.png"), np.uint8), cv2.IMREAD_COLOR)
        for c in COLORS:
            x, y = PIXELS[c]
            got = [float(np.loadtxt(str(bisim_out / f"{SEQ}_{nn}_{name}_{kind}_{c.lower()}.csv"), delimiter=",")[y, x])
                   for kind in ("stat", "deg", "deg2")]
            vals[(nn, c)] = (*got, int(img[y, x, BGR[c]]))
    return vals


def sheet_compare(wb, cols, first, bisim_out: Path, bisim_label: str):
    ws = wb.create_sheet("比較")
    vals = load_bisim(bisim_out)
    heads = ["時点 [h]", "色", "画素 (x, y)",
             "累積時間 stat\nExcel", "累積時間 stat\nbisim（CSV）", "相対差",
             "輝度残存率 deg\nExcel", "輝度残存率 deg\nbisim（CSV）", "差",
             "deg2\nExcel", "deg2\nbisim（CSV）", "差",
             "評価画像の画素値\nExcel", "評価画像の画素値\nbisim（PNG）", "差",
             "判定", "bisim の値の出典（CSV は 行=y+1・列=x+1）"]
    widths = [8, 5, 12, 22, 22, 10, 22, 22, 10, 22, 22, 10, 14, 14, 6, 7, 70]
    for i, (h, w) in enumerate(zip(heads, widths), start=1):
        col = get_column_letter(i)
        ws.column_dimensions[col].width = w
        cell(ws, f"{col}4", h, f(bold=True), HEAD_FILL, align=Alignment(horizontal="center", vertical="center", wrap_text=True))
    ws.row_dimensions[4].height = 48
    cell(ws, "A1", "Excel の数式で計算した理論値と bisim の出力の比較（新コア）", f(bold=True, size=12), border=False)
    cell(ws, "A2", f"bisim の出力：{bisim_label}", f(size=9), border=False)
    r = 5
    for i, (nn, name, hours) in enumerate(EVALS):
        cr = first + i
        for c in COLORS:
            k = cols[c]
            x, y = PIXELS[c]
            bst, bdg, bd2, bpx = vals[(nn, c)]
            cell(ws, f"A{r}", hours, fmt="0.0")
            cell(ws, f"B{r}", c, align=Alignment(horizontal="center"))
            cell(ws, f"C{r}", f"({x}, {y})", align=Alignment(horizontal="center"))
            cell(ws, f"D{r}", f"=計算!{k['stat']}{cr}", fmt=NUM)
            cell(ws, f"E{r}", bst, INPUT, fmt=NUM)
            cell(ws, f"F{r}", f"=ABS(D{r}-E{r})/D{r}", fmt="0.0E+00")
            cell(ws, f"G{r}", f"=計算!{k['deg']}{cr}", fmt=NUM)
            cell(ws, f"H{r}", bdg, INPUT, fmt=NUM)
            cell(ws, f"I{r}", f"=ABS(G{r}-H{r})", fmt="0.0E+00")
            cell(ws, f"J{r}", f"=計算!{k['deg2']}{cr}", fmt=NUM)
            cell(ws, f"K{r}", bd2, INPUT, fmt=NUM)
            cell(ws, f"L{r}", f"=ABS(J{r}-K{r})", fmt="0.0E+00")
            cell(ws, f"M{r}", f"=計算!{k['val']}{cr}")
            cell(ws, f"N{r}", bpx, INPUT)
            cell(ws, f"O{r}", f"=ABS(M{r}-N{r})")
            cell(ws, f"P{r}", f'=IF(AND(F{r}<1E-9,I{r}<1E-9,L{r}<1E-9,O{r}<=1),"OK","NG")',
                 f(bold=True), align=Alignment(horizontal="center"))
            cell(ws, f"Q{r}", f"{SEQ}_{nn}_{name}_stat/deg/deg2_{c.lower()}.csv の {y + 1}行{x + 1}列、"
                              f"_image.png の (x={x}, y={y}) の {c}", f(size=8))
            r += 1
    last = r - 1
    cell(ws, "A3", "総合判定", f(bold=True), OK_FILL)
    cell(ws, "B3", f'=IF(COUNTIF(P5:P{last},"NG")=0,"OK（理論どおり）","NG あり")', f(bold=True), OK_FILL)
    ws.merge_cells("B3:D3")
    cell(ws, f"A{last + 2}",
         "判定基準：累積時間の相対差・deg と deg2 の差がいずれも 1E-9 未満、評価画像の画素値の差が 1 以内。"
         "Excel と Python（bisim）は同じ倍精度で計算するが、計算の順番（bisim はフレームごとに足し、Excel は掛け算）や EXP・べき乗の最後の桁が違うため、"
         "完全一致ではなくこの基準にしている。", f(size=9), border=False)
    ws.freeze_panes = "D5"
    return ws


# --------------------------------------------------------------------------- #
def sheet_readme(wb, bisim_label, bands, panel):
    _eff, b1, b2 = bands
    ws = wb.active
    ws.title = "説明"
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 130
    lines = [
        ("理論確認テスト（3色円）：Excel の数式による理論値の計算と bisim との比較（新コア）", "title"),
        ("", None),
        ("■ 目的", "h"),
        ("bisim（劣化シミュレータ）が、劣化モデル（新コア：松井さん Burn_in_sim_core_01、2026-11-10）の式どおりに"
         "累積時間・輝度残存率（deg）・サブモデルの残存率（deg2）・劣化画像を計算していることを、Excel の数式だけで計算した理論値と比べて確かめる。", None),
        ("", None),
        ("■ 劣化モデルの式（DPK_ON=0、固定温度のとき）", "h"),
        ("新コアでは、ストレスは「劣化前の画素電流」で貯まる（旧コアは劣化した後の輝度で貯まっていた）。"
         "そのため、同じ画像を表示し続ければ、累積時間はフレーム数に比例して増える。", None),
        ("  (1) Band の補間位置    t = (DBV_eff − DBV2) ÷ (DBV1 − DBV2)　　duty = duty2 + (duty1 − duty2) × t", "eq"),
        ("  (2) 画素電流           ipix = GI2[v]×C2/C1 + (GI1[v] − GI2[v]×C2/C1) × t　　（GI＝GI_LUT、C＝CURR_BC。BC1 の単位にそろえる）", "eq"),
        ("  (3) 発光電流           iemit = ipix ÷ duty × GADJ", "eq"),
        ("  (4) 累積時間           stat = フレーム数 × Δt × duty × ACCEL_RATIO × (iemit × C1)^N ÷ (K0 × exp(Q÷T)) × (B0 + A×T) ÷ B0", "eq"),
        ("  (5) 輝度残存率         deg = exp(−stat^β)　β = B0 + A×T（コアの中）。出力の deg CSV は β = B0", "eq"),
        ("  (6) サブモデル         deg2_BC = 表[電流, 劣化] を (iemit, deg) で 劣化方向 → 電流方向 の順に直線補間（BC2 は iemit × C1/C2 で引く）", "eq"),
        ("                         deg2 = deg2_BC2 + (deg2_BC1 − deg2_BC2) × s　　s = (L_eff − L2) ÷ (L1 − L2)、L = DBV ÷ duty", "eq"),
        ("  (7) 評価画像の画素値   INT( 255 × ((v/255)^γ × deg × deg2)^(1/γ) )", "eq"),
        ("  T = 温度[℃] + 273、 Δt = 1 ÷ fps。表の外は端の2点を結ぶ直線で延長し、補間の途中・結果が 0 未満なら 0", "eq"),
        ("", None),
        ("■ 記号の意味", "h"),
        ("  stat：累積時間（累積ストレス）  deg：輝度残存率（1＝劣化なし。基準の電流密度での値）  deg2：サブモデルの残存率（表示する電流による違い）", None),
        ("  v：画素値（0〜255）  γ：ガンマ 2.2  N：加速係数  K0：寿命の目安に相当する係数  Q：温度依存の係数  B0・A：劣化カーブの形 β を決める係数", None),
        ("  DBV_NIT：パネルの輝度設定  Band：輝度設定ごとの駆動条件（bcsetting.csv の列）  GI_LUT：階調→電流の表  Duty：発光している時間の割合", None),
        ("", None),
        ("■ 数値例（R、v＝255、DBV_NIT＝2000）", "h"),
        (f"  使う Band：BC1＝Band{b1}（{panel.dbv[b1]:g} nit）、BC2＝Band{b2}（{panel.dbv[b2]:g} nit）。"
         f"t = (2000 − {panel.dbv[b2]:g}) ÷ ({panel.dbv[b1]:g} − {panel.dbv[b2]:g}) = {(2000 - panel.dbv[b2]) / (panel.dbv[b1] - panel.dbv[b2]):.4f}", None),
        ("  1フレーム（120 秒分）の stat の増分と、各時点の値は「パラメータ」「計算」シートを参照", None),
        ("", None),
        ("■ 比較に使う画素", "h"),
        ("  R の円 (x=120, y=159)、G の円 (x=64, y=285)、B の円 (x=175, y=287)。", None),
        ("  Aging 用の動画（rgbcircle-aging_movie.mp4）は MP4 の非可逆圧縮で、画素値が理想の 0/255 から数階調ずれる所がある。"
         "上の画素は 30 フレームすべてで「その色＝255、ほかの色＝0」のまま保たれている画素なので、Excel 側の入力を v = 255 の定数にできる。", None),
        ("  評価画像は全面白（v＝255）。deg2 は評価ステップの値（PQ評価：温度 25℃、ストレスは貯めない）。", None),
        ("", None),
        ("■ シートの内容", "h"),
        ("  パラメータ：モデルパラメータ・Sim条件・Band のデータ（青字が入力）と、そこから求める値（電流・増分・補間位置）", None),
        ("  サブモデル：degparam_sm.csv のうち、使う2つの Band の表（R/G/B）", None),
        ("  計算：1行＝評価時点（0.5h〜50h）。3行目に各列の Excel の数式を文字で表示（FORMULATEXT 関数）、4行目に式の意味", None),
        ("  比較：7つの評価時点 × R/G/B で、Excel の値と bisim の値を並べて判定。最上部に総合判定", None),
        ("", None),
        ("■ 比較した bisim の結果", "h"),
        (f"  {bisim_label}", None),
        ("  シーケンス rgbcircle.seq.json（ACCEL_RATIO=3600、固定温度 25℃、DBV_NIT=2000、DPK_ON=0、Aging→PQ評価 を累積 0.5h〜50h で7回）", None),
        ("", None),
        ("■ 作り直し方", "h"),
        ("  bisim2\\.venv\\Scripts\\python tool\\rgbcircle_excel.py --seq <シーケンスファイル> [--bisim-out <bisim の出力フォルダ>] [--out <xlsx>]", None),
    ]
    for r, (text, kind) in enumerate(lines, start=1):
        c = ws[f"B{r}"]
        c.value = text
        if kind == "title":
            c.font = f(bold=True, size=14)
        elif kind == "h":
            c.font = f(bold=True, size=11)
        elif kind == "eq":
            c.font = Font(name="Consolas", size=10, color="1F3864")
        else:
            c.font = f(size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    return ws


# --------------------------------------------------------------------------- #
def recalc_with_excel(path: Path) -> bool:
    """Excel があれば開いて全再計算・保存（数式の計算結果をファイルに残す）。"""
    import subprocess
    ps = (f'$xl = New-Object -ComObject Excel.Application; $xl.Visible=$false; $xl.DisplayAlerts=$false; '
          f'$wb = $xl.Workbooks.Open("{path}"); $xl.CalculateFull(); $wb.Worksheets.Item(1).Activate(); '
          f'$wb.Save(); $wb.Close($false); $xl.Quit()')
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=300)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seq", type=Path, default=REPO / "eval_test" / "rgbcircle" / "rgbcircle.seq.json",
                    help="bisim で実行したシーケンス（出力フォルダはここから決める）")
    ap.add_argument("--bisim-out", type=Path, help="bisim の出力フォルダ（既定：シーケンスの output）")
    ap.add_argument("--out", type=Path, help="作る xlsx（既定：シーケンスの横の 理論値_Excel検算.xlsx）")
    ap.add_argument("--bcset", type=Path, help="bcsetting.csv（既定：シーケンスのパネル設定）")
    ap.add_argument("--sm", type=Path, help="degparam_sm.csv（既定：シーケンスのパネル設定）")
    ap.add_argument("--app-dir", type=Path, help=APP_DIR_HELP)
    ap.add_argument("--label", help="ブックに書く「比較した bisim の結果」の説明（既定：出力フォルダのパス）")
    a = ap.parse_args()

    seq, seq_path = load_sequence(a.seq)
    a.bisim_out = resolve_folder(seq, seq_path, "output", "output", a.bisim_out, a.app_dir)
    if not a.bisim_out.is_dir():
        sys.exit(f"bisim の出力フォルダが見つかりません: {a.bisim_out}（--bisim-out で指定できます）")
    bc_path, sm_path, mm = panel_files(seq, seq_path, a)
    panel = Panel(bc_path, sm_path)
    rc = next(r for r in seq["recipes"] if r.get("step_type", "aging") == "aging")
    sim = dict(SIM_DEFAULTS)
    sim.update(rc["sim_param"])
    if int(sim["DPK_ON"]) != 0:
        sys.exit("DPK_ON=0 のシーケンスだけに対応しています")
    bands = panel.bands(float(sim["DBV_NIT"]))
    a.out = a.out or (seq_path.parent / "理論値_Excel検算.xlsx")
    a.label = a.label or display_path(a.bisim_out, REPO)
    print(f"シーケンス: {seq_path}")
    print(f"bisim の出力: {a.bisim_out}")
    print(f"パネル設定: {bc_path} / {sm_path}（Band{bands[1]}・Band{bands[2]}）")

    wb = Workbook()
    sheet_readme(wb, a.label, bands, panel)
    sheet_params(wb, mm, sim, panel, bands)
    sheet_submodel(wb, panel, bands)
    _ws, cols, first = sheet_calc(wb)
    sheet_compare(wb, cols, first, a.bisim_out, a.label)
    out = a.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    ok = recalc_with_excel(out)
    print(f"保存: {out}（Excel で再計算: {'済' if ok else '未（Excel で開くと計算されます）'}）")


if __name__ == "__main__":
    sys.exit(main())
