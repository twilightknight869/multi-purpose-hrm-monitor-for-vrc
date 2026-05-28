# ===========================================================
#  HRM Monitor — Constants
# ===========================================================
import base64 as _b64

# App version & update-check endpoint
VERSION      = "1.5.2"
GITHUB_OWNER = "twilightknight869"                  # your GitHub username
GITHUB_REPO  = "Multi-Purpose-HRM-Monitor-For-VRC" # your repository name

# Pulsoid
TOKEN   = "YOUR_PULSOID_TOKEN"
WS_URL  = "wss://dev.pulsoid.net/api/v1/data/real_time"

# BPM thresholds
GRAPH_MAX_POINTS = 60
BPM_HIGH         = 140
BPM_MED          = 100

# Screen shake
SHAKE_HIGH_BPM = 160;  SHAKE_HIGH_INT = 12
SHAKE_MED_BPM  = 140;  SHAKE_MED_INT  = 7
SHAKE_LOW_BPM  = 120;  SHAKE_LOW_INT  = 4

# VR / OSC defaults
VRC_OSC_IP        = "127.0.0.1"
VRC_OSC_PORT      = 9000
VRC_OSC_HR_PARAM  = "/avatar/parameters/HR"
VRC_OSC_PCT_PARAM = "/avatar/parameters/HRPercent"
VRC_HR_MAX        = 255            # normalise HRPercent 0-1

# Chatbox
VRC_CHATBOX_INPUT    = "/chatbox/input"
CHATBOX_INTERVAL_SEC = 2.5         # VRChat rate-limits chatbox to ~3 s

# SteamVR wrist overlay
VR_OVERLAY_KEY   = "hrm_monitor_overlay"
VR_OVERLAY_NAME  = "HRM Monitor"
VR_OVERLAY_WIDTH = 0.12            # metres
VR_TEXTURE_SIZE  = 256             # px square
STEAMVR_POLL_SEC = 5

# Friend HR sharing — Ably Realtime (no port forwarding needed)
# Uses Ably's enterprise pub/sub over port 443 (never blocked).
# Get a free API key at https://ably.com — paste it in Settings.
# The host generates a 6-char room code; the friend enters it.
ABLY_CHANNEL_PREFIX = "hrm-monitor-v1"
ROOM_CODE_LEN       = 6

# Spotify polling (seconds)
SPOTIFY_POLL_SEC = 3

# Status auto-rotate interval (seconds)
STATUS_ROTATE_SEC = 30

# VRC Chatbox truncation limits
# HR line and status are now separated by \n so each sits on its own line.
# Per-line limits keep individual lines from wrapping; total limit stays at 144.
VRC_CHATBOX_MAX_LENGTH = 144  # VRChat API limit (multi-line messages are fine)
VRC_STATUS_MAX_LENGTH  = 60   # status line max chars (its own line, after \n)
VRC_HLINE_MAX_LENGTH   = 50   # HR line max chars (first line, before \n)

# Desktop overlay Spotify label truncation
OVERLAY_TRACK_MAX_LEN  = 25   # max chars for track name shown on overlay
OVERLAY_ARTIST_MAX_LEN = 20   # max chars for artist name shown on overlay

# Chatbox Spotify name truncation (applied before plugging into {track}/{artist})
CHATBOX_TRACK_MAX_LEN  = 20   # max chars for track name inside chatbox template
CHATBOX_ARTIST_MAX_LEN = 15   # max chars for artist name inside chatbox template

# Keyboard binding for overlay exit
OVERLAY_EXIT_KEY = "Escape"
OVERLAY_EXIT_KEY_CODE = 16777216  # Qt.Key.Key_Escape

# Developer beta key (base64 encoded to prevent casual discovery)
_DEV_KEY_ENCODED = "TQJMjQJLjQ=="  # Intentionally obscured — not the actual key
_DEV_KEY_ACTUAL = _b64.b64decode("MjIzNDc1").decode()  # Actual key decoded at runtime

# Default chatbox template — placeholders: {bpm} {bar} {tier} {icon} {track} {artist}
DEFAULT_CHATBOX_TEMPLATE = "{icon} {bpm} BPM  [{bar}]"
DEFAULT_STATUS_ENTRIES: list[str] = []   # user's favourited VRChat statuses

