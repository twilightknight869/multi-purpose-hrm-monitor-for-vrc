import sys
import json
import time
import random
import threading
import traceback
import pathlib
import os
import socket
import subprocess

import websocket

# Optional deps — imported at runtime so missing ones degrade gracefully
try:
    import openvr
    OPENVR_OK = True
except ImportError:
    OPENVR_OK = False

try:
    from pythonosc import udp_client as osc_udp
    OSC_OK = True
except ImportError:
    OSC_OK = False

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QSlider, QCheckBox,
    QGroupBox, QLineEdit, QListWidget, QListWidgetItem,
    QTabWidget, QSizePolicy, QSpacerItem
)
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QLinearGradient, QBrush, QPainterPath, QPolygon
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QSettings, QPoint, QRect


# ==========================================
# CONSTANTS
# ==========================================
TOKEN = "YOUR_PULSOID_TOKEN"
WS_URL = "wss://dev.pulsoid.net/api/v1/data/real_time"
GRAPH_MAX_POINTS = 60
BPM_HIGH = 140
BPM_MED  = 100
SHAKE_HIGH_BPM   = 160
SHAKE_HIGH_INT   = 12
SHAKE_MED_BPM    = 140
SHAKE_MED_INT    = 7
SHAKE_LOW_BPM    = 120
SHAKE_LOW_INT    = 4

# VR / OSC
VRC_OSC_IP        = "127.0.0.1"
VRC_OSC_PORT      = 9000
VRC_OSC_HR_PARAM  = "/avatar/parameters/HR"
VRC_OSC_PCT_PARAM = "/avatar/parameters/HRPercent"
VRC_HR_MAX        = 255          # used to normalise HRPercent 0-1

# Chatbox (KillFrenzy / boihanny style)
VRC_CHATBOX_INPUT    = "/chatbox/input"   # args: (message, send_immediately, trigger_sfx)
CHATBOX_INTERVAL_SEC = 2.5               # VRChat rate-limits chatbox to ~3 s
VR_OVERLAY_KEY    = "horror_hr_overlay"
VR_OVERLAY_NAME   = "Horror HR"
VR_OVERLAY_WIDTH  = 0.12         # metres wide on wrist
VR_TEXTURE_SIZE   = 256          # px square texture sent to OpenVR
STEAMVR_POLL_SEC  = 5            # how often to check if SteamVR started/stopped

# Friend viewer sharing
SHARE_PORT        = 5050          # TCP port friends connect to
SHARE_HOST        = "0.0.0.0"    # listen on all interfaces

DARK_STYLE = """
QWidget {
    background-color: #0d0d0d;
    color: #cccccc;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #3a0000;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px;
    color: #cc0000;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    background-color: #1a0000;
    border: 1px solid #cc0000;
    border-radius: 4px;
    color: #ff4444;
    padding: 6px 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #330000;
    color: #ff6666;
}
QPushButton:pressed {
    background-color: #550000;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #330000;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #cc0000;
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #880000;
    border-radius: 2px;
}
QCheckBox::indicator {
    border: 1px solid #cc0000;
    background: #1a0000;
    width: 14px;
    height: 14px;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background: #cc0000;
}
QListWidget {
    background: #0a0a0a;
    border: 1px solid #330000;
    border-radius: 4px;
    color: #cccccc;
}
QListWidget::item:selected {
    background: #330000;
    color: #ff4444;
}
QLineEdit {
    background: #0a0a0a;
    border: 1px solid #330000;
    border-radius: 4px;
    color: #cccccc;
    padding: 4px 8px;
}
QLineEdit:focus {
    border-color: #880000;
}
QTabWidget::pane {
    border: 1px solid #3a0000;
    border-radius: 4px;
}
QTabBar::tab {
    background: #1a0000;
    color: #cc0000;
    padding: 6px 16px;
    border: 1px solid #3a0000;
    border-bottom: none;
    border-radius: 4px 4px 0 0;
}
QTabBar::tab:selected {
    background: #330000;
    color: #ff4444;
}
QLabel {
    color: #bbbbbb;
}
"""


# ==========================================
# SIGNALS
# ==========================================
class SignalHandler(QObject):
    bpm_signal      = pyqtSignal(int)
    status_signal   = pyqtSignal(str)   # "connected" / "disconnected" / "error"
    mode_signal     = pyqtSignal(str)   # "desktop" / "vr"

signals = SignalHandler()


