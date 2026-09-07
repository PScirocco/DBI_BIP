"""劣化エンジン（T4）

- ``DegradationModel``  : 差し替え点（Protocol）。1フレーム更新 ＋ 劣化率マップ算出
- ``MasterModel``       : ``source/main.py`` の関数をラップした現行の暫定モデル
- ``StressState``       : 累積ストレス(stat_r/g/b) の保持・CSV load/save・shape検証
- ``RunControl``        : UIスレッドからの 中断・再開・停止
- ``run_recipe``        : 1レシピ（動画1本 or 静止画1枚）のフレームループ
- ``run_sequence``      : シーケンス全体（初期ストレスの解決・連鎖・Aging時間累積）
- ``write_recipe_outputs`` / ``discard_recipe_outputs`` : 出力の確定 / 破棄

``source/`` は無改変。Unicode パス対策は静止画=``imio``、動画=``cv2`` 直（VideoWriter は
ASCII一時ファイル→``shutil.move``）。
"""
from __future__ import annotations

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
from bisim.model import Recipe, Sequence
from bisim.paths import SOURCE_DIR


class EngineError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
#  累積ストレス状態
# --------------------------------------------------------------------------- #
@dataclass(eq=False)
class StressState:
    r: np.ndarray
    g: np.ndarray
    b: np.ndarray

    @property
    def shape(self) -> tuple:
        return self.r.shape          # (h, w)

    def channel(self, c: str) -> np.ndarray:
        return {"r": self.r, "g": self.g, "b": self.b}[c]

    @classmethod
    def zeros(cls, height: int, width: int) -> "StressState":
        return cls(*(np.zeros((height, width), dtype=float) for _ in range(3)))

    @classmethod
    def load(cls, path_r, path_g, path_b) -> "StressState":
        return cls(_load_csv_map(path_r), _load_csv_map(path_g), _load_csv_map(path_b))

    def save(self, path_r, path_g, path_b) -> None:
        np.savetxt(str(path_r), self.r, delimiter=",")
        np.savetxt(str(path_g), self.g, delimiter=",")
        np.savetxt(str(path_b), self.b, delimiter=",")

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
               state: StressState, model_param: dict, sim_param: dict) -> None:
        """img_bgr を劣化画像にインプレース更新し、state を dt ぶん進める。"""

    def deg_maps(self, state: StressState, temp_kelvin: np.ndarray,
                 model_param: dict) -> dict:
        """現在の state から劣化率マップ ``{"r":arr, "g":arr, "b":arr}`` を返す。"""


class MasterModel:
    """``source/main.py`` の ``temp_update_stat_and_burn_img`` をラップ（暫定モデル）。"""

    name = "master"

    def __init__(self) -> None:
        if str(SOURCE_DIR) not in sys.path:
            sys.path.insert(0, str(SOURCE_DIR))
        from main import temp_update_stat_and_burn_img  # noqa: E402  (source/)
        self._fn = temp_update_stat_and_burn_img

    def update(self, dt, img_bgr, ht_bgr, state, model_param, sim_param) -> None:
        mm = paramio.to_mm_dict(model_param)
        rc = self._fn(dt, img_bgr, ht_bgr, {}, mm,
                      simconf_dict=dict(sim_param),
                      stat_r=state.r, stat_g=state.g, stat_b=state.b)
        if rc != 0:
            raise EngineError("temp_update_stat_and_burn_img rtn=-1")

    def deg_maps(self, state, temp_kelvin, model_param) -> dict:
        mm = paramio.to_mm_dict(model_param)
        out = {}
        for c in "rgb":
            b0, a = mm[f"B0_{c}"], mm[f"A_{c}"]
            out[c] = np.exp(-1.0 * (state.channel(c) ** (b0 + a * temp_kelvin)))
        return out


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
    outputs: dict = field(default_factory=dict)
    cumulative_aging_seconds: float = 0.0
    _tmp_video: Optional[Path] = None
    _img_bgr: Optional[np.ndarray] = None


def format_aging(seconds: float) -> str:
    """加速込み Aging 時間の表示（既定は時間、48h 超は日も併記）。"""
    h = seconds / 3600.0
    if h >= 48:
        return f"{h / 24:.1f} day ({h:,.0f} h)"
    return f"{h:.2f} h"


