"""劣化エンジン（T4）

- ``DegradationModel``  : 差し替え点（Protocol）。1フレーム更新 ＋ 劣化率マップ算出
- ``CoreModel``         : ``source/main.py``（新コア ``burn_in_core``。フェーズF）をラップしたモデル
- ``check_bcset`` / ``check_sm`` : パネル設定ファイル（bcsetting・サブモデル）の検査
- ``RGBMaps``           : 画素ごと・RGB 別のマップ（deg2 の受け取りなど）
- ``StressState``       : 累積ストレス(stat_r/g/b) の保持・CSV load/save・shape検証
- ``RunControl``        : UIスレッドからの 中断・再開・停止
- ``run_recipe``        : 1レシピ（動画1本 or 静止画1枚）のフレームループ
- ``run_sequence``      : シーケンス全体（初期ストレスの解決・連鎖・Aging時間累積）
- ``write_recipe_outputs`` / ``discard_recipe_outputs`` : 出力の確定 / 破棄

``source/`` は bisim 側で追加した箇所（「追加(bisim側)」のコメント）以外は無改変。Unicode パス対策は静止画=``imio``、動画=``cv2`` 直（VideoWriter は
ASCII一時ファイル→``shutil.move``）。
"""
from __future__ import annotations

import math
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol, runtime_checkable

import cv2
import numpy as np

from bisim import imio, naming, paramio
from bisim.model import (
    CHECKPOINT_ROOT, DEFAULT_MODEL, DEFAULT_SIM, Recipe, Sequence, StopState,
)
from bisim.paths import SOURCE_DIR, STD_BCSET, STD_DEGPARAM_SM

# 停止チェックポイント内の素のファイル名（フォルダ名が識別子。日時なし・常に最新1件）
_CKPT_STAT = {c: f"stat_{c}.csv" for c in "rgb"}
_CKPT_DEG = {c: f"deg_{c}.csv" for c in "rgb"}
_CKPT_DEG2 = {c: f"deg2_{c}.csv" for c in "rgb"}
_CKPT_MOVIE = "movie.mp4"
_CKPT_IMAGE = "image.png"


class EngineError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
#  累積ストレス状態
# --------------------------------------------------------------------------- #
@dataclass(eq=False)
class RGBMaps:
    """画素ごと・RGB 別のマップ 3 枚（各 (h, w) の float 配列）。"""

    r: np.ndarray
    g: np.ndarray
    b: np.ndarray

    @property
    def shape(self) -> tuple:
        return self.r.shape          # (h, w)

    def channel(self, c: str) -> np.ndarray:
        return {"r": self.r, "g": self.g, "b": self.b}[c]

    @classmethod
    def full(cls, height: int, width: int, value: float):
        return cls(*(np.full((height, width), float(value), dtype=float) for _ in range(3)))

    @classmethod
    def zeros(cls, height: int, width: int):
        return cls.full(height, width, 0.0)

    @classmethod
    def load(cls, path_r, path_g, path_b):
        return cls(_load_csv_map(path_r), _load_csv_map(path_g), _load_csv_map(path_b))

    def save(self, path_r, path_g, path_b) -> None:
        np.savetxt(str(path_r), self.r, delimiter=",")
        np.savetxt(str(path_g), self.g, delimiter=",")
        np.savetxt(str(path_b), self.b, delimiter=",")


@dataclass(eq=False)
class StressState(RGBMaps):
    """累積ストレス stat_r/g/b（ステップ間で引き継ぐ）。"""

    def require_shape(self, height: int, width: int) -> None:
        if self.shape != (height, width):
            raise EngineError(
                f"継承ストレスのサイズ {self.shape} が入力 {(height, width)} と不一致")


def _load_csv_map(path) -> np.ndarray:
    arr = np.loadtxt(str(path), delimiter=",", dtype=float)
    if arr.ndim == 2 and np.all(np.isnan(arr[:, -1])):   # trailing comma 対策
        arr = arr[:, :-1]
    return arr


# --------------------------------------------------------------------------- #
#  劣化モデル（差し替え点）
# --------------------------------------------------------------------------- #
@runtime_checkable
class DegradationModel(Protocol):
    name: str

    def update(self, dt: float, img_bgr: np.ndarray, ht_bgr: np.ndarray,
               state: StressState, model_param: dict, sim_param: dict,
               deg2: "Optional[RGBMaps]" = None) -> None:
        """img_bgr を劣化画像にインプレース更新し、state を dt ぶん進める。

        ``deg2`` が渡されたら、今回のフレームのサブモデルの輝度残存率で中身を上書きする。
        """

    def deg_maps(self, state: StressState, temp_kelvin: np.ndarray,
                 model_param: dict) -> dict:
        """現在の state から輝度残存率マップ（deg1）``{"r":arr, "g":arr, "b":arr}`` を返す。"""


_CORE_MOD = None


def _load_core():
    """``source/main.py``（新コア）をモジュールとして読み込んで返す。

    PyInstaller で固めた EXE でも確実に動くよう、まず ``SOURCE_DIR/main.py`` を
    **ファイルパスから直接ロード**する。``import main`` は他パッケージのトップレベル
    モジュール名と衝突しやすく、frozen 環境では frozen 用インポータが優先されて
    別の ``main`` を掴むことがあるため使わない。
    使う関数：``burn_in_core``・``burn_in_band_extract``、``main.py`` が import している
    ``load_com_info``（属性名 ``com_info``）の ``load_bcset``・``load_degparam_sm``。
    """
    global _CORE_MOD
    if _CORE_MOD is not None:
        return _CORE_MOD

    src = str(SOURCE_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)          # main.py 内の `import load_com_info` 用

    main_py = SOURCE_DIR / "main.py"
    if main_py.is_file():
        import importlib.util
        modname = "bisim_core_source"
        spec = importlib.util.spec_from_file_location(modname, str(main_py))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[modname] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as e:  # noqa: BLE001
            raise EngineError(
                f"劣化コア {main_py} の読み込みに失敗: {type(e).__name__}: {e}") from e
        where = str(main_py)
    else:
        # フォールバック: モジュール検索（source/ が sys.path 上にある開発環境）
        import importlib
        try:
            mod = importlib.import_module("main")
        except ImportError as e:
            raise EngineError(
                f"劣化コア main.py が見つかりません（SOURCE_DIR={SOURCE_DIR}）: {e}") from e
        where = f"import した main（{getattr(mod, '__file__', '?')}）"
    missing = [n for n in ("burn_in_core", "burn_in_band_extract", "com_info")
               if not hasattr(mod, n)]
    if missing:
        raise EngineError(
            f"{where} に {', '.join(missing)} が無い（新コアではない／別モジュールを掴んでいる可能性）")
    _CORE_MOD = mod
    return mod