# ==========================================
# BPM GRAPH WIDGET
# ==========================================
class BPMGraph(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history: list[int] = []
        self.setMinimumHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def push(self, bpm: int):
        self.history.append(bpm)
        if len(self.history) > GRAPH_MAX_POINTS:
            self.history.pop(0)
        self.update()

    def paintEvent(self, event):
        if len(self.history) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        lo, hi = min(self.history), max(self.history)
        span = max(hi - lo, 20)

        def y_for(bpm):
            return int(h - ((bpm - lo) / span) * (h - 8) - 4)

        # Gradient fill under the line
        pts = [(int(i / (GRAPH_MAX_POINTS - 1) * w), y_for(v))
               for i, v in enumerate(self.history)]

        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor(200, 0, 0, 120))
        gradient.setColorAt(1.0, QColor(200, 0, 0, 0))

        fill_pts = [QPoint(pts[0][0], h)] + [QPoint(x, y) for x, y in pts] + [QPoint(pts[-1][0], h)]
        poly = QPolygon(fill_pts)
        p.setBrush(QBrush(gradient))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(poly)

        # Line
        pen = QPen(QColor(255, 60, 60), 2)
        p.setPen(pen)
        for i in range(1, len(pts)):
            p.drawLine(pts[i-1][0], pts[i-1][1], pts[i][0], pts[i][1])

        # Latest BPM dot
        lx, ly = pts[-1]
        p.setBrush(QBrush(QColor(255, 80, 80)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(lx - 4, ly - 4, 8, 8)

        p.end()


# ==========================================
# CUSTOM MESSAGE EDITOR
# ==========================================
class MessageEditor(QWidget):
    def __init__(self, messages: dict, parent=None):
        super().__init__(parent)
        self.messages = messages
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.lists: dict[str, QListWidget] = {}

        for tier in ("calm", "medium", "high"):
            container = QWidget()
            vl = QVBoxLayout(container)
            vl.setSpacing(6)

            lst = QListWidget()
            for msg in messages[tier]:
                lst.addItem(QListWidgetItem(msg))
            self.lists[tier] = lst
            vl.addWidget(lst)

            row = QHBoxLayout()
            entry = QLineEdit()
            entry.setPlaceholderText("Type a message…")
            add_btn = QPushButton("Add")
            del_btn = QPushButton("Remove")

            add_btn.setFixedWidth(60)
            del_btn.setFixedWidth(80)

            add_btn.clicked.connect(lambda _, t=tier, e=entry: self._add(t, e))
            del_btn.clicked.connect(lambda _, t=tier: self._remove(t))

            row.addWidget(entry)
            row.addWidget(add_btn)
            row.addWidget(del_btn)
            vl.addLayout(row)

            self.tabs.addTab(container, tier.capitalize())

        layout.addWidget(self.tabs)

    def _add(self, tier: str, entry: QLineEdit):
        text = entry.text().strip()
        if text:
            self.lists[tier].addItem(QListWidgetItem(text))
            self.messages[tier].append(text)
            entry.clear()

    def _remove(self, tier: str):
        lst = self.lists[tier]
        row = lst.currentRow()
        if row >= 0:
            lst.takeItem(row)
            self.messages[tier].pop(row)

    def get_messages(self) -> dict:
        return self.messages


# ==========================================
# SETTINGS WINDOW
# ==========================================
class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("💀 Horror Overlay")
        self.setMinimumSize(400, 320)
        self.resize(440, 480)
        self.setStyleSheet(DARK_STYLE)

        self.settings = QSettings("HorrorOverlay", "Settings")
        self.messages = {k: list(v) for k, v in DEFAULT_MESSAGES.items()}

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 10, 12, 10)

        # ---- Title bar ----
        title = QLabel("☠  HORROR HEART RATE OVERLAY")
        title.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #cc0000; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        credit = QLabel("made by CRIMSON  •  dc: crimsondreamz")
        credit.setFont(QFont("Consolas", 9))
        credit.setStyleSheet("color: #550000; letter-spacing: 1px;")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        root.addWidget(credit)

        # ---- Top-level tabs: Broadcaster | Viewer ----
        self.mode_tabs = QTabWidget()
        self.mode_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.mode_tabs, stretch=1)

        self.mode_tabs.addTab(self._build_broadcaster_tab(), "📡  Broadcaster")
        self.mode_tabs.addTab(self._build_viewer_tab(),      "👁  Viewer")

        # Restore last-used tab
        self.mode_tabs.setCurrentIndex(int(self.settings.value("last_tab", 0)))

    # ------------------------------------------------------------------
    # TAB BUILDERS
    # ------------------------------------------------------------------
    def _build_broadcaster_tab(self) -> QWidget:
        """Full overlay tab — token, appearance, options, VR/OSC, messages."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # Token
        tok_group = QGroupBox("Pulsoid Token")
        tok_layout = QHBoxLayout(tok_group)
        tok_layout.setContentsMargins(8, 4, 8, 4)
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Paste your Pulsoid access token here")
        self.token_input.setText(self.settings.value("token", TOKEN))
        tok_layout.addWidget(self.token_input)
        layout.addWidget(tok_group)

        # Appearance + Options side by side
        mid_row = QHBoxLayout()
        mid_row.setSpacing(6)

        appear_group = QGroupBox("Appearance")
        ag_layout = QVBoxLayout(appear_group)
        ag_layout.setContentsMargins(8, 4, 8, 4)
        ag_layout.setSpacing(4)
        self.overlay_slider = self._make_slider(ag_layout, "Scale",   50, 200, 100, "%",  "overlay_scale")
        self.heart_slider   = self._make_slider(ag_layout, "Heart",   60, 180,  95, "pt", "heart_size")
        self.opacity_slider = self._make_slider(ag_layout, "Opacity", 20, 100, 100, "%",  "opacity")
        mid_row.addWidget(appear_group, stretch=2)

        opt_group = QGroupBox("Options")
        og_layout = QVBoxLayout(opt_group)
        og_layout.setContentsMargins(8, 4, 8, 4)
        og_layout.setSpacing(4)
        self.shake_checkbox = QCheckBox("Screen shake")
        self.shake_checkbox.setChecked(self._bool_setting("shake", True))
        og_layout.addWidget(self.shake_checkbox)
        self.share_checkbox = QCheckBox("Broadcast HR\n(port 5050)")
        self.share_checkbox.setChecked(self._bool_setting("share_enabled", False))
        og_layout.addWidget(self.share_checkbox)
        og_layout.addStretch()
        mid_row.addWidget(opt_group, stretch=1)

        layout.addLayout(mid_row)

        # VR / OSC (compact two-column)
        vr_group = QGroupBox("SteamVR + VRChat OSC")
        vg_layout = QVBoxLayout(vr_group)
        vg_layout.setContentsMargins(8, 4, 8, 4)
        vg_layout.setSpacing(4)

        vr_osc_row = QHBoxLayout()
        self.vr_checkbox = QCheckBox("SteamVR wrist overlay")
        self.vr_checkbox.setChecked(self._bool_setting("vr_enabled", True))
        if not OPENVR_OK:
            self.vr_checkbox.setText("SteamVR (install openvr)")
            self.vr_checkbox.setChecked(False)
            self.vr_checkbox.setEnabled(False)
        vr_osc_row.addWidget(self.vr_checkbox)

        self.osc_checkbox = QCheckBox("VRChat OSC")
        self.osc_checkbox.setChecked(self._bool_setting("osc_enabled", True))
        if not OSC_OK:
            self.osc_checkbox.setText("OSC (install python-osc)")
            self.osc_checkbox.setChecked(False)
            self.osc_checkbox.setEnabled(False)
        vr_osc_row.addWidget(self.osc_checkbox)
        vg_layout.addLayout(vr_osc_row)

        self.chatbox_checkbox = QCheckBox("Send HR to VRChat chatbox (boihanny style)")
        self.chatbox_checkbox.setChecked(self._bool_setting("chatbox_enabled", False))
        if not OSC_OK:
            self.chatbox_checkbox.setChecked(False)
            self.chatbox_checkbox.setEnabled(False)
        vg_layout.addWidget(self.chatbox_checkbox)

        osc_addr_row = QHBoxLayout()
        osc_addr_row.addWidget(QLabel("IP:"))
        self.osc_ip = QLineEdit(str(self.settings.value("osc_ip", VRC_OSC_IP)))
        osc_addr_row.addWidget(self.osc_ip, stretch=1)
        osc_addr_row.addWidget(QLabel("Port:"))
        self.osc_port = QLineEdit(str(self.settings.value("osc_port", str(VRC_OSC_PORT))))
        self.osc_port.setFixedWidth(52)
        osc_addr_row.addWidget(self.osc_port)
        vg_layout.addLayout(osc_addr_row)

        layout.addWidget(vr_group)

        # Messages (collapsible-ish via stretch)
        msg_group = QGroupBox("Custom Horror Messages")
        mg_layout = QVBoxLayout(msg_group)
        mg_layout.setContentsMargins(8, 4, 8, 4)
        self.msg_editor = MessageEditor(self.messages)
        mg_layout.addWidget(self.msg_editor)
        layout.addWidget(msg_group, stretch=1)

        # Start button
        start_btn = QPushButton("▶  START OVERLAY")
        start_btn.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        start_btn.setFixedHeight(38)
        start_btn.clicked.connect(self.start_overlay)
        layout.addWidget(start_btn)

        return page

    def _build_viewer_tab(self) -> QWidget:
        """Viewer tab — enter a host IP and watch someone else's HR."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addStretch()

        # Heading
        lbl = QLabel("Watch a friend's heart rate")
        lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #cc0000;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

        sub = QLabel("Ask them to enable \"Broadcast HR\" and share their IP.")
        sub.setStyleSheet("color: #666666; font-size: 11px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        layout.addWidget(sub)

        layout.addSpacing(8)

        # IP entry
        ip_group = QGroupBox("Host IP Address")
        ip_layout = QVBoxLayout(ip_group)
        ip_layout.setContentsMargins(10, 6, 10, 10)
        ip_layout.setSpacing(6)

        self.viewer_ip_input = QLineEdit()
        self.viewer_ip_input.setPlaceholderText("e.g. 192.168.1.42  or  73.12.34.56")
        self.viewer_ip_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_ip_input.setFont(QFont("Consolas", 12))
        saved_ip = self.settings.value("viewer_ip", "")
        self.viewer_ip_input.setText(saved_ip)
        ip_layout.addWidget(self.viewer_ip_input)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port:"))
        self.viewer_port_input = QLineEdit(str(self.settings.value("viewer_port", str(SHARE_PORT))))
        self.viewer_port_input.setFixedWidth(60)
        port_row.addWidget(self.viewer_port_input)
        port_row.addStretch()
        ip_layout.addLayout(port_row)

        layout.addWidget(ip_group)

        # Watch button
        watch_btn = QPushButton("👁  CONNECT & WATCH")
        watch_btn.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        watch_btn.setFixedHeight(38)
        watch_btn.clicked.connect(self._launch_viewer)
        layout.addWidget(watch_btn)

        layout.addSpacing(12)

        # Your IP hint
        hint_group = QGroupBox("Your IP  (share this if you're the host)")
        hint_layout = QHBoxLayout(hint_group)
        hint_layout.setContentsMargins(10, 4, 10, 6)
        self.local_ip_lbl = QLabel(self._get_local_ip())
        self.local_ip_lbl.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.local_ip_lbl.setStyleSheet("color: #cc0000;")
        self.local_ip_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.local_ip_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_layout.addWidget(self.local_ip_lbl)
        layout.addWidget(hint_group)

        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def _make_slider(self, layout, label_text, lo, hi, default, unit, key=None):
        row = QHBoxLayout()
        row.setSpacing(4)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(48)
        val_lbl = QLabel(f"{default}{unit}")
        val_lbl.setFixedWidth(42)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(lo)
        slider.setMaximum(hi)
        if key is None:
            key = label_text.lower().replace(" ", "_")
        slider.setValue(int(self.settings.value(key, default)))
        slider.valueChanged.connect(lambda v, vl=val_lbl, u=unit: vl.setText(f"{v}{u}"))
        row.addWidget(lbl)
        row.addWidget(slider)
        row.addWidget(val_lbl)
        layout.addLayout(row)
        return slider

    def _bool_setting(self, key: str, default: bool) -> bool:
        """QSettings stores booleans as 'true'/'false' strings — convert safely."""
        v = self.settings.value(key, default)
        if isinstance(v, str):
            return v.lower() == "true"
        return bool(v)

    @staticmethod
    def _get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "unavailable"

    def _launch_viewer(self):
        host = self.viewer_ip_input.text().strip()
        if not host:
            return
        try:
            port = int(self.viewer_port_input.text().strip() or SHARE_PORT)
        except ValueError:
            port = SHARE_PORT
        self.settings.setValue("viewer_ip",   host)
        self.settings.setValue("viewer_port", port)
        viewer = ViewerOverlay(host, port)
        QApplication.instance()._viewer = viewer
        viewer.show()
        self.hide()

    # ------------------------------------------------------------------
    # START (broadcaster)
    # ------------------------------------------------------------------
    def start_overlay(self):
        self.settings.setValue("last_tab", self.mode_tabs.currentIndex())
        cfg = {
            "token":         self.token_input.text().strip(),
            "overlay_scale": self.overlay_slider.value() / 100,
            "heart_size":    self.heart_slider.value(),
            "opacity":       self.opacity_slider.value() / 100,
            "shake_enabled": self.shake_checkbox.isChecked(),
            "messages":      self.msg_editor.get_messages(),
            "vr_enabled":    self.vr_checkbox.isChecked() and OPENVR_OK,
            "osc_enabled":   self.osc_checkbox.isChecked() and OSC_OK,
            "osc_ip":        self.osc_ip.text().strip() or VRC_OSC_IP,
            "osc_port":      int(self.osc_port.text().strip() or VRC_OSC_PORT),
            "share_enabled": self.share_checkbox.isChecked(),
            "chatbox_enabled": self.chatbox_checkbox.isChecked() and OSC_OK,
        }
        # Persist
        self.settings.setValue("token",           cfg["token"])
        self.settings.setValue("overlay_scale",   self.overlay_slider.value())
        self.settings.setValue("heart_size",      self.heart_slider.value())
        self.settings.setValue("opacity",         self.opacity_slider.value())
        self.settings.setValue("shake",           cfg["shake_enabled"])
        self.settings.setValue("vr_enabled",      cfg["vr_enabled"])
        self.settings.setValue("osc_enabled",     cfg["osc_enabled"])
        self.settings.setValue("osc_ip",          cfg["osc_ip"])
        self.settings.setValue("osc_port",        cfg["osc_port"])
        self.settings.setValue("share_enabled",   cfg["share_enabled"])
        self.settings.setValue("chatbox_enabled", cfg["chatbox_enabled"])

        # Store on app so it isn't garbage-collected when this window closes
        overlay = Overlay(cfg)
        QApplication.instance()._overlay = overlay
        overlay.show()

        threading.Thread(target=websocket_thread, args=(cfg["token"],), daemon=True).start()

        if cfg["osc_enabled"]:
            threading.Thread(target=osc_thread, args=(cfg,), daemon=True).start()

        if cfg["vr_enabled"]:
            threading.Thread(target=steamvr_watcher_thread, args=(cfg,), daemon=True).start()

        if cfg["share_enabled"]:
            threading.Thread(target=share_server_thread, daemon=True).start()

        self.hide()


# ==========================================
# HEART WIDGET  (QPainter, squeeze + ripple)
# ==========================================
class HeartWidget(QWidget):
    """Draws a vector heart with squeeze-on-beat and expanding ripple rings."""

    # Normalised cubic-bezier heart path, centred at (0,0), radius ~1.0
    # Two lobes: left and right, meeting at top-centre and bottom tip
    _HEART_PATH_CMDS = None  # built once in _build_path()

    def __init__(self, size_px: int, parent=None):
        super().__init__(parent)
        self.size_px       = size_px
        self.scale_x       = 1.0   # current squeeze x
        self.scale_y       = 1.0   # current squeeze y
        self.ripples: list[dict] = []  # [{r, alpha}]

        fixed = size_px + 40        # extra room for ripples
        self.setFixedSize(fixed, fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Animation ticker at ~60 fps
        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(16)

        # Beat sequencer — fires every beat_interval ms
        self._beat_interval = 1000
        self._beat_timer = QTimer()
        self._beat_timer.timeout.connect(self._on_beat)
        self._beat_timer.start(self._beat_interval)

        # Squeeze state machine
        self._sq_t        = 1.0    # 0.0 → 1.0 through the squeeze curve
        self._sq_speed    = 0.0    # fraction per 16 ms tick
        self._sq_amount   = 0.28   # max squeeze depth
        self._sq_phase    = 'idle' # 'in' | 'out' | 'idle'

        # Heart fill colour (animated toward target)
        self._color       = QColor(200, 40, 40)
        self._target_color= QColor(200, 40, 40)

        self._path = self._build_path()

    def set_bpm(self, bpm: int):
        interval = int(60000 / max(30, min(bpm, 220)))
        if interval != self._beat_interval:
            self._beat_interval = interval
            self._beat_timer.start(interval)
        # Colour target
        if bpm >= BPM_HIGH:
            self._target_color = QColor(255, 30, 30)
            self._sq_amount    = 0.38
        elif bpm >= BPM_MED:
            self._target_color = QColor(230, 120, 20)
            self._sq_amount    = 0.30
        else:
            self._target_color = QColor(200, 40, 40)
            self._sq_amount    = 0.22

    def _on_beat(self):
        # Kick off squeeze animation
        self._sq_t     = 0.0
        self._sq_phase = 'in'
        # Beat duration: use 35 % of interval for squeeze in+out
        beat_frac = self._beat_interval * 0.35
        steps_total = beat_frac / 16.0
        self._sq_speed = 1.0 / max(steps_total, 1)
        # Add two ripple rings, second delayed
        self.ripples.append({'r': 0.0, 'alpha': 200, 'delay': 0})
        self.ripples.append({'r': 0.0, 'alpha': 160, 'delay': 8})

    def _tick(self):
        # Advance squeeze
        if self._sq_phase == 'in':
            self._sq_t += self._sq_speed * 2
            if self._sq_t >= 1.0:
                self._sq_t = 1.0
                self._sq_phase = 'out'
            t = self._sq_t
            depth = self._sq_amount * (1.0 - t)
            self.scale_x = 1.0 + depth * 0.55
            self.scale_y = 1.0 - depth
        elif self._sq_phase == 'out':
            self._sq_t += self._sq_speed * 1.4
            if self._sq_t >= 2.0:
                self._sq_t    = 2.0
                self._sq_phase = 'idle'
                self.scale_x  = 1.0
                self.scale_y  = 1.0
            else:
                t = self._sq_t - 1.0  # 0→1
                depth = self._sq_amount * (1.0 - t) * 0.4
                self.scale_x = 1.0 + depth * 0.3
                self.scale_y = 1.0 - depth * 0.5

        # Advance ripples
        alive = []
        for rip in self.ripples:
            if rip['delay'] > 0:
                rip['delay'] -= 1
                alive.append(rip)
                continue
            rip['r']     += 1.6
            rip['alpha'] -= 7
            if rip['alpha'] > 0:
                alive.append(rip)
        self.ripples = alive

        # Lerp colour
        def lerp_ch(a, b, t): return int(a + (b - a) * t)
        t = 0.08
        self._color = QColor(
            lerp_ch(self._color.red(),   self._target_color.red(),   t),
            lerp_ch(self._color.green(), self._target_color.green(), t),
            lerp_ch(self._color.blue(),  self._target_color.blue(),  t),
        )

        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width()  / 2
        cy = self.height() / 2
        r  = self.size_px  / 2

        # --- Ripple rings ---
        for rip in self.ripples:
            if rip['delay'] > 0:
                continue
            rip_color = QColor(self._color)
            rip_color.setAlpha(rip['alpha'])
            pen = QPen(rip_color, 1.8)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            rad = r + rip['r']
            p.drawEllipse(
                int(cx - rad), int(cy - rad),
                int(rad * 2),  int(rad * 2)
            )

        # --- Heart shape ---
        p.save()
        p.translate(cx, cy)
        p.scale(self.scale_x * r, self.scale_y * r)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._color))
        p.drawPath(self._path)

        # Highlight lobe
        hi = QColor(255, 255, 255, 45)
        p.setBrush(QBrush(hi))
        p.setPen(Qt.PenStyle.NoPen)
        # small ellipse top-left of heart
        hi_path = self._build_highlight()
        p.drawPath(hi_path)

        p.restore()
        p.end()

    @staticmethod
    def _build_path():
        """Unit heart centred at (0,0), fits inside ±1.0."""
        path = QPainterPath()
        # Heart via two cubic beziers
        # Tip at bottom (0, 0.9), top-centre notch at (0, -0.3)
        path.moveTo(0, 0.9)
        # Left lobe
        path.cubicTo(-0.05, 0.6,  -1.0,  0.4,  -1.0, -0.1)
        path.cubicTo(-1.0, -0.6,  -0.5, -0.9,   0.0, -0.3)
        # Right lobe
        path.cubicTo( 0.5, -0.9,   1.0, -0.6,   1.0, -0.1)
        path.cubicTo( 1.0,  0.4,   0.05, 0.6,   0.0,  0.9)
        path.closeSubpath()
        return path

    @staticmethod
    def _build_highlight():
        path = QPainterPath()
        path.addEllipse(-0.55, -0.65, 0.35, 0.22)
        return path


