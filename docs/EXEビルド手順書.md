# BI-sim EXE ビルド手順書（PyInstaller）

`bisim/` の本番GUIを、Python 環境の無いPCでも動く **EXE** にして配布するための手順。
フェーズE（T9）の成果物 `packaging/` を使う。IP設計者への配布・社内試用を想定。

- 対象: Windows 10 / 11（64bit）
- 所要時間: 初回 15〜30 分（依存DL含む）、2回目以降 3〜7 分
- 必要環境: **社内ネットワーク接続**（pip が社内ミラー固定のため）

---

## 0. TL;DR（慣れた人向け）

```powershell
# リポジトリ直下・社内ネットワーク接続
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\python -m bisim.selftest        # 49/49 pass を確認
.\packaging\build_exe.ps1
# → dist\BI-sim\BI-sim.exe  ＋  dist\BI-sim_YYMMDD.zip
```

生成された `dist\BI-sim\` を丸ごと zip で配布。受け取り側は展開して `BI-sim.exe` を実行するだけ。

---

## 1. 前提の確認

| 項目 | 確認方法 | 期待 |
|---|---|---|
| リポジトリ | `git status` | ブランチ `master`、作業ツリーがクリーン |
| Python | `py -0p` または `.\.venv\Scripts\python --version` | 3.9 系（リポジトリの `.venv` と同じ） |
| 仮想環境 | `Test-Path .\.venv\Scripts\python.exe` | `True` |
| 依存パッケージ | `.\.venv\Scripts\pip list` | PySide6 / numpy / opencv-python / matplotlib が入っている |
| ネットワーク | `pip config list` に社内ミラー、社内NW接続中 | pip install が通る |

`.venv` が無い場合:

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\pip install -r bisim\requirements.txt
```

---

## 2. PyInstaller の導入

```powershell
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\pyinstaller --version      # 6.x であること
```

> `bisim/requirements.txt` にも `pyinstaller>=6` を記載済み（ビルド時のみ必要）。
> `ERROR: Could not find a version that satisfies the requirement pyinstaller`
> が出たら社内ネットワーク未接続。VPN 等で接続してから再実行。

---

## 3. ビルド前チェック（必須）

```powershell
.\.venv\Scripts\python -m bisim.selftest
```

- **`49/49 passed`（または以降で増えた総数が全 pass）** を確認してから進む。
- 1件でも FAIL があるならビルドしない（原因を潰す）。

あわせて GUI が起動することも確認（任意）:

```powershell
.\.venv\Scripts\python -m bisim
```

---

## 4. ビルド実行

### 4-A. スクリプトで（推奨）

```powershell
.\packaging\build_exe.ps1
```

`build_exe.ps1` の動作:
1. `.venv` の存在確認
2. pyinstaller 未導入なら導入
3. `build\BI-sim` `dist\BI-sim` を消してクリーンビルド
4. `pyinstaller --noconfirm --clean packaging\bisim.spec` を実行
5. `dist\BI-sim` を `dist\BI-sim_YYMMDD.zip` に圧縮
6. フォルダ総サイズと配布 zip のパスを表示

### 4-B. 手動で（スクリプトを使わない場合）

```powershell
# 必ずリポジトリ直下で実行（spec が SPECPATH からリポジトリ位置を解決する）
Remove-Item -Recurse -Force build\BI-sim, dist\BI-sim -ErrorAction SilentlyContinue
.\.venv\Scripts\pyinstaller --noconfirm --clean packaging\bisim.spec
Compress-Archive -Path dist\BI-sim\* -DestinationPath ("dist\BI-sim_{0}.zip" -f (Get-Date -Format yyMMdd))
```

ビルドログの最後に `Building COLLECT ... completed successfully.` が出れば成功。
警告（`WARNING: ...`）は多少出るが、`ERROR` が無ければ基本OK。

---

## 5. 生成物の構成（onedir）