# 新コアの Sim 条件の既定値（2026-11-17 決定。``model.DEFAULT_SIM`` と同じ値を ``simconf_dict`` の形で）
CORE_SIM_DEFAULTS = {"DBV_NIT": float(DEFAULT_SIM["DBV_NIT"]), "DPK_ON": int(DEFAULT_SIM["DPK_ON"]),
                     **{f"GADJ_{c}": float(v) for c, v in zip("RGB", DEFAULT_SIM["GADJ"])}}


def core_sim_dict(sim_param: dict) -> dict:
    """bisim の Sim 条件を ``burn_in_core`` の ``simconf_dict`` の形にする。

    無い項目は ``CORE_SIM_DEFAULTS`` で補う。``GADJ`` が ``[r, g, b]`` で来たら
    ``GADJ_R/G/B`` に分ける（``load_com_info.load_simconf`` と同じ形）。
    """
    d = dict(CORE_SIM_DEFAULTS)
    d.update(sim_param)
    gadj = d.pop("GADJ", None)
    if gadj is not None:
        d["GADJ_R"], d["GADJ_G"], d["GADJ_B"] = (float(x) for x in gadj)
    d["DBV_NIT"] = float(d["DBV_NIT"])
    d["DPK_ON"] = int(d["DPK_ON"])
    return d


# --------------------------------------------------------------------------- #
#  パネル設定ファイルの検査（ファイルを選んだとき・実行前。手順5）
# --------------------------------------------------------------------------- #
_BC_KEYS = ("BC_BAND_NUM", "APL_DPK", "DBV_NIT_DPK", "DBV_NIT_BC", "DUTY_BC",
            "CURR_BC_R", "CURR_BC_G", "CURR_BC_B", "CURR_RATIO", "GI_LUT_WRD_GRY", "GI_LUT_GRY")
_SM_KEYS = ("DEG_2D_WRD_DEG", "DEG_2D_DEG_R", "DEG_2D_DEG_G", "DEG_2D_DEG_B",
            "DEG_2D_WRD_I", "DEG_2D_I_R", "DEG_2D_I_G", "DEG_2D_I_B")


def _csv_keys(path: Path) -> set:
    """CSV の各行の先頭の欄（キー名）の集合。"""
    keys = set()
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            k = line.split(",", 1)[0].strip()
            if k:
                keys.add(k)
    return keys


@dataclass(eq=False)
class PanelCheck:
    """パネル設定ファイルの検査結果。``problems`` が空なら使える。"""

    problems: list = field(default_factory=list)
    band_num: Optional[int] = None        # 読めたときの Band 数
    data: Optional[dict] = None           # 読み込んだ辞書（load_com_info の戻り値）

    @property
    def ok(self) -> bool:
        return not self.problems


def check_bcset(path) -> PanelCheck:
    """``bcsetting.csv`` の検査：ファイルの有無・キー行の欠落・読み込み（行数・列数）・各 Band の値の数。

    値の並び順（大きい順・小さい順）は見ない（2026-11-18 担当者判断：キー名と行数・列数だけ）。
    """
    p = Path(path)
    chk = PanelCheck()
    if not p.is_file():
        chk.problems.append(f"ファイルがありません: {p}")
        return chk
    try:
        missing = [k for k in _BC_KEYS if k not in _csv_keys(p)]
    except (OSError, UnicodeDecodeError) as e:
        chk.problems.append(f"読めません: {type(e).__name__}: {e}")
        return chk
    if missing:
        chk.problems.append("キーの行がありません: " + ", ".join(missing))
        return chk
    rc, bc = _load_core().com_info.load_bcset(str(p))
    if rc != 0:
        chk.problems.append("読み込みに失敗しました（GI_LUT の行数・列数が GI_LUT_WRD_GRY・BC_BAND_NUM と"
                            "合わない、数値でない値がある、など）")
        return chk
    n = int(bc["BC_BAND_NUM"])
    for k in ("DBV_NIT_BC", "DUTY_BC", "CURR_BC_R", "CURR_BC_G", "CURR_BC_B"):
        if len(bc[k]) != n:
            chk.problems.append(f"{k} の値の数 {len(bc[k])} が BC_BAND_NUM={n} と違います")
    if not len(bc["DBV_NIT_DPK"]) < n:     # 通常の最大 Band（HBM）＝DBV_NIT_BC[len(DBV_NIT_DPK)]
        chk.problems.append(f"DBV_NIT_DPK の値の数 {len(bc['DBV_NIT_DPK'])} は BC_BAND_NUM={n} より少なくしてください")
    chk.band_num, chk.data = n, bc
    return chk


def check_sm(path, band_num: Optional[int] = None) -> PanelCheck:
    """``degparam_sm.csv`` の検査：ファイルの有無・キー行の欠落・読み込み（行数・列数）・Band 数。

    ``band_num`` を渡すと bcsetting の Band 数と比べる。
    軸の値の決まり（``source/main.py`` の説明：劣化軸 ``DEG_2D_DEG_*`` は 1.0 から始まる降順、電流軸 ``DEG_2D_I_*`` は
    昇順で最後が 1.0）は見ない（2026-11-18 担当者判断：キー名と行数・列数だけ）。守られていないと deg2 の補間が正しくならない。
    """
    p = Path(path)
    chk = PanelCheck()
    if not p.is_file():
        chk.problems.append(f"ファイルがありません: {p}")
        return chk
    try:
        missing = [k for k in _SM_KEYS if k not in _csv_keys(p)]
    except (OSError, UnicodeDecodeError) as e:
        chk.problems.append(f"読めません: {type(e).__name__}: {e}")
        return chk
    if missing:
        chk.problems.append("キーの行がありません: " + ", ".join(missing))
        return chk
    rc, sm = _load_core().com_info.load_degparam_sm(str(p))
    if rc != 0:
        chk.problems.append("読み込みに失敗しました（軸の値の数が DEG_2D_WRD_DEG・DEG_2D_WRD_I と合わない、"
                            "表の行数・列数が合わない、数値でない値がある、など）")
        return chk
    n = int(sm["DEG_2D_BC_IxDEG_R"].shape[0])
    if band_num is not None and n != band_num:
        chk.problems.append(f"Band 数 {n} が bcsetting の BC_BAND_NUM={band_num} と違います")
    chk.band_num, chk.data = n, sm
    return chk


