"""④ 実行（仕様 5-④ / 7）

- 全ステップ実行 / 実行するステップを選択（**単一**）/ 中断・再開 / 停止
- 進捗（step i/N ＋ frame j/M ＋ ライブフレーム）
- 時間表示：計算時間 ＋ Aging時間（加速込み）
- 停止時：保存要否ダイアログ（MainWindow 側）
- ログ表示（T5 Logger の listener）

中断・再開＝メモリ保持のみ（ファイル出力なし）。停止＝保存確認のうえ日時付きで出力。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from bisim import engine
from bisim.model import Sequence
from bisim.ui.i18n import t
from bisim.ui.widgets import ImagePanel


class RunTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._running = False
        self._paused = False
        lay = QVBoxLayout(self)

        row1 = QHBoxLayout()
        self.b_all = QPushButton(t("run.btn.all"))
        self.b_all.clicked.connect(lambda: self.main.run_steps("all"))
        row1.addWidget(self.b_all)
        self.lbl_sel = QLabel(t("run.sel_which"))
        row1.addWidget(self.lbl_sel)
        self.cmb_sel = QComboBox()
        self.cmb_sel.currentIndexChanged.connect(lambda _=0: self.update_resume_btn())
        self.cmb_sel.currentIndexChanged.connect(lambda _=0: self._update_movie_info())
        row1.addWidget(self.cmb_sel, 1)
        self.b_sel = QPushButton(t("run.btn.sel"))
        self.b_sel.clicked.connect(lambda: self.main.run_steps("selected"))
        row1.addWidget(self.b_sel)
        lay.addLayout(row1)

        # 選択中レシピの動画情報（評価メモ #1）：フレーム数・fps・ネイティブ長さ・
        # 現在のACCEL_RATIOで1周回がどれだけのAging時間になるか。AGING_TIME を
        # 設定する前に「打ち切りになるか周回になるか」の見積りに使う
        self.lbl_movie_info = QLabel(t("run.movie_info_none"))
        self.lbl_movie_info.setWordWrap(True)
        lay.addWidget(self.lbl_movie_info)

        row2 = QHBoxLayout()
        self.b_pause = QPushButton(t("run.btn.pause"))
        self.b_pause.clicked.connect(self._toggle_pause)
        self.b_stop = QPushButton(t("run.btn.stop"))
        self.b_stop.clicked.connect(self.main.stop_run)
        self.b_resume_stop = QPushButton(t("run.btn.resume_stop"))
        self.b_resume_stop.clicked.connect(lambda: self.main.run_steps("resume"))
        row2.addWidget(self.b_pause)
        row2.addWidget(self.b_stop)
        row2.addWidget(self.b_resume_stop)
        row2.addStretch(1)
        lay.addLayout(row2)

        self.lbl_step = QLabel(t("run.idle"))
        self.pb_step = QProgressBar()
        self.lbl_frame = QLabel(t("run.dash"))
        self.pb_frame = QProgressBar()
        self.lbl_calc = QLabel(t("run.calc_time", s=0.0))
        self.lbl_aging = QLabel(t("run.aging_time", v=t("run.dash")))
        for w in (self.lbl_step, self.pb_step, self.lbl_frame, self.pb_frame,
                  self.lbl_calc, self.lbl_aging):
            lay.addWidget(w)

        self.preview = ImagePanel(t("run.preview"), min_h=200)
        lay.addWidget(self.preview, 1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(6000)
        lay.addWidget(self.log, 1)
        self.set_running(False)

    # -- steps combo --
    def refresh_steps(self):
        cur = self.cmb_sel.currentIndex()
        self.cmb_sel.blockSignals(True)
        self.cmb_sel.clear()
        for i, r in enumerate(self.main.sequence.recipes):
            self.cmb_sel.addItem(f"#{i + 1}  {Sequence.recipe_number(i)}  {r.recipe_name}")
        if 0 <= cur < self.cmb_sel.count():
            self.cmb_sel.setCurrentIndex(cur)
        self.cmb_sel.blockSignals(False)
        self.update_resume_btn()
        self._update_movie_info()

    def _update_movie_info(self):
        idx = self.selected_index()
        rs = self.main.sequence.recipes
        if idx is None or not (0 <= idx < len(rs)):
            self.lbl_movie_info.setText(t("run.movie_info_none"))
            return
        r = rs[idx]
        if r.is_eval:
            self.lbl_movie_info.setText(t("run.movie_info_eval"))
            return
        path = Path(self.main.sequence.folders["input_image"]) / r.input_image
        if not r.input_image or not path.exists():
            self.lbl_movie_info.setText(t("run.movie_info_none"))
            return
        if path.suffix.lower() != ".mp4":
            # 静止画 Aging：同じ絵を fps=1 で繰り返す（run_recipe と同じ見積り）
            accel = float(r.sim_param.get("ACCEL_RATIO", 0.0))
            dt_accel = accel / engine.STILL_AGING_FPS
            target_sec = float(r.sim_param.get("AGING_TIME", 0.0))
            if target_sec > 0:
                target_str = engine.format_aging(target_sec)
                n_frames = engine.aging_time_add_frames(dt_accel, target_sec)
            else:
                target_str, n_frames = t("run.movie_info_still_aging.zero"), 1
            self.lbl_movie_info.setText(t(
                "run.movie_info_still_aging", accel=f"{accel:g}",
                accel_time=engine.format_aging(dt_accel), target=target_str, frames=n_frames))
            return
        fps, frames = engine.movie_meta(path)
        if fps <= 0 or frames <= 0:
            self.lbl_movie_info.setText(t("run.movie_info_none"))
            return
        native_sec = frames / fps
        accel = float(r.sim_param.get("ACCEL_RATIO", 0.0))
        dt_accel = (1.0 / fps) * accel
        pass_sec = native_sec * accel
        target_sec = float(r.sim_param.get("AGING_TIME", 0.0))

        # 設定中の AGING_TIME を、1周回の時間と比べて「無制限／打切り／周回」を直接表示する
        # （③で AGING_TIME を変えたら、ここにそのまま反映される）。実際に処理される見積り
        # フレーム数も併記する（run_recipe と同じ aging_time_add_frames を使う。
        # ACCEL_RATIO が大きいと1フレーム=千秒規模になり、小さいAGING_TIMEはどれも
        # 「最低1フレーム」に丸められて区別できなくなることがあるため、数値を見せて誤解を防ぐ）
        n_frames = engine.aging_time_add_frames(dt_accel, target_sec)
        if target_sec <= 0:
            target_str = t("run.movie_info.unlimited_value")
            verdict = t("run.movie_info.verdict_unlimited")
        elif target_sec < pass_sec:
            target_str = engine.format_aging(target_sec)
            verdict = t("run.movie_info.verdict_truncate", n=n_frames)
        else:
            target_str = engine.format_aging(target_sec)
            n_passes = target_sec / pass_sec if pass_sec > 0 else 0.0
            verdict = t("run.movie_info.verdict_loop", n=f"{n_passes:.1f}", frames=n_frames)

        self.lbl_movie_info.setText(t(
            "run.movie_info", frames=frames, fps=fps,
            native=engine.format_aging(native_sec), accel=f"{accel:g}",
            accel_time=engine.format_aging(pass_sec),
            target=target_str, verdict=verdict))

    def update_resume_btn(self):
        if self._running or getattr(self.main, "run_tab", None) is not self:
            return   # MainWindow がまだ RunTab を保持していない（初期化中）
        self.b_resume_stop.setEnabled(self.main.resumable_nn_for_selected() is not None)

    def selected_index(self) -> int | None:
        i = self.cmb_sel.currentIndex()
        return i if 0 <= i < len(self.main.sequence.recipes) else None

    # -- running state --
    def set_running(self, on: bool):
        self._running = on
        if not on:
            self._paused = False
        self.b_all.setEnabled(not on)
        self.b_sel.setEnabled(not on)
        self.cmb_sel.setEnabled(not on)
        self.b_pause.setEnabled(on)
        self.b_stop.setEnabled(on)
        self.b_pause.setText(t("run.btn.pause"))
        if on:
            self.b_resume_stop.setEnabled(False)
        else:
            self.update_resume_btn()

    def _toggle_pause(self):
        if not self._running:
            return
        self._paused = not self._paused
        if self._paused:
            self.main.pause_run()
            self.b_pause.setText(t("run.btn.resume"))
            self.lbl_step.setText(t("run.state.paused"))
        else:
            self.main.resume_run()
            self.b_pause.setText(t("run.btn.pause"))

    # -- log listener --
    def append_log(self, line: str):
        self.log.appendPlainText(line)

    # -- worker callbacks (main thread) --
    def on_run_started(self, nsteps: int):
        self.log.clear()
        self.pb_step.setRange(0, max(nsteps, 1))
        self.pb_step.setValue(0)
        self.pb_frame.setRange(0, 1)
        self.pb_frame.setValue(0)
        self.lbl_aging.setText(t("run.aging_time", v=t("run.dash")))
        self.append_log(t("run.log.start", n=nsteps))

    def on_step(self, pos: int, n: int, name: str):
        self.lbl_step.setText(t("run.step", i=pos + 1, n=n, name=name))
        self.pb_step.setValue(pos)

    def on_progress(self, pos, n, f, ft, qimg):
        self.lbl_frame.setText(t("run.frame", f=f, ft=ft))
        self.pb_frame.setRange(0, max(ft, 1))
        self.pb_frame.setValue(f)
        if qimg is not None:
            self.preview.set_qimage(qimg)

    def on_calc_time(self, sec: float):
        self.lbl_calc.setText(t("run.calc_time", s=sec))

    def on_aging_time(self, text: str):
        self.lbl_aging.setText(t("run.aging_time", v=text))

    def on_finished(self, stopped: bool):
        self.pb_step.setValue(self.pb_step.maximum())
        self.lbl_step.setText(t("run.state.stopped") if stopped else t("run.state.done"))
        self.append_log(t("run.log.stopped") if stopped else t("run.log.done"))
        self.set_running(False)

    def on_error(self, msg: str):
        self.append_log(t("run.log.err", msg=msg))
        self.lbl_step.setText(t("run.state.err"))
        self.set_running(False)

    def retranslate(self):
        self.b_all.setText(t("run.btn.all"))
        self.b_sel.setText(t("run.btn.sel"))
        self.lbl_sel.setText(t("run.sel_which"))
        self.b_pause.setText(t("run.btn.resume") if self._paused else t("run.btn.pause"))
        self.b_stop.setText(t("run.btn.stop"))
        self.b_resume_stop.setText(t("run.btn.resume_stop"))
        self.preview.set_title(t("run.preview"))
        self._update_movie_info()
        if not self._running:
            self.lbl_step.setText(t("run.idle"))
            self.lbl_frame.setText(t("run.dash"))
