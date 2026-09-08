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

## 現在の状況（2026-09-07）

- UX検証プロトタイプ（`prototype/`）は完成、**2026-09-03 に IP設計者レビュー実施済み**。
- レビュー結果を反映した**本番GUIを新パッケージ `bisim/` として実装中**（プロトタイプは参照用に残す）。
  確定仕様 `docs/GUI仕様.md`、実装手順 `docs/実装計画.md`（T1〜T10 を フェーズA〜F に区分）。
- **進捗：フェーズA〜E 実装済み・commit 済み。selftest 49/49。**
  A（T1〜T3 データモデル・命名規則）／ B（T4〜T5 エンジン・ログ）／ C（T6〜T7 UIシェル・5タブ）
  ／ D（T8 中断・停止・再開）／ E（T9 パッケージング：`installer/bisim.spec` ＋ `build_exe.ps1` ＋ `docs/EXEビルド手順書.md`。
  担当者が別PCで実ビルド・評価中。劣化コアは `_internal/source/main.py` を datas 同梱＋ファイルパスロード＝`engine._load_burn_fn`）。
  残：フェーズF（T10 IP設計者コア差し替え・結合試験・原理確認。10月初〜、コア受領後）。
- IP設計者のアルゴリズムコア着手は**10月初め**。統合 → 原理確認 → 社内試用 を経て10月末完成予定。
- 当面先/スコープ外：出力マップの画像フォーマット化＋専用ビューア、CPU並列（画像分割）、
  DBI/BIP補正実装、実機データ比較・モデル修正。
- 経緯・スケジュールは `docs/progress/`。

## 本番GUI `bisim/`（実装中）

| モジュール | 役割 | フェーズ |
|---|---|---|
| `paths.py` | SOURCE_DIR / APP_DIR / LOG_DIR / 既定フォルダ6種 | A |
| `model.py` | `Recipe` / `Sequence` / `AppConfig`（JSON, `ensure_ascii=False`、レシピ単体保存可） | A |
| `naming.py` | 入出力ファイル名の生成・分解、`sanitize_name`（`_`→`-`）、`stop_state_name`（`_resume_` サイドカー） | A/D |
| `paramio.py` | model/sim パラメータ CSV I/O（CLI版 `degparam_mm.csv` / `simconf.csv` と互換） | B |
| `imio.py` | Unicode パス対応の画像 I/O（prototype から移植） | B |
| `engine.py` | `DegradationModel`（差し替え点）/ `MasterModel`（`source/` ラップ）/ `StressState` / `RunControl` / `StopState`・`ResumePlan`（停止・再開）/ `run_recipe`（`resume_from`/`resume_video` で連続動画）/ `run_sequence` / 出力の確定・破棄 / `format_aging` | B/D |
| `logio.py` | `Logger`（`_log_BISim/` 日付ローテーション、容量上限、画面表示 listener） | B |
| `ui/` | `theme.py`（明るいグレー基調）/ `i18n.py`（JP/EN・文言レビュー反映）/ `widgets.py` / `main_window.py`（`MainWindow`＋`SimWorker`）/ `tabs/`（5タブ） | C/D |
| `installer/` | `bisim.spec`（PyInstaller 6.x・onedir）/ `bisim_launcher.py` / `build_exe.ps1` / `README.md`。手順は `docs/EXEビルド手順書.md` | E |

- 実行：`python -m bisim`（GUI 起動）／ `python -m bisim --info`（データ層＋エンジン確認）／ **テスト：`python -m bisim.selftest`（pytest 不要、46/46 pass。UI は `QT_QPA_PLATFORM=offscreen` 推奨）**
- 依存：`bisim/requirements.txt`（prototype と同じ ＋ pytest）
- ファイル命名規則：入力 `レシピ名_種別[_色].ext` ／ 出力 `シーケンス名_NN_レシピ名_種別[_色].ext`、停止保存は末尾 `_YYMMDD-HHMM` ＋ 再開用 `シーケンス名_NN_レシピ名_resume_YYMMDD-HHMM.json`。色トークンは `deg`/`stat` のみ
- 中断＝メモリ保持・出力なし・計算時間フリーズ。停止＝保存確認→日時付き出力＋`StopState` サイドカー。再開＝④タブのボタン（同一起動中）／メニュー「停止結果を読み込んで再開…」（再起動後）

## GUI プロトタイプ（レビュー済み・参照用）

`prototype/` … PySide6、5タブ。JP/EN 切替（`prototype/i18n.py`）、明るいグレー基調。
本番の UI レイアウトの下敷き。`i18n.py` / `widgets.py` / `apply_light_theme` は `bisim/ui/` に移植済み（文言はレビュー反映）。詳細は `prototype/README.md`。

- 実行環境: リポジトリ直下に `.venv`（`bisim/requirements.txt` = prototype と同内容 ＋ pytest）。
  社給PCの pip は社内ミラー固定のため、インストールは社内ネットワーク接続時に行う。
- Unicode パス注意: `cv2.imread/imwrite` は `C:\ユーザー\…` で PNG を扱えない。
  `prototype/imio.py` ／ `bisim/imio.py` で回避。動画I/Oは cv2 直で可（`bisim` は VideoWriter を ASCII 一時ファイル経由）。`source/main.py` の静止画ステップはこのパスでは失敗する。

## 詳細ドキュメント

- `docs/GUI仕様.md` — 本番GUIの確定仕様（Config構造・命名規則・タブ別仕様・状態遷移）。9月実装フェーズの基準
- `docs/実装計画.md` — 9月フェーズの実装タスク（T1〜T10、フェーズA〜Fに区分、この順で進める）。チェックボックスで進捗管理。フェーズ完了判定＝全チェック＋selftest 全pass＋commit
- `docs/EXEビルド手順書.md` — PyInstaller で EXE を作る手順（前提・ビルド・確認・トラブルシュート・onefile）
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

- `source/.venv` はベースPythonが不在で壊れている。`prototype/` `bisim/` ともリポジトリ直下の `.venv` を使用（Python 3.9）。
- OpenCVは画素並びが BGR。動画は (w,h)、静止画は (h,w) の順に注意。
- Python 3.9 のため各モジュール先頭で `from __future__ import annotations`（`str | None` 等を実行時に評価させない）。
- git 管理下（ブランチ master、remote `https://github.com/PScirocco/DBI_BIP`）。
- コミットは日本語メッセージ。末尾に `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`。
