"""理論確認テスト：3色円の Aging → 白評価 の理論値を計算し、表にする（bisim の結果との比較も可）。

``tools/make_rgbcircle_test.py`` が作ったシーケンス（``rgbcircle.seq.json``）を読み、
各ステップのパラメータ（モデル・AGING_TIME・ACCEL_RATIO・固定温度）どおりに劣化モデルを
1フレームずつ計算する。劣化コア ``source/main.py`` は使わず、モデル式から独立に実装している:

    deg  = exp( -stat ** (B0 + A·T) )                       … 輝度残存率（そのフレーム開始時点）
    lum  = (画素値/255) ** 2.2 × deg                         … 劣化後の輝度（0〜1）
    stat += dt × ACCEL_RATIO × lum ** N / (K0 × exp(Q / T))  … 累積ストレス（劣化後の輝度で貯まる）
    評価画像 = floor( 255 × ((画素値/255) ** 2.2 × deg) ** (1/2.2) )

T は固定温度[℃]+273。Aging のフレーム数は bisim と同じ規則（AGING_TIME 到達で打切り、
不足なら動画を周回）。入力の画素値は MP4 から読み出した値を使う（MP4 は非可逆なので
理想の 0/255 から数階調ずれる。bisim が実際に見る値と揃えるため）。
比較用に、画素値が理想どおり 255 の場合の値（理想値）も表に載せる。

出力（既定 ``eval_test/rgbcircle/theory/``）:
  rgbcircle_theory_table.png   Aging時間ごとの 理論の評価画像・累積時間マップ R/G/B（--compare で bisim の評価画像も）
  rgbcircle_theory_values.md   数値表（理想値／領域ごとの値）
  rgbcircle_theory_values.csv  同上（CSV）
  rgbcircle_compare.md         --compare 時：bisim 出力との差（全ステップ）

使い方:
  python tools/rgbcircle_theory.py                 理論値だけ
  python tools/rgbcircle_theory.py --compare       bisim の出力フォルダ（シーケンスの output）と比較
  python tools/rgbcircle_theory.py --compare --bisim-out <フォルダ>   出力先を指定して比較
  python tools/rgbcircle_theory.py --seq <別PCからコピーしたフォルダ>/rgbcircle.seq.json --compare

  python tools/rgbcircle_theory.py --seq <bisim.exe のフォルダ>/eval_test/rgbcircle/rgbcircle.seq.json ^
        --app-dir <bisim.exe のフォルダ> --compare     別PCの EXE で実行した結果と比較

フォルダの決め方（tools/_seqpaths.py）: コマンドの指定 → シーケンスに書かれたパス（相対パスは
bisim.exe のフォルダ＝--app-dir が基準。既定はリポジトリ直下）→ それが無ければシーケンスファイルの横の input / output
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

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from bisim import naming  # noqa: E402  （出力ファイル名の規則だけ借りる）
sys.path.insert(0, str(REPO / "tools"))
from _seqpaths import APP_DIR_HELP, load_sequence, resolve_folder  # noqa: E402

COLORS = "rgb"
EVAL_TEMP_C = 25.0                               # bisim.engine.EVAL_TEMP_C と同じ（評価は温度設定なし）
BGR_INDEX = {"b": 0, "g": 1, "r": 2}
MODEL_INDEX = {"r": 0, "g": 1, "b": 2}           # model_param の並びは [R, G, B]
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


# --------------------------------------------------------------------------- #
#  モデル（source/main.py とは独立に、式から実装）
# --------------------------------------------------------------------------- #
@dataclass
class Params:
    N: dict
    K0: dict
    Q: dict
    B0: dict
    A: dict
    accel: float
    temp_k: float
    aging_time: float

    @classmethod
    def from_recipe(cls, rc: dict, is_aging: bool) -> "Params":
        # 評価ステップは温度設定なし（bisim は EVAL_TEMP_C 固定）。Aging は固定温度モードのみ対応
        if is_aging and rc.get("heatmap_mode") != "fixed":
            sys.exit(f"{rc['recipe_name']}: 固定温度モード（ヒートマップなし）のみ対応")
        mp, sp = rc["model_param"], rc["sim_param"]
        per = {k: {c: float(mp[k][MODEL_INDEX[c]]) for c in COLORS} for k in ("N", "K0", "Q", "B0", "A")}
        temp_c = float(rc["fixed_temp_c"]) if is_aging else EVAL_TEMP_C
        return cls(**per, accel=float(sp["ACCEL_RATIO"]),
                   temp_k=temp_c + 273.0,
                   aging_time=float(sp.get("AGING_TIME", 0.0)))

    def beta(self, c: str) -> float:
        return self.B0[c] + self.A[c] * self.temp_k

    def deg(self, c: str, stat: np.ndarray) -> np.ndarray:
        return np.exp(-1.0 * (stat ** self.beta(c)))

    def accumulate(self, c: str, stat: np.ndarray, lum: np.ndarray, dt: float) -> None:
        stat += dt * self.accel * (lum ** self.N[c]) / (self.K0[c] * np.exp(self.Q[c] / self.temp_k))


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
    is_aging: bool                # True=Aging ステップ / False=評価ステップ
    frames: int
    aging_seconds: float          # このステップの加速込み Aging 時間
    cum_seconds: float            # 累積
    stat: dict                    # c -> ndarray
    deg: dict                     # c -> ndarray（ステップ終了時点。bisim の deg CSV に相当）
    image: np.ndarray | None = None   # 評価ステップの劣化画像（BGR, uint8）
    ideal: dict = field(default_factory=dict)  # c -> (stat, deg, 評価値)：画素値=255 の理想値


def simulate(seq: dict, in_dir: Path) -> list:
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
            sys.exit(f"{nn}: 対応しているのは「Aging×動画」と「評価×静止画」だけです"
                     f"（{step_type}×{path.suffix}）")
        p = Params.from_recipe(rc, is_aging)
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
            lum0 = [{c: (f[:, :, BGR_INDEX[c]] / 255) ** 2.2 for c in COLORS} for f in frames]
            for k in range(n):
                L = lum0[k % len(frames)]          # 動画終端で先頭に戻って周回
                for c in COLORS:
                    lum = L[c] * p.deg(c, stat[c])
                    p.accumulate(c, stat[c], lum, dt)
                    # 理想値（画素値=255 → (255/255)^2.2 = 1）
                    d = math.exp(-1.0 * ideal[c] ** p.beta(c))
                    ideal[c] += dt * p.accel * (d ** p.N[c]) / (p.K0[c] * math.exp(p.Q[c] / p.temp_k))
            aging = n * dt_accel
            image = None
        else:
            n, aging = 1, 0.0                       # 静止画は Aging しない（dt=0）
            image = img0.copy()
            for c in COLORS:
                lum = (img0[:, :, BGR_INDEX[c]] / 255) ** 2.2 * p.deg(c, stat[c])
                image[:, :, BGR_INDEX[c]] = (255 * (lum ** (1 / 2.2))).astype(np.uint8)
        cum += aging
        degs = {c: p.deg(c, stat[c]) for c in COLORS}
        ideal_vals = {}
        for c in COLORS:
            d = math.exp(-1.0 * ideal[c] ** p.beta(c))
            ideal_vals[c] = (ideal[c], d, int(255 * d ** (1 / 2.2)))
        results.append(StepResult(nn, rc["recipe_name"], is_aging, n, aging, cum,
                                  {c: stat[c].copy() for c in COLORS}, degs, image, ideal_vals))
        print(f"  {nn} {rc['recipe_name']:<14} {'Aging' if is_movie else '評価 '}"
              f" {n:>5} フレーム  累積 {cum / 3600:8.2f} h")
    return results


# --------------------------------------------------------------------------- #
#  表（数値）
# --------------------------------------------------------------------------- #
def interior_masks(regions: np.ndarray) -> dict:
    """各領域の内側（縁から4画素以上内側。MP4 の縁のにじみを避ける）。"""
    k = np.ones((9, 9), np.uint8)
    return {rid: cv2.erode((regions == rid).astype(np.uint8), k).astype(bool) for rid in REGION_ORDER}


def write_values(evals: list, regions: np.ndarray, out_dir: Path) -> None:
    masks = interior_masks(regions)
    rows_ideal, rows_region = [], []
    for r in evals:
        hrs = r.cum_seconds / 3600
        row = {"累積Aging[h]": f"{hrs:g}"}
        for c in COLORS:
            s, d, v = r.ideal[c]
            row.update({f"stat_{c}": f"{s:.4f}", f"deg_{c}": f"{d:.4f}", f"評価値_{c}": str(v)})
        rows_ideal.append(row)
        for rid in REGION_ORDER:
            m = masks[rid]
            px = r.image[m]                       # (n, 3) BGR
            med = np.median(px, axis=0).astype(int)
            rng = [f"{px[:, i].min()}-{px[:, i].max()}" for i in (2, 1, 0)]
            rows_region.append({
                "累積Aging[h]": f"{hrs:g}", "領域": REGION_NAMES[rid],
                "評価画像R": str(med[2]), "評価画像G": str(med[1]), "評価画像B": str(med[0]),
                "範囲R": rng[0], "範囲G": rng[1], "範囲B": rng[2],
                "deg_r": f"{np.median(r.deg['r'][m]):.4f}", "deg_g": f"{np.median(r.deg['g'][m]):.4f}",
                "deg_b": f"{np.median(r.deg['b'][m]):.4f}",
                "stat_r": f"{np.median(r.stat['r'][m]):.4g}", "stat_g": f"{np.median(r.stat['g'][m]):.4g}",
                "stat_b": f"{np.median(r.stat['b'][m]):.4g}",
            })

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
        "# 3色円テスト 理論値",
        "",
        "## 理想値（その色が点灯している画素。画素値=255 として計算）",
        "",
        "stat=累積時間（累積ストレス）、deg=輝度残存率、評価値=白で評価したときの画素値 floor(255×deg^(1/2.2))。",
        "消灯している色は stat=0・deg=1・評価値=255（劣化なし）。",
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
    lines = ["# 3色円テスト bisim 出力との比較", "",
             f"bisim 出力フォルダ: `{bisim_out}`", "",
             "| NN | レシピ | 最大相対差 stat (R/G/B) | 最大差 deg (R/G/B) | 評価画像 最大差[階調] / 差のある画素数 | 判定 |",
             "|---|---|---|---|---|---|"]
    bisim_images: dict = {}
    all_ok = True
    for r in results:
        def op(kind, c=None, ext="csv"):
            return bisim_out / naming.output_name(name, r.nn, r.recipe_name, kind, c, ext=ext)
        if not op("stat", "r").exists():
            lines.append(f"| {r.nn} | {r.recipe_name} | （出力なし） | | | — |")
            all_ok = False
            continue
        rel, dd = [], []
        for c in COLORS:
            bs, bd = load_csv(op("stat", c)), load_csv(op("deg", c))
            rel.append(float(np.max(np.abs(bs - r.stat[c]) / (np.abs(r.stat[c]) + 1e-9))))
            dd.append(float(np.max(np.abs(bd - r.deg[c]))))
        ok = max(rel) < 1e-9 and max(dd) < 1e-9
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
                     f"{' / '.join(f'{x:.1e}' for x in dd)} | {img_cell} | {'OK' if ok else '**NG**'} |")
    lines += ["", f"**総合判定: {'OK（理論どおり）' if all_ok else 'NG あり'}**", "",
              "判定基準：stat の相対差・deg の差が 1e-9 未満、評価画像の差が 1 階調以内"
              "（浮動小数点の丸めで 8bit 化の切り捨てが1つずれることは許容）。"]
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
                ax.set_xlabel(f"deg R {iv['r'][1]:.3f}\nG {iv['g'][1]:.3f}  B {iv['b'][1]:.3f}", fontsize=8)
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
    fig.suptitle("3色円テスト：累積Aging時間ごとの理論値"
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
    ap.add_argument("--app-dir", type=Path, help=APP_DIR_HELP)
    a = ap.parse_args()

    seq, seq_path = load_sequence(a.seq)
    in_dir = resolve_folder(seq, seq_path, "input_image", "input", a.input_dir, a.app_dir)
    a.out = a.out or (seq_path.parent / "theory")
    a.out.mkdir(parents=True, exist_ok=True)
    print(f"シーケンス: {seq_path}")
    print(f"入力画像: {in_dir}")
    results = simulate(seq, in_dir)
    evals = [r for r in results if not r.is_aging]

    regions = read_png(in_dir / "rgbcircle-regions.png", cv2.IMREAD_GRAYSCALE)
    write_values(evals, regions, a.out)
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
