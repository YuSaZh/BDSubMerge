"""Desktop application entry point."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from importlib import import_module


def main(argv: Sequence[str] | None = None) -> int:
    """Start the high-DPI PySide6 desktop workspace."""
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from bdsubmerge.ui import MainWindow

    QCoreApplication.setOrganizationName("BDSubMerge")
    QCoreApplication.setApplicationName("BDSubMerge")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    arguments = list(sys.argv if argv is None else argv)
    smoke_test = "--smoke-test" in arguments
    if smoke_test:
        arguments.remove("--smoke-test")
    existing_application = QApplication.instance()
    if existing_application is None:
        application = QApplication(arguments)
    elif isinstance(existing_application, QApplication):
        application = existing_application
    else:
        raise RuntimeError("a non-GUI Qt application already exists")
    application.setStyle("Fusion")
    window = MainWindow()
    if smoke_test:
        import_module("shinya.bd")
        import_module("pysubs2")
        window.show()
        application.processEvents()
        window.close()
        return 0
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
