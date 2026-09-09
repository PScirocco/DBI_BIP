# bisim — 本番GUI

`prototype/`（UX検証・破棄予定）を置き換える本番実装。
仕様: `../docs/GUI仕様.md` ／ 実装計画: `../docs/実装計画.md`

## 状態

- **フェーズA（T1〜T3）実装済み**: データモデル（`model.py`）＋ 命名規則（`naming.py`）＋ パス（`paths.py`）
- **フェーズB（T4〜T5）実装済み**: 劣化エンジン（`engine.py`）＋ パラメータCSV I/O（`paramio.py`）＋ ログ（`logio.py`）＋ 画像I/O（`imio.py`）
- **フェーズC（T6〜T7）実装済み**: 本番GUI（`ui/`。PySide6、5タブ）。`python -m bisim` で起動
- **フェーズD（T8）実装済み**: 中断・停止・再開の状態遷移（仕様 7）。停止時は
  `<出力>/_stops/<シーケンス名_NN_レシピ名>/` にチェックポイント（素ファイル名・最新1件）を出力し、
  シーケンス JSON の `stops` に `model.StopState` を内包・自動保存（評価反映フェーズ2でサイドカーから移行）。
  同一起動中も再起動後（「シーケンスを開く」で復元）も④タブ「▶↻ 停止位置から再開」。
  再開時は部分動画を連結して連続動画を出力し、完了で `stops`／`_stops/` を掃除
- **フェーズE（T9）実装済み**: `installer/`（PyInstaller spec・ビルドスクリプト）。手順は `../docs/EXEビルド手順書.md`。
  実ビルドは社内ネットワーク接続時に `installer/build_exe.ps1`。frozen 時は既定出力が実行ファイル横 `bisim_output/`
- **評価反映（2026-09-09〜）**: `docs/progress/260907_評価チェックシート_checked.md` の指摘を
  `docs/progress/260909_評価反映_実装方針.md` の方針で反映。フェーズ1（Sim Param CSV I/O・
  フォルダ永続化）／フェーズ2（Stop を Sequence JSON の `stops` に内包＋`_stops/` チェックポイント）／
  フェーズ3（シーケンス名↔ファイル名）すべて実装済み

## セットアップ

```powershell
# リポジトリ直下
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r bisim/requirements.txt
```

## 実行・確認

```powershell
python -m bisim            # 本番GUI（5タブ）を起動
python -m bisim --info     # データ層＋エンジンの存在確認のみ（GUIなし）
python -m bisim.selftest   # 全テスト（pytest 不要。UIは QT_QPA_PLATFORM=offscreen 推奨）
python -m pytest bisim/tests   # pytest がある場合
```

## モジュール

| ファイル | 内容 |
|---|---|
| `paths.py` | SOURCE_DIR / APP_DIR / LOG_DIR / 既定フォルダ6種 |
| `model.py` | `Recipe` / `Sequence`（`stops` に停止状態を内包）/ `StopState` / `AppConfig`（JSON, `ensure_ascii=False`） |
| `naming.py` | 入出力ファイル名の生成・分解、`sanitize_name`、`stop_dir`（`_stops/` フォルダ名） |
| `paramio.py` | model/sim パラメータ CSV の読み書き（CLI版 `degparam_mm.csv` / `simconf.csv` と互換） |
| `imio.py` | Unicode パス対応の画像 I/O（prototype から移植） |
| `engine.py` | `DegradationModel`（差し替え点）/ `MasterModel` / `StressState` / `RunControl` / `ResumePlan`・`write_stop_checkpoint`・`build_resume_plan`・`remove_stop_checkpoint`（停止・再開。`StopState` は `model.py`）/ `run_recipe` / `run_sequence` / 出力の確定・破棄 |
| `logio.py` | `Logger`（`_log_BISim/` 日付ローテーション、容量上限、画面表示 listener） |
| `ui/` | 本番GUI。`theme.py`（明るいグレー基調）/ `i18n.py`（JP/EN・文言はレビュー反映）/ `widgets.py`（ImagePanel, MplCanvas）/ `main_window.py`（MainWindow＋SimWorker）/ `tabs/`（5タブ） |
| `__main__.py` | エントリ（`python -m bisim`＝GUI起動、`--info`＝データ層確認） |
| `selftest.py` | pytest 無しのテストランナー |
| `tests/` | `test_model` / `test_naming` / `test_paramio` / `test_engine` / `test_logio` / `test_ui`（headless）/ `test_packaging`（spec 静的チェック） |