```
dist\BI-sim\
├─ BI-sim.exe                    ← これを実行
├─ _internal\                    ← 依存一式（PyInstaller 6.x）
│   ├─ PySide6\ ...
│   ├─ cv2\  (opencv_videoio_ffmpeg*.dll を含む)
│   ├─ numpy\ ...
│   ├─ matplotlib\ mpl-data\ ...
│   └─ source\                   ← 同梱データ
│       ├─ dbi_conf\  degparam_mm.csv / simconf.csv
│       ├─ dbi_input\ bcsetting.csv
│       └─ dbi_common\ mov_001_480x270.mp4 / mov_ht_001_480x270.mp4 / eval_img*.png
└─ （初回起動後に以下が自動生成）
    ├─ bisim_output\             ← シミュレーション出力の既定先
    ├─ _log_BISim\BISim_YYMMDD.log
    └─ bisim_app.json            ← 言語・ログ容量設定
```

- **`dist\BI-sim\` フォルダごと**配布する（`BI-sim.exe` 単体では動かない）。
- `劣化コア`（`source/main.py` / `load_com_info.py`）は `_internal` 内にモジュールとして取り込まれる。
- 大きい原寸動画（`input.*` / `mov_001.mp4`）と `dbi_output/`（CLI結果 96MB）は**同梱しない**。

### サイズ目安

| 形態 | フォルダ | zip |
|---|---|---|
| onedir（既定） | 約 200〜260 MB | 約 120〜150 MB |
| onefile（§9） | ― | 約 90〜130 MB（単一 .exe） |

---

## 6. ビルドしたPCでの動作確認

```powershell
& dist\BI-sim\BI-sim.exe
```

1. 5タブのウィンドウが開く
2. ②実行ステップ「追加」→ ③で入力画像「参照」→ `_internal\source\dbi_common\mov_001_480x270.mp4`、
   ヒートマップ → `mov_ht_001_480x270.mp4` →「この設定を適用」
3. ④実行「全ステップ実行」→ フレームが進み、劣化後プレビューが出る
4. 実行中に「中断」→「再開」→「停止」→ 保存ダイアログ「はい」
   → `dist\BI-sim\bisim_output\` に `*_deg_*.csv` `*_stat_*.csv` `*_movie.mp4` `*_resume_*.json`
5. 「▶↻ 停止位置から再開」→ 最後まで走り ⑤結果タブにマップ表示
6. `dist\BI-sim\_log_BISim\BISim_YYMMDD.log` にログが出ている

---

## 7. クリーンPCでの受け入れ確認

Python も開発ツールも無いPC（社内の別PC / まっさらな VM）で:

1. `BI-sim_YYMMDD.zip` を任意フォルダに展開（例 `C:\Tools\BI-sim\`）
   - できれば**半角パス**に置く（§8 の Unicode 注意）
2. `BI-sim.exe` 実行 → SmartScreen が出たら「詳細情報」→「実行」
3. §6 の 1〜6 を同様に実施
4. 一度終了 → 再度起動 → メニュー「停止結果を読み込んで再開…」で
   `bisim_output\*_resume_*.json` を選び、続きから再開できること
   （※現シーケンスにレシピ名が一致するステップが必要）

これが通れば配布可。

---

## 8. トラブルシューティング

### ビルドは通るが起動しない / すぐ落ちる

**まず詳細を出す。** `packaging\bisim.spec` を一時的に編集:

```python
exe = EXE(
    ...
    debug=True,        # ← 変更
    console=True,      # ← 変更（コンソールにエラーが出る）
    ...
)
```

再ビルドし、`cmd` から `dist\BI-sim\BI-sim.exe` を実行してトレースバックを読む。
原因を直したら `debug=False` / `console=False` に戻して本ビルド。

| トレースバック | 対処 |
|---|---|
| `ModuleNotFoundError: No module named 'xxx'` | `bisim.spec` の `hiddenimports` に `'xxx'` を追加して再ビルド |
| `No module named 'main'` / `'load_com_info'` | `pathex` に `str(SRC)` があるか確認（spec 済み）。`source/*.py` が実在するか |
| `Could not find the Qt platform plugin "windows"` | `excludes` を削りすぎ。`dist\BI-sim\_internal\PySide6\plugins\platforms\qwindows.dll` の有無を確認 |
| `matplotlib ... backend_qtagg` 関連 | `hiddenimports` に既に入れてある。無ければ追加、またはビルド時に `--collect-submodules matplotlib` |

### 実行時の DLL エラー

| 症状 | 対処 |
|---|---|
| `api-ms-win-crt-*.dll が見つかりません` / `VCRUNTIME140.dll` | 対象PCに **VC++ 再頒布可能パッケージ 2015-2022 (x64)** を入れる。配布に含めたい場合は下記 |
| 動画の書き出しが無音で失敗（`*_movie.mp4` が 0 バイト） | `dist\BI-sim\_internal\cv2\` に `opencv_videoio_ffmpeg*.dll` があるか確認。無ければ `bisim.spec` の `binaries` に明示追加 |

VC++ ランタイムを同梱したい場合、`bisim.spec` に追記:

```python
import ctypes.util
_rt = [ctypes.util.find_library(n) for n in ("vcruntime140", "vcruntime140_1", "msvcp140")]
binaries = [(p, ".") for p in _rt if p]
# Analysis(..., binaries=binaries, ...)
```

### セキュリティ製品にブロックされる

- SmartScreen: 「詳細情報」→「実行」。恒久対応は**コード署名**（社内CA/証明書）。
- 企業のウイルス対策: 検体提出 or 例外登録を情シスへ依頼。`upx=False`（設定済み）で誤検知は減る。

### ⑤結果のグラフが日本語で「□□□」（豆腐）

matplotlib のフォント。対象PCに **Yu Gothic / Meiryo**（Windows 標準）があれば解消。
無い環境向けにフォントを同梱する場合は `bisim.spec` の `datas` に `.ttf` を足し、
`bisim/ui/theme.py` の `font.family` にその名を追加。

### `temp_update_stat_and_burn_img rtn=-1`（実行時）

ビルドの問題ではない。入力画像とヒートマップの解像度不一致、または
初期ストレス CSV のサイズ不一致。③ステップ設定で入力を見直す。

### Unicode パス（`C:\ユーザー\...` / 日本語ユーザー名）

- GUI 内の画像・動画 I/O は `bisim/imio.py` と一時ファイル経由で対策済み。
- ただし **onefile 版**は起動時に `%TEMP%`（日本語ユーザー名だと日本語を含む）へ自己展開する。
  トラブルを避けるため配布は **onedir を半角パスに展開**して使うのが無難。

---

## 9. onefile（単一 .exe）で作りたい場合

`packaging\bisim.spec` を次のように変更:

```python
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,          # ← 追加
    a.datas,             # ← 追加
    [],
    name="BI-sim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
# COLLECT(...) ブロックを丸ごと削除、exclude_binaries=True の行も削除
```

- 生成物は `dist\BI-sim.exe` の1ファイル。
- 初回起動時に自己展開するため **初回だけ 5〜15 秒**待ちがある。
- 出力・ログは exe と同じフォルダに作られる（`app_dir()` は exe の場所を返す）。
- 単一ファイルが要件でなければ **onedir 推奨**（起動が速い・AV 誤検知が少ない・差分更新しやすい）。

---

## 10. 再ビルド・更新時

1. コードを更新して `git commit`
2. `python -m bisim.selftest` が全 pass
3. `.\packaging\build_exe.ps1`（`--clean` 込みなのでキャッシュ事故は起きにくい）
4. zip 名の日付が変わる。配布済みの版と区別できるよう、必要なら
   `bisim/__init__.py` の `__version__` を上げてから配布

`build/` `dist/` は `.gitignore` 済み。**生成物はコミットしない。**

---

## 11. 既知の制限（フェーズE時点）

- アプリアイコン未設定（`bisim.spec` の `icon=` を有効化し `packaging/bisim.ico` を置けば付く）
- 劣化コアは暫定モデル（`source/main.py`）。IP設計者の最終コア差し替えはフェーズF（T10）
- 実ビルド＋クリーンPC実機確認は、この手順書作成時点で**未実施**（社内NW接続環境で本手順を実施すること）
- 大解像度対応・CPU並列・DBI/BIP補正・実機比較はスコープ外（`docs/GUI仕様.md` 8章）

---

## 関連

- `packaging/bisim.spec` … PyInstaller 定義（同梱データ・除外モジュール）
- `packaging/bisim_launcher.py` … エントリ（`python -m bisim` 相当）
- `packaging/build_exe.ps1` … 本手順 §4-A のスクリプト
- `bisim/paths.py::_default_output` … frozen 時に出力先を exe 横 `bisim_output/` に切替
- `bisim/tests/test_packaging.py` … spec / launcher の静的チェック
