"""5タブ（仕様 5）。

- :class:`FoldersTab`     ① フォルダ設定
- :class:`StepsTab`       ② 実行ステップ（順序操作のみ・ファイル指定不可）
- :class:`StepConfigTab`  ③ ステップ設定（レシピ編集）
- :class:`RunTab`         ④ 実行（全/選択・中断再開・停止）
- :class:`ResultsTab`     ⑤ 結果（プレビュー / 1・劣化率 / 累積時間 / 時系列 / A/B）
"""
from __future__ import annotations

from bisim.ui.tabs.folders import FoldersTab
from bisim.ui.tabs.results import ResultsTab
from bisim.ui.tabs.run import RunTab
from bisim.ui.tabs.step_config import StepConfigTab
from bisim.ui.tabs.steps import StepsTab

__all__ = ["FoldersTab", "StepsTab", "StepConfigTab", "RunTab", "ResultsTab"]
