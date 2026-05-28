#!/usr/bin/env python3
# ===========================================================
#  HRM Monitor — Boot Splash & Startup Checker
# ===========================================================
import os
import sys
import pathlib
import shutil
import tempfile
import threading
import urllib.request
import urllib.error
import zipfile
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QApplication, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QColor, QPen

from constants import DARK_STYLE, VERSION, GITHUB_OWNER, GITHUB_REPO


# ===========================================================
#  Tag colours & badges
# ===========================================================
_TAG_COLOR = {
    "ok":    "#44dd88",
    "warn":  "#ffaa33",
    "error": "#ff4444",
    "info":  "#4488cc",
    "run":   "#555555",
}
_TAG_BADGE = {
    "ok":    "  OK  ",
    "warn":  " WARN ",
    "error": " FAIL ",
    "info":  " INFO ",
    "run":   "  ··· ",
}


def _line_html(tag: str, msg: str) -> str:
    c = _TAG_COLOR.get(tag, "#888888")
    b = _TAG_BADGE.get(tag, "      ")
    return (
        f'<span style="color:#2d2d2d;">[</span>'
        f'<span style="color:{c};font-weight:bold;">{b}</span>'
        f'<span style="color:#2d2d2d;">]</span>'
        f'&nbsp;<span style="color:#aaaaaa;">{msg}</span>'
    )


# ===========================================================
#  Individual startup checks  (all run off-thread-safe;
#  they are called from the Qt main thread in the sequencer)
# ===========================================================

def _check_python() -> tuple[str, str]:
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if v < (3, 10):
        return "error", f"Python {ver} — requires 3.10 or newer"
    return "ok", f"Python {ver}"


def _check_pyqt6() -> tuple[str, str]:
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR
        return "ok", f"PyQt6 {PYQT_VERSION_STR}"
    except ImportError:
        return "error", "PyQt6 — MISSING (required)"


def _check_websocket() -> tuple[str, str]:
    try:
        import websocket
        v = getattr(websocket, "__version__", "")
        return "ok", f"websocket-client{(' ' + v) if v else ''}"
    except ImportError:
        return "error", "websocket-client — MISSING (required)"


def _check_pkg(import_name: str, display: str) -> tuple[str, str]:
    try:
        mod = __import__(import_name.replace("-", "_"))
        v   = getattr(mod, "__version__", "")
        return "ok", f"{display}{(' ' + v) if v else ''}"
    except ImportError:
        return "warn", f"{display} — not installed (optional)"


def _check_paho() -> tuple[str, str]:
    """paho-mqtt lives at paho.mqtt.client — needs special handling."""
    try:
        import paho.mqtt.client as _mc          # noqa: F401
        import paho as _p
        v = getattr(_p, "__version__", "")
        return "ok", f"paho-mqtt{(' ' + v) if v else ''}"
    except ImportError:
        return "warn", "paho-mqtt — not installed (optional)"


def _check_settings() -> tuple[str, str]:
    from PyQt6.QtCore import QSettings
    s = QSettings("HRMMonitor", "Settings")
    tok = s.value("token", "")
    if tok and tok != "YOUR_PULSOID_TOKEN":
        return "ok", "Configuration loaded (token found)"
    return "warn", "Configuration loaded (no Pulsoid token set yet)"


def _fetch_update() -> tuple[str, str, str | None]:
    """
    Runs in a background thread — hits GitHub releases API.
    Returns (tag, message, download_url_or_None).
    download_url is set only when a newer version is available.
    """
    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": f"HRMMonitor/{VERSION}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read())

        latest = data.get("tag_name", "").lstrip("v")
        if not latest:
            return "info", "Update check — no releases published yet", None

        def _vtuple(s: str):
            try:
                return tuple(int(x) for x in s.split("."))
            except Exception:
                return (0,)

        if _vtuple(latest) > _vtuple(VERSION):
            dl_url = data.get("zipball_url", "")
            return (
                "warn",
                f"New version v{latest} found — downloading update…",
                dl_url,
            )
        return "ok", f"v{VERSION} — up to date", None

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "info", "No releases published yet — you are on the latest build", None
        return "info", f"Update check failed (HTTP {e.code})", None
    except urllib.error.URLError:
        return "info", "Update check skipped (no internet connection)", None
    except Exception as e:
        return "info", f"Update check skipped ({type(e).__name__})", None


