""" レビュー用のサンプルデータ投入（プロトタイプ）

    source/eval_exec.bat 相当の4ステップを登録し、
    source/dbi_output/ に残っている既存の実行結果を結果タブへ読み込む。
"""
from __future__ import annotations

from pathlib import Path

import cv2

import imio
from sim_runner import StepResult
from state import Step, load_model_csv, load_simconf_csv

# (名前キー, 入力画像, ヒートマップ, 初期ストレス)  ―― eval_exec.bat の並びに対応
SAMPLE_STEPS = [
    ("sample.s1", "mov_001_480x270.mp4", "mov_ht_001_480x270.mp4", "none"),
    ("sample.s2", "eval_img.png",        "eval_img_ht.png",        "prev"),
    ("sample.s3", "mov_001_480x270.mp4", "mov_ht_001_480x270.mp4", "prev"),
    ("sample.s4", "eval_img.png",        "eval_img_ht.png",        "prev"),
]


def sample_available(folders: dict) -> bool:
    d = Path(folders["input_image"])
    return (d / "mov_001_480x270.mp4").exists() and (d / "eval_img.png").exists()


def build_sample_steps(folders: dict) -> list[Step]:
    mcsv = Path(folders["model"]) / "degparam_mm.csv"
    scsv = Path(folders["simconf"]) / "simconf.csv"
    model = load_model_csv(mcsv) if mcsv.exists() else None
    simc = load_simconf_csv(scsv) if scsv.exists() else None

    steps: list[Step] = []
    for name_key, img, ht, init in SAMPLE_STEPS:
        s = Step(name_key=name_key, input_image=img, heatmap=ht, init_stress=init)
        if model:
            s.model = {k: list(v) for k, v in model.items()}
        if simc:
            s.simconf = dict(simc)
        steps.append(s)
    return steps


def load_existing_results(folders: dict, max_idx: int = 64) -> dict[int, StepResult]:
    out_dir = Path(folders["output"])
    results: dict[int, StepResult] = {}
    for idx in range(1, max_idx + 1):
        out_img = None
        for ext in (".mp4", ".png"):
            cand = out_dir / f"{idx}_out_img{ext}"
            if cand.exists():
                out_img = cand
                break
        if out_img is None:
            continue
        deg_paths = {c: str(out_dir / f"{idx}_deg_{c}.csv") for c in "rgb"}
        stat_paths = {c: str(out_dir / f"{idx}_stat_{c}.csv") for c in "rgb"}
        if not all(Path(p).exists() for p in deg_paths.values()):
            continue

        is_mov = out_img.suffix.lower() == ".mp4"
        try:
            if is_mov:
                cap = cv2.VideoCapture(str(out_img))
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
            else:
                im = imio.imread(out_img)
                h, w = im.shape[:2]
        except Exception:
            w = h = 0

        results[idx] = StepResult(idx, str(out_img), deg_paths, stat_paths,
                                  (w, h), is_mov, means=None)
    return results