def file_key(path) -> tuple:
    """ファイルの同一性の目印（絶対パス・更新時刻・大きさ）。無ければ時刻・大きさは ``None``。"""
    p = Path(path)
    try:
        st = p.stat()
        return (str(p.resolve()), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(p.resolve()), None, None)


def panel_key(bcset_path, sm_path) -> tuple:
    """パネル設定（bcsetting・sm）の目印。:attr:`CoreModel.panel_key` と比べる。"""
    return (file_key(bcset_path), file_key(sm_path))


class CoreModel:
    """新コア（``source/main.py`` の ``burn_in_core``）をラップしたモデル（フェーズF）。

    - パネル設定（bcsetting・サブモデル degparam_sm）は作成時に読み込む（既定は標準ファイル
      ``source/dbi_conf/``。画面はシーケンスのパネル設定を渡す）。
      マスターモデルのパラメータ（mm）は ``update``・``deg_maps`` の引数（シーケンスのパネル設定）。
    - サブモデルはステップごとに差し替えられる（``use_sm``。表示＝deg2 だけに効く）。読んだ sm は覚えておく
    - Band 選択（``burn_in_band_extract``）は画像に依らず sm・``DBV_NIT``・``DPK_ON`` だけで
      決まるので、その組ごとに1回だけ計算して覚えておく。
    - ``deg_maps``（deg1）は新コアの出力と同じ ``exp(-stat^B0)``（温度は使わない）。
    """

    name = "core01"

    def __init__(self, bcset_path=None, sm_path=None, log=None) -> None:
        self._core = _load_core()
        self.log = log
        self.bcset_path = Path(bcset_path or STD_BCSET)
        self.base_sm_path = Path(sm_path or STD_DEGPARAM_SM)
        self._bc_key = file_key(self.bcset_path)
        bc = check_bcset(self.bcset_path)
        if not bc.ok:
            raise EngineError(f"BC設定 {self.bcset_path} を使えません:\n  " + "\n  ".join(bc.problems))
        self.bc_dict = bc.data
        self._sm_cache: dict = {}
        self._band_cache: dict = {}
        self._base_sm_key = file_key(self.base_sm_path)
        self.sm_path, self._sm_key = self.base_sm_path, self._base_sm_key
        self.sm_dict = self._load_sm(self.base_sm_path, self._sm_key)

    @property
    def panel_key(self) -> tuple:
        """読み込んだときのパネル設定（bcsetting・シーケンスの sm）の :func:`panel_key`。

        画面はシーケンスのパネル設定の ``panel_key`` と比べ、違えば（別のファイルを選んだ・
        Excel で直して保存し直した）モデルを作り直す。
        """
        return (self._bc_key, self._base_sm_key)

    def _load_sm(self, path: Path, key: tuple) -> dict:
        sm = self._sm_cache.get(key)
        if sm is None:
            chk = check_sm(path, self.bc_dict["BC_BAND_NUM"])
            if not chk.ok:
                raise EngineError(f"サブモデル {path} を使えません:\n  " + "\n  ".join(chk.problems))
            sm = self._sm_cache[key] = chk.data
        return sm

    def use_sm(self, path=None) -> None:
        """このステップで使うサブモデルに切り替える（``None``＝シーケンスの sm）。"""
        path = Path(path) if path is not None else self.base_sm_path
        key = file_key(path)
        if key == self._sm_key:
            return
        self.sm_dict = self._load_sm(path, key)
        self.sm_path, self._sm_key = path, key
        if self.log:
            self.log.action(f"サブモデル: {path.name}")

    def band_data(self, sim: dict) -> dict:
        """``burn_in_core`` に渡す Band 間補間用データ（sm・``DBV_NIT``・``DPK_ON`` ごとにキャッシュ）。"""
        dbv, dpk = float(sim["DBV_NIT"]), int(sim["DPK_ON"])
        key = (self._sm_key, dbv, dpk)
        band = self._band_cache.get(key)
        if band is None:
            rc, band, blog = self._core.burn_in_band_extract(self.bc_dict, self.sm_dict, sim)
            if rc != 0:
                raise EngineError(
                    f"Band 選択（burn_in_band_extract）に失敗: DBV_NIT={dbv:g}, DPK_ON={dpk}"
                    + (f"\n{blog.rstrip()}" if blog else ""))
            self._band_cache[key] = band
            if self.log:
                self.log.action(f"Band 選択 DBV_NIT={dbv:g} DPK_ON={dpk}\n{blog.rstrip()}")
        return band

    def update(self, dt, img_bgr, ht_bgr, state, model_param, sim_param, deg2=None) -> None:
        mm = paramio.to_mm_dict(model_param)
        sim = core_sim_dict(sim_param)
        kw = {}
        if deg2 is not None:
            kw = {"deg2_r": deg2.r, "deg2_g": deg2.g, "deg2_b": deg2.b}
        rc = self._core.burn_in_core(
            dt, img_bgr, ht_bgr, self.bc_dict, mm, self.sm_dict, sim,
            stat_r=state.r, stat_g=state.g, stat_b=state.b,
            **self.band_data(sim), **kw)
        if rc != 0:
            raise EngineError("劣化コア burn_in_core が異常終了（rtn=-1）")

    def deg_maps(self, state, temp_kelvin, model_param) -> dict:
        mm = paramio.to_mm_dict(model_param)
        return {c: np.exp(-1.0 * (state.channel(c) ** mm[f"B0_{c}"])) for c in "rgb"}


