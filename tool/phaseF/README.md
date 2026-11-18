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
| `run_seq_headless.py` | `bisim2` `<seq.json>` `<出力フォルダ>` | シーケンスを画面なしで実行（GUI と同じ `run_sequence` → `write_recipe_outputs`）。出力先だけ差し替える。手順2の基準データ作成に使用。**今は旧コアの `engine.MasterModel` を使う**ので、新コア組み込み後はモデルのクラス名を合わせる |

## 2026-11-17 時点の結果

- `check_extract.py`：(a)(b) とも差 0（11 ケース）
- `check_deg2.py`：再現の差 0 階調
- `check_deg2_movie.py`：最終フレームとの差 0
- `check_resume.py`：stat・全フレーム画像とも差 0（DPK OFF／ON）
