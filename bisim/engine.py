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


_BURN_FN = None


def _load_burn_fn():
    """``source/main.py`` の ``temp_update_stat_and_burn_img`` を取得する。

    PyInstaller で固めた EXE でも確実に動くよう、まず ``SOURCE_DIR/main.py`` を
    **ファイルパスから直接ロード**する。``import main`` は他パッケージのトップレベル
    モジュール名と衝突しやすく、frozen 環境では frozen 用インポータが優先されて
    別の ``main`` を掴むことがあるため使わない。
    """
    global _BURN_FN
    if _BURN_FN is not None:
        return _BURN_FN

    src = str(SOURCE_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)          # main.py 内の `import load_com_info` 用

    main_py = SOURCE_DIR / "main.py"
    if main_py.is_file():
        import importlib.util
        modname = "bisim_master_source"
        spec = importlib.util.spec_from_file_location(modname, str(main_py))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[modname] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as e:  # noqa: BLE001
            raise EngineError(
                f"劣化コア {main_py} の読み込みに失敗: {type(e).__name__}: {e}") from e
        fn = getattr(mod, "temp_update_stat_and_burn_img", None)
        if fn is None:
            raise EngineError(f"{main_py} に temp_update_stat_and_burn_img が無い")
        _BURN_FN = fn
        return fn

    # フォールバック: モジュール検索（source/ が sys.path 上にある開発環境）
    import importlib
    try:
        m = importlib.import_module("main")
    except ImportError as e:
        raise EngineError(
            f"劣化コア main.py が見つかりません（SOURCE_DIR={SOURCE_DIR}）: {e}") from e
    fn = getattr(m, "temp_update_stat_and_burn_img", None)
    if fn is None:
        raise EngineError(
            f"import した main（{getattr(m, '__file__', '?')}）に "
            f"temp_update_stat_and_burn_img が無い（別モジュールを掴んでいる可能性）")
    _BURN_FN = fn
    return fn


class MasterModel:
    """``source/main.py`` の ``temp_update_stat_and_burn_img`` をラップ（暫定モデル）。"""

    name = "master"

    def __init__(self) -> None:
        self._fn = _load_burn_fn()

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
    resumed_from: int = 0          # 停止位置から再開したときの開始フレーム（絶対）
    _tmp_video: Optional[Path] = None
    _img_bgr: Optional[np.ndarray] = None

    @property
    def frames_absolute(self) -> int:
        """このレシピで累積処理済みの絶対フレーム数（再開分を含む）。"""
        return self.resumed_from + self.frames_done


# --------------------------------------------------------------------------- #
#  停止状態（後で読み込んで継続するためのサイドカー。仕様 7）
# --------------------------------------------------------------------------- #
@dataclass
class StopState:
    sequence_name: str
    nn: str
    recipe_name: str
    input_image: str
    heatmap: str
    is_movie: bool
    frames_done: int              # 停止までに処理した絶対フレーム数
    frames_total: int
    aging_seconds: float          # 停止までの加速込み Aging 時間
    timestamp: str                # YYMMDD-HHMM（保存名と一致）
    stat_files: dict = field(default_factory=dict)   # {"r":name,"g":..,"b":..}（出力フォルダ内）
    movie_file: str = ""          # 部分動画の出力名（あれば）

    def to_dict(self) -> dict:
        return {
            "sequence_name": self.sequence_name, "nn": self.nn,
            "recipe_name": self.recipe_name, "input_image": self.input_image,
            "heatmap": self.heatmap, "is_movie": self.is_movie,
            "frames_done": self.frames_done, "frames_total": self.frames_total,
            "aging_seconds": self.aging_seconds, "timestamp": self.timestamp,
            "stat_files": dict(self.stat_files), "movie_file": self.movie_file,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StopState":
        return cls(
            sequence_name=str(d.get("sequence_name", "")),
            nn=str(d.get("nn", "")),
            recipe_name=str(d.get("recipe_name", "")),
            input_image=str(d.get("input_image", "")),
            heatmap=str(d.get("heatmap", "")),
            is_movie=bool(d.get("is_movie", False)),
            frames_done=int(d.get("frames_done", 0)),
            frames_total=int(d.get("frames_total", 0)),
            aging_seconds=float(d.get("aging_seconds", 0.0)),
            timestamp=str(d.get("timestamp", "")),
            stat_files=dict(d.get("stat_files") or {}),
            movie_file=str(d.get("movie_file", "")),
        )

    def save(self, path) -> None:
        import json
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "StopState":
        import json
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(eq=False)
class ResumePlan:
    """停止結果からの再開に必要な情報（``run_sequence`` の先頭ステップに適用）。"""

    state: "StressState"
    frames_done: int
    aging_seconds: float = 0.0
    video: Optional[Path] = None      # 継続元の部分動画（連続出力のため先頭に連結）


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
    resume_video: Optional[Path] = None,      # 停止位置から再開時、先頭に連結する部分動画
    resume_aging_seconds: float = 0.0,        # 停止までの加速込み Aging 時間（積み増し）
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
    aging_seconds = float(resume_aging_seconds)
    frames_done = 0
    stopped = False
    img_last = None
    tmp_video: Optional[Path] = None
    start = max(resume_from, 0) if is_movie else 0

    def _temp(ht):
        return (ht[:, :, 0] / 255.0) * (tmp_h_k - tmp_l_k) + tmp_l_k

    if is_movie:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        _fd, _tmp = tempfile.mkstemp(suffix=".mp4")            # ASCII パス
        os.close(_fd)                                          # mkstemp のハンドルを閉じる（Windowsでロック解除）
        tmp_video = Path(_tmp)
        writer = cv2.VideoWriter(str(tmp_video), fourcc, fps, (width, height))
        end = frames_total if max_frames is None else min(frames_total, start + max_frames)
        if start > 0:
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
        resumed_from=start,
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
    recipe: "Optional[Recipe]" = None,   # 停止サイドカーに入力名を残すため（任意）
    log=None,
) -> dict:
    out_dir = Path(folders["output"])
    out_dir.mkdir(parents=True, exist_ok=True)
    seq, nn, rc = sequence_name, result.nn, result.recipe_name
    ts = None
    if stopped_at is not None:
        ts = stopped_at if isinstance(stopped_at, str) else naming.timestamp(stopped_at)

    def outp(kind, color=None, ext="csv"):
        return out_dir / naming.output_name(seq, nn, rc, kind, color, ext=ext,
                                            stopped_at=ts)

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

    # ---- 停止保存時: 再開用サイドカー（仕様 7）----
    if ts is not None:
        state_file = out_dir / naming.stop_state_name(seq, nn, rc, ts)
        StopState(
            sequence_name=seq, nn=nn, recipe_name=rc,
            input_image=(recipe.input_image if recipe else ""),
            heatmap=(recipe.heatmap if recipe else ""),
            is_movie=result.is_movie,
            frames_done=result.frames_absolute, frames_total=result.frames_total,
            aging_seconds=result.aging_seconds, timestamp=ts,
            stat_files={c: Path(outputs[f"stat_{c}"]).name for c in "rgb"},
            movie_file=(Path(outputs["movie"]).name if "movie" in outputs else ""),
        ).save(state_file)
        outputs["resume_state"] = state_file

    result.outputs = outputs
    if log:
        for p in outputs.values():
            log.io("out", Path(p).name)
        log.action(
            f"{seq}_{nn}_{rc} 出力"
            + (" [停止保存]" if ts is not None else "")
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
