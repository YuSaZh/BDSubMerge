"""Desktop application entry point."""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from importlib import import_module
from os import environ
from pathlib import Path

from bdsubmerge import __version__
from bdsubmerge.runtime_logging import configure_runtime_logging, record_runtime_exception


def main(argv: Sequence[str] | None = None) -> int:
    """Start the high-DPI PySide6 desktop workspace."""
    configure_runtime_logging()
    try:
        return _run(argv)
    except Exception as error:
        record_runtime_exception("gui_runtime_failed", error)
        raise


def _run(argv: Sequence[str] | None = None) -> int:
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    from PySide6.QtWidgets import QApplication

    from bdsubmerge.ui import MainWindow, ThemeMode

    QCoreApplication.setOrganizationName("BDSubMerge")
    QCoreApplication.setApplicationName("BDSubMerge")
    QCoreApplication.setApplicationVersion(__version__)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    arguments = list(sys.argv if argv is None else argv)
    parser = ArgumentParser(add_help=False)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--expect-version")
    parser.add_argument("--capture-screenshot", type=Path)
    parser.add_argument("--locale", choices=("zh_CN", "en_US"))
    parser.add_argument("--theme", choices=tuple(mode.value for mode in ThemeMode))
    program = arguments[0] if arguments else "bdsubmerge-gui"
    options, qt_arguments = parser.parse_known_args(arguments[1:])
    if options.expect_version is not None and options.expect_version != __version__:
        return 2
    existing_application = QApplication.instance()
    if existing_application is None:
        application = QApplication([program, *qt_arguments])
    elif isinstance(existing_application, QApplication):
        application = existing_application
    else:
        raise RuntimeError("a non-GUI Qt application already exists")
    application.setStyle("Fusion")
    if options.capture_screenshot is not None and sys.platform == "win32":
        fonts_root = Path(environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
        font_filename = "msyh.ttc" if options.locale == "zh_CN" else "segoeui.ttf"
        font_path = fonts_root / font_filename
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        font_families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if not font_families:
            raise RuntimeError(f"could not load screenshot font: {font_path}")
        application.setFont(QFont(font_families[0]))
    window = MainWindow()
    if options.locale is not None:
        window.set_language(options.locale)
    if options.theme is not None:
        window.set_theme(ThemeMode(options.theme))
    if options.smoke_test:
        import_module("shinya.bd")
        import_module("pysubs2")
        window.show()
        application.processEvents()
        window.close()
        return 0
    if options.capture_screenshot is not None:
        destination = options.capture_screenshot
        destination.parent.mkdir(parents=True, exist_ok=True)
        window.resize(1440, 1000)
        window.show()
        application.processEvents()
        image = window.grab().toImage()
        if image.width() < 1200 or image.height() < 800:
            raise RuntimeError(
                f"unexpected screenshot size: {image.width()}x{image.height()}"
            )
        if not image.save(str(destination)):
            raise RuntimeError(f"could not save UI screenshot: {destination}")
        window.close()
        return 0
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