# --------------------------------------------------------------------------- #
#  実行制御・結果
# --------------------------------------------------------------------------- #
class RunControl:
    """UI スレッドからの 中断(pause)・再開(resume)・停止(stop)。"""

    def __init__(self) -> None:
        self._pause = False
        self._stop = False

    def request_pause(self) -> None:
        self._pause = True

    def request_resume(self) -> None:
        self._pause = False

    def request_stop(self) -> None:
        self._stop = True

    def reset(self) -> None:
        self._pause = self._stop = False

    @property
    def paused(self) -> bool:
        return self._pause

    @property
    def stopped(self) -> bool:
        return self._stop


@dataclass(eq=False)
class RunResult:
    recipe_name: str
    nn: str
    is_movie: bool
    size: tuple                 # (w, h)
    frames_total: int
    frames_done: int
    aging_seconds: float        # このレシピの加速込みエージング時間
    stopped: bool
    state: StressState          # 実行後の累積ストレス（メモリ保持）
    temp_kelvin: np.ndarray     # 最終フレームの温度マップ（deg 計算用）
    deg2: Optional[RGBMaps] = None  # サブモデルの輝度残存率（最後に処理したフレームの値。未処理なら 1.0）
    # 最後に処理した入力フレームで、その色が 0（黒）の画素（{c: bool配列}。未処理なら None）。
    # 黒の画素の deg2 は意味のない値になるので、⑤の deg2 表示で除くのに使う（ファイルには出さない。5-4）
    input_black: Optional[dict] = None
    outputs: dict = field(default_factory=dict)
    cumulative_aging_seconds: float = 0.0
    resumed_from: int = 0          # 停止位置から再開したときの開始フレーム（絶対）
    dt_accel: float = 0.0          # 1フレームあたりの加速込み Aging 時間 [s]（静止画は 0）
    _tmp_video: Optional[Path] = None
    _img_bgr: Optional[np.ndarray] = None

    @property
    def frames_absolute(self) -> int:
        """このレシピで累積処理済みの絶対フレーム数（再開分を含む）。"""
        return self.resumed_from + self.frames_done


# --------------------------------------------------------------------------- #
#  再開プラン（``StopState`` は仕様 7 のとおり ``bisim.model`` に移動。
#  ``Sequence.stops`` が停止状態を内包し、実体は ``<output>/_stops/<dir>/``）
# --------------------------------------------------------------------------- #
@dataclass(eq=False)
class ResumePlan:
    """停止結果からの再開に必要な情報（``run_sequence`` の先頭ステップに適用）。"""

    state: "StressState"
    frames_done: int
    aging_seconds: float = 0.0
    video: Optional[Path] = None      # 継続元の部分動画（連続出力のため先頭に連結）


def aging_time_add_frames(dt_accel: float, remaining_seconds: float) -> int:
    """AGING_TIME（残り目標秒数）から、追加で処理するフレーム数を見積もる。

    ``run_recipe`` 本体と ④実行タブの動画情報表示（評価メモ対応）が同じ計算を
    共有する。残りが0以下なら0（もう目標達成）、それ以外は**最低1フレーム**
    （退化防止。目標が1フレーム未満の時間でも、少なくとも1フレームは処理する）。
    """
    if dt_accel <= 0 or remaining_seconds <= 0:
        return 0
    return max(1, math.ceil(remaining_seconds / dt_accel))


def movie_meta(path) -> tuple:
    """動画ファイルの (fps, 総フレーム数) を返す。読めない場合は (0.0, 0)。

    ④実行タブで「選択中のレシピは何フレームか／ACCEL_RATIO換算で1周回がどれだけの
    Aging時間になるか」を表示するために使う（評価メモ #1）。
    """
    cap = cv2.VideoCapture(str(path))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        cap.release()
    return fps, frames


def format_aging(seconds: float) -> str:
    """加速込み Aging 時間の表示。

    時:分:秒（``00h 00m 00s``）。小さい ACCEL_RATIO 等で数十秒規模になる場合も
    分かるように、時間の小数表示（例 ``0.00 h``）ではなく hms で表す（評価反映3 (B-3)）。
    24時間を超える場合は日数も先頭に付ける（例 ``4d 04h 00m 00s``）。
    """
    total = max(0, int(round(seconds)))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    hms = f"{hours:02d}h {minutes:02d}m {secs:02d}s"
    return f"{days}d {hms}" if days > 0 else hms


# --------------------------------------------------------------------------- #
#  画像サイズ（シーケンス内で全画像を同じサイズにそろえる）
# --------------------------------------------------------------------------- #
def media_size(path) -> Optional[tuple]:
    """画像・動画の ``(幅, 高さ)``。読めなければ ``None``。"""
    p = Path(path)
    if not p.is_file():
        return None
    if p.suffix.lower() == ".mp4":
        cap = cv2.VideoCapture(str(p))
        try:
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        finally:
            cap.release()
        return (w, h) if w > 0 and h > 0 else None
    img = imio.imread(p)
    return None if img is None else (img.shape[1], img.shape[0])


@dataclass(eq=False)
class SizeRef:
    """サイズ判定の基準になった画像（どのステップのどの欄か）。"""

    size: tuple                 # (w, h)
    index: int                  # ステップ（0始まり）
    field: str                  # "input_image" | "heatmap"
    name: str                   # ファイル名


def sequence_reference_size(sequence: Sequence, skip: Optional[tuple] = None) -> Optional[SizeRef]:
    """シーケンス内の画像サイズの基準（仕様: 2026-10-19 担当者決定）。

    ステップ順に「入力画像 → ヒートマップ」と見ていき、最初に読めた画像のサイズを基準にする
    （通常はシーケンスの最初に選んだ画像）。動画か静止画かは問わない。ヒートマップは
    実際に使う場合（Aging ステップ・ファイルモード）だけ数える。
    ``skip=(index, field)`` の欄は除く（選び直そうとしている欄そのもの）。
    基準になる画像がまだ無ければ ``None``（何を選んでもよい）。
    """
    for i, r in enumerate(sequence.recipes):
        slots = [("input_image", r.input_image)]
        if not r.is_eval and r.heatmap_mode == "file":
            slots.append(("heatmap", r.heatmap))
        for field_key, name in slots:
            if not name or (skip is not None and (i, field_key) == tuple(skip)):
                continue
            size = media_size(Path(sequence.folders[field_key]) / name)
            if size is not None:
                return SizeRef(size=size, index=i, field=field_key, name=name)
    return None


