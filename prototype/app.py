""" OLED 劣化シミュレータ — GUI プロトタイプ（UX 検証用・使い捨て）

    起動:  python prototype/app.py          （リポジトリ直下から）
    要件:  PySide6 / numpy / opencv-python / matplotlib
           劣化計算は source/main.py の関数をそのまま利用（source/ は無改変）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("QtAgg")
# matplotlib の日本語ラベルが豆腐にならないように（Windows 標準フォント）
matplotlib.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QTabWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sample import build_sample_steps, load_existing_results, sample_available
from sim_runner import run_step
from state import AppState
from tabs import FoldersTab, ResultsTab, RunTab, StepConfigTab, StepsTab


class SimWorker(QThread):
    sig_started = Signal(int)
    sig_step = Signal(int, int, str)                 # si, n, name
    sig_progress = Signal(int, int, int, int, object)  # si, n, frame, total, QImage|None
    sig_log = Signal(str)
    sig_step_done = Signal(int, object)              # idx, StepResult
    sig_finished = Signal(bool)                      # aborted
    sig_error = Signal(str)

    def __init__(self, jobs, folders):
        super().__init__()
        self.jobs = jobs        # list of (step, idx, prev_idx)
        self.folders = folders

    def run(self):
        from widgets import bgr_to_qimage
        n = len(self.jobs)
        self.sig_started.emit(n)
        try:
            for si, (step, idx, prev_idx) in enumerate(self.jobs):
                if self.isInterruptionRequested():
                    break
                self.sig_step.emit(si, n, step.name)

                def prog(f, ft, bgr, _si=si):
                    if f == ft or f % 10 == 0:
                        qimg = bgr_to_qimage(bgr) if bgr is not None else None
                        self.sig_progress.emit(_si, n, f, ft, qimg)

                res = run_step(
                    step, self.folders, idx, prev_idx,
                    progress_cb=prog,
                    abort_cb=self.isInterruptionRequested,
                    log_cb=self.sig_log.emit,
                )
                self.sig_step_done.emit(idx, res)
        except Exception as e:  # noqa: BLE001  (プロトタイプ: まとめて表示)
            self.sig_error.emit(f"{type(e).__name__}: {e}")
            return
        self.sig_finished.emit(self.isInterruptionRequested())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OLED 劣化シミュレータ (proto)")
        self.resize(1180, 820)

        self.state = AppState()
        self.results: dict[int, object] = {}
        self.current_row: int | None = None
        self.worker: SimWorker | None = None
        self._t0 = 0.0

        self.tabs = QTabWidget()
        self.folders_tab = FoldersTab(self)
        self.steps_tab = StepsTab(self)
        self.config_tab = StepConfigTab(self)
        self.run_tab = RunTab(self)
        self.results_tab = ResultsTab(self)
        self.tabs.addTab(self.folders_tab, "① フォルダ設定")
        self.tabs.addTab(self.steps_tab, "② 実行ステップ")
        self.tabs.addTab(self.config_tab, "③ ステップ設定")
        self.tabs.addTab(self.run_tab, "④ 実行")
        self.tabs.addTab(self.results_tab, "⑤ 結果")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("準備完了")

        m = self.menuBar().addMenu("デモ")
        m.addAction("サンプルステップ + 既存結果を読み込む").triggered.connect(
            lambda: self.load_demo())
        m.addAction("結果をクリア").triggered.connect(self.clear_results)

        self._elapsed = QTimer(self)
        self._elapsed.setInterval(200)
        self._elapsed.timeout.connect(lambda: self.run_tab.on_elapsed(time.time() - self._t0))

        self.steps_changed()
        self.load_demo(startup=True)

    # ---- demo / sample data ----
    def load_demo(self, startup: bool = False):
        folders = self.state.folders
        if not sample_available(folders):
            if not startup:
                QMessageBox.information(
                    self, "デモ",
                    "サンプル入力（source/dbi_common/mov_001_480x270.mp4 など）が見つかりません。\n"
                    "①フォルダ設定で入力画像フォルダを確認してください。")
            return

        if not self.state.steps:
            self.state.steps = build_sample_steps(folders)

        loaded = 0
        for idx, res in load_existing_results(folders).items():
            self.results[idx] = res
            if idx - 1 < len(self.state.steps):
                self.state.steps[idx - 1].status = "実行済（既存出力）"
            self.results_tab.add_result(idx)
            loaded += 1

        self.current_row = 0 if self.state.steps else None
        self.steps_changed()
        if self.current_row is not None:
            self.steps_tab._select_row(0)
        self.statusBar().showMessage(
            f"サンプル {len(self.state.steps)} ステップ / 既存結果 {loaded} 件を読み込みました", 5000)

    def clear_results(self):
        self.results.clear()
        self.results_tab.clear_results()
        for s in self.state.steps:
            s.status = "未実行"
        self.steps_tab.refresh()
        self.statusBar().showMessage("結果をクリアしました", 3000)

    # ---- cross-tab coordination ----
    def folders_changed(self):
        self.folders_tab.refresh()

    def steps_changed(self):
        self.steps_tab.refresh()
        if self.current_row is not None and self.current_row >= len(self.state.steps):
            self.current_row = None
        self.config_tab.load(
            self.state.steps[self.current_row] if self.current_row is not None else None,
            self.current_row,
        )

    def select_step(self, row):
        self.current_row = row
        self.config_tab.load(
            self.state.steps[row] if row is not None else None, row)

    def goto_config(self):
        if self.current_row is None and self.state.steps:
            self.steps_tab._select_row(0)
        self.tabs.setCurrentWidget(self.config_tab)

    # ---- run ----
    def run_steps(self, mode: str):
        if self.worker is not None:
            return
        steps = self.state.steps
        if not steps:
            QMessageBox.information(self, "実行", "ステップがありません。")
            return

        if mode == "all":
            rows = list(range(len(steps)))
        else:
            if self.current_row is None:
                QMessageBox.information(self, "実行", "②実行ステップでステップを選択してください。")
                return
            rows = [self.current_row]

        jobs = []
        for r in rows:
            s = steps[r]
            if not s.input_image or not s.heatmap:
                QMessageBox.warning(self, "実行",
                                    f"ステップ #{r + 1} の入力画像 / ヒートマップが未設定です。")
                return
            prev_idx = r if r >= 1 else None
            jobs.append((s, r + 1, prev_idx))

        self.tabs.setCurrentWidget(self.run_tab)
        self.run_tab.set_running(True)
        self._t0 = time.time()
        self._elapsed.start()

        self.worker = SimWorker(jobs, dict(self.state.folders))
        self.worker.sig_started.connect(self.run_tab.on_run_started)
        self.worker.sig_step.connect(self._on_step)
        self.worker.sig_progress.connect(self.run_tab.on_progress)
        self.worker.sig_log.connect(self.run_tab.append_log)
        self.worker.sig_step_done.connect(self._on_step_done)
        self.worker.sig_finished.connect(self._on_finished)
        self.worker.sig_error.connect(self._on_error)
        self.worker.start()

    def abort_run(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            self.run_tab.append_log("中断要求…（現在のフレーム終了後に停止）")

    def _on_step(self, si, n, name):
        self.run_tab.on_step(si, n, name)
        if si < len(self.state.steps):
            self.state.steps[si].status = "実行中"
            self.steps_tab.refresh()

    def _on_step_done(self, idx, res):
        self.results[idx] = res
        if idx - 1 < len(self.state.steps):
            self.state.steps[idx - 1].status = "実行済"
        self.steps_tab.refresh()
        self.results_tab.add_result(idx)

    def _cleanup_worker(self):
        self._elapsed.stop()
        if self.worker is not None:
            self.worker.wait()
            self.worker = None

    def _on_finished(self, aborted):
        self._cleanup_worker()
        self.run_tab.on_finished(aborted)
        self.statusBar().showMessage("中断" if aborted else "実行完了", 4000)

    def _on_error(self, msg):
        self._cleanup_worker()
        self.run_tab.on_error(msg)
        QMessageBox.critical(self, "実行エラー", msg)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
