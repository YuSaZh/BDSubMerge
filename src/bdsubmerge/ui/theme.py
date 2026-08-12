"""Small accessible theme layer using Qt palettes."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


class ThemeMode(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


def apply_theme(application: QApplication, mode: ThemeMode) -> None:
    if mode is ThemeMode.SYSTEM:
        application.setPalette(application.style().standardPalette())
        application.setStyleSheet("")
        return
    palette = QPalette()
    if mode is ThemeMode.DARK:
        palette.setColor(QPalette.ColorRole.Window, QColor("#202124"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#f1f3f4"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#17181a"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#292b2f"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#f1f3f4"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#303236"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#f1f3f4"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#3b82c4"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    else:
        palette.setColor(QPalette.ColorRole.Window, QColor("#f7f8fa"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#202124"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f0f2f5"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#202124"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#202124"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#1769aa"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    application.setPalette(palette)
    application.setStyleSheet(
        "QGroupBox { font-weight: 600; margin-top: 8px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        "QPushButton { min-height: 26px; padding: 2px 10px; }"
        "QLineEdit, QComboBox, QSpinBox { min-height: 26px; }"
    )
