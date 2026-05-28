#!/usr/bin/env python3
# ===========================================================
#  HRM Monitor — Entry Point
# ===========================================================
import sys
import pathlib
import traceback


# ===========================================================
#  Pre-boot: ensure core packages are installed
#  Runs BEFORE any PyQt6 import so it works even when
#  PyQt6 itself is missing.
# ===========================================================
def _ensure_core_deps() -> None:
    """
    Install PyQt6 and websocket-client if they're absent.
    Runs BEFORE any PyQt6 import so it works on a brand-new system.
    """
    import subprocess

    CORE = [
        ("PyQt6",     "PyQt6>=6.6.0"),
        ("websocket", "websocket-client>=1.7.0"),
    ]

    def _importable(name: str) -> bool:
        try:
            __import__(name)
            return True
        except ImportError:
            return False

    missing = [pkg for name, pkg in CORE if not _importable(name)]

    if not missing:
        return

    print("[HRM Monitor] Installing missing packages:", ", ".join(missing))
    print("[HRM Monitor] This may take a minute...")

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + missing,
    )

    if result.returncode == 0:
        print("[HRM Monitor] Done. Restarting...")
        # Spawn a fresh process and exit — os.execv is unreliable on Windows
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)
    else:
        print()
        print("[HRM Monitor] ERROR: pip install failed.")
        print("Please double-click install_deps.bat and try again.")
        print()
        input("Press Enter to close...")
        sys.exit(1)


_ensure_core_deps()

from PyQt6.QtWidgets import QApplication, QMessageBox


def _hide_console() -> None:
    """
    Detach / hide the Windows console so no black window appears.
    Works for both classic cmd and Windows Terminal.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # First try: hide the console window (classic cmd / conhost)
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        # Second: fully detach the console from this process so any
        # remaining attached terminal (Windows Terminal, VS Code, etc.)
        # stops receiving our stdout/stderr output.
        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass


def crash_log(exc: BaseException) -> None:
    desktop  = pathlib.Path.home() / "Desktop"
    log_path = desktop / "HRMMonitor_crash.log"
    try:
        with open(log_path, "w") as f:
            f.write(traceback.format_exc())
    except Exception:
        pass


def main() -> None:
    _hide_console()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    # Imports must happen AFTER QApplication exists —
    # they create QObjects (signal bus, widgets) at module level.
    from constants import DARK_STYLE
    from bootloader import SplashBoot
    from settings_window import SettingsWindow

    app.setStyleSheet(DARK_STYLE)

    # ── Boot splash ──────────────────────────────────────────────
    splash = SplashBoot()
    app._splash = splash          # keep alive

    def _on_boot_done():
        win = SettingsWindow()
        app._main_window = win    # keep alive
        win.show()

    splash.finished.connect(_on_boot_done)
    splash.show()

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
