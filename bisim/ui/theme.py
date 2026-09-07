"""明るいグレー基調のテーマ（仕様 2「明るいグレー基調に固定」）

``prototype/app.py`` の ``apply_light_theme`` ＋ matplotlib の配色/日本語フォント設定を移植。
"""
from __future__ import annotations


def setup_matplotlib() -> None:
    """matplotlib を明るい配色・日本語ラベル対応にする。QApplication 生成前に呼ぶ。"""
    import matplotlib

    matplotlib.use("QtAgg")
    rc = matplotlib.rcParams
    # Windows 標準の日本語フォント（無ければ sans-serif へフォールバック）
    rc["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "sans-serif"]
    rc["axes.unicode_minus"] = False
    rc["figure.facecolor"] = "#f2f3f5"
    rc["axes.facecolor"] = "#ffffff"
    rc["savefig.facecolor"] = "#f2f3f5"
    for k in ("text.color", "axes.labelcolor", "axes.titlecolor",
              "xtick.color", "ytick.color"):
        rc[k] = "#20242a"
    rc["axes.edgecolor"] = "#9aa0a6"


def apply_light_theme(app) -> None:
    """OS のダークテーマに関わらず明るいグレー基調に固定する。"""
    from PySide6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    bg, base, alt = QColor("#e9eaec"), QColor("#f7f8f9"), QColor("#eef0f2")
    text, dis, hl = QColor("#20242a"), QColor("#9aa0a6"), QColor("#3d6fb4")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, bg)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.AlternateBase, alt)
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.Button, bg)
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.ToolTipBase, base)
    pal.setColor(QPalette.ColorRole.ToolTipText, text)
    pal.setColor(QPalette.ColorRole.PlaceholderText, dis)
    pal.setColor(QPalette.ColorRole.Highlight, hl)
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, dis)
    app.setPalette(pal)
