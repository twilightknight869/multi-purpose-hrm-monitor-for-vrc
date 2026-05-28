#!/usr/bin/env python3
# ===========================================================
#  HRM Monitor — Entry Point
# ===========================================================
import sys
import pathlib
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox


def crash_log(exc: BaseException) -> None:
    desktop  = pathlib.Path.home() / "Desktop"
    log_path = desktop / "HRMMonitor_crash.log"
    try:
        with open(log_path, "w") as f:
            f.write(traceback.format_exc())
    except Exception:
        pass


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    # These must be imported AFTER QApplication exists —
    # they create QObjects (signal bus, widgets) at module level.
    from constants import DARK_STYLE
    from settings_window import SettingsWindow

    app.setStyleSheet(DARK_STYLE)

    win = SettingsWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        crash_log(e)
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            msg = QMessageBox()
            msg.setWindowTitle("HRM Monitor — Crash")
            msg.setText(f"The overlay crashed:\n\n{traceback.format_exc()}")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.exec()
        except Exception:
            pass
        raise
