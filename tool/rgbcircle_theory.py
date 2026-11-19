"""理論確認テスト：3色円の Aging → 白評価 の理論値を計算し、表にする（bisim の結果との比較も可）。

``tool/make_rgbcircle_test.py`` が作ったシーケンス（``rgbcircle.seq.json``）を読み、
各ステップのパラメータどおりに劣化モデル（新コア：松井さん Burn_in_sim_core_01、2026-11-10）を
1フレームずつ計算する。劣化コア ``source/main.py``・``load_com_info.py`` は使わず、
式とパネル設定ファイル（bcsetting.csv・degparam_sm.csv）の読み込みを独立に実装している。

対応する条件：固定温度（ヒートマップなし）・DPK_ON=0。Aging×動画、PQ評価×静止画。

■ 式（画素ごと・色ごと。v＝画素値 0〜255、c＝R/G/B）
  Band の選び方：DBV_NIT を通常の Band（DBV_NIT_DPK の数より後ろ）の範囲に収め（DBV_eff）、
    DBV_eff をはさむ2つの Band（上＝BC1、下＝BC2）を使う。t = (DBV_eff − DBV2) ÷ (DBV1 − DBV2)
  画素電流   ipix = GI2[v]×C2/C1 + (GI1[v] − GI2[v]×C2/C1) × t      … BC1 の電流の単位にそろえて Band 間を補間
  Duty       duty = duty2 + (duty1 − duty2) × t
  発光電流   iemit = ipix ÷ duty × GADJ                            … BC1 の単位（BC2 の表を引くときは × C1/C2）
  ストレス   stat += Δt × duty × ACCEL_RATIO × (iemit × C1)^N ÷ (K0 × exp(Q ÷ T)) × (B0 + A×T) ÷ B0
             ※ 劣化前の電流で貯まる（劣化が進んでも貯まり方は変わらない）
  deg1       deg = exp(−stat^(B0 + A×T))                        … T＝TMP_L＋273（コアの中）
             出力の deg CSV は exp(−stat^B0)（11/12 決定：β の温度依存の食い違いはそのまま）
  deg2       サブモデルの表（電流 × 劣化）を、BC1・BC2 それぞれ 劣化方向 → 電流方向 の順に直線補間
             （表の外は端の2点で延長、途中で 0 未満は 0）。Band 間は 発光輝度 DBV÷duty で補間
             deg2 = deg2_BC2 + (deg2_BC1 − deg2_BC2) × (L_eff − L2) ÷ (L1 − L2)、L = DBV ÷ duty
  画像       floor( 255 × ((v/255)^2.2 × deg × deg2)^(1/2.2) )     … deg はそのフレームを処理する前の stat から

Aging のフレーム数は bisim と同じ規則（AGING_TIME 到達で打切り、不足なら動画を周回）。
入力の画素値は MP4 から読み出した値を使う（MP4 は非可逆なので理想の 0/255 から数階調ずれる。
bisim が実際に見る値と揃えるため）。比較用に、画素値が理想どおり 255 の場合の値（理想値）も表に載せる。

出力（既定 ``<シーケンスの横>/theory/``）:
  rgbcircle_theory_table.png   Aging時間ごとの 理論の評価画像・累積時間マップ R/G/B（--compare で bisim の評価画像も）
  rgbcircle_theory_values.md   数値表（理想値／領域ごとの値）
  rgbcircle_theory_values.csv  同上（CSV）
  rgbcircle_compare.md         --compare 時：bisim 出力との差（全ステップ）

使い方（Burn-In_Simv2 直下で）:
  bisim2\\.venv\\Scripts\\python tool\\rgbcircle_theory.py                 理論値だけ
  bisim2\\.venv\\Scripts\\python tool\\rgbcircle_theory.py --compare       bisim の出力フォルダ（シーケンスの output）と比較
  ... --compare --bisim-out <フォルダ>                                     出力先を指定して比較
  ... --seq <bisim.exe のフォルダ>/eval_test/rgbcircle/rgbcircle.seq.json --app-dir <bisim.exe のフォルダ> --compare
                                                                           別PCの EXE で実行した結果と比較

フォルダの決め方（tool/_seqpaths.py）: コマンドの指定 → シーケンスに書かれたパス（相対パスは
bisim.exe のフォルダ＝--app-dir が基準。既定は bisim2）→ それが無ければシーケンスファイルの横の input / output。
パネル設定ファイル（bcsetting・degparam_sm）は シーケンスの panel のファイル名 ＋ folders の bcset・model
（書かれていなければ bisim の標準フォルダ bisim2/source/dbi_conf）。--bcset・--sm で直接指定もできる。
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# bisim 本体（bisim/・source/・eval_test/）は tool/ の横の bisim2/ にある
REPO = Path(__file__).resolve().parent.parent / "bisim2"
TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
from bisim import naming  # noqa: E402  （出力ファイル名の規則だけ借りる）
sys.path.insert(0, str(TOOL_DIR))
from _seqpaths import APP_DIR_HELP, load_sequence, resolve_folder  # noqa: E402

COLORS = "rgb"
EVAL_TEMP_C = 25.0                               # bisim.engine.EVAL_TEMP_C と同じ（PQ評価は温度設定なし）
STD_CONF = REPO / "source" / "dbi_conf"          # bisim の標準のパネル設定フォルダ
STD_BCSET, STD_SM = "bcsetting.csv", "degparam_sm.csv"
BGR_INDEX = {"b": 0, "g": 1, "r": 2}
MODEL_INDEX = {"r": 0, "g": 1, "b": 2}           # model_param の並びは [R, G, B]
DEFAULT_MM = {"N": [1.5, 1.3, 1.7], "K0": [500.0, 1000.0, 100.0], "Q": [1000.0, 800.0, 600.0],
              "B0": [0.7, 0.8, 0.4], "A": [0.0, 0.0, 0.0]}
SIM_DEFAULTS = {"DBV_NIT": 2000.0, "DPK_ON": 0, "GADJ": [1.0, 1.0, 1.0]}   # bisim の既定値と同じ
REGION_NAMES = {0: "背景", 4: "R", 2: "G", 1: "B", 6: "R+G(黄)", 5: "R+B(マゼンタ)",
                3: "G+B(シアン)", 7: "R+G+B(白)"}
REGION_ORDER = [4, 2, 1, 6, 5, 3, 7, 0]


# --------------------------------------------------------------------------- #
#  入力
# --------------------------------------------------------------------------- #
def read_png(path: Path, flags=cv2.IMREAD_COLOR) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(str(path), np.uint8), flags)
    if img is None:
        sys.exit(f"画像を読めません: {path}")
    return img


def read_movie(path: Path) -> tuple:
    """(fps, CAP_PROP_FRAME_COUNT, フレームのリスト) — bisim と同じく cv2 で順に読む。"""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        sys.exit(f"動画を開けません: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    return fps, count, frames


def read_keyed_csv(path: Path) -> tuple:
    """パネル設定 CSV を読む（コアの load_com_info とは別に実装）。

    1列目が文字の行 → {キー: [数値…]}、1列目が数値の行 → 表の行（数値のリスト）。空の欄は無視。
    """
    keys, rows = {}, []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            cells = [x.strip() for x in line.rstrip("\r\n").split(",")]
            if not cells or not cells[0]:
                continue
            nums = [float(x) for x in cells[1:] if x != ""]
            try:
                rows.append([float(cells[0])] + nums)
            except ValueError:
                keys[cells[0]] = nums
    return keys, rows


# --------------------------------------------------------------------------- #
#  パネル設定（BC設定・サブモデル）
# --------------------------------------------------------------------------- #
class Panel:
    """bcsetting.csv・degparam_sm.csv の中身（色ごとに整理）。"""

    def __init__(self, bc_path: Path, sm_path: Path):
        self.bc_path, self.sm_path = bc_path, sm_path
        k, rows = read_keyed_csv(bc_path)
        self.nb = int(k["BC_BAND_NUM"][0])
        self.n_dpk = len(k["DBV_NIT_DPK"])                  # DPK 用の Band の数（通常の Band はこの後ろから）
        self.dbv = np.array(k["DBV_NIT_BC"])
        self.duty = np.array(k["DUTY_BC"])
        self.curr = {c: np.array(k[f"CURR_BC_{c.upper()}"]) for c in COLORS}
        gi = np.array(rows, dtype=float)                    # 行＝階調、列＝ Band0 の R,G,B, Band1 の R,G,B, …
        if gi.shape != (int(k["GI_LUT_WRD_GRY"][0]), self.nb * 3):
            sys.exit(f"{bc_path.name}: GI_LUT の表の大きさが {gi.shape}（期待 {int(k['GI_LUT_WRD_GRY'][0])}×{self.nb * 3}）")
        self.gi = {c: gi[:, i::3] for i, c in enumerate(COLORS)}          # (階調, Band)

        k, rows = read_keyed_csv(sm_path)
        self.d_axis = {c: np.array(k[f"DEG_2D_DEG_{c.upper()}"]) for c in COLORS}   # 劣化軸（1 から降順）
        self.i_axis = {c: np.array(k[f"DEG_2D_I_{c.upper()}"]) for c in COLORS}     # 電流軸（昇順、最後が 1）
        nd, ni = int(k["DEG_2D_WRD_DEG"][0]), int(k["DEG_2D_WRD_I"][0])
        t = np.array(rows, dtype=float)                     # 行＝ Band × 電流、列＝ R の劣化軸, G…, B…
        if t.shape != (self.nb * ni, 3 * nd):
            sys.exit(f"{sm_path.name}: 表の大きさが {t.shape}（期待 {self.nb * ni}×{3 * nd}）")
        self.lut = {c: t[:, i * nd:(i + 1) * nd].reshape(self.nb, ni, nd) for i, c in enumerate(COLORS)}

    def bands(self, dbv_nit: float) -> tuple:
        """(DBV_eff, BC1, BC2)。DPK_ON=0 の Band の選び方。"""
        hbm = self.n_dpk                                    # 通常時の最大の Band（HBM）
        eff = min(max(dbv_nit, self.dbv[-1]), self.dbv[hbm])
        j = next((i for i in range(hbm, self.nb) if self.dbv[i] <= eff), self.nb)   # DBV_eff 以下になる最初の Band
        j = min(max(j, hbm + 1), self.nb - 1)
        return eff, j - 1, j


def lut2d(table: np.ndarray, i_axis: np.ndarray, d_axis: np.ndarray, i: np.ndarray, d: np.ndarray) -> np.ndarray:
    """サブモデルの表 table[電流, 劣化] を (i, d) で引く：劣化方向 → 電流方向の順に直線補間。

    表の外は端の2点を結ぶ直線で延長する。途中の値・結果が 0 未満なら 0。
    """
    ni, nd = len(i_axis), len(d_axis)
    hi = np.clip(np.searchsorted(i_axis, i, side="left"), 1, ni - 1)        # i 以上になる最初の点（電流は昇順）
    lo_d = np.clip(np.searchsorted(-d_axis, -d, side="left"), 1, nd - 1)    # d 以下になる最初の点（劣化は降順）
    d_lo, d_hi = d_axis[lo_d], d_axis[lo_d - 1]
    wd = (d - d_lo) / (d_hi - d_lo)

    def along_d(row):
        v = table[row, lo_d] + (table[row, lo_d - 1] - table[row, lo_d]) * wd
        return np.maximum(v, 0.0)

    v_lo, v_hi = along_d(hi - 1), along_d(hi)
    i_lo, i_hi = i_axis[hi - 1], i_axis[hi]
    return np.maximum(v_lo + (v_hi - v_lo) * (i - i_lo) / (i_hi - i_lo), 0.0)


# --------------------------------------------------------------------------- #
#  モデル（source/main.py とは独立に、式から実装）
# --------------------------------------------------------------------------- #
@dataclass
class Params:
    """1ステップ分の条件。階調ごとの値（電流・ストレスの速さ）を前もって 256 階調ぶん計算しておく。"""
    panel: Panel
    mm: dict                  # {"N": {"r":…}, …}
    accel: float
    temp_k: float
    aging_time: float
    dbv: float
    gadj: dict
    detail: dict = field(default_factory=dict)

    @classmethod
    def from_recipe(cls, rc: dict, is_aging: bool, panel: Panel, mm_list: dict) -> "Params":
        # PQ評価は温度設定なし（bisim は EVAL_TEMP_C 固定）。Aging は固定温度モードのみ対応
        if is_aging and rc.get("heatmap_mode") != "fixed":
            sys.exit(f"{rc['recipe_name']}: 固定温度モード（ヒートマップなし）のみ対応")
        sp = dict(SIM_DEFAULTS)
        sp.update(rc["sim_param"])
        if int(sp["DPK_ON"]) != 0:
            sys.exit(f"{rc['recipe_name']}: DPK_ON=0 のみ対応")
        mm = {k: {c: float(mm_list[k][MODEL_INDEX[c]]) for c in COLORS} for k in ("N", "K0", "Q", "B0", "A")}
        temp_c = float(rc["fixed_temp_c"]) if is_aging else EVAL_TEMP_C
        p = cls(panel=panel, mm=mm, accel=float(sp["ACCEL_RATIO"]), temp_k=temp_c + 273.0,
                aging_time=float(sp.get("AGING_TIME", 0.0)), dbv=float(sp["DBV_NIT"]),
                gadj={c: float(sp["GADJ"][MODEL_INDEX[c]]) for c in COLORS})
        p._prepare()
        return p

    def _prepare(self) -> None:
        pn = self.panel
        eff, b1, b2 = pn.bands(self.dbv)
        d1, d2 = pn.dbv[b1], pn.dbv[b2]
        t = (eff - d2) / (d1 - d2)
        duty = pn.duty[b2] + (pn.duty[b1] - pn.duty[b2]) * t
        L1, L2, Le = d1 / pn.duty[b1], d2 / pn.duty[b2], eff / duty
        s = (Le - L2) / (L1 - L2)
        self.detail = dict(dbv_eff=eff, bc1=b1, bc2=b2, t=t, duty=duty, s=s)
        self.iemit, self.rate = {}, {}
        for c in COLORS:
            c1, c2 = pn.curr[c][b1], pn.curr[c][b2]
            g1, g2 = pn.gi[c][:, b1], pn.gi[c][:, b2]
            ipix = g2 * c2 / c1 + (g1 - g2 * c2 / c1) * t            # 256 階調ぶん
            self.iemit[c] = ipix / duty * self.gadj[c]                # BC1 の単位
            m = self.mm
            self.rate[c] = (duty * self.accel * (self.iemit[c] * c1) ** m["N"][c]
                            / (m["K0"][c] * math.exp(m["Q"][c] / self.temp_k))
                            * (m["B0"][c] + m["A"][c] * self.temp_k) / m["B0"][c])  # 表示1秒あたりの stat の増え方

    def beta_core(self, c: str) -> float:
        return self.mm["B0"][c] + self.mm["A"][c] * self.temp_k

    def deg_core(self, c: str, stat: np.ndarray) -> np.ndarray:
        """コアの中で画像に使う deg1（β＝B0＋A×T）。"""
        return np.exp(-1.0 * (stat ** self.beta_core(c)))

    def deg_out(self, c: str, stat: np.ndarray) -> np.ndarray:
        """出力の deg CSV（β＝B0）。"""
        return np.exp(-1.0 * (stat ** self.mm["B0"][c]))

    def deg2(self, c: str, v: np.ndarray, deg: np.ndarray) -> np.ndarray:
        pn, dt = self.panel, self.detail
        b1, b2 = dt["bc1"], dt["bc2"]
        ie1 = self.iemit[c][v]
        ie2 = ie1 * pn.curr[c][b1] / pn.curr[c][b2]
        x1 = lut2d(pn.lut[c][b1], pn.i_axis[c], pn.d_axis[c], ie1, deg)
        x2 = lut2d(pn.lut[c][b2], pn.i_axis[c], pn.d_axis[c], ie2, deg)
        return np.maximum(x2 + (x1 - x2) * dt["s"], 0.0)

    def image(self, frame: np.ndarray, stat: dict) -> tuple:
        """劣化画像（BGR, uint8）と deg2 {c: map}。stat はこのフレームを処理する前の値。"""
        out, d2 = frame.copy(), {}
        for c in COLORS:
            v = frame[:, :, BGR_INDEX[c]]
            deg = self.deg_core(c, stat[c])
            d2[c] = self.deg2(c, v, deg)
            lum = (v / 255) ** 2.2 * deg * d2[c]
            out[:, :, BGR_INDEX[c]] = (255 * (lum ** (1 / 2.2))).astype(np.uint8)
        return out, d2


def aging_frame_count(dt_accel: float, target: float, frames_total: int) -> int:
    """bisim の規則：AGING_TIME>0 なら到達まで（最低1フレーム、到達した時点で打切り）、0 なら1周回。"""
    if dt_accel <= 0 or target <= 0:
        return frames_total
    limit = max(1, math.ceil(target / dt_accel))
    aging, n = 0.0, 0
    while n < limit:
        aging += dt_accel
        n += 1
        if aging >= target:
            break
    return n


@dataclass
class StepResult:
    nn: str
    recipe_name: str
    is_aging: bool                # True=Aging ステップ / False=PQ評価ステップ
    frames: int
    aging_seconds: float          # このステップの加速込み Aging 時間
    cum_seconds: float            # 累積
    stat: dict                    # c -> ndarray
    deg: dict                     # c -> ndarray（ステップ終了時点。bisim の deg CSV に相当＝β は B0）
    deg2: dict                    # c -> ndarray（最後に処理したフレームの値。bisim の deg2 CSV に相当）
    image: np.ndarray | None = None   # PQ評価ステップの劣化画像（BGR, uint8）
    ideal: dict = field(default_factory=dict)  # c -> (stat, deg, deg2, 評価値)：画素値=255 の理想値


def panel_files(seq: dict, seq_path: Path, a) -> tuple:
    """(bcsetting のパス, degparam_sm のパス, mm)。bisim の Sequence と同じ決め方。"""
    panel = seq.get("panel")
    if isinstance(panel, dict):
        bc_name, sm_name, mm = panel.get("bcsetting") or STD_BCSET, panel.get("degparam_sm") or STD_SM, panel["model_param"]
        bc_dir = resolve_folder(seq, seq_path, "bcset", "__none__", None, a.app_dir, quiet=True)
        sm_dir = resolve_folder(seq, seq_path, "model", "__none__", None, a.app_dir, quiet=True)
        if "bcset" not in (seq.get("folders") or {}) or not (bc_dir / bc_name).is_file():
            bc_dir = STD_CONF
        if "model" not in (seq.get("folders") or {}) or not (sm_dir / sm_name).is_file():
            sm_dir = STD_CONF
    else:                                     # 旧形式（フェーズF より前）：標準ファイル、mm は1番目のステップ
        bc_name, sm_name, bc_dir, sm_dir = STD_BCSET, STD_SM, STD_CONF, STD_CONF
        mm = (seq["recipes"][0].get("model_param") if seq["recipes"] else None) or DEFAULT_MM
    bc = Path(a.bcset).resolve() if a.bcset else bc_dir / bc_name
    sm = Path(a.sm).resolve() if a.sm else sm_dir / sm_name
    for p in (bc, sm):
        if not p.is_file():
            sys.exit(f"パネル設定ファイルが見つかりません: {p}")
    return bc, sm, mm


def simulate(seq: dict, in_dir: Path, panel: Panel, mm_list: dict) -> list:
    movies: dict = {}
    results: list = []
    stat = ideal = None
    cum = 0.0
    for i, rc in enumerate(seq["recipes"]):
        nn = f"{i + 1:02d}"
        path = in_dir / rc["input_image"]
        is_movie = path.suffix.lower() == ".mp4"
        # ステップ種別（bisim と同じ：欄が無い旧 JSON は拡張子から。.png→評価、それ以外→Aging）
        step_type = rc.get("step_type") or ("eval" if path.suffix.lower() == ".png" else "aging")
        is_aging = step_type == "aging"
        if is_aging != is_movie:
            sys.exit(f"{nn}: 対応しているのは「Aging×動画」と「PQ評価×静止画」だけです"
                     f"（{step_type}×{path.suffix}）")
        p = Params.from_recipe(rc, is_aging, panel, mm_list)
        if is_movie:
            if path not in movies:
                movies[path] = read_movie(path)
            fps, count, frames = movies[path]
            h, w = frames[0].shape[:2]
        else:
            img0 = read_png(path)
            h, w = img0.shape[:2]

        init = rc.get("init_stress", "none")
        if init == "none" or stat is None:
            if init == "prev":
                sys.exit(f"{nn}: 前ステップ継承だが前ステップが無い")
            stat = {c: np.zeros((h, w)) for c in COLORS}
            ideal = {c: 0.0 for c in COLORS}
        elif init != "prev":
            sys.exit(f"{nn}: init_stress={init!r} は未対応（none / prev のみ）")

        if is_movie:
            dt = 1.0 / fps
            dt_accel = dt * p.accel
            n = aging_frame_count(dt_accel, p.aging_time, count)
            deg2 = {}
            for k in range(n):
                f = frames[k % len(frames)]          # 動画終端で先頭に戻って周回
                if k == n - 1:                       # deg2 の出力は最後のフレームの値（処理前の stat で）
                    _, deg2 = p.image(f, stat)
                for c in COLORS:
                    stat[c] += dt * p.rate[c][f[:, :, BGR_INDEX[c]]]
                    ideal[c] += dt * float(p.rate[c][255])
            aging = n * dt_accel
            image = None
        else:
            n, aging = 1, 0.0                       # PQ評価はストレスを貯めない（dt=0）
            image, deg2 = p.image(img0, stat)
        cum += aging
        degs = {c: p.deg_out(c, stat[c]) for c in COLORS}
        ideal_vals = {}
        for c in COLORS:
            d_core = math.exp(-1.0 * ideal[c] ** p.beta_core(c))
            d2 = float(p.deg2(c, np.array([255]), np.array([d_core]))[0])
            val = int(255 * (d_core * d2) ** (1 / 2.2))
            ideal_vals[c] = (ideal[c], math.exp(-1.0 * ideal[c] ** p.mm["B0"][c]), d2, val)
        results.append(StepResult(nn, rc["recipe_name"], is_aging, n, aging, cum,
                                  {c: stat[c].copy() for c in COLORS}, degs, deg2, image, ideal_vals))
        print(f"  {nn} {rc['recipe_name']:<14} {'Aging' if is_movie else 'PQ評価'}"
              f" {n:>5} フレーム  累積 {cum / 3600:8.2f} h")
    return results


# --------------------------------------------------------------------------- #
#  表（数値）
# --------------------------------------------------------------------------- #
def interior_masks(regions: np.ndarray) -> dict:
    """各領域の内側（縁から4画素以上内側。MP4 の縁のにじみを避ける）。"""
    k = np.ones((9, 9), np.uint8)
    return {rid: cv2.erode((regions == rid).astype(np.uint8), k).astype(bool) for rid in REGION_ORDER}


def write_values(evals: list, regions: np.ndarray, out_dir: Path, params_note: list) -> None:
    masks = interior_masks(regions)
    rows_ideal, rows_region = [], []
    for r in evals:
        hrs = r.cum_seconds / 3600
        row = {"累積Aging[h]": f"{hrs:g}"}
        for c in COLORS:
            s, d, d2, v = r.ideal[c]
            row.update({f"stat_{c}": f"{s:.4f}", f"deg_{c}": f"{d:.4f}", f"deg2_{c}": f"{d2:.4f}",
                        f"評価値_{c}": str(v)})
        rows_ideal.append(row)
        for rid in REGION_ORDER:
            m = masks[rid]
            px = r.image[m]                       # (n, 3) BGR
            med = np.median(px, axis=0).astype(int)
            rng = [f"{px[:, i].min()}-{px[:, i].max()}" for i in (2, 1, 0)]
            row = {"累積Aging[h]": f"{hrs:g}", "領域": REGION_NAMES[rid],
                   "評価画像R": str(med[2]), "評価画像G": str(med[1]), "評価画像B": str(med[0]),
                   "範囲R": rng[0], "範囲G": rng[1], "範囲B": rng[2]}
            for key, fmt in (("deg", ".4f"), ("deg2", ".4f"), ("stat", ".4g")):
                for c in COLORS:
                    src = getattr(r, key)[c]
                    row[f"{key}_{c}"] = format(float(np.median(src[m])), fmt)
            rows_region.append(row)

    with open(out_dir / "rgbcircle_theory_values.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["[理想値] 画素値=255 の画素（その色が点灯している領域）"])
        w.writerow(list(rows_ideal[0]))
        w.writerows([list(r.values()) for r in rows_ideal])
        w.writerow([])
        w.writerow(["[領域ごと] MP4 から読み出した画素値で計算（領域の内側の中央値／範囲）"])
        w.writerow(list(rows_region[0]))
        w.writerows([list(r.values()) for r in rows_region])

    def md_table(rows):
        keys = list(rows[0])
        lines = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
        lines += ["| " + " | ".join(r[k] for k in keys) + " |" for r in rows]
        return "\n".join(lines)

    md = [
        "# 3色円テスト 理論値（新コア）",
        "",
        *params_note,
        "",
        "## 理想値（その色が点灯している画素。Aging 中の画素値=255、評価は白=255 として計算）",
        "",
        "stat=累積時間（累積ストレス）、deg=輝度残存率（基準電流密度、出力の deg CSV）、deg2=サブモデルの残存率（白で評価したとき）、",
        "評価値=白で評価したときの画素値 floor(255×(deg×deg2)^(1/2.2))。",
        "消灯している色は stat=0・deg=1 で、評価値は deg2（劣化 1 のときの表の値）だけで決まる。",
        "",
        md_table(rows_ideal),
        "",
        "## 領域ごと（MP4 から読み出した画素値で計算。領域の内側の中央値、範囲は最小-最大）",
        "",
        md_table(rows_region),
        "",
    ]
    (out_dir / "rgbcircle_theory_values.md").write_text("\n".join(md), encoding="utf-8")


# --------------------------------------------------------------------------- #
#  bisim 出力との比較
# --------------------------------------------------------------------------- #
def load_csv(path: Path) -> np.ndarray:
    a = np.loadtxt(str(path), delimiter=",", dtype=float)
    if a.ndim == 2 and np.all(np.isnan(a[:, -1])):
        a = a[:, :-1]
    return a


def compare(results: list, seq: dict, bisim_out: Path, out_dir: Path) -> dict:
    """bisim の出力を読み、ステップごとの差をまとめる。戻り値 nn -> bisim の評価画像。"""
    name = seq["sequence_name"]
    lines = ["# 3色円テスト bisim 出力との比較（新コア）", "",
             f"bisim 出力フォルダ: `{bisim_out}`", "",
             "| NN | レシピ | 最大相対差 stat (R/G/B) | 最大差 deg (R/G/B) | 最大差 deg2 (R/G/B) | 評価画像 最大差[階調] / 差のある画素数 | 判定 |",
             "|---|---|---|---|---|---|---|"]
    bisim_images: dict = {}
    all_ok = True
    for r in results:
        def op(kind, c=None, ext="csv"):
            return bisim_out / naming.output_name(name, r.nn, r.recipe_name, kind, c, ext=ext)
        if not op("stat", "r").exists() or not op("deg2", "r").exists():
            lines.append(f"| {r.nn} | {r.recipe_name} | （出力なし） | | | | — |")
            all_ok = False
            continue
        rel, dd, d2d = [], [], []
        for c in COLORS:
            bs, bd, b2 = load_csv(op("stat", c)), load_csv(op("deg", c)), load_csv(op("deg2", c))
            rel.append(float(np.max(np.abs(bs - r.stat[c]) / (np.abs(r.stat[c]) + 1e-9))))
            dd.append(float(np.max(np.abs(bd - r.deg[c]))))
            d2d.append(float(np.max(np.abs(b2 - r.deg2[c]))))
        ok = max(rel) < 1e-9 and max(dd) < 1e-9 and max(d2d) < 1e-9
        img_cell = "—"
        if not r.is_aging:
            p = op("image", ext="png")
            if p.exists():
                bi = read_png(p)
                bisim_images[r.nn] = bi
                diff = np.abs(bi.astype(int) - r.image.astype(int))
                img_cell = f"{diff.max()} / {int((diff.max(axis=2) > 0).sum())}"
                ok = ok and diff.max() <= 1
            else:
                img_cell = "（画像なし）"
                ok = False
        all_ok &= ok
        lines.append(f"| {r.nn} | {r.recipe_name} | {' / '.join(f'{x:.1e}' for x in rel)} | "
                     f"{' / '.join(f'{x:.1e}' for x in dd)} | {' / '.join(f'{x:.1e}' for x in d2d)} | "
                     f"{img_cell} | {'OK' if ok else '**NG**'} |")
    lines += ["", f"**総合判定: {'OK（理論どおり）' if all_ok else 'NG あり'}**", "",
              "判定基準：stat の相対差・deg・deg2 の差が 1e-9 未満、評価画像の差が 1 階調以内"
              "（計算の順番の違いによる浮動小数点の丸めで、8bit 化の切り捨てが1つずれることは許容）。"
              "deg2 は Aging ステップでは最後のフレームの値。"]
    (out_dir / "rgbcircle_compare.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[4:]))
    return bisim_images


# --------------------------------------------------------------------------- #
#  表（画像）
# --------------------------------------------------------------------------- #
def write_table_png(evals: list, out_dir: Path, bisim_images: dict) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Meiryo", "Yu Gothic", "MS Gothic", "sans-serif"]

    rows = [("理論：評価画像（白で評価）", "eval")]
    if bisim_images:
        rows.append(("bisim：評価画像", "bisim"))
    rows += [(f"理論：累積時間 {c.upper()}（暗＝大）", c) for c in COLORS]
    vmax = {c: max(float(r.stat[c].max()) for r in evals) or 1.0 for c in COLORS}

    ncol = len(evals)
    fig, axes = plt.subplots(len(rows), ncol, figsize=(1.55 * ncol + 1.2, 3.25 * len(rows)),
                             squeeze=False)
    for j, r in enumerate(evals):
        hrs = r.cum_seconds / 3600
        for i, (label, key) in enumerate(rows):
            ax = axes[i][j]
            ax.set_xticks([])
            ax.set_yticks([])
            if key == "eval":
                ax.imshow(cv2.cvtColor(r.image, cv2.COLOR_BGR2RGB))
                ax.set_title(f"{hrs:g} h\n{r.nn} {r.recipe_name}", fontsize=9)
                iv = r.ideal
                ax.set_xlabel(f"deg×deg2 R {iv['r'][1] * iv['r'][2]:.3f}\n"
                              f"G {iv['g'][1] * iv['g'][2]:.3f}  B {iv['b'][1] * iv['b'][2]:.3f}", fontsize=8)
            elif key == "bisim":
                bi = bisim_images.get(r.nn)
                if bi is None:
                    ax.text(0.5, 0.5, "出力なし", ha="center", va="center", transform=ax.transAxes)
                else:
                    ax.imshow(cv2.cvtColor(bi, cv2.COLOR_BGR2RGB))
                    d = int(np.abs(bi.astype(int) - r.image.astype(int)).max())
                    ax.set_xlabel(f"理論との最大差 {d} 階調", fontsize=8)
            else:
                im = ax.imshow(r.stat[key], cmap="gray_r", vmin=0, vmax=vmax[key])
                ax.set_xlabel(f"stat {key.upper()} {r.ideal[key][0]:.3f}", fontsize=8)
                if j == ncol - 1:
                    fig.colorbar(im, ax=ax, fraction=0.08, pad=0.04)
            if j == 0:
                ax.set_ylabel(label, fontsize=9)
    fig.suptitle("3色円テスト：累積Aging時間ごとの理論値（新コア）"
                 "（数値は その色が点灯している画素の理想値）", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    path = out_dir / "rgbcircle_theory_table.png"
    fig.savefig(str(path), dpi=110)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    base = REPO / "eval_test" / "rgbcircle"
    ap.add_argument("--seq", type=Path, default=base / "rgbcircle.seq.json")
    ap.add_argument("--out", type=Path, help="結果の出力先（既定：シーケンスの横の theory）")
    ap.add_argument("--compare", action="store_true", help="bisim の出力と比較する")
    ap.add_argument("--bisim-out", type=Path, help="bisim の出力フォルダ（既定：シーケンスの output）")
    ap.add_argument("--input-dir", type=Path, help="入力画像のフォルダ（既定：シーケンスの input_image）")
    ap.add_argument("--bcset", type=Path, help="bcsetting.csv（既定：シーケンスのパネル設定）")
    ap.add_argument("--sm", type=Path, help="degparam_sm.csv（既定：シーケンスのパネル設定）")
    ap.add_argument("--app-dir", type=Path, help=APP_DIR_HELP)
    a = ap.parse_args()

    seq, seq_path = load_sequence(a.seq)
    in_dir = resolve_folder(seq, seq_path, "input_image", "input", a.input_dir, a.app_dir)
    bc_path, sm_path, mm = panel_files(seq, seq_path, a)
    panel = Panel(bc_path, sm_path)
    a.out = a.out or (seq_path.parent / "theory")
    a.out.mkdir(parents=True, exist_ok=True)
    print(f"シーケンス: {seq_path}")
    print(f"入力画像: {in_dir}")
    print(f"パネル設定: {bc_path} / {sm_path}")
    results = simulate(seq, in_dir, panel, mm)
    evals = [r for r in results if not r.is_aging]

    p0 = Params.from_recipe(seq["recipes"][0], seq["recipes"][0].get("step_type", "aging") == "aging", panel, mm)
    dt = p0.detail
    note = [f"パネル設定：`{bc_path.name}`・`{sm_path.name}`。DBV_NIT={p0.dbv:g} → DBV_eff={dt['dbv_eff']:g}、"
            f"Band{dt['bc1']}（{panel.dbv[dt['bc1']]:g} nit）と Band{dt['bc2']}（{panel.dbv[dt['bc2']]:g} nit）の間で補間"
            f"（t={dt['t']:.4f}、duty={dt['duty']:.4f}）。"]
    regions = read_png(in_dir / "rgbcircle-regions.png", cv2.IMREAD_GRAYSCALE)
    write_values(evals, regions, a.out, note)
    for r in evals:
        cv2.imencode(".png", r.image)[1].tofile(str(a.out / f"theory_{r.nn}_{r.recipe_name}_image.png"))

    bisim_images = {}
    if a.compare:
        bisim_out = resolve_folder(seq, seq_path, "output", "output", a.bisim_out, a.app_dir)
        print(f"\nbisim 出力と比較: {bisim_out}")
        bisim_images = compare(results, seq, bisim_out, a.out)
    table = write_table_png(evals, a.out, bisim_images)
    print(f"\n表: {table}\n数値: {a.out / 'rgbcircle_theory_values.md'}")


if __name__ == "__main__":
    main()