# --------------------------------------------------------------------------- #
#  1レシピの実行
# --------------------------------------------------------------------------- #
# 静止画 Aging の仮想 fps（担当者決定 2026-10-19）。1フレーム = 1秒 × ACCEL_RATIO の Aging。
# Aging 時間の刻みは ACCEL_RATIO で調整する。
STILL_AGING_FPS = 1.0
# 評価ステップの温度（評価は温度設定なし。2026-10-19 決定）。モデル変更で温度依存が
# ストレス累積側に移るまでの暫定で、現行モデルでも A=0 なら結果に影響しない。
EVAL_TEMP_C = 25.0


def black_mask_bgr(img: np.ndarray) -> dict:
    """BGR 画像で、その色が 0（黒＝階調0）の画素を True にした ``{"r","g","b": bool配列}``。

    黒の画素は電流 0 でサブモデルの表の範囲外になり、deg2 が意味のない値になる（11/17 決定）。
    ⑤の deg2・deg1×deg2 の表示で、その画素を除くのに使う（フェーズF 5-4）。
    """
    if img.ndim == 2:
        m = img == 0
        return {c: m for c in "rgb"}
    return {"r": img[..., 2] == 0, "g": img[..., 1] == 0, "b": img[..., 0] == 0}


def run_recipe(
    *,
    recipe: Recipe,
    folders: dict,
    sequence_name: str,
    nn: str,
    model: DegradationModel,
    initial_state: Optional[StressState] = None,
    resume_from: int = 0,
    resume_video: Optional[Path] = None,      # 停止位置から再開時、先頭に連結する部分動画
    resume_aging_seconds: float = 0.0,        # 停止までの加速込み Aging 時間（積み増し）
    max_frames: Optional[int] = None,
    control: Optional[RunControl] = None,
    progress_cb: Optional[Callable] = None,   # (done:int, total:int, preview_bgr|None)
    log=None,
    model_param: Optional[dict] = None,       # mm（シーケンスのパネル設定）。None＝既定値
    sm_path=None,                             # このステップのサブモデル（None＝モデルの既定の sm）
) -> RunResult:
    """1ステップを実行する。処理はステップ種別（``recipe.step_type``）で決まる:

    - Aging × 動画   : 1フレーム = (1/fps)×ACCEL_RATIO。AGING_TIME で打切り／周回（従来どおり）
    - Aging × 静止画 : 同じ絵を fps=1 で繰り返す（1フレーム = 1秒×ACCEL_RATIO）。
                       AGING_TIME で回数が決まる（0 なら1フレーム）。出力は最後の劣化画像（PNG）
    - 評価 × 静止画  : ストレスを貯めずに劣化後の画像を1枚作る
    - 評価 × 動画    : ストレスを貯めずに全フレームを1周回（劣化後の見え方の動画を作る）
    評価ステップは温度設定なし（``EVAL_TEMP_C`` 固定・ヒートマップ不使用）。
    """
    control = control or RunControl()
    mm = model_param if model_param is not None else {k: list(v) for k, v in DEFAULT_MODEL.items()}
    use_sm = getattr(model, "use_sm", None)       # サブモデルを差し替えられるモデル（CoreModel）
    if use_sm is not None:
        use_sm(sm_path)
    eval_step = recipe.is_eval
    fixed_temp = eval_step or recipe.heatmap_mode == "fixed"
    temp_c = EVAL_TEMP_C if eval_step else recipe.fixed_temp_c
    in_dir = Path(folders["input_image"])
    ht_dir = Path(folders["heatmap"])
    path_img = in_dir / recipe.input_image
    path_ht = None if fixed_temp else ht_dir / recipe.heatmap
    if not recipe.input_image or not path_img.exists():
        raise EngineError(f"入力画像が見つかりません: {path_img}")
    if path_ht is not None and (not recipe.heatmap or not path_ht.exists()):
        raise EngineError(f"ヒートマップが見つかりません: {path_ht}")

    # 固定温度（ヒートマップなし、または評価ステップ）：source/main.py は無改変のまま、
    # ht の中身に依らず一定温度になるよう TMP_L=TMP_H=固定温度 として渡す
    # （(ht/255)*(TMP_H-TMP_L)+TMP_L が定数になる）
    sim = dict(recipe.sim_param)
    if fixed_temp:
        sim["TMP_L"] = sim["TMP_H"] = float(temp_c)
    accel = float(sim["ACCEL_RATIO"])
    tmp_l_k = float(sim["TMP_L"]) + 273.0
    tmp_h_k = float(sim["TMP_H"]) + 273.0
    is_movie = path_img.suffix.lower() == ".mp4"
    if log:
        log.io("in", path_img.name)
        if eval_step:
            log.action(f"評価ステップ（ストレスを貯めない・温度 {temp_c:g}℃ 固定）")
        elif fixed_temp:
            log.action(f"固定温度 {temp_c:g}℃ でヒートマップ代用")
        else:
            log.io("in", path_ht.name)

    # ---- 入力サイズ確定 ----
    cap = cap_ht = None
    img0 = ht0 = None
    if is_movie:
        cap = cv2.VideoCapture(str(path_img))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    else:
        img0 = imio.imread(path_img)
        if img0 is None:
            raise EngineError(f"画像を読めません: {path_img}")
        height, width = img0.shape[:2]
        fps, frames_total = STILL_AGING_FPS, 1
    if path_ht is not None:
        if path_ht.suffix.lower() == ".mp4":
            cap_ht = cv2.VideoCapture(str(path_ht))
        else:
            ht0 = imio.imread(path_ht)
            if ht0 is None:
                raise EngineError(f"画像を読めません: {path_ht}")
    ht_dummy = np.zeros((height, width, 3), dtype=np.uint8) if fixed_temp else None
    # 評価ステップはストレスを貯めない（dt=0）。Aging は 1フレーム = 1/fps 秒
    dt = 0.0 if eval_step else 1.0 / fps
    dt_accel = dt * accel

    # ---- 初期ストレス ----
    if initial_state is None:
        state = StressState.zeros(height, width)
    else:
        state = initial_state
        state.require_shape(height, width)
    # サブモデルの輝度残存率 deg2（次のステップには引き継がない。フレームごとにコアが上書き）
    deg2 = RGBMaps.full(height, width, 1.0)

    last_temp = np.full((height, width), tmp_l_k, dtype=float)
    aging_seconds = float(resume_aging_seconds)
    frames_done = 0
    stopped = False
    img_last = None
    in_last = None                          # 最後に処理した入力フレーム（コアが書き換える前）
    tmp_video: Optional[Path] = None
    looped = is_movie or not eval_step      # フレームループで処理する（静止画の評価だけは1回）
    start = max(resume_from, 0) if looped else 0
    frames_target = frames_total

    def _temp(ht):
        return (ht[:, :, 0] / 255.0) * (tmp_h_k - tmp_l_k) + tmp_l_k

    def _next_ht(use_target):
        if fixed_temp:
            return ht_dummy
        if cap_ht is None:
            return ht0
        ok2, ht = cap_ht.read()
        if not ok2 and use_target:
            cap_ht.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok2, ht = cap_ht.read()
        return ht if ok2 else None

    if looped:
        writer = None
        if is_movie:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            _fd, _tmp = tempfile.mkstemp(suffix=".mp4")            # ASCII パス
            os.close(_fd)                                          # mkstemp のハンドルを閉じる（Windowsでロック解除）
            tmp_video = Path(_tmp)
            writer = cv2.VideoWriter(str(tmp_video), fourcc, fps, (width, height))

        # ---- AGING_TIME（目標 Aging 時間・秒。仕様: IP設計者レビュー2 (3)）----
        # 0（既定）＝無制限＝動画は1周回のみ（静止画は1フレーム）。正の値なら、
        # 1周回の実時間（frames_total×dt×ACCEL_RATIO）が目標を超えれば途中で打ち切り、
        # 満たなければ先頭へ戻って周回しながら目標に達するまで継続する。
        # 評価ステップは Aging しないので AGING_TIME は使わない（動画を1周回）。
        target_seconds = 0.0 if eval_step else float(sim.get("AGING_TIME", 0.0))
        use_target = dt_accel > 0 and target_seconds > 0
        if use_target:
            add_frames = aging_time_add_frames(dt_accel, target_seconds - aging_seconds)
            frames_target = start + add_frames
        end = frames_target if max_frames is None else min(frames_target, start + max_frames)

        if start > 0 and is_movie:
            # 連続動画にするため、継続元の部分動画から先頭 start フレームを取り込む
            copied = 0
            if resume_video is not None and Path(resume_video).exists():
                rcap = cv2.VideoCapture(str(resume_video))
                try:
                    while copied < start:
                        ok, frm = rcap.read()
                        if not ok:
                            break
                        writer.write(frm)
                        copied += 1
                finally:
                    rcap.release()
            if log:
                log.action(f"再開: 先頭 {copied}/{start} フレームを部分動画から連結")
            # start が動画の実フレーム数を超えることがある（AGING_TIME で周回中の再開）ため
            # 実動画上の位置は周回を畳んだ余り（modulo）で求める
            native_pos = (start % frames_total) if frames_total > 0 else 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, native_pos)
            if cap_ht is not None:
                cap_ht.set(cv2.CAP_PROP_POS_FRAMES, native_pos)
        elif start > 0 and log:
            log.action(f"再開: フレーム {start} から（静止画 Aging）")
        try:
            frame_idx = start
            while frame_idx < end:
                while control.paused and not control.stopped:
                    time.sleep(0.05)
                if control.stopped:
                    stopped = True
                    break
                if is_movie:
                    ok1, img = cap.read()
                    if not ok1 and use_target:
                        # 動画終端 → AGING_TIME 未達なら先頭へ戻って周回を続ける
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ok1, img = cap.read()
                    if not ok1:
                        break
                else:
                    img = img0.copy()            # コアが img をインプレースで書き換えるため毎回複製
                ht = _next_ht(use_target)
                if ht is None:
                    break
                in_last = img.copy()             # コアが img を書き換える前の入力（黒の画素の判定用）
                model.update(dt, img, ht, state, mm, sim, deg2=deg2)
                last_temp = _temp(ht)
                if writer is not None:
                    writer.write(img)
                aging_seconds += dt_accel
                frames_done += 1
                frame_idx += 1
                img_last = img
                if progress_cb:
                    progress_cb(frames_done, end - start, img)
                if use_target and aging_seconds >= target_seconds:
                    break        # 目標時間に到達（周回途中でも打ち切る）
        finally:
            if cap is not None:
                cap.release()
            if cap_ht is not None:
                cap_ht.release()
            if writer is not None:
                writer.release()
    else:
        # 静止画の評価：ストレスを貯めずに劣化後の画像を1枚作る（評価は固定温度なので ht はダミー）
        if control.stopped:
            stopped = True
        else:
            ht0_eff = _next_ht(False)
            in_last = img0.copy()
            model.update(0.0, img0, ht0_eff, state, mm, sim, deg2=deg2)
            last_temp = _temp(ht0_eff)
            frames_done = 1
            img_last = img0
            if progress_cb:
                progress_cb(1, 1, img0)

    # frames_total の意味: 静止画の評価は常に1。それ以外は AGING_TIME 由来の目標フレーム数
    # （進捗バー・停止再開ダイアログ用の目安値。無制限なら入力動画の実フレーム数と同じ）
    reported_frames_total = frames_target if looped else 1
    res = RunResult(
        recipe_name=recipe.recipe_name, nn=nn, is_movie=is_movie,
        size=(width, height), frames_total=reported_frames_total, frames_done=frames_done,
        aging_seconds=aging_seconds, stopped=stopped, state=state, temp_kelvin=last_temp,
        deg2=deg2, resumed_from=start, dt_accel=dt_accel,
        input_black=None if in_last is None else black_mask_bgr(in_last),
    )
    res._tmp_video = tmp_video
    res._img_bgr = None if is_movie else img_last
    return res


