# BI-sim パッケージング（T9 / フェーズE）

IP設計者へ **EXE で配布**するための PyInstaller 一式。

| ファイル | 内容 |
|---|---|
| `bisim.spec` | PyInstaller spec（**6.x 用**。onedir。同梱データ・除外モジュールを定義） |
| `bisim_launcher.py` | エントリスクリプト（`python -m bisim` 相当） |
| `build_exe.ps1` | ビルド補助（.venv + pyinstaller → `dist/BI-sim/` → zip） |

---

## 1. ビルド手順（開発PC・社内ネットワーク接続時）

```powershell
# リポジトリ直下
py -3 -m venv .venv                              # 既にあれば不要
.\.venv\Scripts\pip install -r bisim\requirements.txt
.\.venv\Scripts\pip install pyinstaller          # ミラー経由

.\packaging\build_exe.ps1
```

生成物:
- `dist\BI-sim\BI-sim.exe` … 実行ファイル本体（フォルダごと配布）
- `dist\BI-sim_YYMMDD.zip` … 配布用 zip

`build/` `dist/` は `.gitignore` 済み（コミットしない）。

### サイズ目安

onedir フォルダで **約 200〜260 MB**（zip 圧縮後 120〜150 MB 前後）。
主因は cv2 / numpy / PySide6 / matplotlib。`bisim.spec` の `excludes` で
WebEngine・QML・Qt3D・Multimedia 等は除外済み。さらに削るなら:

- `opencv-python` → `opencv-python-headless`（サイズはほぼ同じだが不要な依存が減る）
- `bisim.spec` の `collect_data_files("matplotlib")` を絞る（フォントの間引き）

### onefile（単一 .exe）にしたい場合

`bisim.spec` 末尾のコメント参照。初回起動時に `%TEMP%` へ自己展開するため
**初回だけ 5〜15 秒**待ちが入る。単一ファイルが必須でなければ onedir 推奨。

---

## 2. 同梱されるもの / されないもの

| 同梱する | 同梱しない |
|---|---|
| `source/main.py` `source/load_com_info.py`（劣化コア＝暫定モデル） | `source/dbi_output/`（CLI の実行結果 96MB） |
| `source/dbi_conf/*.csv`（degparam_mm / simconf） | `source/dbi_common/input.*` `mov_001.mp4`（原寸動画） |
| `source/dbi_input/bcsetting.csv` | `prototype/` `docs/` `.venv/` |
| サンプル入力 `mov_001_480x270.mp4` / `mov_ht_001_480x270.mp4` / `eval_img*.png` | |

- 実行時の既定フォルダ（①フォルダ設定）は同梱データを指す（読み取り専用）。
- **出力の既定は実行ファイル横の `bisim_output\`**（配布時のみ。`bisim/paths.py::_default_output`）。
- ログ `_log_BISim\` とアプリ設定 `bisim_app.json` も実行ファイル横に作られる。

---

## 3. クリーンPC での起動確認手順

Python も Visual C++ ランタイムも無い PC を想定（社内の別PC / まっさらな VM）。

1. `BI-sim_YYMMDD.zip` を任意フォルダに展開（例 `C:\BI-sim\`）
2. `BI-sim.exe` をダブルクリック → **5タブのウィンドウが開く**こと
3. ①フォルダ設定: 6 フォルダのパスが同梱データを指していること（`...\_internal\source\...` 等）
4. ②実行ステップ「追加」→ ③ステップ設定:
   - 入力画像「参照」→ `...\source\dbi_common\mov_001_480x270.mp4`
   - ヒートマップ「参照」→ `mov_ht_001_480x270.mp4`
   - 「この設定を適用」
5. ④実行「全ステップ実行」→ フレームが進み、劣化後プレビューが表示される
6. 実行中に「中断」→「再開」→「停止」→ 保存ダイアログ **はい**
   → `bisim_output\` に `*_deg_*.csv` `*_stat_*.csv` `*_movie.mp4` `*_resume_*.json` ができる
7. 「▶↻ 停止位置から再開」→ 最後まで走って ⑤結果タブにマップが出る
8. 一旦終了 → 再度 `BI-sim.exe` 起動 → メニュー「停止結果を読み込んで再開…」で
   `bisim_output\*_resume_*.json` を選び継続できること（レシピ名が一致する必要あり）
9. `_log_BISim\BISim_YYMMDD.log` に動作ログが出ていること

### つまずきやすい点

| 症状 | 対処 |
|---|---|
| 起動時に「api-ms-win-crt-...dll が無い」 | 対象PCに VC++ 再頒布可能パッケージ（2015-2022 x64）を入れる。または spec で同梱 |
| SmartScreen / AV に止められる | 社内配布は署名 or 例外登録。`upx=False` は設定済み |
| ④実行で「temp_update_stat_and_burn_img rtn=-1」 | 入力とヒートマップのサイズ不一致、または初期ストレス CSV のサイズ不一致 |
| ⑤結果のマップが日本語で豆腐 | matplotlib の日本語フォント。対象PCに Yu Gothic / Meiryo があれば解消（Windows 標準で入っている） |

---

## 4. 既知の制限（フェーズE時点）

- アイコン未設定（`bisim.spec` の `icon=` を有効化すれば付く）
- 劣化コアは暫定モデル（`source/main.py`）。IP設計者の最終コア差し替えはフェーズF（T10）
- 大解像度・CPU並列・DBI/BIP補正・実機比較はスコープ外（`docs/GUI仕様.md` 8章）
