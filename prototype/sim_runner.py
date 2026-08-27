""" 劣化シミュレーションの薄いランナー（プロトタイプ用）

    source/main.py の temp_update_stat_and_burn_img()（1フレーム処理）を import し、
    フレーム単位でコールバックしながらループを回す。
    - 進捗表示（frame j / M）を出すための最小構成
    - 前回のストレス状態（stat_*.csv）からの Aging 再開に対応
    - source/ 配下は無改変
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

import imio
from state import SOURCE_DIR

if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from main import temp_update_stat_and_burn_img  # noqa: E402  (source/main.py)

FILE_OUT_IMG = "out_img"
FILE_OUT_DEG = "deg"
FILE_OUT_STAT = "stat"


def _load_map(path) -> np.ndarray:
    arr = np.loadtxt(str(path), delimiter=",", dtype=float)
    # 末尾に空列（trailing comma）が入っていた場合の保険
    if arr.ndim == 2 and np.all(np.isnan(arr[:, -1])):
        arr = arr[:, :-1]
    return arr


def _mm_dict(model: dict) -> dict:
    d = {}
    for i, c in enumerate("rgb"):
        d[f"N_{c}"] = float(model["N"][i])
        d[f"K0_{c}"] = float(model["K0"][i])
        d[f"Q_{c}"] = float(model["Q"][i])
        d[f"B0_{c}"] = float(model["B0"][i])
        d[f"A_{c}"] = float(model["A"][i])
    return d


class StepResult:
    def __init__(self, idx, out_img, deg_paths, stat_paths, size, is_mov, means=None):
        self.idx = idx
        self.out_img = out_img
        self.deg_paths = deg_paths        # {"r":path,"g":..,"b":..}
        self.stat_paths = stat_paths
        self.size = size                  # (w, h)
        self.is_mov = is_mov
        self._means = means               # {"r":mean_deg,"g":..,"b":..} or None

    def get_means(self) -> dict:
        """ 平均劣化率。既存出力を読み込んだ場合はここで遅延計算する。 """
        if self._means is None:
            self._means = {}
            for c in "rgb":
                try:
                    self._means[c] = float(np.nanmean(
                        np.loadtxt(self.deg_paths[c], delimiter=",")))
                except OSError:
                    self._means[c] = float("nan")
        return self._means


def run_step(step, folders, idx, prev_idx=None,
             progress_cb=None, abort_cb=None, log_cb=None) -> StepResult:
    """ 1 ステップ（1 本の映像 or 1 枚の静止画）を処理する。

    progress_cb(frame_done:int, frame_total:int, bgr_frame|None)
    abort_cb() -> bool   True で中断
    log_cb(msg:str)
    """
    def log(m):
        if log_cb:
            log_cb(m)

    in_dir = Path(folders["input_image"])
    ht_dir = Path(folders["heatmap"])
    out_dir = Path(folders["output"])
    out_dir.mkdir(parents=True, exist_ok=True)

    path_img = in_dir / step.input_image
    path_ht = ht_dir / step.heatmap
    if not path_img.exists():
        raise FileNotFoundError(f"入力画像が見つかりません: {path_img}")
    if not path_ht.exists():
        raise FileNotFoundError(f"ヒートマップが見つかりません: {path_ht}")

    degparam_mm_dict = _mm_dict(step.model)
    simconf_dict = {k: float(v) for k, v in step.simconf.items()}
    bc_dict = {}  # 現行モデルは未使用

    TMP_L = simconf_dict["TMP_L"] + 273.0
    TMP_H = simconf_dict["TMP_H"] + 273.0

    is_mov = path_img.suffix.lower() == ".mp4"

    # ---- 入力サイズの確定 ----
    if is_mov:
        cap_img = cv2.VideoCapture(str(path_img))
        cap_ht = cv2.VideoCapture(str(path_ht))
        width = int(cap_img.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap_img.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap_img.get(cv2.CAP_PROP_FPS) or 30.0
        frame_num = int(cap_img.get(cv2.CAP_PROP_FRAME_COUNT))
        trsh = 1.0 / fps
    else:
        img0 = imio.imread(path_img)
        ht0 = imio.imread(path_ht)
        if img0 is None or ht0 is None:
            raise RuntimeError(f"画像を読めません: {path_img if img0 is None else path_ht}")
        height, width = img0.shape[:2]
        fps, frame_num, trsh = 0.0, 1, 0.0

    # ---- 初期ストレス（Aging 再開 or ゼロ） ----
    if step.init_stress == "prev":
        if prev_idx is None:
            raise ValueError("前ステップがありません（初期ストレス=前ステップ継承）")
        stat_r = _load_map(out_dir / f"{prev_idx}_{FILE_OUT_STAT}_r.csv")
        stat_g = _load_map(out_dir / f"{prev_idx}_{FILE_OUT_STAT}_g.csv")
        stat_b = _load_map(out_dir / f"{prev_idx}_{FILE_OUT_STAT}_b.csv")
        log(f"ストレス継承: step #{prev_idx} の stat_*.csv")
    elif step.init_stress == "file":
        stat_r = _load_map(step.stress_r)
        stat_g = _load_map(step.stress_g)
        stat_b = _load_map(step.stress_b)
        log("ストレス継承: 指定ファイル")
    else:
        stat_r = np.zeros((height, width), dtype=float)
        stat_g = np.zeros((height, width), dtype=float)
        stat_b = np.zeros((height, width), dtype=float)
        log("ストレス初期値: ゼロ")

    if stat_r.shape != (height, width):
        raise ValueError(
            f"継承ストレスのサイズ {stat_r.shape} が入力画像 {(height, width)} と一致しません")

    temp = np.full((height, width), TMP_L, dtype=float)

    # ---- フレームループ ----
    if is_mov:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out_img_path = out_dir / f"{idx}_{FILE_OUT_IMG}.mp4"
        writer = cv2.VideoWriter(str(out_img_path), fourcc, fps, (width, height))
        t0 = time.time()
        try:
            for i in range(frame_num):
                if abort_cb and abort_cb():
                    log(f"中断（{i}/{frame_num} フレームで停止）")
                    break
                ok1, img = cap_img.read()
                ok2, ht = cap_ht.read()
                if not ok1 or not ok2:
                    log(f"フレーム読み込み終了（{i}/{frame_num}）")
                    break
                rc = temp_update_stat_and_burn_img(
                    trsh, img, ht, bc_dict, degparam_mm_dict,
                    simconf_dict=simconf_dict,
                    stat_r=stat_r, stat_g=stat_g, stat_b=stat_b,
                )
                if rc != 0:
                    raise RuntimeError("劣化計算でエラー（temp_update_stat_and_burn_img rtn=-1）")
                temp[:] = (ht[:, :, 0] / 255) * (TMP_H - TMP_L) + TMP_L
                writer.write(img)
                if progress_cb:
                    progress_cb(i + 1, frame_num, img)
        finally:
            cap_img.release()
            cap_ht.release()
            writer.release()
        log(f"映像処理 {time.time() - t0:.1f}s")
    else:
        img, ht = img0, ht0
        rc = temp_update_stat_and_burn_img(
            trsh, img, ht, bc_dict, degparam_mm_dict,
            simconf_dict=simconf_dict,
            stat_r=stat_r, stat_g=stat_g, stat_b=stat_b,
        )
        if rc != 0:
            raise RuntimeError("劣化計算でエラー（temp_update_stat_and_burn_img rtn=-1）")
        temp[:] = (ht[:, :, 0] / 255) * (TMP_H - TMP_L) + TMP_L
        out_img_path = out_dir / f"{idx}_{FILE_OUT_IMG}.png"
        imio.imwrite(out_img_path, img)
        if progress_cb:
            progress_cb(1, 1, img)

    # ---- 劣化率マップ（source/main.py の else 分岐と同じ式） ----
    b0 = {c: degparam_mm_dict[f"B0_{c}"] for c in "rgb"}
    a = {c: degparam_mm_dict[f"A_{c}"] for c in "rgb"}
    deg = {
        "r": np.exp(-1.0 * (stat_r ** (b0["r"] + a["r"] * temp))),
        "g": np.exp(-1.0 * (stat_g ** (b0["g"] + a["g"] * temp))),
        "b": np.exp(-1.0 * (stat_b ** (b0["b"] + a["b"] * temp))),
    }
    stat = {"r": stat_r, "g": stat_g, "b": stat_b}

    deg_paths, stat_paths = {}, {}
    for c in "rgb":
        dp = out_dir / f"{idx}_{FILE_OUT_DEG}_{c}.csv"
        sp = out_dir / f"{idx}_{FILE_OUT_STAT}_{c}.csv"
        np.savetxt(str(dp), deg[c], delimiter=",")
        np.savetxt(str(sp), stat[c], delimiter=",")
        deg_paths[c], stat_paths[c] = str(dp), str(sp)

    means = {c: float(np.nanmean(deg[c])) for c in "rgb"}
    log(f"出力: {idx}_out_img / {idx}_deg_* / {idx}_stat_*  "
        f"(平均劣化率 R={means['r']:.3f} G={means['g']:.3f} B={means['b']:.3f})")

    return StepResult(idx, str(out_img_path), deg_paths, stat_paths,
                      (width, height), is_mov, means)