# ==========================================
# OVERLAY WINDOW
# ==========================================
class Overlay(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg           = cfg
        self.overlay_scale = cfg["overlay_scale"]
        self.heart_size    = cfg["heart_size"]
        self.shake_enabled = cfg["shake_enabled"]
        self.messages      = cfg["messages"]

        # Session stats
        self.session_min   = None
        self.session_max   = None
        self.last_bpm      = 0
        self.last_msg_time = 0
        self.old_pos       = None
        self.shake_int     = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(cfg["opacity"])

        sc = self.overlay_scale
        W  = int(520 * sc)
        H  = int(280 * sc)
        self.resize(W, H)

        # ---- Layout ----
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        # Heart widget
        self.heart_widget = HeartWidget(int(self.heart_size * sc * 1.3))
        top_row.addWidget(self.heart_widget)

        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        # BPM
        self.bpm_lbl = QLabel("-- BPM")
        self.bpm_lbl.setFont(QFont("Consolas", int(36 * sc), QFont.Weight.Bold))
        self.bpm_lbl.setStyleSheet("color: #00ff99; background: transparent;")
        right_col.addWidget(self.bpm_lbl)

        # Status message
        self.status_lbl = QLabel("")
        self.status_lbl.setFont(QFont("Consolas", int(14 * sc)))
        self.status_lbl.setStyleSheet("color: #cc0000; background: transparent;")
        right_col.addWidget(self.status_lbl)

        # Session min/max
        self.minmax_lbl = QLabel("min: --   max: --")
        self.minmax_lbl.setFont(QFont("Consolas", int(11 * sc)))
        self.minmax_lbl.setStyleSheet("color: #666666; background: transparent;")
        right_col.addWidget(self.minmax_lbl)

        # Connection indicator
        self.conn_lbl = QLabel("● disconnected")
        self.conn_lbl.setFont(QFont("Consolas", int(10 * sc)))
        self.conn_lbl.setStyleSheet("color: #555555; background: transparent;")
        right_col.addWidget(self.conn_lbl)

        # Mode indicator + manual toggle
        self.mode_lbl = QLabel("mode: desktop")
        self.mode_lbl.setFont(QFont("Consolas", int(10 * sc)))
        self.mode_lbl.setStyleSheet("color: #444455; background: transparent;")
        right_col.addWidget(self.mode_lbl)

        self.mode_btn = QPushButton("⇄ Force Desktop")
        self.mode_btn.setFont(QFont("Consolas", int(9 * sc)))
        self.mode_btn.setFixedHeight(22)
        self.mode_btn.clicked.connect(self._toggle_mode)
        right_col.addWidget(self.mode_btn)

        right_col.addStretch()
        top_row.addLayout(right_col)
        root.addLayout(top_row)

        # BPM Graph
        self.graph = BPMGraph()
        self.graph.setFixedHeight(int(64 * sc))
        root.addWidget(self.graph)

        # Permanent credit — not removable
        credit = QLabel("made by CRIMSON  •  dc: crimsondreamz")
        credit.setFont(QFont("Consolas", int(8 * sc)))
        credit.setStyleSheet("color: #330000; background: transparent;")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        root.addWidget(credit)

        self.shake_timer = QTimer()
        self.shake_timer.timeout.connect(self._shake_tick)
        self.base_pos = self.pos()

        # ---- Signals ----
        signals.bpm_signal.connect(self._on_bpm)
        signals.status_signal.connect(self._on_status)
        signals.mode_signal.connect(self._on_mode)

        self._current_mode   = "desktop"   # "desktop" | "vr"
        self._force_mode     = None        # None = auto, "desktop" | "vr" = manual override
        self._last_bpm_value = 0

    # ---- BPM Update ----
    def _on_bpm(self, bpm: int):
        # Color
        if bpm >= BPM_HIGH:
            color = "#ff2222"
        elif bpm >= BPM_MED:
            color = "#ffaa00"
        else:
            color = "#00ff99"
        self.bpm_lbl.setText(f"{bpm} BPM")
        self.bpm_lbl.setStyleSheet(f"color: {color}; background: transparent;")

        # Graph
        self.graph.push(bpm)

        # Session stats
        if self.session_min is None or bpm < self.session_min:
            self.session_min = bpm
        if self.session_max is None or bpm > self.session_max:
            self.session_max = bpm
        self.minmax_lbl.setText(
            f"min: {self.session_min}   max: {self.session_max}"
        )

        # Heartbeat speed + colour
        self.heart_widget.set_bpm(bpm)

        # Horror message
        if bpm >= BPM_HIGH:
            pool = self.messages["high"]
        elif bpm >= BPM_MED:
            pool = self.messages["medium"]
        else:
            pool = self.messages["calm"]

        now = time.time()
        spike = bpm - self.last_bpm >= 25
        if pool and (now - self.last_msg_time >= 5 or spike):
            self.status_lbl.setText(random.choice(pool))
            self.last_msg_time = now

        self.last_bpm        = bpm
        self._last_bpm_value = bpm

        # Shake
        if self.shake_enabled:
            if bpm >= SHAKE_HIGH_BPM:
                self._start_shake(SHAKE_HIGH_INT)
            elif bpm >= SHAKE_MED_BPM:
                self._start_shake(SHAKE_MED_INT)
            elif bpm >= SHAKE_LOW_BPM:
                self._start_shake(SHAKE_LOW_INT)
            else:
                self.shake_int = 0

    def _on_mode(self, mode: str):
        """Called from steamvr_watcher_thread via signals."""
        if self._force_mode is not None:
            return   # user has overridden
        self._apply_mode(mode)

    def _toggle_mode(self):
        if self._force_mode == "desktop":
            self._force_mode = None   # back to auto
            self.mode_btn.setText("⇄ Force Desktop")
        else:
            self._force_mode = "desktop"
            self._apply_mode("desktop")
            self.mode_btn.setText("⇄ Back to Auto")

    def _apply_mode(self, mode: str):
        self._current_mode = mode
        if mode == "vr":
            self.hide()
            self.mode_lbl.setText("mode: VR wrist")
            self.mode_lbl.setStyleSheet("color: #4488ff; background: transparent;")
        else:
            self.show()
            self.mode_lbl.setText("mode: desktop")
            self.mode_lbl.setStyleSheet("color: #444455; background: transparent;")

    def _on_status(self, status: str):
        if status == "connected":
            self.conn_lbl.setText("● connected")
            self.conn_lbl.setStyleSheet("color: #00cc44; background: transparent;")
        elif status == "disconnected":
            self.conn_lbl.setText("● disconnected")
            self.conn_lbl.setStyleSheet("color: #555555; background: transparent;")
        else:
            self.conn_lbl.setText("● error")
            self.conn_lbl.setStyleSheet("color: #cc0000; background: transparent;")

    # ---- Shake ----
    def _start_shake(self, intensity: int):
        self.base_pos  = self.pos()
        self.shake_int = intensity
        if not self.shake_timer.isActive():
            self.shake_timer.start(20)

    def _shake_tick(self):
        if self.shake_int <= 0:
            self.move(self.base_pos)
            self.shake_timer.stop()
            return
        self.move(
            self.base_pos.x() + random.randint(-self.shake_int, self.shake_int),
            self.base_pos.y() + random.randint(-self.shake_int, self.shake_int),
        )

    # ---- Drag ----
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    # ---- Background panel ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(10, 0, 0, 210)))
        pen = QPen(QColor(120, 0, 0, 160), 1)
        p.setPen(pen)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.end()


# ==========================================
# SHARE SERVER  (broadcast BPM to friends)
# ==========================================
_share_clients: list[socket.socket] = []
_share_clients_lock = threading.Lock()

def share_server_thread():
    """
    Listens on SHARE_PORT. Each connected friend receives a JSON line
    every time a new BPM arrives: {"bpm": 123}\n
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((SHARE_HOST, SHARE_PORT))
        srv.listen(16)
        print(f"Share server listening on port {SHARE_PORT}")
    except Exception as e:
        print(f"Share server failed to start: {e}")
        return

    def _accept_loop():
        while True:
            try:
                conn, addr = srv.accept()
                print(f"Friend connected: {addr}")
                with _share_clients_lock:
                    _share_clients.append(conn)
            except Exception:
                break

    threading.Thread(target=_accept_loop, daemon=True).start()

    def _broadcast(bpm: int):
        msg = (json.dumps({"bpm": bpm}) + "\n").encode()
        dead = []
        with _share_clients_lock:
            for c in _share_clients:
                try:
                    c.sendall(msg)
                except Exception:
                    dead.append(c)
            for c in dead:
                _share_clients.remove(c)

    signals.bpm_signal.connect(_broadcast)


# ==========================================
# VIEWER OVERLAY  (friend's simple readout)
# ==========================================
class ViewerOverlay(QWidget):
    """
    Minimal overlay for friends watching someone else's HR.
    Shows animated heart + BPM number + colour-coded status.
    No graph, no shake, no settings — just the vitals.
    """
    _bpm_ready = pyqtSignal(int)

    def __init__(self, host: str, port: int = SHARE_PORT):
        super().__init__()
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._reconnect_timer = QTimer()
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._connect)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(260, 120)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(10)

        self.heart_widget = HeartWidget(64)
        top.addWidget(self.heart_widget)

        info = QVBoxLayout()
        info.setSpacing(2)

        self.bpm_lbl = QLabel("-- BPM")
        self.bpm_lbl.setFont(QFont("Consolas", 22, QFont.Weight.Bold))
        self.bpm_lbl.setStyleSheet("color: #00ff99; background: transparent;")
        info.addWidget(self.bpm_lbl)

        self.name_lbl = QLabel(f"watching: {host}")
        self.name_lbl.setFont(QFont("Consolas", 9))
        self.name_lbl.setStyleSheet("color: #555566; background: transparent;")
        info.addWidget(self.name_lbl)

        self.conn_lbl = QLabel("● connecting…")
        self.conn_lbl.setFont(QFont("Consolas", 9))
        self.conn_lbl.setStyleSheet("color: #888800; background: transparent;")
        info.addWidget(self.conn_lbl)

        info.addStretch()
        top.addLayout(info)
        root.addLayout(top)

        # Permanent credit — not removable
        credit = QLabel("made by CRIMSON  •  dc: crimsondreamz")
        credit.setFont(QFont("Consolas", 8))
        credit.setStyleSheet("color: #330000; background: transparent;")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        root.addWidget(credit)

        # Internal signal so the socket thread can update Qt widgets safely
        self._bpm_ready.connect(self._on_bpm)

        self.old_pos = None
        self._connect()

    def _connect(self):
        threading.Thread(target=self._socket_thread, daemon=True).start()

    def _socket_thread(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((self.host, self.port))
            s.settimeout(None)
            self._sock = s
            self.conn_lbl.setText("● connected")
            self.conn_lbl.setStyleSheet("color: #00cc44; background: transparent;")
            buf = ""
            while True:
                chunk = s.recv(256).decode(errors="ignore")
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    try:
                        data = json.loads(line)
                        self._bpm_ready.emit(int(data["bpm"]))
                    except Exception:
                        pass
        except Exception as e:
            print(f"Viewer connection error: {e}")
        finally:
            self.conn_lbl.setText("● disconnected — retrying…")
            self.conn_lbl.setStyleSheet("color: #cc4400; background: transparent;")
            self._reconnect_timer.start(5000)

    def _on_bpm(self, bpm: int):
        if bpm >= BPM_HIGH:
            color = "#ff2222"
        elif bpm >= BPM_MED:
            color = "#ffaa00"
        else:
            color = "#00ff99"
        self.bpm_lbl.setText(f"{bpm} BPM")
        self.bpm_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self.heart_widget.set_bpm(bpm)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(10, 0, 0, 210)))
        p.setPen(QPen(QColor(120, 0, 0, 160), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None


# Thread-safe BPM value shared between the Qt signal and OSC/VR threads
import threading as _threading
_shared_bpm_lock  = _threading.Lock()
_shared_bpm_value = 0

def _update_shared_bpm(bpm: int):
    global _shared_bpm_value
    with _shared_bpm_lock:
        _shared_bpm_value = bpm

signals.bpm_signal.connect(_update_shared_bpm)


# ==========================================
# OSC THREAD  (VRChat HR broadcast + chatbox)
# ==========================================
def osc_thread(cfg: dict):
    """
    Sends HR data to VRChat via OSC:
      - /avatar/parameters/HR          (float — VRChat requires float, not int)
      - /avatar/parameters/HRPercent   (float 0-1)
      - /chatbox/input                 (boihanny-style message, if enabled)
    """
    client   = osc_udp.SimpleUDPClient(cfg["osc_ip"], cfg["osc_port"])
    chatbox_enabled = cfg.get("chatbox_enabled", False)
    last_chatbox_send = 0.0

    def _chatbox_line(bpm: int) -> str:
        """Build the chatbox string matching boihanny magic chatbox style."""
        # Heart icon colour via tier
        if bpm >= BPM_HIGH:
            icon  = "❤️"
            tier  = "HIGH"
        elif bpm >= BPM_MED:
            icon  = "🧡"
            tier  = "MED"
        else:
            icon  = "💚"
            tier  = "LOW"

        # Bar graph — 10 segments
        filled  = round((min(bpm, VRC_HR_MAX) / VRC_HR_MAX) * 10)
        bar     = "█" * filled + "░" * (10 - filled)

        return f"{icon} {bpm} BPM  [{bar}]  {tier}"

    while True:
        try:
            with _shared_bpm_lock:
                last_bpm = _shared_bpm_value
            if last_bpm > 0:
                # Avatar parameters (for HR-driven animations/shaders)
                client.send_message(VRC_OSC_HR_PARAM,  float(last_bpm))
                client.send_message(VRC_OSC_PCT_PARAM, float(min(last_bpm, VRC_HR_MAX) / VRC_HR_MAX))

                # Chatbox
                if chatbox_enabled:
                    now = time.time()
                    if now - last_chatbox_send >= CHATBOX_INTERVAL_SEC:
                        msg = _chatbox_line(last_bpm)
                        # args: message (str), send_immediately (bool), trigger_sfx (bool)
                        client.send_message(VRC_CHATBOX_INPUT, [msg, True, False])
                        last_chatbox_send = now

        except Exception as e:
            print("OSC error:", e)
        time.sleep(1)


# ==========================================
# STEAMVR WATCHER + VR OVERLAY THREAD
# ==========================================
def _steamvr_running() -> bool:
    """True if vrserver.exe is in the process list."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq vrserver.exe", "/NH"],
            stderr=subprocess.DEVNULL
        ).decode()
        return "vrserver.exe" in out
    except Exception:
        return False


