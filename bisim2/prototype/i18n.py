""" 簡易 i18n（プロトタイプ用）

    LANG を切り替えて t(key) で文字列を引く。format 引数を渡すと .format() する。
    Qt に依存しないので sim_runner からも利用可。
"""
from __future__ import annotations

LANG = "ja"          # "ja" | "en"
_LISTENERS: list = []


def set_lang(lang: str) -> None:
    global LANG
    if lang not in ("ja", "en") or lang == LANG:
        return
    LANG = lang
    for cb in list(_LISTENERS):
        cb()


def on_change(cb) -> None:
    """ 言語変更時に呼ぶコールバックを登録（重複登録は無視）。 """
    if cb not in _LISTENERS:
        _LISTENERS.append(cb)


def t(key: str, **kw) -> str:
    entry = STR.get(key)
    if entry is None:
        return key
    s = entry.get(LANG) or entry.get("ja") or key
    return s.format(**kw) if kw else s


FOLDER_KEYS = ["input_image", "heatmap", "bcset", "model", "simconf", "output"]

STR: dict[str, dict[str, str]] = {
    # ---- app / window / menu ----
    "app.title": {"ja": "OLED 劣化シミュレータ (proto)", "en": "OLED Degradation Simulator (proto)"},
    "menu.demo": {"ja": "デモ", "en": "Demo"},
    "menu.demo.load": {"ja": "サンプルステップ + 既存結果を読み込む",
                       "en": "Load sample steps + existing results"},
    "menu.demo.clear": {"ja": "結果をクリア", "en": "Clear results"},
    "menu.lang": {"ja": "言語 / Language", "en": "言語 / Language"},
    "menu.lang.ja": {"ja": "日本語 (JP)", "en": "日本語 (JP)"},
    "menu.lang.en": {"ja": "English (EN)", "en": "English (EN)"},
    "status.ready": {"ja": "準備完了", "en": "Ready"},
    "status.demo_loaded": {"ja": "サンプル {steps} ステップ / 既存結果 {res} 件を読み込みました",
                           "en": "Loaded {steps} sample steps / {res} existing results"},
    "status.results_cleared": {"ja": "結果をクリアしました", "en": "Results cleared"},
    "status.applied": {"ja": "ステップ設定を適用しました", "en": "Step config applied"},
    "status.saved": {"ja": "保存: {path}", "en": "Saved: {path}"},
    "status.aborted": {"ja": "中断", "en": "Aborted"},
    "status.run_done": {"ja": "実行完了", "en": "Run complete"},

    # ---- tabs ----
    "tab.folders": {"ja": "① フォルダ設定", "en": "1. Folders"},
    "tab.steps": {"ja": "② 実行ステップ", "en": "2. Steps"},
    "tab.config": {"ja": "③ ステップ設定", "en": "3. Step config"},
    "tab.run": {"ja": "④ 実行", "en": "4. Run"},
    "tab.results": {"ja": "⑤ 結果", "en": "5. Results"},

    # ---- common ----
    "btn.browse": {"ja": "参照…", "en": "Browse…"},
    "btn.reload": {"ja": "再読込", "en": "Reload"},
    "dlg.select_folder": {"ja": "フォルダを選択", "en": "Select folder"},

    # ---- folders tab ----
    "folders.desc": {
        "ja": "各ファイルの入っているフォルダ。既定値は既存コードの構成（dbi_common / dbi_input / dbi_conf / dbi_output）。",
        "en": "Folders holding each file. Defaults follow the existing code layout (dbi_common / dbi_input / dbi_conf / dbi_output)."},
    "folder.input_image": {"ja": "入力画像フォルダ", "en": "Input image folder"},
    "folder.heatmap": {"ja": "ヒートマップフォルダ", "en": "Heat map folder"},
    "folder.bcset": {"ja": "BC設定フォルダ", "en": "BC settings folder"},
    "folder.model": {"ja": "モデルパラメータフォルダ", "en": "Model parameter folder"},
    "folder.simconf": {"ja": "Sim条件フォルダ", "en": "Sim condition folder"},
    "folder.output": {"ja": "出力フォルダ", "en": "Output folder"},

    # ---- steps tab ----
    "steps.h.num": {"ja": "#", "en": "#"},
    "steps.h.name": {"ja": "名前", "en": "Name"},
    "steps.h.type": {"ja": "種別", "en": "Type"},
    "steps.h.input": {"ja": "入力画像", "en": "Input image"},
    "steps.h.heatmap": {"ja": "ヒートマップ", "en": "Heat map"},
    "steps.h.init": {"ja": "初期ストレス", "en": "Initial stress"},
    "steps.h.status": {"ja": "状態", "en": "Status"},
    "steps.btn.add": {"ja": "追加", "en": "Add"},
    "steps.btn.dup": {"ja": "複製", "en": "Duplicate"},
    "steps.btn.del": {"ja": "削除", "en": "Delete"},
    "steps.btn.up": {"ja": "↑", "en": "↑"},
    "steps.btn.down": {"ja": "↓", "en": "↓"},
    "steps.btn.edit": {"ja": "設定を編集 →", "en": "Edit config →"},
    "steps.new": {"ja": "新規ステップ", "en": "New step"},
    "steps.nth": {"ja": "ステップ{n}", "en": "Step {n}"},
    "steps.copy_suffix": {"ja": "（複製）", "en": " (copy)"},

    "kind.aging": {"ja": "Aging", "en": "Aging"},
    "kind.pq": {"ja": "PQ評価", "en": "PQ Eval"},
    "kind.unknown": {"ja": "―", "en": "—"},

    "init.zero": {"ja": "ゼロ", "en": "Zero"},
    "init.inherit_n": {"ja": "前 #{i} 継承", "en": "Inherit #{i}"},
    "init.file": {"ja": "ファイル", "en": "File"},

    "initsel.none": {"ja": "なし（ゼロから）", "en": "None (from zero)"},
    "initsel.prev": {"ja": "前ステップから継承", "en": "Inherit from previous step"},
    "initsel.file": {"ja": "ファイル指定", "en": "Specify files"},

    "status.pending": {"ja": "未実行", "en": "Not run"},
    "status.running": {"ja": "実行中", "en": "Running"},
    "status.done": {"ja": "実行済", "en": "Done"},
    "status.done_existing": {"ja": "実行済（既存出力）", "en": "Done (existing output)"},

    # ---- step config tab ----
    "cfg.none": {"ja": "ステップ未選択", "en": "No step selected"},
    "cfg.head": {"ja": "ステップ #{n} の設定", "en": "Step #{n} config"},
    "cfg.name": {"ja": "名前", "en": "Name"},
    "cfg.input": {"ja": "入力画像", "en": "Input image"},
    "cfg.heatmap": {"ja": "ヒートマップ", "en": "Heat map"},
    "cfg.kind": {"ja": "種別（自動判定）", "en": "Type (auto)"},
    "cfg.grp.init": {"ja": "初期ストレス（Aging 再開）", "en": "Initial stress (resume aging)"},
    "cfg.grp.model": {"ja": "モデルパラメータ（Master Model）", "en": "Model parameters (Master Model)"},
    "cfg.btn.load_csv": {"ja": "CSVから読込", "en": "Load from CSV"},
    "cfg.btn.save_csv": {"ja": "CSVへ保存", "en": "Save to CSV"},
    "cfg.grp.sim": {"ja": "Sim条件", "en": "Sim conditions"},
    "cfg.tmp_l": {"ja": "TMP_L [℃]", "en": "TMP_L [degC]"},
    "cfg.tmp_h": {"ja": "TMP_H [℃]", "en": "TMP_H [degC]"},
    "cfg.aging_time": {"ja": "AGING_TIME（現状未使用）", "en": "AGING_TIME (unused)"},
    "cfg.grp.future": {"ja": "BC設定 / 処理パイプライン（将来拡張・現在は無効）",
                       "en": "BC settings / processing pipeline (future, disabled)"},
    "cfg.bc_note": {"ja": "BC設定（DBV_NIT, Duty）: 現行モデルは未使用",
                    "en": "BC settings (DBV_NIT, Duty): unused by current model"},
    "cfg.pipe.bip": {"ja": "BIP 前処理", "en": "BIP pre-process"},
    "cfg.pipe.dbi": {"ja": "DBI 補正", "en": "DBI compensation"},
    "cfg.pipe.peak": {"ja": "ピーク輝度制御", "en": "Peak luminance control"},
    "cfg.pipe.ab": {"ja": "補正あり / なし を比較実行", "en": "Run with/without compensation (A/B)"},
    "cfg.btn.apply": {"ja": "この設定を適用", "en": "Apply"},
    "cfg.pv.input": {"ja": "入力画像", "en": "Input image"},
    "cfg.pv.heatmap": {"ja": "ヒートマップ画像", "en": "Heat map image"},
    "cfg.pv.prev": {"ja": "前回の Aging 結果", "en": "Previous aging result"},
    "cfg.pv.prev_named": {"ja": "前回の Aging 結果  (#{n}_out_img{ext})",
                          "en": "Previous aging result  (#{n}_out_img{ext})"},
    "cfg.pv.none": {"ja": "（ステップ未選択）", "en": "(no step selected)"},
    "cfg.pv.first": {"ja": "（初回 Aging / 継承なし）", "en": "(first aging / no inheritance)"},
    "cfg.pv.prev_notrun": {"ja": "step #{n} は未実行です", "en": "step #{n} not run yet"},
    "cfg.err.title": {"ja": "入力エラー", "en": "Input error"},
    "cfg.err.model": {"ja": "モデルパラメータ表に数値でない値があります。",
                      "en": "The model parameter table contains non-numeric values."},
    "cfg.load_fail.title": {"ja": "読込失敗", "en": "Load failed"},
    "cfg.load_fail.msg": {"ja": "CSV を読めませんでした。", "en": "Could not read the CSV."},
    "cfg.dlg.stress_csv": {"ja": "ストレスCSV", "en": "Stress CSV"},
    "cfg.dlg.model_csv": {"ja": "モデルパラメータCSV", "en": "Model parameter CSV"},

    # ---- run tab ----
    "run.btn.all": {"ja": "▶ 全ステップ実行", "en": "▶ Run all steps"},
    "run.btn.sel": {"ja": "▶ 選択ステップのみ", "en": "▶ Run selected step"},
    "run.btn.abort": {"ja": "■ 中断", "en": "■ Abort"},
    "run.idle": {"ja": "待機中", "en": "Idle"},
    "run.dash": {"ja": "―", "en": "—"},
    "run.elapsed": {"ja": "経過 {s:.1f} s", "en": "Elapsed {s:.1f} s"},
    "run.preview": {"ja": "処理中フレーム（劣化後）", "en": "Processing frame (degraded)"},
    "run.log.start": {"ja": "=== 実行開始（{n} ステップ）===", "en": "=== Run start ({n} steps) ==="},
    "run.step": {"ja": "ステップ {i}/{n} : {name}", "en": "Step {i}/{n} : {name}"},
    "run.frame": {"ja": "フレーム {f}/{ft}", "en": "Frame {f}/{ft}"},
    "run.state.aborted": {"ja": "中断しました", "en": "Aborted"},
    "run.state.done": {"ja": "完了", "en": "Done"},
    "run.log.aborted": {"ja": "=== 中断 ===", "en": "=== Aborted ==="},
    "run.log.done": {"ja": "=== 完了 ===", "en": "=== Done ==="},
    "run.log.err": {"ja": "!! エラー: {msg}", "en": "!! Error: {msg}"},
    "run.state.err": {"ja": "エラー終了", "en": "Error"},
    "run.abort_req": {"ja": "中断要求…（現在のフレーム終了後に停止）",
                      "en": "Abort requested (stops after current frame)"},
    "run.msg.title": {"ja": "実行", "en": "Run"},
    "run.msg.nosteps": {"ja": "ステップがありません。", "en": "No steps."},
    "run.msg.noselect": {"ja": "②実行ステップでステップを選択してください。",
                         "en": "Select a step in the Steps tab."},
    "run.msg.unset": {"ja": "ステップ #{n} の入力画像 / ヒートマップが未設定です。",
                      "en": "Step #{n}: input image / heat map not set."},
    "run.err.title": {"ja": "実行エラー", "en": "Run error"},
    "demo.na.title": {"ja": "デモ", "en": "Demo"},
    "demo.na.msg": {
        "ja": "サンプル入力（source/dbi_common/mov_001_480x270.mp4 など）が見つかりません。\n①フォルダ設定で入力画像フォルダを確認してください。",
        "en": "Sample inputs (e.g. source/dbi_common/mov_001_480x270.mp4) not found.\nCheck the input image folder in the Folders tab."},

    # ---- results tab ----
    "res.idx": {"ja": "表示するステップ (idx)", "en": "Step to show (idx)"},
    "res.sub.preview": {"ja": "劣化後プレビュー", "en": "Degraded preview"},
    "res.sub.deg": {"ja": "劣化率マップ", "en": "Degradation map"},
    "res.sub.stat": {"ja": "累積ストレスマップ", "en": "Accumulated stress map"},
    "res.sub.ts": {"ja": "時系列", "en": "Time series"},
    "res.sub.ab": {"ja": "A/B比較", "en": "A/B compare"},
    "res.preview.title": {"ja": "劣化後", "en": "Degraded"},
    "res.ab.note": {"ja": "補正あり / なし の A/B 比較 —— 将来拡張（現在は無効）",
                    "en": "A/B compare with/without compensation — future (disabled)"},
    "res.ts.update": {"ja": "更新", "en": "Update"},
    "res.ts.x": {"ja": "step idx", "en": "step idx"},
    "res.ts.y": {"ja": "平均劣化率 (mean deg)", "en": "mean degradation"},
    "res.ts.none": {"ja": "（結果なし）", "en": "(no results)"},

    "map.view": {"ja": "表示", "en": "View"},
    "map.ch.r": {"ja": "R", "en": "R"},
    "map.ch.g": {"ja": "G", "en": "G"},
    "map.ch.b": {"ja": "B", "en": "B"},
    "map.ch.rgb": {"ja": "RGB合成", "en": "RGB composite"},
    "map.hover.none": {"ja": "カーソル値: ―", "en": "Cursor: —"},
    "map.stats.none": {"ja": "統計: ―", "en": "Stats: —"},
    "map.none": {"ja": "（結果なし）", "en": "(no results)"},
    "map.csv_fail": {"ja": "（CSV読込失敗）", "en": "(CSV load failed)"},
    "map.label.deg": {"ja": "劣化率", "en": "Degradation"},
    "map.label.stat": {"ja": "累積ストレス", "en": "Accum. stress"},
    "map.range01": {"ja": "輝度 0–1", "en": "lum 0–1"},
    "map.rangev": {"ja": "輝度 0–{v}", "en": "lum 0–{v}"},
    "map.title.ch": {"ja": "#{idx} {label} {ch}  ({rng})", "en": "#{idx} {label} {ch}  ({rng})"},
    "map.title.rgb": {"ja": "#{idx} {label} RGB合成  ({rng})",
                      "en": "#{idx} {label} RGB composite  ({rng})"},
    "map.hover.ch": {"ja": "カーソル値: (x={x}, y={y})  {ch} = {v:.4f}",
                     "en": "Cursor: (x={x}, y={y})  {ch} = {v:.4f}"},
    "map.hover.rgb": {"ja": "カーソル値: (x={x}, y={y})  {vals}",
                      "en": "Cursor: (x={x}, y={y})  {vals}"},
    "map.stats.ch": {"ja": "{ch}: min {mn:.4g} / max {mx:.4g} / mean {me:.4g}",
                     "en": "{ch}: min {mn:.4g} / max {mx:.4g} / mean {me:.4g}"},
    "map.stats.rgb": {"ja": "{parts}", "en": "{parts}"},

    # ---- widgets ----
    "img.none": {"ja": "（画像なし）", "en": "(no image)"},

    # ---- sample steps ----
    "sample.s1": {"ja": "① Aging（動画・ゼロから）", "en": "1. Aging (movie, from zero)"},
    "sample.s2": {"ja": "② PQ評価（静止画）", "en": "2. PQ eval (still)"},
    "sample.s3": {"ja": "③ Aging 継続（動画）", "en": "3. Aging continued (movie)"},
    "sample.s4": {"ja": "④ PQ評価（静止画）", "en": "4. PQ eval (still)"},

    # ---- sim_runner logs / errors ----
    "sim.err.input_missing": {"ja": "入力画像が見つかりません: {p}", "en": "Input image not found: {p}"},
    "sim.err.heatmap_missing": {"ja": "ヒートマップが見つかりません: {p}", "en": "Heat map not found: {p}"},
    "sim.err.no_prev": {"ja": "前ステップがありません（初期ストレス=前ステップ継承）",
                        "en": "No previous step (initial stress = inherit previous)"},
    "sim.err.png_read": {"ja": "画像を読めません: {p}", "en": "Cannot read image: {p}"},
    "sim.err.shape": {"ja": "継承ストレスのサイズ {got} が入力画像 {exp} と一致しません",
                      "en": "Inherited stress size {got} does not match input image {exp}"},
    "sim.err.calc": {"ja": "劣化計算でエラー（temp_update_stat_and_burn_img rtn=-1）",
                     "en": "Error in degradation calc (temp_update_stat_and_burn_img rtn=-1)"},
    "sim.log.inherit_prev": {"ja": "ストレス継承: step #{idx} の stat_*.csv",
                             "en": "Inherit stress: stat_*.csv of step #{idx}"},
    "sim.log.inherit_file": {"ja": "ストレス継承: 指定ファイル", "en": "Inherit stress: specified files"},
    "sim.log.zero": {"ja": "ストレス初期値: ゼロ", "en": "Initial stress: zero"},
    "sim.log.abort": {"ja": "中断（{i}/{n} フレームで停止）", "en": "Aborted (stopped at frame {i}/{n})"},
    "sim.log.frame_end": {"ja": "フレーム読み込み終了（{i}/{n}）", "en": "Frame read finished ({i}/{n})"},
    "sim.log.video_time": {"ja": "映像処理 {t:.1f}s", "en": "Video processing {t:.1f}s"},
    "sim.log.output": {
        "ja": "出力: {idx}_out_img / {idx}_deg_* / {idx}_stat_*  (平均劣化率 R={r:.3f} G={g:.3f} B={b:.3f})",
        "en": "Output: {idx}_out_img / {idx}_deg_* / {idx}_stat_*  (mean deg R={r:.3f} G={g:.3f} B={b:.3f})"},
}
