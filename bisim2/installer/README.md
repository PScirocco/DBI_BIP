# BI-sim パッケージング（T9 / フェーズE）  — `installer/`

IP設計者へ **EXE で配布**するための PyInstaller 一式。
（フォルダ名は `installer/`。PyPI の `packaging` ライブラリと名前が衝突しないため）

> **ビルド手順は `docs/EXEビルド手順書.md` を参照。** ここは `installer/` 内ファイルの索引と
> 「何が同梱されるか」のリファレンス。

| ファイル | 内容 |
|---|---|
| `bisim.spec` | PyInstaller spec（**6.x 用**。2026-11-25 から onefile＝1つの EXE。同梱データ・除外モジュールを定義） |
| `bisim_launcher.py` | エントリスクリプト（`python -m bisim` 相当。`freeze_support`） |
| `build_exe.ps1` | ビルド補助（.venv + pyinstaller → `dist/BI-sim/` → zip → インストーラ） |
| `setup_main.py` | インストーラの本体（2026-11-25）。画面（tkinter）・コピー・ショートカット・アンインストールの登録 |
| `setup.spec` | インストーラの PyInstaller spec（onefile。`dist/BI-sim_payload.zip` を中に持つ） |

## クイックビルド

```powershell
# リポジトリ直下・社内ネットワーク接続時
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\python -m bisim.selftest      # 全 pass を確認
.\installer\build_exe.ps1
# → dist\BI-sim\BI-sim.exe ＋ dist\BI-sim_YYMMDD.zip ＋ dist\BI-sim_setup_YYMMDD.exe（インストーラ）
```

## インストーラ（`BI-sim_setup_YYMMDD.exe`。2026-11-25）

- **1つの EXE を実行するだけでインストールできる**（インストールするPCに Python は要らない）
- インストール先の既定は `%LOCALAPPDATA%\Programs\BI-sim`（**管理者権限は不要**）。BI-sim はログ・設定・既定の出力を
  EXE と同じフォルダに書くので、書き込みのできるユーザーのフォルダに入れる（Program Files には入れない）
- 前のバージョンがあれば、プログラム（`BI-sim.exe`・`_internal`）だけ入れ替える。ログ・設定・出力（`_log_BISim`・
  `bisim_app.json`・`bisim_output`）やユーザーが置いたデータ（`eval_test` など）は残す
- スタートメニュー（BI-sim・BI-sim のアンインストール）とデスクトップ（任意）にショートカットを作る
- Windows の「インストールされているアプリ」に登録（HKCU）。アンインストールはインストール先の `uninstall.bat`
  （プログラム・ショートカット・登録を消し、ログ・設定・出力を消すかは聞く）
- 署名していないので、初回は SmartScreen の「Windows によって PC が保護されました」が出ることがある →「詳細情報」→「実行」
- 画面なしのテスト：`python installer\setup_main.py --silent --payload <zip> --dir <先> --startmenu-dir <dir> --desktop-dir <dir> --reg-name <名前>`

## 同梱されるもの / されないもの

| 同梱する | 同梱しない |
|---|---|
| `source/main.py` `source/load_com_info.py`（劣化コア＝新コア。**datas で `source/` に配置**（起動時に一時フォルダへ展開）し `engine._load_core` がファイルパスで直接ロード） | `source/dbi_output/`（CLI の実行結果 96MB） |
| `source/dbi_conf/*.csv`（パネル設定の標準ファイル：bcsetting / degparam_mm / degparam_sm） | `source/dbi_common/input.*` `mov_001.mp4` `mov_ht_001.mp4`（原寸動画） |
| `source/dbi_input/simconf.csv` | `prototype/` `docs/` `.venv/` `build/` `dist/` `source/old_core_261117/`（旧コア） |
| サンプル入力 `mov_001_480x270.mp4` / `mov_ht_001_480x270.mp4` / `eval_img*.png` | |
| `matplotlib` の mpl-data（フォント等） | WebEngine / QML / Qt3D / Multimedia / tkinter（`excludes`） |

- 実行時の既定フォルダ（①フォルダ設定）は同梱データ（起動時の展開先 `%TEMP%\_MEIxxxxxx\source\...`）を指す（読み取り専用。終了すると消える）。
- **出力の既定は実行ファイル横の `bisim_output\`**（配布時のみ。`bisim/paths.py::_default_output`）。
- ログ `_log_BISim\` とアプリ設定 `bisim_app.json` も実行ファイル横に作られる。

## 既知の制限（フェーズE時点）

- アイコン未設定（`bisim.spec` の `icon=` を有効化すれば付く）
- 劣化コアは 2026-11-18 から新コア（松井さん `Burn_in_sim_core_01`）。旧コアは `source/old_core_261117/`（同梱しない）
- 実ビルド＋クリーンPC実機確認は担当者が別PCで実施中（`docs/EXEビルド手順書.md` §7）
- 大解像度・CPU並列・DBI/BIP補正・実機比較はスコープ外（`docs/GUI仕様.md` 8章）