# --------------------------------------------------------------------------- #
#  1レシピの実行
# --------------------------------------------------------------------------- #
def run_recipe(
    *,
    recipe: Recipe,
    folders: dict,
    sequence_name: str,
    nn: str,
    model: DegradationModel,
    initial_state: Optional[StressState] = None,
    resume_from: int = 0,
    max_frames: Optional[int] = None,
    control: Optional[RunControl] = None,
    progress_cb: Optional[Callable] = None,   # (done:int, total:int, preview_bgr|None)
    log=None,
) -> RunResult:
    control = control or RunControl()
    in_dir = Path(folders["input_image"])
    ht_dir = Path(folders["heatmap"])
    path_img = in_dir / recipe.input_image
    path_ht = ht_dir / recipe.heatmap
    if not path_img.exists():
        raise EngineError(f"入力画像が見つかりません: {path_img}")
    if not path_ht.exists():
        raise EngineError(f"ヒートマップが見つかりません: {path_ht}")

    sim = recipe.sim_param
    accel = float(sim["ACCEL_RATIO"])
    tmp_l_k = float(sim["TMP_L"]) + 273.0
    tmp_h_k = float(sim["TMP_H"]) + 273.0
    is_movie = path_img.suffix.lower() == ".mp4"
    if log:
        log.io("in", path_img.name)
        log.io("in", path_ht.name)

    # ---- 入力サイズ確定 ----
    if is_movie:
        cap = cv2.VideoCapture(str(path_img))
        cap_ht = cv2.VideoCapture(str(path_ht))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dt = 1.0 / fps
    else:
        img0 = imio.imread(path_img)
        ht0 = imio.imread(path_ht)
        if img0 is None or ht0 is None:
            raise EngineError(
                f"画像を読めません: {path_img if img0 is None else path_ht}")
        height, width = img0.shape[:2]
        fps, frames_total, dt = 0.0, 1, 0.0

    # ---- 初期ストレス ----
    if initial_state is None:
        state = StressState.zeros(height, width)
    else:
        state = initial_state
        state.require_shape(height, width)

    last_temp = np.full((height, width), tmp_l_k, dtype=float)
    aging_seconds = 0.0
    frames_done = 0
    stopped = False
    img_last = None
    tmp_video: Optional[Path] = None

    def _temp(ht):
        return (ht[:, :, 0] / 255.0) * (tmp_h_k - tmp_l_k) + tmp_l_k

    if is_movie:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        _fd, _tmp = tempfile.mkstemp(suffix=".mp4")            # ASCII パス
        os.close(_fd)                                          # mkstemp のハンドルを閉じる（Windowsでロック解除）
        tmp_video = Path(_tmp)
        writer = cv2.VideoWriter(str(tmp_video), fourcc, fps, (width, height))
        start = max(resume_from, 0)
        end = frames_total if max_frames is None else min(frames_total, start + max_frames)
        if start > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start)
            cap_ht.set(cv2.CAP_PROP_POS_FRAMES, start)
        try:
            for _i in range(start, end):
                while control.paused and not control.stopped:
                    time.sleep(0.05)
                if control.stopped:
                    stopped = True
                    break
                ok1, img = cap.read()
                ok2, ht = cap_ht.read()
                if not ok1 or not ok2:
                    break
                model.update(dt, img, ht, state, recipe.model_param, sim)
                last_temp = _temp(ht)
                writer.write(img)
                aging_seconds += dt * accel
                frames_done += 1
                img_last = img
                if progress_cb:
                    progress_cb(frames_done, end - start, img)
        finally:
            cap.release()
            cap_ht.release()
            writer.release()
    else:
        if control.stopped:
            stopped = True
        else:
            model.update(dt, img0, ht0, state, recipe.model_param, sim)
            last_temp = _temp(ht0)
            frames_done = 1
            img_last = img0
            if progress_cb:
                progress_cb(1, 1, img0)

    res = RunResult(
        recipe_name=recipe.recipe_name, nn=nn, is_movie=is_movie,
        size=(width, height), frames_total=frames_total, frames_done=frames_done,
        aging_seconds=aging_seconds, stopped=stopped, state=state, temp_kelvin=last_temp,
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
    stopped_at=None,        # datetime | "YYMMDD-HHMM"（停止保存時のみ）
    log=None,
) -> dict:
    out_dir = Path(folders["output"])
    out_dir.mkdir(parents=True, exist_ok=True)
    seq, nn, rc = sequence_name, result.nn, result.recipe_name

    def outp(kind, color=None, ext="csv"):
        return out_dir / naming.output_name(seq, nn, rc, kind, color, ext=ext,
                                            stopped_at=stopped_at)

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

    result.outputs = outputs
    if log:
        for p in outputs.values():
            log.io("out", Path(p).name)
        log.action(
            f"{seq}_{nn}_{rc} 出力"
            + (" [停止保存]" if stopped_at is not None else "")
            + f" 平均1/劣化率 R={float(np.nanmean(deg['r'])):.3f}"
            f" G={float(np.nanmean(deg['g'])):.3f} B={float(np.nanmean(deg['b'])):.3f}")
    return outputs


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
) -> list:
    control = control or RunControl()
    indices = [only_index] if only_index is not None else list(range(len(sequence.recipes)))
    results: list = []
    cumulative = 0.0
    prev_idx: Optional[int] = None
    prev_state: Optional[StressState] = None
    for pos, idx in enumerate(indices):
        if control.stopped:
            break
        recipe = sequence.recipes[idx]
        nn = sequence.recipe_number(idx)
        if log:
            log.action(f"ステップ {pos + 1}/{len(indices)} 開始: {sequence.sequence_name}_{nn}_{recipe.recipe_name}")
        # "prev" は直前ステップの状態をメモリ直結（連続実行時）。単独実行時はディスクから。
        if recipe.init_stress == "prev" and prev_state is not None and prev_idx == idx - 1:
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
            progress_cb=_pcb, log=log, max_frames=max_frames,
        )
        cumulative += res.aging_seconds
        res.cumulative_aging_seconds = cumulative
        results.append(res)
        prev_idx, prev_state = idx, res.state
        if step_done_cb:
            step_done_cb(res)
        if res.stopped:
            break
    return results
