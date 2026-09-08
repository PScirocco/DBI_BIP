"""UIシェル（T6）: MainWindow ＋ 5タブ ＋ ステータスバー ＋ メニュー ＋ 実行スレッド。

- 状態: 実行シーケンス Config（:class:`bisim.model.Sequence`）＋ アプリ Config
  （:class:`bisim.model.AppConfig`）＋ ログ（:class:`bisim.logio.Logger`）
- 実行は :class:`SimWorker`（QThread）から :func:`bisim.engine.run_sequence` を回す
- 中断・再開＝メモリ保持のみ。停止＝保存要否ダイアログ → 日時付きで出力（仕様 7）
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMessageBox, QTabWidget,
)

from bisim import __version__, engine, naming
from bisim.logio import Logger
from bisim.model import RECIPE_EXT, SEQ_EXT, AppConfig, Recipe, Sequence
from bisim.paths import APP_CONFIG_PATH
from bisim.ui import i18n
from bisim.ui.i18n import on_change, set_lang, t
from bisim.ui.tabs import FoldersTab, ResultsTab, RunTab, StepConfigTab, StepsTab
from bisim.ui.tabs._common import set_recipe_status

_TAB_KEYS = ["tab.folders", "tab.steps", "tab.config", "tab.run", "tab.results"]


# --------------------------------------------------------------------------- #
@dataclass(eq=False)
class ResultEntry:
    """⑤結果タブが表示に使う 1 ステップぶんの出力。"""

    nn: int
    recipe_name: str
    is_movie: bool
    outputs: dict = field(default_factory=dict)   # kind -> Path
    stopped_at: str | None = None


# --------------------------------------------------------------------------- #
class SimWorker(QThread):
    sig_started = Signal(int)
    sig_step = Signal(int, int, str)                    # pos, n, name
    sig_progress = Signal(int, int, int, int, object)   # pos, n, frame, total, QImage|None
    sig_aging = Signal(str)
    sig_step_done = Signal(int, object)                 # nn, ResultEntry
    sig_finished = Signal(bool)                         # stopped
    sig_error = Signal(str)

    def __init__(self, sequence: Sequence, model, control, logger,
                 only_index=None, max_frames=None, resume=None):
        super().__init__()
        self.sequence = sequence
        self.model = model
        self.control = control
        self.logger = logger
        self.only_index = only_index
        self.max_frames = max_frames
        self.resume = resume
        self.stopped_result: engine.RunResult | None = None
        self._cum_done = 0.0
        self._dt_accel = 0.0
        self._indices = ([only_index] if only_index is not None
                         else list(range(len(sequence.recipes))))

    # -- callbacks from engine --
    def _progress(self, pos, n, fd, ft, preview_bgr):
        if fd == 1:
            idx = self._indices[pos]
            r = self.sequence.recipes[idx]
            self.sig_step.emit(pos, n, r.recipe_name)
            self._dt_accel = (float(r.sim_param["ACCEL_RATIO"]) / ft) if ft > 1 else 0.0
        if fd == ft or fd % 10 == 0 or fd == 1:
            from bisim.ui.widgets import bgr_to_qimage
            qimg = bgr_to_qimage(preview_bgr) if preview_bgr is not None else None
            self.sig_progress.emit(pos, n, fd, ft, qimg)
            live = self._cum_done + fd * self._dt_accel
            self.sig_aging.emit(engine.format_aging(live))

    def _step_done(self, res: engine.RunResult):
        if res.stopped:
            self.stopped_result = res
            return
        self._cum_done = res.cumulative_aging_seconds
        self.sig_aging.emit(engine.format_aging(res.cumulative_aging_seconds))
        outputs = engine.write_recipe_outputs(
            result=res, folders=self.sequence.folders,
            sequence_name=self.sequence.sequence_name, model=self.model,
            model_param=self.sequence.recipes[int(res.nn) - 1].model_param,
            recipe=self.sequence.recipes[int(res.nn) - 1], log=self.logger)
        entry = ResultEntry(nn=int(res.nn), recipe_name=res.recipe_name,
                            is_movie=res.is_movie, outputs=outputs)
        self.sig_step_done.emit(entry.nn, entry)

    def run(self):
        self.sig_started.emit(len(self._indices))
        try:
            results = engine.run_sequence(
                sequence=self.sequence, model=self.model,
                only_index=self.only_index, control=self.control,
                progress_cb=self._progress, step_done_cb=self._step_done,
                log=self.logger, max_frames=self.max_frames, resume=self.resume)
        except Exception as e:  # noqa: BLE001  (UI にまとめて表示)
            self.sig_error.emit(f"{type(e).__name__}: {e}")
            return
        self.sig_finished.emit(any(r.stopped for r in results))


# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    sig_log = Signal(str)

    def __init__(self):
        super().__init__()
        self._apply_default_geometry()

        self.app_config = AppConfig.load_or_default(APP_CONFIG_PATH)
        i18n.LANG = self.app_config.language
        self.logger = Logger(max_mb=self.app_config.log_max_mb)

        self.sequence = Sequence()
        self._seq_path: Path | None = None
        self.results: dict[int, ResultEntry] = {}
        self.current_row: int | None = None
        self._stopped_states: dict[int, engine.StopState] = {}   # nn -> 停止状態（再開用）

        self.model = None
        self.control = engine.RunControl()
        self.worker: SimWorker | None = None
        self._max_frames = None
        self._t0 = 0.0
        self._paused_total = 0.0
        self._pause_t0: float | None = None

        self.tabs = QTabWidget()
        self.folders_tab = FoldersTab(self)
        self.steps_tab = StepsTab(self)
        self.config_tab = StepConfigTab(self)
        self.run_tab = RunTab(self)
        self.results_tab = ResultsTab(self)
        for w in (self.folders_tab, self.steps_tab, self.config_tab,
                  self.run_tab, self.results_tab):
            self.tabs.addTab(w, "")
        self.setCentralWidget(self.tabs)

        self._build_menus()
        self._elapsed = QTimer(self)
        self._elapsed.setInterval(200)
        self._elapsed.timeout.connect(
            lambda: self.run_tab.on_calc_time(self._calc_elapsed()))

        self.sig_log.connect(self.run_tab.append_log)
        self.logger.add_listener(self.sig_log.emit)

        self.retranslate_all()
        on_change(self.retranslate_all)
        self.steps_changed()
        self.statusBar().showMessage(t("status.ready"))
        self.logger.action(f"BI-sim {__version__} 起動")

    def _apply_default_geometry(self):
        """既定ウィンドウサイズ。縦は利用可能画面の約 80%（フルスクリーンにしない）。

        マウスでのリサイズ挙動（フォントは固定、画像エリアが伸縮）は変えない。
        """
        w, h = 1200, 760
        scr = QApplication.primaryScreen()
        if scr is not None:
            av = scr.availableGeometry()
            w = max(900, min(1200, int(av.width() * 0.92)))
            h = max(560, min(900, int(av.height() * 0.80)))
        self.resize(w, h)

    # ---- menus ----
    def _build_menus(self):
        self.menu_file = self.menuBar().addMenu("")
        self.act_open = self.menu_file.addAction("")
        self.act_open.triggered.connect(self.open_sequence)
        self.act_save = self.menu_file.addAction("")
        self.act_save.triggered.connect(self.save_sequence)
        self.act_save_as = self.menu_file.addAction("")
        self.act_save_as.triggered.connect(lambda: self.save_sequence(as_new=True))
        self.menu_file.addSeparator()
        self.act_recipe_load = self.menu_file.addAction("")
        self.act_recipe_load.triggered.connect(self.load_recipe)
        self.act_recipe_save = self.menu_file.addAction("")
        self.act_recipe_save.triggered.connect(self.save_recipe)
        self.menu_file.addSeparator()
        self.act_resume_load = self.menu_file.addAction("")
        self.act_resume_load.triggered.connect(self.load_stopped_and_resume)

        self.menu_lang = self.menuBar().addMenu("")
        grp = QActionGroup(self)
        grp.setExclusive(True)
        self.act_lang_ja = self.menu_lang.addAction("")
        self.act_lang_en = self.menu_lang.addAction("")
        for a, code in ((self.act_lang_ja, "ja"), (self.act_lang_en, "en")):
            a.setCheckable(True)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, c=code: self._set_lang(c))
        self.act_lang_ja.setChecked(i18n.LANG == "ja")
        self.act_lang_en.setChecked(i18n.LANG == "en")

    def _set_lang(self, code: str):
        set_lang(code)
        if self.app_config.language != i18n.LANG:
            self.app_config.language = i18n.LANG
            try:
                self.app_config.save(APP_CONFIG_PATH)
            except OSError:
                pass

    def retranslate_all(self):
        self.setWindowTitle(t("app.title"))
        for i, key in enumerate(_TAB_KEYS):
            self.tabs.setTabText(i, t(key))
        self.menu_file.setTitle(t("menu.file"))
        self.act_open.setText(t("menu.seq.open"))
        self.act_save.setText(t("menu.seq.save"))
        self.act_save_as.setText(t("menu.seq.save_as"))
        self.act_recipe_load.setText(t("menu.recipe.load"))
        self.act_recipe_save.setText(t("menu.recipe.save"))
        self.act_resume_load.setText(t("menu.resume.load"))
        self.menu_lang.setTitle(t("menu.lang"))
        self.act_lang_ja.setText(t("menu.lang.ja"))
        self.act_lang_en.setText(t("menu.lang.en"))
        self.act_lang_ja.setChecked(i18n.LANG == "ja")
        self.act_lang_en.setChecked(i18n.LANG == "en")
        for w in (self.folders_tab, self.steps_tab, self.config_tab,
                  self.run_tab, self.results_tab):
            w.retranslate()

    # ---- sequence / recipe I/O ----
    def open_sequence(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("menu.seq.open"), "", t("dlg.seq_filter"))
        if not path:
            return
        try:
            seq = Sequence.load(path)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, t("dlg.err.title"), t("dlg.load_fail", msg=str(e)))
            return
        self.sequence = seq
        self._seq_path = Path(path)
        self.results.clear()
        self._stopped_states.clear()
        self.results_tab.clear_results()
        self.current_row = 0 if seq.recipes else None
        self.folders_changed()
        self.steps_changed()
        self.logger.action(f"シーケンス読込: {Path(path).name}（レシピ {len(seq.recipes)}）")
        self.statusBar().showMessage(t("status.seq_opened", name=seq.sequence_name), 4000)

    def save_sequence(self, as_new: bool = False):
        path = self._seq_path
        if as_new or path is None:
            start = f"{self.sequence.sequence_name}{SEQ_EXT}"
            chosen, _ = QFileDialog.getSaveFileName(
                self, t("menu.seq.save_as"), start, t("dlg.seq_filter"))
            if not chosen:
                return
            path = Path(chosen)
        try:
            self.sequence.save(path)
        except OSError as e:
            QMessageBox.critical(self, t("dlg.err.title"), str(e))
            return
        self._seq_path = Path(path)
        self.logger.io("out", Path(path).name)
        self.logger.action(f"シーケンス保存: {Path(path).name}")
        self.statusBar().showMessage(t("status.seq_saved", path=str(path)), 4000)

    def load_recipe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("menu.recipe.load"), self.sequence.folders.get("model", ""),
            t("dlg.recipe_filter"))
        if not path:
            return
        try:
            recipe = Recipe.load(path)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, t("dlg.err.title"), t("dlg.load_fail", msg=str(e)))
            return
        self.sequence.recipes.append(recipe)
        self.current_row = len(self.sequence.recipes) - 1
        self.steps_changed()
        self.steps_tab._select_row(self.current_row)
        self.logger.action(f"レシピ読込: {Path(path).name}")
        self.statusBar().showMessage(t("status.recipe_loaded", name=recipe.recipe_name), 4000)

    def save_recipe(self):
        r = self._current_recipe()
        if r is None:
            QMessageBox.information(self, t("menu.recipe.save"), t("dlg.no_recipe"))
            return
        start = f"{r.recipe_name}{RECIPE_EXT}"
        path, _ = QFileDialog.getSaveFileName(
            self, t("menu.recipe.save"), start, t("dlg.recipe_filter"))
        if not path:
            return
        try:
            r.save(path)
        except OSError as e:
            QMessageBox.critical(self, t("dlg.err.title"), str(e))
            return
        self.logger.io("out", Path(path).name)
        self.statusBar().showMessage(t("status.recipe_saved", path=path), 4000)

    # ---- cross-tab coordination ----
    def _current_recipe(self) -> Recipe | None:
        rs = self.sequence.recipes
        if self.current_row is not None and 0 <= self.current_row < len(rs):
            return rs[self.current_row]
        return None

    def current_result(self) -> ResultEntry | None:
        return self.results.get(self.results_tab.current_idx())

    def folders_changed(self):
        self.folders_tab.refresh()

    def steps_changed(self):
        rs = self.sequence.recipes
        if self.current_row is not None and self.current_row >= len(rs):
            self.current_row = None if not rs else len(rs) - 1
        self.steps_tab.refresh()
        self.run_tab.refresh_steps()
        self.config_tab.load(self._current_recipe(), self.current_row)

    def select_step(self, row):
        self.current_row = row
        self.config_tab.load(self._current_recipe(), row)

    def goto_config(self):
        if self.current_row is None and self.sequence.recipes:
            self.steps_tab._select_row(0)
        self.tabs.setCurrentWidget(self.config_tab)

    def log_param_apply(self, recipe: Recipe):
        self.logger.action(f"レシピ '{recipe.recipe_name}' の設定を適用")

    # ---- run ----
    def _ensure_model(self) -> bool:
        if self.model is not None:
            return True
        try:
            self.model = engine.MasterModel()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, t("dlg.err.title"),
                                 f"{type(e).__name__}: {e}")
            return False
        return True

    def _calc_elapsed(self) -> float:
        """一時停止中の時間を除いた実PC計算時間。"""
        now = time.time()
        paused = self._paused_total + (now - self._pause_t0 if self._pause_t0 else 0.0)
        return now - self._t0 - paused

    def resumable_nn_for_selected(self) -> int | None:
        """④の選択ステップに再開できる停止結果があれば NN を返す。"""
        i = self.run_tab.selected_index()
        if i is None:
            return None
        st = self._stopped_states.get(i + 1)
        return i + 1 if (st is not None and st.is_movie) else None

    def _build_resume_plan(self, st: engine.StopState):
        out = Path(self.sequence.folders["output"])
        try:
            state = engine.StressState.load(*(out / st.stat_files[c] for c in "rgb"))
        except (OSError, KeyError, ValueError) as e:
            return None, str(e)
        video = out / st.movie_file if st.movie_file else None
        if video is not None and not video.exists():
            video = None
        return engine.ResumePlan(state=state, frames_done=st.frames_done,
                                 aging_seconds=st.aging_seconds, video=video), None

    def run_steps(self, mode: str):
        if self.worker is not None:
            return
        rs = self.sequence.recipes
        if not rs:
            QMessageBox.information(self, t("run.msg.title"), t("run.msg.nosteps"))
            return
        resume_plan = None
        if mode == "resume":
            only = self.run_tab.selected_index()
            st = self._stopped_states.get(only + 1) if only is not None else None
            if st is None:
                QMessageBox.information(self, t("run.resume.title"), t("run.msg.no_resume"))
                return
            resume_plan, err = self._build_resume_plan(st)
            if err:
                QMessageBox.warning(self, t("run.resume.title"), err)
                return
            ans = QMessageBox.question(
                self, t("run.resume.title"),
                t("run.resume.msg", name=st.recipe_name, f=st.frames_done,
                  ft=st.frames_total, aging=engine.format_aging(st.aging_seconds)))
            if ans != QMessageBox.StandardButton.Yes:
                return
            check = [only]
        elif mode == "selected":
            only = self.run_tab.selected_index()
            if only is None:
                QMessageBox.information(self, t("run.msg.title"), t("run.msg.nosteps"))
                return
            check = [only]
        else:
            only = None
            check = list(range(len(rs)))
        for i in check:
            if not rs[i].input_image or not rs[i].heatmap:
                QMessageBox.warning(self, t("run.msg.title"), t("run.msg.unset", n=i + 1))
                return
        if not self._ensure_model():
            return

        for i in check:
            set_recipe_status(rs[i], "pending")
        self.control.reset()
        self.tabs.setCurrentWidget(self.run_tab)
        self.run_tab.set_running(True)
        self._t0 = time.time()
        self._paused_total = 0.0
        self._pause_t0 = None
        self._elapsed.start()
        if mode == "resume":
            self.logger.action(t("run.log.resume", name=rs[check[0]].recipe_name,
                                 f=resume_plan.frames_done))

        self.worker = SimWorker(self.sequence, self.model, self.control, self.logger,
                                only_index=only, max_frames=self._max_frames,
                                resume=resume_plan)
        self.worker.sig_started.connect(self.run_tab.on_run_started)
        self.worker.sig_step.connect(self._on_step)
        self.worker.sig_progress.connect(self.run_tab.on_progress)
        self.worker.sig_aging.connect(self.run_tab.on_aging_time)
        self.worker.sig_step_done.connect(self._on_step_done)
        self.worker.sig_finished.connect(self._on_finished)
        self.worker.sig_error.connect(self._on_error)
        self.worker.start()

    def pause_run(self):
        self.control.request_pause()
        if self._pause_t0 is None:
            self._pause_t0 = time.time()
        self.logger.action("中断（メモリ保持・出力なし）")

    def resume_run(self):
        self.control.request_resume()
        if self._pause_t0 is not None:
            self._paused_total += time.time() - self._pause_t0
            self._pause_t0 = None
        self.logger.action("再開")

    def stop_run(self):
        self.control.request_stop()
        self.logger.action("停止要求（現フレーム終了後に停止）")

    def _on_step(self, pos, n, name):
        self.run_tab.on_step(pos, n, name)
        idx = self._step_index(pos)
        if idx is not None:
            set_recipe_status(self.sequence.recipes[idx], "running")
            self.steps_tab.refresh()

    def _step_index(self, pos: int) -> int | None:
        if self.worker is None:
            return None
        idxs = self.worker._indices
        return idxs[pos] if 0 <= pos < len(idxs) else None

    def _on_step_done(self, nn: int, entry: ResultEntry):
        self.results[nn] = entry
        if 0 <= nn - 1 < len(self.sequence.recipes):
            set_recipe_status(self.sequence.recipes[nn - 1], "done")
        self.steps_tab.refresh()
        self.results_tab.add_result(nn)

    def _cleanup_worker(self):
        self._elapsed.stop()
        if self.worker is not None:
            self.worker.wait()

    def _on_finished(self, stopped: bool):
        self._cleanup_worker()
        saved = None
        if stopped and self.worker is not None and self.worker.stopped_result is not None:
            saved = self._handle_stopped(self.worker.stopped_result)
        self.worker = None
        self.run_tab.on_finished(stopped)
        self.run_tab.update_resume_btn()
        if stopped:
            self.statusBar().showMessage(
                t("status.stopped") if saved else t("status.stopped_discard"), 5000)
        else:
            self.statusBar().showMessage(t("status.run_done"), 4000)

    def _handle_stopped(self, res: engine.RunResult) -> bool:
        """停止結果を保存要否ダイアログにかける。保存したら True。"""
        nn = int(res.nn)
        recipe = self.sequence.recipes[nn - 1] if 0 <= nn - 1 < len(self.sequence.recipes) else None
        if recipe is not None:
            set_recipe_status(recipe, "stopped")
            self.steps_tab.refresh()
        ans = QMessageBox.question(
            self, t("run.save.title"),
            t("run.save.msg", name=res.recipe_name, f=res.frames_absolute))
        if ans != QMessageBox.StandardButton.Yes:
            engine.discard_recipe_outputs(res)
            self.logger.action(f"{self.sequence.sequence_name}_{res.nn}_{res.recipe_name} 停止（破棄）")
            return False
        ts = datetime.now()
        outputs = engine.write_recipe_outputs(
            result=res, folders=self.sequence.folders,
            sequence_name=self.sequence.sequence_name, model=self.model,
            model_param=recipe.model_param if recipe else {},
            recipe=recipe, stopped_at=ts, log=self.logger)
        self.results[nn] = ResultEntry(nn=nn, recipe_name=res.recipe_name,
                                       is_movie=res.is_movie, outputs=outputs,
                                       stopped_at=naming.timestamp(ts))
        self.results_tab.add_result(nn)
        if "resume_state" in outputs:
            try:
                self._stopped_states[nn] = engine.StopState.load(outputs["resume_state"])
            except (OSError, ValueError):
                pass
        return True

    # ---- resume from a stopped result file (app が再起動された後など) ----
    def load_stopped_and_resume(self):
        if self.worker is not None:
            return
        start = self.sequence.folders.get("output", "")
        path, _ = QFileDialog.getOpenFileName(
            self, t("menu.resume.load"), start, t("dlg.resume_filter"))
        if not path:
            return
        try:
            st = engine.StopState.load(path)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, t("dlg.err.title"), t("dlg.load_fail", msg=str(e)))
            return
        if not st.is_movie:
            QMessageBox.information(self, t("run.resume.title"), t("dlg.resume_notmovie"))
            return
        idxs = [i for i, r in enumerate(self.sequence.recipes)
                if r.recipe_name == st.recipe_name]
        if not idxs:
            QMessageBox.warning(self, t("run.resume.title"),
                                t("dlg.resume_nomatch", name=st.recipe_name))
            return
        idx = idxs[0]
        self._stopped_states[idx + 1] = st
        self.current_row = idx
        self.steps_changed()
        self.steps_tab._select_row(idx)
        self.run_tab.cmb_sel.setCurrentIndex(idx)
        self.statusBar().showMessage(t("status.resumed", name=st.recipe_name), 4000)
        self.run_steps("resume")

    def _on_error(self, msg):
        self._cleanup_worker()
        self.worker = None
        self.run_tab.on_error(msg)
        self.logger.error(msg)
        QMessageBox.critical(self, t("dlg.err.title"), msg)

    # ---- lifecycle ----
    def closeEvent(self, e):  # noqa: N802
        if self.worker is not None:
            self.control.request_stop()
            self.control.request_resume()
            self.worker.wait(5000)
        self.results_tab._release_cap()
        try:
            self.app_config.save(APP_CONFIG_PATH)
        except OSError:
            pass
        super().closeEvent(e)


# --------------------------------------------------------------------------- #
def run(argv=None) -> int:
    import sys

    from bisim.ui.theme import apply_light_theme, setup_matplotlib

    setup_matplotlib()
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    apply_light_theme(app)
    win = MainWindow()
    win.show()
    return app.exec()
