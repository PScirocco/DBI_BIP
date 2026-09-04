# DBI_BIP — OLED焼き付き劣化シミュレータ

## このプロジェクトは何か

OLEDディスプレイの**焼き付き（Burn-in / Image Sticking）**の
- **補正 = DBI（De-Burn-In）**
- **防止 = BIP（Burn-In Prevention）**

を開発するための、**パネル劣化シミュレータ（Burn-in simulator）**。
`source/` はこのシミュレータの「概略ソフト（コンセプト説明用・暫定版）」。
コマンドライン実行のみ可能（`source/eval_exec.bat` に実行例）。

## 担当者（このリポジトリで作業する人）の役割

このシミュレータを **GUIベースで追加実装して完成させる**こと。
完成後、DBI/BIPの**IP設計の参考データ収集**に使う。
コード・資料はIPハード設計者から受領。担当者はディスプレイ／パネル開発は未経験。

**分担の目安**：劣化モデルの数式（`temp_update_stat_and_burn_img`）は暫定・未完成で
IPハード設計者の担当。担当者は GUI・ワークフロー・可視化・入出力管理を作る。
→ モデル計算部を**差し替え可能な形に分離**しておくこと。

## 資料

| ファイル | 内容 |
|---|---|
| `AMOLED_Image_sticking_prevention_compensation_v01.pptx`（2018, Matsui） | DBI補正アルゴリズムの理論。劣化モデルの根拠 |
| `Platform Concept for DBI & BIP development.pptx`（2026.07, Matsui & Isobe） | シミュレータ＋DBI/BIP評価プラットフォームの構想 |

## 現在の状況（2026-09）

- UX検証プロトタイプ（`prototype/`）は完成、**2026-09-03 に IP設計者レビュー実施済み**。
- 次フェーズ：レビュー結果を反映した**本番GUIの実装**。確定仕様は `docs/GUI仕様.md`。
  プロトタイプは破棄し、本番は作り直す。
- IP設計者のアルゴリズムコア着手は**10月初め**。統合 → 原理確認 → 社内試用 を経て10月末完成予定。
- 当面先/スコープ外：出力マップの画像フォーマット化＋専用ビューア、CPU並列（画像分割）、
  DBI/BIP補正実装、実機データ比較・モデル修正。
- 経緯・スケジュールは `docs/progress/`。

## GUI プロトタイプ（レビュー済み・破棄予定）

`prototype/` … PySide6、5タブ（フォルダ設定 / 実行ステップ / ステップ設定 / 実行 / 結果）。
起動時に `eval_exec.bat` 相当の4ステップと `dbi_output/` の既存結果を自動読み込み。
JP/EN 切替（`prototype/i18n.py`）、明るいグレー基調。
劣化計算は `source/` の `temp_update_stat_and_burn_img()` を import（`source/` 無改変）。詳細は `prototype/README.md`。

- 実行環境: リポジトリ直下に `.venv`（`prototype/requirements.txt`: PySide6/numpy/opencv-python/matplotlib）。
  社給PCの pip は社内ミラー固定のため、インストールは社内ネットワーク接続時に行う。
- Unicode パス注意: `cv2.imread/imwrite` は `C:\ユーザー\…` で PNG を扱えない。
  prototype は `prototype/imio.py` で回避。`source/main.py` の静止画ステップはこのパスでは失敗する。

## 詳細ドキュメント

- `docs/GUI仕様.md` — 本番GUIの確定仕様（Config構造・命名規則・タブ別仕様・状態遷移）。9月実装フェーズの基準
- `docs/progress/` — 進捗報告と IP設計者レビュー記録（`260903_*`）
- `docs/理解と方針.md` — コードと資料の対応、モデル式の解説、実装ステータス、GUI方針
- 図解（Artifact, 要ログイン）: https://claude.ai/code/artifact/1d4f42d1-9610-4952-b669-e83fc9571caf
  （時間×電流の履歴 / Δη₁・Δη₂の2成分分解 / Iref換算 / コード対応）
  ローカル保存: `2成分モデルとIref換算.mhtml`

## コードの要点

- エントリ: `source/main.py`（`temp_burn_in` が本体、`temp_update_stat_and_burn_img` が劣化モデル）
- 設定読み込み: `source/load_com_info.py`
- 補助: `mov_resize.py`（入力動画整形）, `tmp_htmap_mov_gen.py`（簡易ヒートマップ生成）, `eval_img_gen.py`（評価用画像生成）
- 入力: `dbi_common/`（映像・ヒートマップ）, `dbi_input/bcsetting.csv`, `dbi_conf/degparam_mm.csv`・`simconf.csv`
- 出力: `dbi_output/`（`{idx}_out_img.*`, `{idx}_deg_{r,g,b}.csv`, `{idx}_stat_{r,g,b}.csv`）

### 劣化モデル（暫定）

```
# ストレス累積（＝Iref換算ストレス時間 t_eq の積算）
stat += Δt · ACCEL_RATIO · lum**N / (K0 · exp(Q / temp))
# 劣化率（輝度残存率）＝ Δη₁ の基準カーブ
deg  = exp( -( stat ** (B0 + A·temp) ) )
```

画素ごと・RGB別に計算。`stat`=累積ストレス、`deg`=輝度残存率（大きいほど劣化少）。
`lum**N`=(I/Iref)ⁿ（信号レベル換算）, `K0`≈τ₀·Irefⁿ, `exp(Q/temp)`=温度依存(アレニウス),
`ACCEL_RATIO`=シミュレーション加速, β=`B0+A·temp`。
本番GUIの UI 表記は `deg`→「1/劣化率 / inverse degradation」、`stat`→「累積時間 / accumulated time」に変更
（ファイル名トークンは `deg` / `stat` 維持）。加速込みAging時間 = (フレーム数/fps)×`ACCEL_RATIO`。

## 環境メモ

- `source/.venv` はベースPythonが不在で壊れている。プロトタイプ用にリポジトリ直下の `.venv` を使用。
- OpenCVは画素並びが BGR。動画は (w,h)、静止画は (h,w) の順に注意。
- git 管理下（ブランチ master）。
