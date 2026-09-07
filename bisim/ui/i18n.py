"""簡易 i18n（本番GUI）

``prototype/i18n.py`` を土台に、レビュー反映の文言変更を入れたもの。
- 「劣化率」→「1/劣化率 / inverse degradation」（出力トークン ``deg`` は不変）
- 「累積ストレス」→「累積時間 / accumulated time」（出力トークン ``stat`` は不変）

Qt 非依存。``set_lang`` で切替、``t(key, **fmt)`` で引く。既定はリリース仕様どおり英語。
"""
from __future__ import annotations

LANG = "en"                 # "ja" | "en"（リリースは英語。仕様 2）
_LISTENERS: list = []


def set_lang(lang: str) -> None:
    global LANG
    if lang not in ("ja", "en") or lang == LANG:
        return
    LANG = lang
    for cb in list(_LISTENERS):
        cb()


def on_change(cb) -> None:
    if cb not in _LISTENERS:
        _LISTENERS.append(cb)


def t(key: str, **kw) -> str:
    entry = STR.get(key)
    if entry is None:
        return key
    s = entry.get(LANG) or entry.get("ja") or key
    return s.format(**kw) if kw else s


STR: dict[str, dict[str, str]] = {
    # ---- app / window / menu ----
    "app.title": {"ja": "OLED 劣化シミュレータ (BI-sim)",
                  "en": "OLED Burn-in Simulator (BI-sim)"},
    "menu.file": {"ja": "ファイル", "en": "File"},
    "menu.seq.open": {"ja": "シーケンスを開く…", "en": "Open sequence…"},
    "menu.seq.save": {"ja": "シーケンスを保存", "en": "Save sequence"},
    "menu.seq.save_as": {"ja": "シーケンスに名前を付けて保存…", "en": "Save sequence as…"},
    "menu.recipe.load": {"ja": "レシピを読込…", "en": "Load recipe…"},
    "menu.recipe.save": {"ja": "選択レシピを保存…", "en": "Save selected recipe…"},
    "menu.resume.load": {"ja": "停止結果を読み込んで再開…", "en": "Load stopped result & resume…"},
    "menu.lang": {"ja": "言語 / Language", "en": "言語 / Language"},
    "menu.lang.ja": {"ja": "日本語 (JP)", "en": "日本語 (JP)"},
    "menu.lang.en": {"ja": "English (EN)", "en": "English (EN)"},

    "status.ready": {"ja": "準備完了", "en": "Ready"},
    "status.seq_opened": {"ja": "シーケンスを開きました: {name}", "en": "Sequence opened: {name}"},
    "status.seq_saved": {"ja": "シーケンスを保存: {path}", "en": "Sequence saved: {path}"},
    "status.recipe_loaded": {"ja": "レシピを読込: {name}", "en": "Recipe loaded: {name}"},
    "status.recipe_saved": {"ja": "レシピを保存: {path}", "en": "Recipe saved: {path}"},
    "status.applied": {"ja": "ステップ設定を適用しました", "en": "Step config applied"},
    "status.saved": {"ja": "保存: {path}", "en": "Saved: {path}"},
    "status.stopped": {"ja": "停止しました（保存済み／再開可）", "en": "Stopped (saved / resumable)"},
    "status.stopped_discard": {"ja": "停止しました（破棄）", "en": "Stopped (discarded)"},
    "status.run_done": {"ja": "実行完了", "en": "Run complete"},
    "status.resumed": {"ja": "停止位置から再開: {name}", "en": "Resumed from stop: {name}"},

    "dlg.resume_filter": {"ja": "停止結果 (*_resume_*.json)", "en": "Stopped result (*_resume_*.json)"},
    "dlg.resume_nomatch": {"ja": "この停止結果のレシピ「{name}」が現在のシーケンスに見つかりません。",
                           "en": "Recipe \"{name}\" from this stopped result is not in the current sequence."},
    "dlg.resume_notmovie": {"ja": "静止画ステップは再開の必要がありません。", "en": "Still-image steps do not need resume."},

    "dlg.seq_filter": {"ja": "シーケンス (*.seq.json)", "en": "Sequence (*.seq.json)"},
    "dlg.recipe_filter": {"ja": "レシピ (*.recipe.json)", "en": "Recipe (*.recipe.json)"},
    "dlg.err.title": {"ja": "エラー", "en": "Error"},
    "dlg.load_fail": {"ja": "読み込みに失敗しました:\n{msg}", "en": "Failed to load:\n{msg}"},
    "dlg.no_recipe": {"ja": "レシピが選択されていません。", "en": "No recipe selected."},

    # ---- tabs ----
    "tab.folders": {"ja": "① フォルダ設定", "en": "1. Folders"},
    "tab.steps": {"ja": "② 実行ステップ", "en": "2. Steps"},
    "tab.config": {"ja": "③ ステップ設定", "en": "3. Step config"},
    "tab.run": {"ja": "④ 実行", "en": "4. Run"},
    "tab.results": {"ja": "⑤ 結果", "en": "5. Results"},

    # ---- common ----
    "btn.browse": {"ja": "参照…", "en": "Browse…"},
    "btn.reload": {"ja": "再読込", "en": "Reload"},

    # ---- folders tab ----
    "folders.desc": {
        "ja": "各ファイルの入っているフォルダ。既定値は source/ の構成"
              "（dbi_common / dbi_input / dbi_conf / dbi_output）。"
              "③でファイルを選ぶと、その親フォルダがここへ反映されます。",
        "en": "Folders holding each file. Defaults follow the source/ layout "
              "(dbi_common / dbi_input / dbi_conf / dbi_output). Picking a file in "
              "tab 3 updates the matching folder here."},
    "folder.input_image": {"ja": "入力画像フォルダ", "en": "Input image folder"},
    "folder.heatmap": {"ja": "ヒートマップフォルダ", "en": "Heat map folder"},
    "folder.bcset": {"ja": "BC設定フォルダ", "en": "BC settings folder"},
    "folder.model": {"ja": "モデルパラメータフォルダ", "en": "Model parameter folder"},
    "folder.simconf": {"ja": "Sim条件フォルダ", "en": "Sim condition folder"},
    "folder.output": {"ja": "出力フォルダ", "en": "Output folder"},

    # ---- steps tab ----
    "steps.seq_name": {"ja": "シーケンス名", "en": "Sequence name"},
    "steps.h.num": {"ja": "#", "en": "#"},
    "steps.h.nn": {"ja": "NN", "en": "NN"},
    "steps.h.name": {"ja": "レシピ名", "en": "Recipe name"},
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
    "steps.note": {"ja": "ここは順序操作のみ。ファイル指定は③ステップ設定で行います。",
                   "en": "Order operations only. Assign files in tab 3 (Step config)."},
    "steps.nth": {"ja": "レシピ{n}", "en": "recipe{n}"},
    "steps.copy_suffix": {"ja": "-copy", "en": "-copy"},

    "kind.aging": {"ja": "Aging", "en": "Aging"},
    "kind.pq": {"ja": "PQ評価", "en": "PQ Eval"},
    "kind.unknown": {"ja": "―", "en": "—"},

    "init.none": {"ja": "なし", "en": "None"},
    "init.prev": {"ja": "前ステップ継承", "en": "Inherit prev"},
    "init.file": {"ja": "ファイル指定", "en": "From files"},

    "status.pending": {"ja": "未実行", "en": "Not run"},
    "status.running": {"ja": "実行中", "en": "Running"},
    "status.done": {"ja": "実行済", "en": "Done"},
    "status.stopped_row": {"ja": "停止", "en": "Stopped"},

    # ---- step config tab ----
    "cfg.none": {"ja": "ステップ未選択（②でレシピを追加してください）",
                 "en": "No step selected (add a recipe in tab 2)"},
    "cfg.head": {"ja": "レシピ #{n}（NN={nn}）の設定", "en": "Recipe #{n} (NN={nn}) config"},
    "cfg.name": {"ja": "レシピ名", "en": "Recipe name"},
    "cfg.input": {"ja": "入力画像", "en": "Input image"},
    "cfg.heatmap": {"ja": "ヒートマップ", "en": "Heat map"},
    "cfg.kind": {"ja": "種別（自動判定）", "en": "Type (auto)"},
    "cfg.grp.init": {"ja": "初期ストレス（Aging 再開）", "en": "Initial stress (resume aging)"},
    "cfg.grp.model": {"ja": "モデルパラメータ（Master Model）", "en": "Model parameters (Master Model)"},
    "cfg.model_csv": {"ja": "参照CSV: {name}", "en": "CSV: {name}"},
    "cfg.model_csv_none": {"ja": "参照CSV: （なし・インライン値）", "en": "CSV: (none, inline values)"},
    "cfg.btn.load_csv": {"ja": "CSVから読込", "en": "Load from CSV"},
    "cfg.btn.save_csv": {"ja": "CSVへ保存", "en": "Save to CSV"},
    "cfg.grp.sim": {"ja": "Sim条件", "en": "Sim conditions"},
    "cfg.sim_csv": {"ja": "参照CSV: {name}", "en": "CSV: {name}"},
    "cfg.sim_csv_none": {"ja": "参照CSV: （なし・インライン値）", "en": "CSV: (none, inline values)"},
    "cfg.accel": {"ja": "ACCEL_RATIO（加速）", "en": "ACCEL_RATIO (acceleration)"},
    "cfg.tmp_l": {"ja": "TMP_L [℃]", "en": "TMP_L [degC]"},
    "cfg.tmp_h": {"ja": "TMP_H [℃]", "en": "TMP_H [degC]"},
    "cfg.aging_time": {"ja": "AGING_TIME（現状未使用）", "en": "AGING_TIME (unused)"},
    "cfg.init.file_r": {"ja": "初期 stat_r CSV", "en": "Initial stat_r CSV"},
    "cfg.init.file_g": {"ja": "初期 stat_g CSV", "en": "Initial stat_g CSV"},
    "cfg.init.file_b": {"ja": "初期 stat_b CSV", "en": "Initial stat_b CSV"},
    "cfg.grp.future": {"ja": "BC設定 / 処理パイプライン（将来拡張・現在は無効）",
                       "en": "BC settings / processing pipeline (future, disabled)"},
    "cfg.bc_note": {"ja": "BC設定（DBV_NIT, Duty）: 現行モデルは未使用",
                    "en": "BC settings (DBV_NIT, Duty): unused by current model"},
    "cfg.pipe.bip": {"ja": "BIP 前処理", "en": "BIP pre-process"},
    "cfg.pipe.dbi": {"ja": "DBI 補正", "en": "DBI compensation"},
    "cfg.pipe.peak": {"ja": "ピーク輝度制御", "en": "Peak luminance control"},
    "cfg.pipe.ab": {"ja": "補正あり / なし を比較実行 (A/B)", "en": "Run with/without compensation (A/B)"},
    "cfg.btn.apply": {"ja": "この設定を適用", "en": "Apply"},
    "cfg.pv.input": {"ja": "入力画像", "en": "Input image"},
    "cfg.pv.heatmap": {"ja": "ヒートマップ画像", "en": "Heat map image"},
    "cfg.pv.prev": {"ja": "前回の Aging 結果", "en": "Previous aging result"},
    "cfg.pv.prev_named": {"ja": "前回の Aging 結果 ({name})", "en": "Previous aging result ({name})"},
    "cfg.pv.none": {"ja": "（ステップ未選択）", "en": "(no step selected)"},
    "cfg.pv.first": {"ja": "（初回 / 継承なし）", "en": "(first / no inheritance)"},
    "cfg.pv.prev_notrun": {"ja": "前ステップ #{n} は未実行です", "en": "Previous step #{n} not run yet"},
    "cfg.err.title": {"ja": "入力エラー", "en": "Input error"},
    "cfg.err.model": {"ja": "モデルパラメータ表に数値でない値があります。",
                      "en": "The model parameter table contains non-numeric values."},
    "cfg.load_fail.title": {"ja": "読込失敗", "en": "Load failed"},
    "cfg.load_fail.msg": {"ja": "CSV を読めませんでした。", "en": "Could not read the CSV."},
    "cfg.dlg.stress_csv": {"ja": "ストレスCSV", "en": "Stress CSV"},
    "cfg.dlg.model_csv": {"ja": "モデルパラメータCSV", "en": "Model parameter CSV"},

    # ---- run tab ----
    "run.btn.all": {"ja": "▶ 全ステップ実行", "en": "▶ Run all steps"},
    "run.btn.sel": {"ja": "▶ 選択ステップのみ実行", "en": "▶ Run selected step"},
    "run.sel_which": {"ja": "実行するステップ", "en": "Step to run"},
    "run.btn.pause": {"ja": "❚❚ 中断", "en": "❚❚ Pause"},
    "run.btn.resume": {"ja": "▶ 再開", "en": "▶ Resume"},
    "run.btn.stop": {"ja": "■ 停止（保存確認）", "en": "■ Stop (save prompt)"},
    "run.btn.resume_stop": {"ja": "▶↻ 停止位置から再開", "en": "▶↻ Resume from stop"},
    "run.idle": {"ja": "待機中", "en": "Idle"},
    "run.dash": {"ja": "―", "en": "—"},
    "run.calc_time": {"ja": "計算時間: {s:.1f} s", "en": "Compute time: {s:.1f} s"},
    "run.aging_time": {"ja": "Aging時間（加速込み）: {v}", "en": "Aging time (accelerated): {v}"},
    "run.preview": {"ja": "処理中フレーム（劣化後）", "en": "Processing frame (degraded)"},
    "run.log.start": {"ja": "=== 実行開始（{n} ステップ）===", "en": "=== Run start ({n} steps) ==="},
    "run.step": {"ja": "ステップ {i}/{n} : {name}", "en": "Step {i}/{n} : {name}"},
    "run.frame": {"ja": "フレーム {f}/{ft}", "en": "Frame {f}/{ft}"},
    "run.state.paused": {"ja": "中断中（再開できます）", "en": "Paused (resume available)"},
    "run.state.stopped": {"ja": "停止しました", "en": "Stopped"},
    "run.state.done": {"ja": "完了", "en": "Done"},
    "run.state.err": {"ja": "エラー終了", "en": "Error"},
    "run.log.stopped": {"ja": "=== 停止 ===", "en": "=== Stopped ==="},
    "run.log.done": {"ja": "=== 完了 ===", "en": "=== Done ==="},
    "run.log.err": {"ja": "!! エラー: {msg}", "en": "!! Error: {msg}"},
    "run.msg.title": {"ja": "実行", "en": "Run"},
    "run.msg.nosteps": {"ja": "レシピがありません。", "en": "No recipes."},
    "run.msg.unset": {"ja": "レシピ #{n} の入力画像 / ヒートマップが未設定です。",
                      "en": "Recipe #{n}: input image / heat map not set."},
    "run.msg.no_resume": {"ja": "選択したステップに再開できる停止結果がありません。",
                          "en": "The selected step has no resumable stopped result."},
    "run.resume.title": {"ja": "停止位置から再開", "en": "Resume from stop"},
    "run.resume.msg": {"ja": "「{name}」をフレーム {f}/{ft} から再開します。\n"
                             "累積 Aging 時間: {aging}",
                       "en": "Resume \"{name}\" from frame {f}/{ft}.\n"
                             "Accumulated aging time: {aging}"},
    "run.log.resume": {"ja": "停止位置から再開: {name}（フレーム {f}）", "en": "Resume from stop: {name} (frame {f})"},
    "run.save.title": {"ja": "停止 — 出力の保存", "en": "Stop — save output"},
    "run.save.msg": {"ja": "ステップ「{name}」を {f} フレームで停止しました。\n"
                           "ここまでの結果をファイルに保存しますか？\n"
                           "（保存名には日時が付きます。後で読み込んで継続できます）",
                     "en": "Step \"{name}\" stopped at frame {f}.\n"
                           "Save the partial result to files?\n"
                           "(A timestamp is appended; you can reload it later to continue.)"},

    # ---- results tab ----
    "res.idx": {"ja": "表示するステップ", "en": "Step to show"},
    "res.sub.preview": {"ja": "劣化後プレビュー", "en": "Degraded preview"},
    "res.sub.deg": {"ja": "1/劣化率マップ", "en": "Inverse-degradation map"},
    "res.sub.stat": {"ja": "累積時間マップ", "en": "Accumulated-time map"},
    "res.sub.ts": {"ja": "時系列", "en": "Time series"},
    "res.sub.ab": {"ja": "A/B比較", "en": "A/B compare"},
    "res.preview.title": {"ja": "劣化後", "en": "Degraded"},
    "res.frame": {"ja": "フレーム {v}", "en": "Frame {v}"},
    "res.ab.note": {"ja": "補正あり / なし の A/B 比較 —— 将来拡張（現在は無効）",
                    "en": "A/B compare with/without compensation — future (disabled)"},
    "res.ts.note": {"ja": "時系列の表示内容はアルゴリズム担当者間で継続検討中。"
                          "現状は白紙の軸のみ表示します。",
                    "en": "Time-series content is still under discussion by the algorithm owners. "
                          "For now only blank axes are shown."},
    "res.ts.x": {"ja": "時間", "en": "time"},
    "res.ts.y": {"ja": "（未定）", "en": "(TBD)"},
    "res.none": {"ja": "（結果なし）", "en": "(no results)"},

    "map.view": {"ja": "表示", "en": "View"},
    "map.ch.r": {"ja": "R", "en": "R"},
    "map.ch.g": {"ja": "G", "en": "G"},
    "map.ch.b": {"ja": "B", "en": "B"},
    "map.ch.rgb": {"ja": "RGB合成", "en": "RGB composite"},
    "map.hover.none": {"ja": "カーソル値: ―", "en": "Cursor: —"},
    "map.stats.none": {"ja": "統計: ―", "en": "Stats: —"},
    "map.none": {"ja": "（結果なし）", "en": "(no results)"},
    "map.csv_fail": {"ja": "（CSV読込失敗）", "en": "(CSV load failed)"},
    "map.label.deg": {"ja": "1/劣化率", "en": "inv. degradation"},
    "map.label.stat": {"ja": "累積時間", "en": "accum. time"},
    "map.range01": {"ja": "明＝劣化少 (0–1)", "en": "bright = less degraded (0-1)"},
    "map.rangev": {"ja": "面内最大で正規化 (max {v})", "en": "normalized to in-plane max ({v})"},
    "map.title.ch": {"ja": "#{idx} {label} {ch}  ({rng})", "en": "#{idx} {label} {ch}  ({rng})"},
    "map.title.rgb": {"ja": "#{idx} {label} RGB合成  ({rng})",
                      "en": "#{idx} {label} RGB composite  ({rng})"},
    "map.hover.ch": {"ja": "カーソル: (x={x}, y={y})  {ch} = {v:.4f}",
                     "en": "Cursor: (x={x}, y={y})  {ch} = {v:.4f}"},
    "map.hover.rgb": {"ja": "カーソル: (x={x}, y={y})  {vals}",
                      "en": "Cursor: (x={x}, y={y})  {vals}"},
    "map.stats.ch": {"ja": "{ch}: min {mn:.4g} / max {mx:.4g} / mean {me:.4g}",
                     "en": "{ch}: min {mn:.4g} / max {mx:.4g} / mean {me:.4g}"},

    # ---- widgets ----
    "img.none": {"ja": "（画像なし）", "en": "(no image)"},
}
