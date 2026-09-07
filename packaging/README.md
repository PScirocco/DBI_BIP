# BI-sim パッケージング（T9 / フェーズE）

IP設計者へ **EXE で配布**するための PyInstaller 一式。

> **ビルド手順は `docs/EXEビルド手順書.md` を参照。** ここは packaging/ 内ファイルの索引と
> 「何が同梱されるか」のリファレンス。

| ファイル | 内容 |
|---|---|
| `bisim.spec` | PyInstaller spec（**6.x 用**。onedir。同梱データ・除外モジュールを定義） |
| `bisim_launcher.py` | エントリスクリプト（`python -m bisim` 相当。`freeze_support`） |
| `build_exe.ps1` | ビルド補助（.venv + pyinstaller → `dist/BI-sim/` → zip） |

## クイックビルド

```powershell
# リポジトリ直下・社内ネットワーク接続時
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\python -m bisim.selftest      # 全 pass を確認
.\packaging\build_exe.ps1
# → dist\BI-sim\BI-sim.exe ＋ dist\BI-sim_YYMMDD.zip
```

## 同梱されるもの / されないもの

| 同梱する | 同梱しない |
|---|---|
| `source/main.py` `source/load_com_info.py`（劣化コア＝暫定モデル。モジュールとして取込） | `source/dbi_output/`（CLI の実行結果 96MB） |
| `source/dbi_conf/*.csv`（degparam_mm / simconf） | `source/dbi_common/input.*` `mov_001.mp4` `mov_ht_001.mp4`（原寸動画） |
| `source/dbi_input/bcsetting.csv` | `prototype/` `docs/` `.venv/` `build/` `dist/` |
| サンプル入力 `mov_001_480x270.mp4` / `mov_ht_001_480x270.mp4` / `eval_img*.png` | |
| `matplotlib` の mpl-data（フォント等） | WebEngine / QML / Qt3D / Multimedia / tkinter（`excludes`） |

- 実行時の既定フォルダ（①フォルダ設定）は同梱データ `_internal\source\...` を指す（読み取り専用）。
- **出力の既定は実行ファイル横の `bisim_output\`**（配布時のみ。`bisim/paths.py::_default_output`）。
- ログ `_log_BISim\` とアプリ設定 `bisim_app.json` も実行ファイル横に作られる。

## 既知の制限（フェーズE時点）

- アイコン未設定（`bisim.spec` の `icon=` を有効化すれば付く）
- 劣化コアは暫定モデル（`source/main.py`）。IP設計者の最終コア差し替えはフェーズF（T10）
- 実ビルド＋クリーンPC実機確認は未実施（社内NW接続環境で `docs/EXEビルド手順書.md` を実施）
- 大解像度・CPU並列・DBI/BIP補正・実機比較はスコープ外（`docs/GUI仕様.md` 8章）