# --------------------------------------------------------------------------- #
#  出力の確定 / 破棄
# --------------------------------------------------------------------------- #
def write_recipe_outputs(
    *,
    result: RunResult,
    folders: dict,
    sequence_name: str,
    model: DegradationModel,
    model_param: dict,
    log=None,
) -> dict:
    """通常完了時の出力（``シーケンス名_NN_レシピ名_種別[_色].拡張子``）。"""
    out_dir = Path(folders["output"])
    out_dir.mkdir(parents=True, exist_ok=True)
    seq, nn, rc = sequence_name, result.nn, result.recipe_name

    def outp(kind, color=None, ext="csv"):
        return out_dir / naming.output_name(seq, nn, rc, kind, color, ext=ext)

    outputs: dict = {}

    if result.is_movie:
        if result._tmp_video and Path(result._tmp_video).exists():
            dest = outp("movie", ext="mp4")
            shutil.move(str(result._tmp_video), str(dest))
            outputs["movie"] = dest
    else:
        if result._img_bgr is not None:
            dest = outp("image", ext="png")
            imio.imwrite(dest, result._img_bgr)
            outputs["image"] = dest

    deg = model.deg_maps(result.state, result.temp_kelvin, model_param)
    for c in "rgb":
        dp, sp = outp("deg", c), outp("stat", c)
        np.savetxt(str(dp), deg[c], delimiter=",")
        np.savetxt(str(sp), result.state.channel(c), delimiter=",")
        outputs[f"deg_{c}"], outputs[f"stat_{c}"] = dp, sp
        if result.deg2 is not None:
            d2p = outp("deg2", c)
            np.savetxt(str(d2p), result.deg2.channel(c), delimiter=",")
            outputs[f"deg2_{c}"] = d2p

    result.outputs = outputs
    if log:
        for p in outputs.values():
            log.io("out", Path(p).name)
        log.action(
            f"{seq}_{nn}_{rc} 出力"
            f" 平均1/劣化率 R={float(np.nanmean(deg['r'])):.3f}"
            f" G={float(np.nanmean(deg['g'])):.3f} B={float(np.nanmean(deg['b'])):.3f}")
    return outputs