# -------------------------------------------------------
#  Qt Dark Stylesheet  —  HRM Monitor, MagicChatbox-style polish
# -------------------------------------------------------
DARK_STYLE = """
/* ── Base ───────────────────────────────────────────── */
QWidget {
    background-color: #0d0d0d;
    color: #d0d0d0;
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 13.5px;
}

/* ── Top-level navigation tab widget (#mode_tabs) ───── */
#mode_tabs {
    background: transparent;
}
#mode_tabs::pane {
    border: none;
    border-top: 1px solid #2a0000;
    border-radius: 0;
    background: #0d0d0d;
    top: -1px;
}
#mode_tabs QTabBar {
    background: #0d0d0d;
}
#mode_tabs QTabBar::tab {
    background: transparent;
    color: #664444;
    padding: 10px 30px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: bold;
    font-size: 13px;
    min-width: 90px;
}
#mode_tabs QTabBar::tab:selected {
    color: #ff4444;
    border-bottom: 2px solid #cc0000;
}
#mode_tabs QTabBar::tab:hover:!selected {
    color: #aa4444;
    border-bottom: 2px solid #440000;
}

/* ── Inner sub-navigation tabs ──────────────────────── */
QTabWidget::pane {
    border: 1px solid #2a0000;
    border-radius: 0 6px 6px 6px;
    background: #0d0d0d;
    top: -1px;
}
QTabBar::tab {
    background: #0f0000;
    color: #886666;
    padding: 7px 18px;
    border: 1px solid #2a0000;
    border-bottom: none;
    border-radius: 5px 5px 0 0;
    font-size: 13px;
    min-width: 52px;
}
QTabBar::tab:selected {
    background: #1a0000;
    color: #ff6666;
    border-bottom: 1px solid #1a0000;
}
QTabBar::tab:hover:!selected {
    background: #150000;
    color: #cc5555;
}

/* ── GroupBox ───────────────────────────────────────── */
QGroupBox {
    border: 1px solid #2a0000;
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    background: #0a0000;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #dd5555;
    font-weight: bold;
    font-size: 13px;
}

/* ── Buttons ────────────────────────────────────────── */
QPushButton {
    background: #160000;
    border: 1px solid #880000;
    border-radius: 8px;
    color: #ff5555;
    padding: 7px 18px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton:hover {
    background: #2a0000;
    border-color: #cc0000;
    color: #ff7777;
}
QPushButton:pressed { background: #440000; }

/* ── Line / Text inputs ─────────────────────────────── */
QLineEdit {
    background: #080808;
    border: 1px solid #2a0000;
    border-radius: 6px;
    color: #cccccc;
    padding: 5px 10px;
    selection-background-color: #550000;
}
QLineEdit:focus { border-color: #880000; }

QTextEdit {
    background: #080808;
    border: 1px solid #2a0000;
    border-radius: 6px;
    color: #cccccc;
    padding: 5px 10px;
    selection-background-color: #550000;
}
QTextEdit:focus { border-color: #880000; }

/* ── Slider ─────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 4px;
    background: #2a0000;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #cc0000;
    border: 2px solid #ff3333;
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #880000;
    border-radius: 2px;
}

/* ── Checkbox ───────────────────────────────────────── */
QCheckBox {
    spacing: 8px;
    color: #bbbbbb;
}
QCheckBox::indicator {
    border: 1px solid #880000;
    background: #080808;
    width: 15px;
    height: 15px;
    border-radius: 4px;
}
QCheckBox::indicator:checked {
    background: #cc0000;
    border-color: #ff3333;
}
QCheckBox::indicator:hover { border-color: #cc0000; }

/* ── List widget ────────────────────────────────────── */
QListWidget {
    background: #080808;
    border: 1px solid #2a0000;
    border-radius: 6px;
    color: #cccccc;
    outline: none;
}
QListWidget::item {
    padding: 5px 10px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background: #330000;
    color: #ff5555;
}
QListWidget::item:hover:!selected { background: #150000; }

/* ── SpinBox ────────────────────────────────────────── */
QSpinBox {
    background: #080808;
    border: 1px solid #2a0000;
    border-radius: 6px;
    color: #cccccc;
    padding: 4px 8px;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 18px;
    background: #1a0000;
    border: none;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background: #2d0000;
}

/* ── ComboBox ───────────────────────────────────────── */
QComboBox {
    background: #080808;
    border: 1px solid #2a0000;
    border-radius: 6px;
    color: #cccccc;
    padding: 4px 10px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: #080808;
    border: 1px solid #2a0000;
    color: #cccccc;
    selection-background-color: #330000;
}

/* ── Labels ─────────────────────────────────────────── */
QLabel { color: #bbbbbb; }

/* ── Scrollbars ─────────────────────────────────────── */
QScrollBar:vertical {
    background: #080808;
    width: 6px;
    margin: 0;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #3a0000;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background: #080808;
    height: 6px;
    margin: 0;
    border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background: #3a0000;
    border-radius: 3px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal { width: 0; }

QScrollArea { border: none; background: transparent; }

/* ── Frame separators ───────────────────────────────── */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {
    color: #2a0000;
    background: #2a0000;
}
"""
