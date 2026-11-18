# tool/phaseF — フェーズF（新コアの組み込み）の確認用スクリプト

2026-11-12〜11-17 に、新コア（`receive/Burn_in_sim_core_01/`）の確認に使ったスクリプト。
手順6（結合試験）で再利用する。どれも `Burn-In_Simv2` 直下から `bisim2\.venv\Scripts\python -I tool\phaseF\<スクリプト> …` で実行する。

## 準備：コアの作業用コピー

`check_*.py` はコアのフォルダで `dbi_output/` に書き出すので、**受領物そのもの（`receive/`）では実行しない**。
作業用フォルダにコピーしてから使う（`<work>` は任意の一時フォルダ）。

```
mkdir <work>\core_new\dbi_output
copy receive\Burn_in_sim_core_01\main.py, load_com_info.py と dbi_common\ dbi_conf\ dbi_input\ を <work>\core_new\ へ
```

## スクリプト

| スクリプト | 引数 | 内容 |
|---|---|---|
| `check_extract.py` | `<work>\core_new` `receive\Burn_in_sim_core_01\dbi_output` `<python.exe のパス>` | `eval_exec_debug.bat` の 11 ケースを (a) `burn_in`（CLI）と (b) `burn_in_band_extract`＋`burn_in_core` で実行し、松井さんの `dbi_output` と比較。Band 抽出部分のログの一致も確認 |
| `check_deg2.py` | `<work>\core_new` `receive\Burn_in_sim_core_01\dbi_output` | 先に `check_extract.py` を実行しておく。入力画像 × deg × `deg2_*.csv` で出力画像を再現できるか（deg2 CSV が画像に使われた値か） |
| `check_deg2_movie.py` | `<work>\core_new` | 先に動画を CLI で idx=20 として実行しておく（`main.py mov_001_480x270.mp4 mov_ht_001_480x270.mp4 bcsetting.csv degparam_mm.csv degparam_sm.csv simconf_2000_aging.csv 0 0 0 0 0 20`）。`20_deg2_*.csv` が最終フレームの値かを確認 |
| `check_resume.py` | `<work>\core_new` `<work>` | 動画 40 フレームを一気に計算した結果と、17 フレームで止めて stat だけ CSV 保存→読み戻して再開した結果を比較 |
| `run_seq_headless.py` | `bisim2` `<seq.json>` `<出力フォルダ>` | シーケンスを画面なしで実行（GUI と同じ `run_sequence` → `write_recipe_outputs`）。出力先だけ差し替える。手順2の基準データ作成に使用（当時は旧コアの `engine.MasterModel`）。2026-11-18 から新コアの `engine.CoreModel` |
| `check_engine_cases.py` | `bisim2` `receive\Burn_in_sim_core_01` `<出力フォルダ>` | 11 ケースを bisim のエンジンで実行して松井さんの `dbi_output` と比較（stat・deg・画像）。deg2 の出力も確認 |
| `make_selftest_core_data.py` | `bisim2` `receive\Burn_in_sim_core_01` | selftest の基準データ `bisim2/bisim/tests/data/core01_case1-2.npz` を作る。松井さんのケース1→2（DPK_ON=0）の各象限から 8×8 を取り 16×16 に並べたもの（入力・stat・deg・出力画像は松井さんの出力、deg2 は bisim 側の deg2 出力）。`receive/` には書き込まない |
| `make_integ_seq.py` | `bisim2` `receive\Burn_in_sim_core_01` `"material\Core Part in simulator_brief confirmation result.pptx"` [`--cli-ref`] | 手順6 の準備。`bisim2/eval_test/phaseF_integ/` に入力・設定・松井さんの結果・スライドの結果画像をコピーし、シーケンス4本（`integ-cases`・`integ-cases-pq`・`integ-movie`・`integ-timing`）を作る。`--cli-ref` で動画を CLI でも実行して比べる相手を作る（一時フォルダで実行。約4分） |
| `check_integ.py` | `bisim2` `cases`／`pq`／`movie` [`<出力フォルダ>`] | 手順6 の比較。シーケンスの出力を松井さんの結果・スライドの画像（cases・pq）、CLI の結果（movie）と比べる。出力フォルダを省くとシーケンスの出力先。GUI・別PCで実行した結果も比べられる |

## 2026-11-17 時点の結果

- `check_extract.py`：(a)(b) とも差 0（11 ケース）
- `check_deg2.py`：再現の差 0 階調
- `check_deg2_movie.py`：最終フレームとの差 0
- `check_resume.py`：stat・全フレーム画像とも差 0（DPK OFF／ON）

## 2026-11-18（手順4）の結果

- bisim のエンジン（`run_recipe` → `write_recipe_outputs`）で 11 ケースを実行（テストステップは「Aging・静止画（fps=1）」）：stat・deg・出力画像とも差 0、deg2 の CSV も出力。
  スクリプトは `check_engine_cases.py`（引数 `bisim2` `receive\Burn_in_sim_core_01` `<出力フォルダ>`）。手順6 の結合試験でも使う

## 2026-11-18（手順6）の結果

- `integ-cases`（松井さんの 11 ケースを 12 ステップのシーケンスで）：stat・deg・出力画像・スライドの画像とも差 0、deg2 の CSV から出力画像の再現も差 0
- `integ-cases-pq`（参考）：出力画像は差 0、deg はテストの1秒ぶん違う（B で最大 0.07）
- `integ-movie`：stat・deg・deg2 とも CLI と差 0
- 計算時間：480×270 で1フレーム約 0.57 秒（CLI 単独と同程度）、1920×1080 で約 12 秒。詳細は `doc/progress/261117_フェーズF_進め方と決定事項.md` の「手順6 の結果」