# --------------------------------------------------------------------------- #
#  停止チェックポイント（仕様 7: Sequence が内包・実体は <output>/_stops/<dir>/）
# --------------------------------------------------------------------------- #
def _checkpoint_dir(folders: dict, sequence_name: str, nn, recipe_name: str) -> Path:
    return (Path(folders["output"]) / CHECKPOINT_ROOT
            / naming.stop_dir(sequence_name, nn, recipe_name))


def write_stop_checkpoint(
    *,
    result: RunResult,
    folders: dict,
    sequence_name: str,
    model: DegradationModel,
    model_param: dict,
    timestamp: "Optional[str]" = None,
    log=None,
) -> tuple:
    """停止時のチェックポイントを ``<output>/_stops/<dir>/`` に素のファイル名で書く。

    戻り値 ``(StopState, outputs)``。``outputs`` は ⑤結果タブがプレビュー／マップに
    使う ``{"movie"|"image", "deg_{c}", "stat_{c}", "deg2_{c}"}`` → :class:`pathlib.Path`。
    （deg2 は再開には使わない。再開後の最初のフレームでコアが計算し直す）
    既存の同一チェックポイントがあれば作り直す（常に最新1件）。
    """
    seq, nn, rc = sequence_name, result.nn, result.recipe_name
    ts = timestamp or naming.timestamp()
    ckpt = _checkpoint_dir(folders, seq, nn, rc)
    if ckpt.exists():
        shutil.rmtree(ckpt, ignore_errors=True)
    ckpt.mkdir(parents=True, exist_ok=True)

    outputs: dict = {}
    if result.is_movie:
        if result._tmp_video and Path(result._tmp_video).exists():
            dest = ckpt / _CKPT_MOVIE
            shutil.move(str(result._tmp_video), str(dest))
            outputs["movie"] = dest
    else:
        if result._img_bgr is not None:
            dest = ckpt / _CKPT_IMAGE
            imio.imwrite(dest, result._img_bgr)
            outputs["image"] = dest

    deg = model.deg_maps(result.state, result.temp_kelvin, model_param)
    for c in "rgb":
        dp, sp = ckpt / _CKPT_DEG[c], ckpt / _CKPT_STAT[c]
        np.savetxt(str(dp), deg[c], delimiter=",")
        np.savetxt(str(sp), result.state.channel(c), delimiter=",")
        outputs[f"deg_{c}"], outputs[f"stat_{c}"] = dp, sp
        if result.deg2 is not None:
            d2p = ckpt / _CKPT_DEG2[c]
            np.savetxt(str(d2p), result.deg2.channel(c), delimiter=",")
            outputs[f"deg2_{c}"] = d2p

    rel = f"{CHECKPOINT_ROOT}/{ckpt.name}"
    st = StopState(
        recipe_name=rc, frames_done=result.frames_absolute,
        frames_total=result.frames_total, aging_seconds=result.aging_seconds,
        is_movie=result.is_movie, timestamp=ts, dir=rel)
    result.outputs = outputs
    if log:
        log.action(f"{seq}_{nn}_{rc} 停止チェックポイント保存: {rel}/"
                   f"（フレーム {st.frames_done}/{st.frames_total}）")
    return st, outputs


def stop_checkpoint_outputs(folders: dict, st: StopState) -> dict:
    """``StopState.dir`` 配下の素ファイルを ⑤結果タブ用の outputs 辞書にする。"""
    base = Path(folders["output"]) / st.dir
    outputs: dict = {}
    for c in "rgb":
        outputs[f"deg_{c}"] = base / _CKPT_DEG[c]
        outputs[f"stat_{c}"] = base / _CKPT_STAT[c]
        if (base / _CKPT_DEG2[c]).exists():         # deg2 が無い（フェーズF より前の）停止にも対応
            outputs[f"deg2_{c}"] = base / _CKPT_DEG2[c]
    if st.is_movie and (base / _CKPT_MOVIE).exists():
        outputs["movie"] = base / _CKPT_MOVIE
    elif (base / _CKPT_IMAGE).exists():
        outputs["image"] = base / _CKPT_IMAGE
    return outputs


