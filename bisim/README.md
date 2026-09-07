# bisim — 本番GUI

`prototype/`（UX検証・破棄予定）を置き換える本番実装。
仕様: `../docs/GUI仕様.md` ／ 実装計画: `../docs/実装計画.md`

## 状態

- **フェーズA（T1〜T3）実装済み**: データモデル（`model.py`）＋ 命名規則（`naming.py`）＋ パス（`paths.py`）
- **フェーズB（T4〜T5）実装済み**: 劣化エンジン（`engine.py`）＋ パラメータCSV I/O（`paramio.py`）＋ ログ（`logio.py`）＋ 画像I/O（`imio.py`）
- **フェーズC（T6〜T7）実装済み**: 本番GUI（`ui/`。PySide6、5タブ）。`python -m bisim` で起動
- **フェーズD（T8）実装済み**: 中断・停止・再開の状態遷移（仕様 7）。停止時に再開用サイドカー
  `..._resume_YYMMDD-HHMM.json`（`engine.StopState`）を出力。同一起動中は④タブの「停止位置から再開」、
  再起動後はメニュー「停止結果を読み込んで再開…」。再開時は部分動画を連結して連続動画を出力

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
| `model.py` | `Recipe` / `Sequence` / `AppConfig`（JSON, `ensure_ascii=False`） |
| `naming.py` | 入出力ファイル名の生成・分解、`sanitize_name` |
| `paramio.py` | model/sim パラメータ CSV の読み書き（CLI版 `degparam_mm.csv` / `simconf.csv` と互換） |
| `imio.py` | Unicode パス対応の画像 I/O（prototype から移植） |
| `engine.py` | `DegradationModel`（差し替え点）/ `MasterModel` / `StressState` / `RunControl` / `StopState`・`ResumePlan`（停止・再開）/ `run_recipe` / `run_sequence` / 出力の確定・破棄 |
| `logio.py` | `Logger`（`_log_BISim/` 日付ローテーション、容量上限、画面表示 listener） |
| `ui/` | 本番GUI。`theme.py`（明るいグレー基調）/ `i18n.py`（JP/EN・文言はレビュー反映）/ `widgets.py`（ImagePanel, MplCanvas）/ `main_window.py`（MainWindow＋SimWorker）/ `tabs/`（5タブ） |
| `__main__.py` | エントリ（`python -m bisim`＝GUI起動、`--info`＝データ層確認） |
| `selftest.py` | pytest 無しのテストランナー |
| `tests/` | `test_model` / `test_naming` / `test_paramio` / `test_engine` / `test_logio` / `test_ui`（headless） |
