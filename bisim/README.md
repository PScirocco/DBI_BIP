# bisim — 本番GUI

`prototype/`（UX検証・破棄予定）を置き換える本番実装。
仕様: `../docs/GUI仕様.md` ／ 実装計画: `../docs/実装計画.md`

## 状態

- **フェーズA（T1〜T3）実装済み**: データモデル（`model.py`）＋ ファイル命名規則（`naming.py`）＋ パス（`paths.py`）
- UI・エンジン・ログは未実装（フェーズB以降）

## セットアップ

```powershell
# リポジトリ直下
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r bisim/requirements.txt
```

## 実行・確認

```powershell
python -m bisim            # 現状: データ層の存在確認のみ
python -m bisim.selftest   # 全テスト（pytest 不要）
python -m pytest bisim/tests   # pytest がある場合
```

## モジュール

| ファイル | 内容 |
|---|---|
| `paths.py` | SOURCE_DIR / APP_DIR / LOG_DIR / 既定フォルダ6種 |
| `model.py` | `Recipe` / `Sequence` / `AppConfig`（JSON, `ensure_ascii=False`） |
| `naming.py` | 入出力ファイル名の生成・分解、`sanitize_name` |
| `__main__.py` | エントリ（フェーズCで UI 起動に差し替え） |
| `selftest.py` | pytest 無しのテストランナー |
| `tests/` | `test_model.py` / `test_naming.py` |