# ===========================================================
#  Pulse bar widget  — animates a moving bar at the bottom
# ===========================================================
class _PulseBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self._pos    = 0.0
        self._width  = 0.18   # fraction of total width
        self._timer  = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        self._pos += 0.012
        if self._pos > 1.0 + self._width:
            self._pos = -self._width
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Background rail
        p.fillRect(0, 0, w, h, QColor("#0d0000"))

        # Glowing bar
        x = int((self._pos) * w)
        bw = int(self._width * w)
        for i in range(bw):
            frac = i / bw
            # bell-curve fade
            alpha = int(255 * max(0.0, 1 - abs(2 * frac - 1) ** 1.5))
            p.fillRect(x + i, 0, 1, h, QColor(204, 0, 0, alpha))

    def stop(self):
        self._timer.stop()


# ===========================================================
#  Main splash window
# ===========================================================
class SplashBoot(QWidget):
    """
    Frameless boot splash.  Shows a line-by-line startup log,
    then emits ``finished`` so main.py can open SettingsWindow.
    """
    finished = pyqtSignal()

    # Base timings (full-speed). All scaled by _spd at runtime.
    _BASE_CHECKS = [
        (540, _check_python),
        (360, _check_pyqt6),
        (360, _check_websocket),
        (360, lambda: _check_pkg("pythonosc",  "python-osc")),
        (360, lambda: _check_pkg("openvr",     "openvr")),
        (360, lambda: _check_pkg("spotipy",    "spotipy")),
        (360, _check_paho),
        (480, _check_settings),
    ]
    _BASE_INTRO    = 2100
    _BASE_POLL     = 480
    _BASE_FINALISE = 1080
    _BASE_HOLD     = 10000

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setStyleSheet(DARK_STYLE)
        self.setFixedSize(520, 430)
        self._center()

        # ── Speed multiplier (dev fast-boot setting) ──────────────
        from PyQt6.QtCore import QSettings as _QS
        _s   = _QS("HRMMonitor", "Settings")
        _fb  = _s.value("fast_boot", False)
        _spd = 0.25 if (str(_fb).lower() == "true") else 1.0
        self._checks   = [(max(30, int(d * _spd)), fn)
                          for d, fn in self._BASE_CHECKS]
        self._t_intro   = max(100, int(self._BASE_INTRO    * _spd))
        self._t_poll    = max(60,  int(self._BASE_POLL     * _spd))
        self._t_final   = max(60,  int(self._BASE_FINALISE * _spd))
        self._t_hold    = max(200, int(self._BASE_HOLD     * _spd))

        # ── Root layout ──────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ───────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(
            "background: #080000; border-bottom: 1px solid #2a0000;"
        )
        header.setFixedHeight(80)
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(0, 12, 0, 10)
        hlay.setSpacing(4)

        self._heart_lbl = QLabel("❤")
        self._heart_lbl.setFont(QFont("Segoe UI Emoji", 20))
        self._heart_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._heart_lbl.setStyleSheet(
            "color: #cc0000; background: transparent; border: none;"
        )
        hlay.addWidget(self._heart_lbl)

        title_lbl = QLabel("HRM MONITOR")
        title_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title_lbl.setStyleSheet(
            "color: #cc0000; letter-spacing: 3px; background: transparent; border: none;"
        )
        hlay.addWidget(title_lbl)
        root.addWidget(header)

        # ── Version strip ─────────────────────────────────────────
        ver_lbl = QLabel(f"v{VERSION}  —  starting up")
        ver_lbl.setFont(QFont("Consolas", 9))
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ver_lbl.setStyleSheet(
            "color: #2d2d2d; background: #050000;"
            "border-bottom: 1px solid #1a0000; padding: 4px 0; border: none;"
        )
        root.addWidget(ver_lbl)

        # ── Log scroll area ───────────────────────────────────────
        self._log_inner = QWidget()
        self._log_inner.setStyleSheet("background: #060606; border: none;")
        self._log_layout = QVBoxLayout(self._log_inner)
        self._log_layout.setContentsMargins(22, 12, 22, 12)
        self._log_layout.setSpacing(4)
        self._log_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._log_inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: #060606; border: none;")
        self._scroll = scroll
        root.addWidget(scroll, stretch=1)

        # ── Animated pulse bar ────────────────────────────────────
        self._pulse = _PulseBar()
        root.addWidget(self._pulse)

        # ── Status label ──────────────────────────────────────────
        self._status_lbl = QLabel("Initializing…")
        self._status_lbl.setFont(QFont("Consolas", 9))
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setFixedHeight(26)
        self._status_lbl.setStyleSheet(
            "color: #333333; background: #040000;"
            "border-top: 1px solid #1a0000; padding: 0; border: none;"
        )
        root.addWidget(self._status_lbl)

        # ── State ─────────────────────────────────────────────────
        self._pkg_idx      = 0
        self._has_error    = False
        self._update_tag   = None   # set by background thread
        self._update_msg   = None
        self._update_url   = None   # non-None when a newer version exists
        self._update_done  = False
        self._install_result = None  # None=pending True=ok False=failed
        self._install_msg  = ""

        # ── Heart beat ────────────────────────────────────────────
        self._beat_on = False
        self._beat_timer = QTimer()
        self._beat_timer.timeout.connect(self._beat)
        self._beat_timer.start(480)

        # ── Kick off background update fetch ─────────────────────
        threading.Thread(target=self._bg_update, daemon=True).start()

        # ── Step timer (single-shot, re-armed each step) ──────────
        self._step_timer = QTimer()
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._pkg_step)

        # Short intro pause then start
        QTimer.singleShot(self._t_intro, self._pkg_step)

    # ── Centering ─────────────────────────────────────────────────
    def _center(self):
        geo = QApplication.primaryScreen().availableGeometry()
        self.move(
            geo.x() + (geo.width()  - self.width())  // 2,
            geo.y() + (geo.height() - self.height()) // 2,
        )

    # ── Heart animation ───────────────────────────────────────────
    def _beat(self):
        self._beat_on = not self._beat_on
        color = "#ff2222" if self._beat_on else "#550000"
        self._heart_lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )

    # ── Background update fetch ───────────────────────────────────
    def _bg_update(self):
        tag, msg, url     = _fetch_update()
        self._update_tag  = tag
        self._update_msg  = msg
        self._update_url  = url
        self._update_done = True

    # ── Package check sequencer ───────────────────────────────────
    def _pkg_step(self):
        """Run one package check, then schedule the next."""
        checks = self._checks
        if self._pkg_idx < len(checks):
            delay, fn = checks[self._pkg_idx]
            tag, msg  = fn()
            if tag == "error":
                self._has_error = True
            self._append(tag, msg)
            self._pkg_idx += 1
            self._step_timer.start(delay)
        else:
            # All package checks done — move to update step
            self._append("run", "Checking for updates…")
            self._status_lbl.setText("Checking for updates…")
            self._poll_update()

    # ── Wait for update thread ────────────────────────────────────
    def _poll_update(self):
        if self._update_done:
            self._append(self._update_tag, self._update_msg)
            if self._update_url:
                # New version found — kick off auto-update immediately
                QTimer.singleShot(400, lambda: self._start_auto_update(self._update_url))
            else:
                QTimer.singleShot(self._t_final, self._finalise)
        else:
            QTimer.singleShot(self._t_poll, self._poll_update)

    # ── Auto-updater ──────────────────────────────────────────────
    def _start_auto_update(self, url: str):
        self._append("run", "Downloading update…")
        self._status_lbl.setText("Downloading update…")
        threading.Thread(
            target=self._do_download, args=(url,), daemon=True
        ).start()
        QTimer.singleShot(300, self._poll_install)

    def _do_download(self, url: str):
        """Runs in a background thread. Downloads zip, extracts, copies files."""
        try:
            # Use __file__ (bootloader.py's own location) rather than sys.argv[0]
            # so the path is correct regardless of the working directory at launch.
            app_dir = pathlib.Path(__file__).parent.resolve()

            # ── Download zipball ──────────────────────────────────
            req = urllib.request.Request(
                url, headers={"User-Agent": f"HRMMonitor/{VERSION}"}
            )
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = pathlib.Path(tmp.name)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    shutil.copyfileobj(resp, tmp)

            # ── Extract & copy files ──────────────────────────────
            with zipfile.ZipFile(tmp_path) as zf:
                names = zf.namelist()
                # GitHub zipballs have one top-level dir: owner-repo-sha/
                inner = names[0].split("/")[0] if names else ""
                with tempfile.TemporaryDirectory() as tmpdir:
                    zf.extractall(tmpdir)
                    src = pathlib.Path(tmpdir) / inner
                    if not src.is_dir():
                        src = pathlib.Path(tmpdir)

                    copied = 0
                    for pattern in ("*.py", "*.txt", "*.spec"):
                        for f in src.glob(pattern):
                            shutil.copy2(f, app_dir / f.name)
                            copied += 1

            tmp_path.unlink(missing_ok=True)
            self._install_result = True
            self._install_msg    = f"Update installed — {copied} files replaced"

        except Exception as e:
            self._install_result = False
            self._install_msg    = f"Update failed: {e}"

    def _poll_install(self):
        """Poll until _do_download finishes, then show result and restart."""
        if self._install_result is None:
            QTimer.singleShot(200, self._poll_install)
            return

        if self._install_result:
            self._append("ok",   self._install_msg)
            self._append("ok",   "Restarting HRM Monitor…")
            self._status_lbl.setText("Restarting…")
            QTimer.singleShot(1800, self._do_restart)
        else:
            self._append("warn", self._install_msg)
            self._append("info", "Continuing with current version…")
            QTimer.singleShot(self._t_final, self._finalise)

    def _do_restart(self):
        """Replace the current process with a fresh one (picks up new files)."""
        self._beat_timer.stop()
        self._pulse.stop()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── Final lines ───────────────────────────────────────────────
    def _finalise(self):
        if self._has_error:
            self._append("warn", "Some required packages are missing — check requirements.txt")
        else:
            self._append("ok", "All systems nominal")

        self._status_lbl.setText("Launching HRM Monitor…")
        QTimer.singleShot(self._t_hold, self._launch)

    # ── Close & emit ─────────────────────────────────────────────
    def _launch(self):
        self._beat_timer.stop()
        self._pulse.stop()
        self.close()
        self.finished.emit()

    # ── Log helpers ───────────────────────────────────────────────
    def _append(self, tag: str, msg: str):
        lbl = QLabel()
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setText(_line_html(tag, msg))
        lbl.setFont(QFont("Consolas", 10))
        lbl.setStyleSheet("background: transparent; border: none; padding: 1px 0;")

        # Insert before the trailing stretch
        n = self._log_layout.count()
        self._log_layout.insertWidget(n - 1, lbl)

        # Scroll to bottom
        QTimer.singleShot(10, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))
        # Mirror to status bar (trimmed)
        self._status_lbl.setText(msg[:68] if len(msg) > 68 else msg)


# ===========================================================
#  Runtime Update Watcher — runs while the app is open
# ===========================================================
class UpdateWatcher(QObject):
    """
    Checks GitHub for a newer release every 15 minutes while the app
    is running.  Emits ``update_found(url)`` on the Qt main thread
    when a newer version is detected.
    """
    update_found = pyqtSignal(str)   # download URL of the new release

    _CHECK_INTERVAL_MS = 15 * 60 * 1000   # 15 minutes
    _FIRST_CHECK_MS    =  2 * 60 * 1000   # first check 2 min after launch

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._busy = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._kick)
        self._timer.start(self._CHECK_INTERVAL_MS)

        # First check fires a little after launch so the UI is settled
        QTimer.singleShot(self._FIRST_CHECK_MS, self._kick)

    def _kick(self):
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        """Runs off the main thread."""
        try:
            _, _, url = _fetch_update()
        except Exception:
            url = None
        self._busy = False
        if url:
            self.update_found.emit(url)
