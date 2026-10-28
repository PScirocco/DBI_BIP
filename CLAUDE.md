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

## 担当者（堀部さん）について

- **日本語でやり取りする**。ディスプレイ／パネル開発は**未経験**（コード・資料は IP設計者から受領し、理解が浅いと自認）。
  OLED・焼き付き・劣化モデルの説明は物理現象から噛み砕き、専門用語は都度定義し、数式には具体的な数値例を添える。図解が有効
- チームでの役割：劣化Simulator の全体I/F（GUI・ワークフロー）、補正なしで劣化を再現し画質評価までの流れ、画質評価ツール等の付随ツール
- **提案・相談と作業の開始を分ける**。「まだ始めないで」「素材を渡していない」段階では生成・実装に着手しない
  （2026-10-15、指示前に動画を生成して止められた）

## 資料

| ファイル | 内容 |
|---|---|
| `AMOLED_Image_sticking_prevention_compensation_v01.pptx`（2018, Matsui） | DBI補正アルゴリズムの理論。劣化モデルの根拠 |
| `Platform Concept for DBI & BIP development.pptx`（2026.07, Matsui & Isobe） | シミュレータ＋DBI/BIP評価プラットフォームの構想 |

## 現在の状況（2026-10-19）

- **2026-10-19 リポジトリを `C:\ユーザー\horibe\DBI_BIP` → `C:\Users\h84431495\LLM\DBI_BIP` に移動し、新セッションで再開**
  （`LLM\` は担当者の判断で追加）。移動後の作業と 10/15〜10/16 の作業内容は `docs/progress/261019_引き継ぎ資料.md`。
  `.venv` は旧パスのまま（`python.exe` は動くが `activate`・`pip.exe` は旧パス参照）。作り直しは未実施
- **2026-10-19 理論確認テスト（3色円）作成・確認済み**：`tools/make_rgbcircle_test.py`（入力・シーケンス生成）／
  `tools/rgbcircle_theory.py`（理論値計算・`--compare` で bisim 出力と比較）／`eval_test/rgbcircle/`（README に手順）。
  パネル横240×縦512、ACCEL_RATIO=3600（動画1周回=1h）、累積 0.5h〜50h の7段。エンジン経路で**全14ステップ理論値と完全一致**
- **2026-10-19 議事録 `docs/review/261015_progress-mtg_BI-sim_minutes.txt` の指摘1〜3に対応（実装済み・selftest 85/85）**：
  (1) **ステップ種別を手動選択**（`Recipe.step_type` = `aging`/`eval`。旧 JSON は拡張子から決定）。
  静止画 Aging は **fps=1**（1フレーム=1秒×ACCEL_RATIO）、PQ評価は動画・静止画ともストレスを貯めない（`dt=0`）。
  PQ評価は**温度設定なし**（内部 25℃固定＝`engine.EVAL_TEMP_C`。モデル変更までの暫定）で、③ではヒートマップ・Sim条件欄を隠す
  → 10/16 に見つけた「静止画は Aging しない」「評価ステップの温度不整合」はこれで解消。
  (2) **画像サイズ検査**：③で入力画像・ヒートマップを選んだ時点で、シーケンス内で最初に見つかる画像のサイズと比べ、違えば警告して選択させない（`engine.sequence_reference_size`）。
  (3) ③プレビューの文言「前回の Aging 結果」→「**前ステップの画像**」。
  指摘4（累積時間マップのスケーリング）は **2026-10-23 実装**：⑤累積時間マップに表示スケールの切替（「0〜面内最大」既定／「面内最小〜面内最大」）を追加（`results.py::_MapView`、累積時間マップのみ、表示のみ。selftest 93/93）。松井氏への意味の確認（Excel No.9）は継続。
  ついでに修正：④のライブ Aging 時間表示が1フレームを `ACCEL_RATIO÷総フレーム数` で計算していた → `ACCEL_RATIO÷fps` に
- **2026-10-21 別PC（EXE）で動作確認**（`docs/progress/261021B_動作確認チェックリスト.md`）：A・C〜H は OK。
  理論確認テストは別PCの EXE 出力でも理論値と完全一致（`eval_test_other-PC/`、こちらで `--compare`）。
  Excel の数式による検算ブック `eval_test/rgbcircle/理論値_Excel検算.xlsx`（`tools/rgbcircle_excel.py`）でも15桁一致。
  静止画 Aging の値（B-3〜B-5）がチェックシートの期待値と合わなかった件は、設定条件（温度など）の違いによるもので**問題なし**（担当者確認 2026-10-22）
- **2026-10-22 評価で見つかった不具合を修正（selftest 88/88）**：
  名前を付けて保存で元のシーケンスファイルが消える → 残す／③で参照…からファイルを選ぶと未適用の入力（初期ストレス等）が戻り
  前ステップの画像が消える → ②④の表示だけ更新し③は読み直さない／停止フォルダが開かれていて消せない場合 → ログ・ステータスで警告し
  空フォルダはシーケンスを開いたときに掃除（`engine.cleanup_empty_stop_dirs`）／④の計算時間・Aging時間が言語切替に追従しない → 追従／④で前ステップを実行した後に③へ切り替えても「前ステップの画像」が「未実行です」のまま → ③タブへの切替時に描き直す（selftest 90/90）
- **2026-10-22 別PCへフォルダごとコピーして使えるように**：シーケンス JSON の `folders` に相対パスを許可
  （`Sequence.load` がシーケンスファイルの場所を基準に絶対パスへ読み替え。書かれていない欄はそのPCの既定）。
  `tools/make_rgbcircle_test.py` は相対パス（`input`/`output`）で書く。`tools/rgbcircle_theory.py`・`rgbcircle_excel.py` は
  `tools/_seqpaths.py` でフォルダを決める（コマンド指定 → シーケンスのパス → 無ければシーケンスの横の `input`/`output`）。
  `rgbcircle_excel.py` は `--seq` で対象を指定（既定の出力先はシーケンスの横）
- **2026-10-22 シーケンスのフォルダに相対パスを許可（基準＝BI-sim.exe のフォルダ。開発時はリポジトリ直下＝`paths.APP_DIR`）**：
  `Sequence.load` で絶対パスへ読み替え（保存は絶対パス、書かれていない欄はそのPCの既定）。
  `tools/make_rgbcircle_test.py` は `eval_test/rgbcircle/input` 等の相対パスで書く。
  tools は `tools/_seqpaths.py` でフォルダを決める（コマンド指定 → シーケンスのパス（相対は `--app-dir`＝bisim.exe のフォルダ、
  既定リポジトリ直下）→ 無ければシーケンスの横の `input`/`output`）。結果の既定出力先はシーケンスの横。
  **実行条件（tools はリポジトリから実行・EXE は `<リポジトリ>\dist\BI-sim\`・ビルドで dist\BI-sim が消える等）は `tools/README.md`**
- **2026-10-22 状態遷移（イベント駆動の表示更新）の不具合を調査**：画面を表示なしで操作して7件を確認。
  入出力データが変わりうる2件だけ修正（selftest 92/92）：
  (F) 実行中（一時停止中を含む）は ①②③タブとファイル操作を使えなくする（`MainWindow._set_editing_locked`）、
  (C) 停止中のステップがあるときに②で削除・複製・並べ替えをすると確認し、続けるなら停止状態と `_stops/` を破棄（`MainWindow.confirm_steps_shift`）。
  **残り5件は保留（社内の開発者向けツールのため。入出力データが変わる重要なものだけ直す方針、担当者判断 2026-10-22）**：
  (E) 言語切替で③の未適用入力が消える／(B) ②で別ステップを選ぶと③の未適用入力が警告なしに捨てられる／
  (A) ①でフォルダを変えても③の入力プレビュー・④の動画情報が古いまま／(D) ③で Sim条件CSV を読むとレシピに即反映されるが④の表示が古いまま／
  ⑤の結果も NN で覚えているので、ステップの削除・並べ替え後は番号と中身がずれる（表示のみ）
- **2026-10-28 別PCで 10/22〜10/26 の変更（不具合修正・(F)(C)・相対パス・スケール切替）を確認、全項目OK**
  （`docs/progress/261028_動作確認チェックリスト.md`）→ commit・push 済み
- 2026-10-22 時点で `eval_test/`・`eval_test_other-PC/`・`schedule/`・`team/` は `.gitignore`（Git 管理外。PC 上にのみある）
- 未対応：**BC設定（bcsetting.csv）は bisim に未配線**（`bcset_dict={}`）。新BC仕様は「新しい入力種別の追加」になる
- 以下は 2026-10-15 時点の記述

- UX検証プロトタイプ（`prototype/`）は完成、**2026-09-03 に IP設計者レビュー実施済み**。
- レビュー結果を反映した**本番GUIを新パッケージ `bisim/` として実装中**（プロトタイプは参照用に残す）。
  確定仕様 `docs/GUI仕様.md`、実装手順 `docs/実装計画.md`（T1〜T10 を フェーズA〜F に区分）。
- **進捗：フェーズA〜E 実装済み・commit 済み。**
  A（T1〜T3 データモデル・命名規則）／ B（T4〜T5 エンジン・ログ）／ C（T6〜T7 UIシェル・5タブ）
  ／ D（T8 中断・停止・再開）／ E（T9 パッケージング：`installer/bisim.spec` ＋ `build_exe.ps1` ＋ `docs/EXEビルド手順書.md`）。
  劣化コアは `_internal/source/main.py` を datas 同梱＋ファイルパスロード＝`engine._load_burn_fn`。
- **担当者が別PC（EXE）で評価チェック完了**（`docs/progress/260907_評価チェックシート_checked.md`）。
  評価メモ5件を `docs/progress/260909_評価反映_実装方針.md` の方針で反映：**フェーズ1〜3 実装済み・commit 済み**。
  フェーズ1（Sim CSV I/O・フォルダ永続化）／ フェーズ3（シーケンス名↔ファイル名・名前の注意書き）＝commit 5a6d8c2、
  フェーズ2（Stop 情報を Sequence JSON の `stops` に内包＋`_stops/` チェックポイント。サイドカー廃止）＝selftest 56/56。
- **2026-09-10 EXE配布 → IP設計者2回目レビュー**（`docs/progress/260910_DBI&BIP_prog_mtg.txt`）。指摘3件＋保留1件：
  (1) ログのセッション分割 → **実装済み**（`logio.Logger`、1ファイルの大きさ感は従来の日次ログ相当を維持）、
  (2) ヒートマップなし＝パネル全面固定温度 → **実装済み**（`Recipe.heatmap_mode`/`fixed_temp_c`、③タブにチェックボックス＋数値入力）、
  (3) AGING_TIME を目標時間として機能させる（秒単位。超過で打切り／不足で動画を周回連結） → **実装済み 2026-09-14**
  （`Recipe.sim_param["AGING_TIME"]`。既定 `0`＝無制限＝従来どおり、正値で目標時間駆動に切替。詳細は `docs/progress/260910_評価反映2_実装方針.md`）、
  【保留】パネル表示周波数対応 → 対応不要（着手しない）。selftest 69/69。
- **2026-10-05 IP設計者レビュー3**（`docs/progress/261013_IP設計者レビュー3_実装方針.md`）。変更5〜7 **実装済み 2026-10-13**：
  (5) `deg` の UI 表記を「輝度残存率 / Lum. residual」に変更、(6) 累積時間マップを明暗反転（暗＝累積大）、
  (7) ⑤プレビューのフレームスライダに Aging 時間を併記（`RunResult.dt_accel` → `ResultEntry`）。
  変更8（ブロック分割統計＋ヒストグラム）は別スコープ・仕様確認待ち。
- **2026-10-13 別PCで初回ビルド・起動成功 → 2026-10-14 実機EXEで評価チェック実施**
  （`docs/progress/261014B_動作確認チェックリスト.md`。現在は**全項目OK**）。この評価で見つかった3点に対応済み：
  - 累積時間マップのRGB合成が色ごとに正規化されておらず反転が見えにくい → **R/G/Bを各色独自の最大値で正規化**する方式に変更（`results.py::_MapView`）
  - Aging時間表示が時間の小数（`0.00 h`）で小さい値が見えない → **`format_aging()` を時:分:秒表示**に変更（`00h 00m 10s`、24h超は日数も付記）。④・⑤・停止再開ダイアログ等すべてに反映
  - **AGING_TIMEを変えても結果が同じに見える**（担当者が実機ログ`eval_test/BISim_*.log`で報告）→ 原因判明：既定 ACCEL_RATIO=30000 では1フレーム＝約1000秒になり、小さいAGING_TIME（例 10秒・20秒）はどちらも「最低1フレームは処理する」ルールに丸められ区別できない。**バグではなく仕様上の粒度の制約**。④実行タブに選択ステップの動画情報（フレーム数・fps・1周回のAging時間・AGING_TIMEの判定＋見積りフレーム数）を表示する機能を追加して解消（`engine.movie_meta` / `engine.aging_time_add_frames`）
  - 評価メモの他2件：「結果リセット」専用ボタンは**保留**（要望として記録のみ）、Initial Stress="none"で0スタートになることは確認済み回答
  - selftest **74/74**
- 2026-10-15 時点の対外共有ドキュメント：`docs/review/劣化Sim_ツール評価結果_261013.xlsx`（レビュー3への回答＋9月末/10月の変更一覧をコメント列・追加行で記載）、
  `docs/progress/261014B_動作確認チェックリスト.md`（評価結果・全項目OK）、`docs/progress/2026-10-15_進捗報告04_presen.md`。
  いずれも `team/Meeting/20261015/horibe/` にPDF/xlsxで配置済み。
- 残：フェーズF（T10 IP設計者コア差し替え・結合試験・原理確認）。
- **`team/Meeting/` に DBI&BIP チームの共有資料あり**（日付→メンバー名のフォルダ構成）。
  松井氏＝DBIモデル／理論・劣化Simulatorコア担当、礒部氏＝BIP実機検証・Heat Map物理モデル担当。
  2026-10-15時点で把握した、フェーズF着手時に影響しうる点：
  - 劣化モデルの温度依存の入れ方を変更予定（β側ではなくストレス累積側に温度依存を入れる。
    `team/Meeting/20261008/matsui/Proposals for DBI model_v.0.0.0_261002.pptx`）
  - 入力CSVの仕様変更の可能性：`bcsetting.csv` に `ABL_LIMIT` 追加・15Band分のVI-LUT＋Duty化、
    `simconf.csv` に `PEAK_L`（DBVではなくPeak輝度で設定）追加
    （`team/Meeting/20261015/matsui/劣化Simulator_CorePart進捗.pptx`）
  - 礒部氏がHeat Mapの物理予測モデル（画像content→温度分布、簡易モデルrev2）を開発中。
    将来的にbisimのヒートマップ入力の自動生成元になり得る
  - BIP開発はPhase2で劣化Simulator（bisim）を使った効果検証を計画（Phase1のHW実機検証が現在進行中）
  - 目標Aging時間の実例は500h/1000h規模（AGING_TIME機能の実用レンジ感の参考）
- IP設計者のアルゴリズムコア着手は当初**10月初め**予定だったが、10/8MTG時点では
  「10月中にコアモデル作成・実装」に（やや後ろ倒し）。コア部分以外はGUI評価フィードバック対応を優先、
  本格運用はモデルパラメータ準備後（年内は困難）の見込み。
- **寿命評価装置（劣化実測用）の制御**は bisim とは別テーマとして `C:\Users\h84431495\control_sys\` で扱う（2026-10-16 分離）。
  **このリポジトリでは扱わない**。
- チーム全体のマイルストン（ゴール＝2027-03 の DBI/BIP アルゴ仕様＋Cモデル）と理論モデル変更の bisim への影響は
  `docs/progress/261015_全体スケジュール_マイルストン整理.md`。
- 当面先/スコープ外：出力マップの画像フォーマット化＋専用ビューア、CPU並列（画像分割）、
  DBI/BIP補正実装、実機データ比較・モデル修正。
- 経緯・スケジュールは `docs/progress/`、チーム全体の経緯は `team/Meeting/`。

## 本番GUI `bisim/`（実装中）

| モジュール | 役割 | フェーズ |
|---|---|---|
| `paths.py` | SOURCE_DIR / APP_DIR / LOG_DIR / 既定フォルダ6種 | A |
| `model.py` | `Recipe`（`step_type`＝`aging`/`eval` を手動選択・未指定/旧JSONは拡張子から。`heatmap_mode`/`fixed_temp_c` でヒートマップなし＝固定温度に対応） / `Sequence`（`stops` に停止状態を内包） / `StopState` / `AppConfig`（JSON, `ensure_ascii=False`、レシピ単体保存可） | A/D |
| `naming.py` | 入出力ファイル名の生成・分解、`sanitize_name`（`_`→`-`）、`stop_dir`（`_stops/` チェックポイントのフォルダ名） | A/D |
| `paramio.py` | model/sim パラメータ CSV I/O（CLI版 `degparam_mm.csv` / `simconf.csv` と互換） | B |
| `imio.py` | Unicode パス対応の画像 I/O（prototype から移植） | B |
| `engine.py` | `run_recipe` は種別で分岐（Aging×動画／Aging×静止画＝`STILL_AGING_FPS`=1／PQ評価＝`dt=0`・`EVAL_TEMP_C`=25℃固定）/ `media_size`・`sequence_reference_size`（③の画像サイズ検査）/ `DegradationModel`（差し替え点）/ `MasterModel`（`source/` ラップ）/ `StressState` / `RunControl` / `ResumePlan`・`write_stop_checkpoint`・`build_resume_plan`・`remove_stop_checkpoint`（停止・再開。`StopState` は `model.py`）/ `run_recipe`（`resume_from`/`resume_video` で連続動画。`heatmap_mode="fixed"` 時は `source/` 無改変のまま `TMP_L=TMP_H=fixed_temp_c` を渡してヒートマップ不要に。`AGING_TIME`>0 で目標時間駆動＝超過打切り／不足なら動画を周回連結、`resume_from` が周回をまたぐ場合は `% frames_total` でシーク、見積りは `aging_time_add_frames()` に共通化）/ `run_sequence` / 出力の確定・破棄 / `format_aging`（時:分:秒表示）/ `movie_meta`（fps・総フレーム数） | B/D |
| `logio.py` | `Logger`（`_log_BISim/` セッションローテーション＝起動ごとに新ファイル。容量超過時は同一セッション内でも新パートへ、総容量上限、画面表示 listener） | B |
| `ui/` | `theme.py`（明るいグレー基調）/ `i18n.py`（JP/EN・文言レビュー反映）/ `widgets.py` / `main_window.py`（`MainWindow`＋`SimWorker`）/ `tabs/`（5タブ。`step_config.py`③にステップ種別の選択＋PQ評価時はヒートマップ・Sim条件欄を隠す＋ファイル選択時の画像サイズ検査、`run.py`④に選択ステップの動画情報＋AGING_TIME判定ラベル、`results.py`⑤の累積時間マップはR/G/B各色独自の最大値で正規化） | C/D |
| `installer/` | `bisim.spec`（PyInstaller 6.x・onedir）/ `bisim_launcher.py` / `build_exe.ps1` / `README.md`。手順は `docs/EXEビルド手順書.md` | E |

- 実行：`python -m bisim`（GUI 起動）／ `python -m bisim --info`（データ層＋エンジン確認）／ **テスト：`python -m bisim.selftest`（pytest 不要、テストモジュールごとに別プロセス。`test_ui` は `QT_QPA_PLATFORM=offscreen` 推奨。個別は `python -m bisim.selftest test_engine`）**
- 依存：`bisim/requirements.txt`（prototype と同じ ＋ pytest）
- ファイル命名規則：入力 `レシピ名_種別[_色].ext` ／ 出力 `シーケンス名_NN_レシピ名_種別[_色].ext`。色トークンは `deg`/`stat` のみ。
  停止チェックポイントは `<出力>/_stops/<シーケンス名_NN_レシピ名>/` に素ファイル名（`stat_{c}.csv` / `deg_{c}.csv` / `movie.mp4`、日時なし・最新1件）
- 中断＝メモリ保持・出力なし・計算時間フリーズ。停止＝保存確認→`_stops/` チェックポイント＋シーケンス JSON の `stops["NN"]`（`model.StopState`）に内包・自動保存。
  再開＝④タブ「▶↻ 停止位置から再開」（同一起動中も、再起動後「シーケンスを開く」で `stops` 復元後も同じボタン）。再開が通常完了したら `stops` エントリと `_stops/` を掃除

## GUI プロトタイプ（レビュー済み・参照用）

`prototype/` … PySide6、5タブ。JP/EN 切替（`prototype/i18n.py`）、明るいグレー基調。
本番の UI レイアウトの下敷き。`i18n.py` / `widgets.py` / `apply_light_theme` は `bisim/ui/` に移植済み（文言はレビュー反映）。詳細は `prototype/README.md`。

- 実行環境: リポジトリ直下に `.venv`（`bisim/requirements.txt` = prototype と同内容 ＋ pytest）。
  社給PCの pip は社内ミラー固定のため、インストールは社内ネットワーク接続時に行う。
- Unicode パス注意（日本語を含むパスの場合。旧パス `C:\ユーザー\…` で発生。2026-10-19 以降の `C:\Users\h84431495\LLM\DBI_BIP` では起きない見込み・要確認）: `cv2.imread/imwrite` は日本語パスで PNG を扱えない。
  `prototype/imio.py` ／ `bisim/imio.py` で回避。動画I/Oは cv2 直で可（`bisim` は VideoWriter を ASCII 一時ファイル経由）。`source/main.py` の静止画ステップはこのパスでは失敗する。

## 詳細ドキュメント

- `docs/GUI仕様.md` — 本番GUIの確定仕様（Config構造・命名規則・タブ別仕様・状態遷移）。9月実装フェーズの基準
- `docs/実装計画.md` — 9月フェーズの実装タスク（T1〜T10、フェーズA〜Fに区分、この順で進める）。チェックボックスで進捗管理。フェーズ完了判定＝全チェック＋selftest 全pass＋commit
- `docs/EXEビルド手順書.md` — PyInstaller で EXE を作る手順（前提・ビルド・確認・トラブルシュート・onefile）
- `docs/progress/` — **セッション引き継ぎ（最新 `261026_引き継ぎ資料.md`／開始プロンプト `261026_次セッション開始プロンプト.md`）**・全体整理（`261015_全体スケジュール_マイルストン整理.md`）・
  進捗報告（`2026-09-01_*`〜`2026-10-15_進捗報告04_presen.md`）・レビュー記録（`260903_*`）・
  評価チェック結果（`260907_評価チェックシート_checked.md`／`261014B_動作確認チェックリスト.md`＝最新・全項目OK）・
  評価反映方針（`260909_評価反映_実装方針.md`／`260910_評価反映2_実装方針.md`／`261013_IP設計者レビュー3_実装方針.md`）・
  IP設計者2回目レビュー原文（`260910_DBI&BIP_prog_mtg.txt`）
- `docs/review/劣化Sim_ツール評価結果_261013.xlsx` — IP設計者レビュー3（元資料は261005）への回答・対応をコメント列に記載、
  9月末〜10月の変更一覧を追加行で記載（別名保存。元の`_261005.xlsx`は無変更）
- `team/Meeting/` — DBI&BIPチーム全体の共有資料（日付→メンバー名フォルダ）。松井氏＝DBIモデル理論・
  劣化Simulatorコア担当、礒部氏＝BIP実機検証・Heat Map物理モデル担当。会議議事録 `meeting_minutes_DBI&BIP_dev_*.txt`
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
本番GUIの UI 表記は `deg`→「輝度残存率(1-劣化率) / lum. residual (1-degradation)」、`stat`→「累積時間 / accumulated time」に変更
（ファイル名トークンは `deg` / `stat` 維持）。加速込みAging時間 = (フレーム数/fps)×`ACCEL_RATIO`。
`AGING_TIME`[秒]はこの加速込みAging時間の**目標値**（`0`＝無制限）。超過なら打ち切り、不足なら
動画を周回連結して埋める（`bisim/engine.py::run_recipe`。`source/` 側は無改変・未使用のまま）。
**注意（粒度）**：1フレームあたりの加速込み時間 ＝ `(1/fps)×ACCEL_RATIO`。既定値（30fps・ACCEL_RATIO=30000）
だと約1000秒/フレームになるため、AGING_TIMEがそれより小さい値はどれも「最低1フレーム処理」に
丸められ区別できない（バグではない。④タブの見積りフレーム数表示で事前に確認できる）。
`format_aging()` の表示は時:分:秒（`00h 00m 10s`。24h超は日数も付記）で、時間の小数表示はしない。

## 環境メモ

- `source/.venv` はベースPythonが不在で壊れている。`prototype/` `bisim/` ともリポジトリ直下の `.venv` を使用（Python 3.9）。
  **フォルダを移動したら `.venv` は作り直す**（中に作成時の場所が書き込まれているため）。docs の xlsx/pptx 処理には `openpyxl` / `pandas` / `python-pptx` も使う
- チーム資料の pptx は表が WMF 画像のことがある（Pillow で PNG 化して読む）。xlsx のガントは図形（`xl/drawings/*.xml`）で描かれていることがある
- OpenCVは画素並びが BGR。動画は (w,h)、静止画は (h,w) の順に注意。
- Python 3.9 のため各モジュール先頭で `from __future__ import annotations`（`str | None` 等を実行時に評価させない）。
- git 管理下（ブランチ master、remote `https://github.com/PScirocco/DBI_BIP`）。
- コミットは日本語メッセージ。末尾に `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`。