def build_resume_plan(folders: dict, st: StopState) -> tuple:
    """``StopState`` から :class:`ResumePlan` を作る。戻り値 ``(plan|None, err|None)``。"""
    base = Path(folders["output"]) / st.dir
    if not base.is_dir():
        return None, f"停止チェックポイントが見つかりません: {base}"
    try:
        state = StressState.load(*(base / _CKPT_STAT[c] for c in "rgb"))
    except (OSError, ValueError) as e:
        return None, f"停止チェックポイントの読み込みに失敗: {e}"
    video = base / _CKPT_MOVIE
    if not (st.is_movie and video.exists()):
        video = None
    return ResumePlan(state=state, frames_done=st.frames_done,
                      aging_seconds=st.aging_seconds, video=video), None


def remove_stop_checkpoint(folders: dict, st: StopState) -> bool:
    """再開完了時などにチェックポイント実体を消す（``Sequence.stops`` の掃除は呼び出し側）。

    戻り値: 消せた（または元から無い）なら True。Windows ではフォルダをエクスプローラーで
    開いているとファイルは消えてもフォルダが残るため、その場合は False（呼び出し側で警告し、
    残った空フォルダは :func:`cleanup_empty_stop_dirs` で後から消す）。
    """
    if not st.dir:
        return True
    base = Path(folders["output"]) / st.dir
    if base.is_dir():
        shutil.rmtree(base, ignore_errors=True)
    return not base.exists()


def cleanup_empty_stop_dirs(folders: dict) -> list:
    """``<output>/_stops/`` の下に残った**空の**フォルダを消す（中身のあるものは触らない）。

    再開完了時に消せなかった停止フォルダ（エクスプローラーで開いていた等）の後始末。
    ``_stops/`` 自体も空になれば消す。戻り値は消したフォルダ名のリスト。
    """
    root = Path(folders["output"]) / CHECKPOINT_ROOT
    removed: list = []
    if not root.is_dir():
        return removed
    for d in sorted(root.iterdir()):
        if d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
                removed.append(d.name)
            except OSError:
                pass
    try:
        if not any(root.iterdir()):
            root.rmdir()
    except OSError:
        pass
    return removed


def discard_recipe_outputs(result: RunResult) -> None:
    """停止して『保存しない』を選んだとき、一時ファイルを片付ける。"""
    if result._tmp_video and Path(result._tmp_video).exists():
        Path(result._tmp_video).unlink()


# --------------------------------------------------------------------------- #
#  シーケンス実行
# --------------------------------------------------------------------------- #
def _resolve_init_state(seq: Sequence, idx: int, recipe: Recipe, log) -> Optional[StressState]:
    if recipe.init_stress == "none":
        return None
    if recipe.init_stress == "prev":
        if idx == 0:
            raise EngineError("初期ストレス=前ステップ継承 だが前ステップが無い")
        out_dir = Path(seq.folders["output"])
        p_nn = seq.recipe_number(idx - 1)
        p_rc = seq.recipes[idx - 1].recipe_name
        paths = [out_dir / naming.output_name(seq.sequence_name, p_nn, p_rc, "stat", c)
                 for c in "rgb"]
        if log:
            log.action(f"ストレス継承: {paths[0].name} ほか")
        return StressState.load(*paths)
    if recipe.init_stress == "file":
        f = recipe.init_stress_files
        if not all(f.get(c) for c in "rgb"):
            raise EngineError("初期ストレス=ファイル指定 だが r/g/b の指定が不足")
        return StressState.load(f["r"], f["g"], f["b"])
    raise EngineError(f"未知の init_stress: {recipe.init_stress!r}")


def run_sequence(
    *,
    sequence: Sequence,
    model: DegradationModel,
    only_index: Optional[int] = None,   # 「実行するステップを選択」（単一）
    control: Optional[RunControl] = None,
    progress_cb: Optional[Callable] = None,   # (step_pos, step_n, frame_done, frame_total, preview)
    step_done_cb: Optional[Callable] = None,  # (RunResult)
    log=None,
    max_frames: Optional[int] = None,
    resume: Optional[ResumePlan] = None,      # 先頭ステップを停止位置から再開
) -> list:
    control = control or RunControl()
    indices = [only_index] if only_index is not None else list(range(len(sequence.recipes)))
    results: list = []
    cumulative = 0.0
    prev_idx: Optional[int] = None
    prev_state: Optional[StressState] = None
    for pos, idx in enumerate(indices):
        while control.paused and not control.stopped:
            time.sleep(0.05)
        if control.stopped:
            break
        recipe = sequence.recipes[idx]
        nn = sequence.recipe_number(idx)
        if log:
            log.action(f"ステップ {pos + 1}/{len(indices)} 開始: {sequence.sequence_name}_{nn}_{recipe.recipe_name}")
        rf, rv, ras = 0, None, 0.0
        if pos == 0 and resume is not None:
            init_state = resume.state
            rf, rv, ras = resume.frames_done, resume.video, resume.aging_seconds
            if log:
                log.action(f"停止位置から再開: フレーム {rf} / Aging {format_aging(ras)}")
        # "prev" は直前ステップの状態をメモリ直結（連続実行時）。単独実行時はディスクから。
        elif recipe.init_stress == "prev" and prev_state is not None and prev_idx == idx - 1:
            init_state = prev_state
            if log:
                log.action("ストレス継承: 直前ステップ（メモリ）")
        else:
            init_state = _resolve_init_state(sequence, idx, recipe, log)

        def _pcb(fd, ft, prev, _pos=pos):
            if progress_cb:
                progress_cb(_pos, len(indices), fd, ft, prev)

        res = run_recipe(
            recipe=recipe, folders=sequence.folders,
            sequence_name=sequence.sequence_name, nn=nn, model=model,
            initial_state=init_state, control=control,
            resume_from=rf, resume_video=rv, resume_aging_seconds=ras,
            progress_cb=_pcb, log=log, max_frames=max_frames,
            model_param=sequence.panel.model_param, sm_path=sequence.sm_path(idx),
        )
        # 累積 Aging 時間は「今のストレスの履歴」の時間。初期ストレスが前ステップ継承でなければ
        # （なし・ファイル指定）このステップから数え直す（2026-11-19。以前はシーケンスの最初からの合計だった）
        if recipe.init_stress != "prev":
            cumulative = 0.0
        cumulative += res.aging_seconds
        res.cumulative_aging_seconds = cumulative
        results.append(res)
        prev_idx, prev_state = idx, res.state
        if step_done_cb:
            step_done_cb(res)
        if res.stopped:
            break
    return results