def _render_vr_texture(bpm: int) -> bytes:
    """Paint heart + BPM onto a QImage and return raw RGBA bytes for OpenVR."""
    size = VR_TEXTURE_SIZE
    img  = __import__('PyQt6.QtGui', fromlist=['QImage']).QImage(
        size, size, __import__('PyQt6.QtGui', fromlist=['QImage']).QImage.Format.Format_RGBA8888
    )
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background pill
    p.setBrush(QBrush(QColor(12, 0, 0, 210)))
    p.setPen(QPen(QColor(120, 0, 0, 160), 2))
    p.drawRoundedRect(4, 4, size - 8, size - 8, 20, 20)

    # Heart
    p.save()
    p.translate(size * 0.28, size * 0.42)
    r = size * 0.22
    p.scale(r, r)
    if bpm >= BPM_HIGH:
        fill = QColor(255, 30, 30)
    elif bpm >= BPM_MED:
        fill = QColor(230, 120, 20)
    else:
        fill = QColor(200, 40, 40)
    p.setBrush(QBrush(fill))
    p.setPen(Qt.PenStyle.NoPen)
    path = QPainterPath()
    path.moveTo(0, 0.9)
    path.cubicTo(-0.05, 0.6, -1.0,  0.4, -1.0, -0.1)
    path.cubicTo(-1.0, -0.6, -0.5, -0.9,  0.0, -0.3)
    path.cubicTo( 0.5, -0.9,  1.0, -0.6,  1.0, -0.1)
    path.cubicTo( 1.0,  0.4,  0.05, 0.6,  0.0,  0.9)
    path.closeSubpath()
    p.drawPath(path)
    p.restore()

    # BPM text
    if bpm >= BPM_HIGH:
        tc = QColor(255, 60, 60)
    elif bpm >= BPM_MED:
        tc = QColor(255, 170, 0)
    else:
        tc = QColor(0, 255, 153)
    p.setPen(tc)
    p.setFont(QFont("Consolas", 36, QFont.Weight.Bold))
    p.drawText(QRect(size // 2 - 10, size // 2 - 28, size // 2, 48),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               str(bpm) if bpm > 0 else "--")
    p.setPen(QColor(150, 150, 150))
    p.setFont(QFont("Consolas", 14))
    p.drawText(QRect(size // 2 - 10, size // 2 + 22, size // 2, 28),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "BPM")
    p.end()

    ptr = img.bits()
    ptr.setsize(size * size * 4)
    return bytes(ptr)


def steamvr_watcher_thread(cfg: dict):
    """
    Polls for SteamVR. When found, opens an OpenVR wrist overlay and
    renders BPM each frame. Emits mode_signal so the desktop overlay
    hides/shows itself accordingly.
    """
    vr_system   = None
    vr_overlay  = None
    overlay_handle = None
    was_running = False

    def _init_vr():
        nonlocal vr_system, vr_overlay, overlay_handle
        try:
            vr_system  = openvr.init(openvr.VRApplication_Overlay)
            vr_overlay = openvr.IVROverlay()
            _, overlay_handle = vr_overlay.createOverlay(VR_OVERLAY_KEY, VR_OVERLAY_NAME)
            vr_overlay.setOverlayWidthInMeters(overlay_handle, VR_OVERLAY_WIDTH)
            vr_overlay.showOverlay(overlay_handle)
            return True
        except Exception as e:
            print("OpenVR init error:", e)
            return False

    def _shutdown_vr():
        nonlocal vr_system, vr_overlay, overlay_handle
        try:
            if vr_overlay and overlay_handle:
                vr_overlay.destroyOverlay(overlay_handle)
        except Exception:
            pass
        try:
            openvr.shutdown()
        except Exception:
            pass
        vr_system = vr_overlay = overlay_handle = None

    def _update_wrist_transform():
        """Position overlay on left wrist controller."""
        try:
            poses = vr_system.getDeviceToAbsoluteTrackingPose(
                openvr.TrackingUniverseStanding, 0,
                openvr.k_unMaxTrackedDeviceCount
            )
            left_hand_idx = vr_system.getTrackedDeviceIndexForControllerRole(
                openvr.TrackedControllerRole_LeftHand
            )
            if left_hand_idx == openvr.k_unTrackedDeviceIndexInvalid:
                return
            pose = poses[left_hand_idx]
            if not pose.bPoseIsValid:
                return
            mat = pose.mDeviceToAbsoluteTracking
            # Offset slightly above the wrist (local Y)
            transform = openvr.HmdMatrix34_t()
            for i in range(3):
                for j in range(4):
                    transform[i][j] = mat[i][j]
            transform[1][3] += 0.06  # 6 cm above wrist
            vr_overlay.setOverlayTransformAbsolute(
                overlay_handle,
                openvr.TrackingUniverseStanding,
                transform
            )
        except Exception:
            pass

    while True:
        running = _steamvr_running()

        if running and not was_running:
            # SteamVR just started
            if _init_vr():
                was_running = True
                signals.mode_signal.emit("vr")
                print("SteamVR detected — switching to VR overlay")

        elif not running and was_running:
            # SteamVR just stopped
            _shutdown_vr()
            was_running = False
            signals.mode_signal.emit("desktop")
            print("SteamVR stopped — switching to desktop overlay")

        if was_running and vr_overlay and overlay_handle:
            try:
                _update_wrist_transform()
                with _shared_bpm_lock:
                    last_bpm = _shared_bpm_value
                raw = _render_vr_texture(last_bpm)
                size = VR_TEXTURE_SIZE
                tex = openvr.VRTextureWithPoseAndColorSpace_t()
                # Use raw pixel data via overlay setOverlayRaw
                vr_overlay.setOverlayRaw(overlay_handle, raw, size, size, 4)
            except Exception as e:
                print("VR render error:", e)
            time.sleep(1 / 30)   # ~30 fps
        else:
            time.sleep(STEAMVR_POLL_SEC)


# ==========================================
# WEBSOCKET
# ==========================================
_ws_instance = None

def websocket_thread(token: str):
    global _ws_instance

    def on_open(ws):
        signals.status_signal.emit("connected")

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "data" in data:
                signals.bpm_signal.emit(data["data"]["heart_rate"])
        except Exception as e:
            print("Message error:", e)

    def on_error(ws, error):
        signals.status_signal.emit("error")
        print("WebSocket error:", error)

    def on_close(ws, code, msg):
        signals.status_signal.emit("disconnected")
        print("Disconnected — reconnecting in 5s…")
        time.sleep(5)
        websocket_thread(token)   # auto-reconnect

    url = f"{WS_URL}?access_token={token}"
    _ws_instance = websocket.WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    _ws_instance.run_forever()


# ==========================================
# ENTRY POINT
# ==========================================
if __name__ == "__main__":
    import traceback
    import os
    import pathlib

    def crash_log(exc: BaseException):
        """Write a crash.log to the Desktop so errors are visible in the exe."""
        desktop = pathlib.Path.home() / "Desktop"
        log_path = desktop / "HorrorOverlay_crash.log"
        try:
            with open(log_path, "w") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass  # if Desktop write fails, nothing we can do silently

    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setQuitOnLastWindowClosed(False)
        win = SettingsWindow()
        win.show()
        sys.exit(app.exec())
    except Exception as e:
        crash_log(e)
        # Also show a Qt error dialog if Qt is alive
        try:
            from PyQt6.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setWindowTitle("Horror Overlay — Crash")
            msg.setText(f"The overlay crashed:\n\n{traceback.format_exc()}")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.exec()
        except Exception:
            pass
        raise
