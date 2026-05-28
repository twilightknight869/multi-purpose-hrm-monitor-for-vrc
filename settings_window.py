# ===========================================================
#  HRM Monitor — Settings Window
# ===========================================================
import socket
import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QGroupBox, QTabWidget, QSlider,
    QSizePolicy, QApplication, QListWidget, QListWidgetItem,
    QTextEdit, QSpinBox, QScrollArea, QFrame,
)
from PyQt6.QtGui  import QFont
from PyQt6.QtCore import Qt, QSettings, QTimer

import threads
from constants import (
    TOKEN, VRC_OSC_IP, VRC_OSC_PORT,
    VRC_OSC_HR_PARAM, VRC_OSC_PCT_PARAM,
    SHARE_PORT,
    DEFAULT_CHATBOX_TEMPLATE, DEFAULT_STATUS_ENTRIES,
    STATUS_ROTATE_SEC, DARK_STYLE,
)
from overlay_window import Overlay, ViewerOverlay
from widgets import BPMGraph, HeartWidget

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

try:
    import spotipy
    SPOTIPY_OK = True
except ImportError:
    SPOTIPY_OK = False


class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HRM Monitor")
        self.setMinimumSize(500, 580)
        self.resize(540, 680)
        self.setStyleSheet(DARK_STYLE)

        self.settings = QSettings("HRMMonitor", "Settings")

        # Store refs for cross-tab access
        self.rotate_checkbox = None
        self.status_list = None

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header bar ──────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("background: #080000; border-bottom: 1px solid #2a0000;")
        header.setFixedHeight(46)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(16, 0, 16, 0)
        header_row.setSpacing(0)

        title = QLabel("HRM MONITOR")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #cc0000; letter-spacing: 1px; background: transparent; border: none;")
        header_row.addWidget(title)

        header_row.addStretch()

        credit = QLabel("made by CRIMSON   •   DC: crimsondreamz")
        credit.setFont(QFont("Segoe UI", 9))
        credit.setStyleSheet("color: #440000; background: transparent; border: none;")
        credit.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        header_row.addWidget(credit)

        root.addWidget(header)

        # ── Top-level tabs (navigation style) ───────────────────
        self.mode_tabs = QTabWidget()
        self.mode_tabs.setObjectName("mode_tabs")
        self.mode_tabs.setDocumentMode(True)
        self.mode_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.mode_tabs.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.mode_tabs, stretch=1)

        self.mode_tabs.addTab(self._build_broadcaster_tab(), "📡  Broadcaster")
        self.mode_tabs.addTab(self._build_viewer_tab(),      "👁  Viewer")

        self.mode_tabs.setCurrentIndex(int(self.settings.value("last_tab", 0)))
        
        # Initialize chatbox preview
        self._preview_chatbox()

    # ===========================================================
    #  BROADCASTER TAB
    # ===========================================================
    def _build_broadcaster_tab(self) -> QWidget:
        page   = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner  = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # Inner tabs: Main | OSC | Spotify | Status
        inner_tabs = QTabWidget()
        inner_tabs.addTab(self._build_main_tab(),    "⚙  Main")
        inner_tabs.addTab(self._build_osc_tab(),     "🎛  OSC")
        inner_tabs.addTab(self._build_spotify_tab(), "🎵  Spotify")
        inner_tabs.addTab(self._build_status_tab(),  "💬  Status")
        layout.addWidget(inner_tabs, stretch=1)

        # START button always visible at bottom
        start_btn = QPushButton("▶   START OVERLAY")
        start_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        start_btn.setFixedHeight(42)
        start_btn.setStyleSheet(
            "QPushButton {"
            "  background: #330000; border: 1px solid #cc0000; border-radius: 8px;"
            "  color: #ff4444; font-weight: bold; letter-spacing: 1px;"
            "}"
            "QPushButton:hover { background: #550000; color: #ff6666; border-color: #ff2222; }"
            "QPushButton:pressed { background: #220000; }"
        )
        start_btn.clicked.connect(self.start_overlay)
        layout.addWidget(start_btn)

        scroll.setWidget(inner)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        return page

    # ---- Main sub-tab ----------------------------------------
    def _build_main_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)

        # Beta banner
        if not self.settings.value("beta_removed", False):
            beta_banner = QLabel("🔴 BETA VERSION")
            beta_banner.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            beta_banner.setStyleSheet("color: #ff4444; background: transparent;")
            beta_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(beta_banner)
            layout.addSpacing(4)

        # Token
        tok_group = QGroupBox("Pulsoid Token")
        tok_layout = QHBoxLayout(tok_group)
        tok_layout.setContentsMargins(8, 4, 8, 4)
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Paste your Pulsoid access token here")
        self.token_input.setText(self.settings.value("token", TOKEN))
        tok_layout.addWidget(self.token_input)
        layout.addWidget(tok_group)

        # Appearance + Options
        mid_row = QHBoxLayout()
        mid_row.setSpacing(6)

        appear_group = QGroupBox("Appearance")
        ag = QVBoxLayout(appear_group)
        ag.setContentsMargins(8, 4, 8, 4)
        ag.setSpacing(4)
        self.overlay_slider = self._make_slider(ag, "Scale",   50, 200, 100, "%",  "overlay_scale")
        self.heart_slider   = self._make_slider(ag, "Heart",   60, 180,  95, "pt", "heart_size")
        self.opacity_slider = self._make_slider(ag, "Opacity", 20, 100, 100, "%",  "opacity")
        self.bpm_size_slider = self._make_slider(ag, "BPM Sz", 18, 120,  64, "pt", "bpm_size")
        mid_row.addWidget(appear_group, stretch=2)

        opt_group = QGroupBox("Options")
        og = QVBoxLayout(opt_group)
        og.setContentsMargins(8, 4, 8, 4)
        og.setSpacing(4)
        self.shake_checkbox = QCheckBox("Screen shake")
        self.shake_checkbox.setChecked(self._bool_setting("shake", True))
        og.addWidget(self.shake_checkbox)
        self.share_checkbox = QCheckBox("Broadcast HR\n(port 5050)")
        self.share_checkbox.setChecked(self._bool_setting("share_enabled", False))
        og.addWidget(self.share_checkbox)
        og.addStretch()
        mid_row.addWidget(opt_group, stretch=1)
        layout.addLayout(mid_row)

        # VR
        vr_group = QGroupBox("SteamVR Wrist Overlay")
        vg = QHBoxLayout(vr_group)
        vg.setContentsMargins(8, 4, 8, 4)
        self.vr_checkbox = QCheckBox("Enable SteamVR wrist overlay")
        self.vr_checkbox.setChecked(self._bool_setting("vr_enabled", True))
        if not OPENVR_OK:
            self.vr_checkbox.setText("SteamVR  (pip install openvr)")
            self.vr_checkbox.setChecked(False)
            self.vr_checkbox.setEnabled(False)
        vg.addWidget(self.vr_checkbox)
        layout.addWidget(vr_group)

        # Developer section
        dev_group = QGroupBox("Developer")
        dg = QVBoxLayout(dev_group)
        dg.setContentsMargins(8, 4, 8, 8)
        dg.setSpacing(6)

        dev_label = QLabel("Enter developer key to remove beta banner:")
        dev_label.setStyleSheet("color: #888888; font-size: 12px;")
        dg.addWidget(dev_label)

        dev_row = QHBoxLayout()
        self.dev_key_input = QLineEdit()
        self.dev_key_input.setPlaceholderText("••••••")
        self.dev_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.dev_key_input.setMaximumWidth(120)
        dev_row.addWidget(self.dev_key_input)

        dev_btn = QPushButton("Verify")
        dev_btn.setFixedWidth(70)
        dev_btn.setFixedHeight(24)
        dev_btn.clicked.connect(self._verify_dev_key)
        dev_row.addWidget(dev_btn)
        dev_row.addStretch()
        dg.addLayout(dev_row)

        self.dev_status = QLabel("")
        self.dev_status.setStyleSheet("color: #888888; font-size: 12px;")
        dg.addWidget(self.dev_status)

        if self.settings.value("beta_removed", False):
            self.dev_status.setText("✓ Beta banner removed")
            self.dev_status.setStyleSheet("color: #88ff88; font-size: 12px;")
            self.dev_key_input.setEnabled(False)
            dev_btn.setEnabled(False)

        layout.addWidget(dev_group)

        return w

    # ---- OSC sub-tab -----------------------------------------
    def _build_osc_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # Enable + connection
        enable_group = QGroupBox("Connection")
        eg = QVBoxLayout(enable_group)
        eg.setContentsMargins(8, 4, 8, 8)
        eg.setSpacing(6)

        self.osc_checkbox = QCheckBox("Enable VRChat OSC")
        self.osc_checkbox.setChecked(self._bool_setting("osc_enabled", True))
        if not OSC_OK:
            self.osc_checkbox.setText("VRChat OSC  (pip install python-osc)")
            self.osc_checkbox.setChecked(False)
            self.osc_checkbox.setEnabled(False)
        eg.addWidget(self.osc_checkbox)

        addr_row = QHBoxLayout()
        addr_row.addWidget(QLabel("IP:"))
        self.osc_ip = QLineEdit(str(self.settings.value("osc_ip", VRC_OSC_IP)))
        addr_row.addWidget(self.osc_ip, stretch=1)
        addr_row.addWidget(QLabel("Port:"))
        self.osc_port = QLineEdit(str(self.settings.value("osc_port", str(VRC_OSC_PORT))))
        self.osc_port.setFixedWidth(58)
        addr_row.addWidget(self.osc_port)
        eg.addLayout(addr_row)
        layout.addWidget(enable_group)

        # Parameter addresses
        param_group = QGroupBox("Avatar Parameter Addresses")
        pg = QVBoxLayout(param_group)
        pg.setContentsMargins(8, 4, 8, 8)
        pg.setSpacing(6)

        pg.addWidget(QLabel("HR parameter  (float — numeric BPM sent here):"))
        self.hr_param_input = QLineEdit(
            self.settings.value("hr_param", VRC_OSC_HR_PARAM))
        self.hr_param_input.setPlaceholderText("/avatar/parameters/HR")
        pg.addWidget(self.hr_param_input)

        pg.addWidget(QLabel("HRPercent parameter  (float 0-1 — BPM ÷ 255):"))
        self.pct_param_input = QLineEdit(
            self.settings.value("pct_param", VRC_OSC_PCT_PARAM))
        self.pct_param_input.setPlaceholderText("/avatar/parameters/HRPercent")
        pg.addWidget(self.pct_param_input)

        reset_params_btn = QPushButton("↺  Reset to defaults")
        reset_params_btn.setFixedHeight(26)
        reset_params_btn.clicked.connect(self._reset_osc_params)
        pg.addWidget(reset_params_btn)
        layout.addWidget(param_group)

        # Chatbox
        chatbox_group = QGroupBox("VRChat Chatbox")
        cg = QVBoxLayout(chatbox_group)
        cg.setContentsMargins(8, 4, 8, 8)
        cg.setSpacing(6)

        self.chatbox_checkbox = QCheckBox("Send HR to VRChat chatbox")
        self.chatbox_checkbox.setChecked(self._bool_setting("chatbox_enabled", False))
        self.chatbox_checkbox.stateChanged.connect(self._on_chatbox_settings_changed)
        if not OSC_OK:
            self.chatbox_checkbox.setChecked(False)
            self.chatbox_checkbox.setEnabled(False)
        cg.addWidget(self.chatbox_checkbox)

        self.spotify_in_chatbox_checkbox = QCheckBox(
            "Include Spotify track in chatbox  (uses {track} / {artist})")
        self.spotify_in_chatbox_checkbox.setChecked(
            self._bool_setting("spotify_in_chatbox", False))
        self.spotify_in_chatbox_checkbox.stateChanged.connect(self._preview_chatbox)
        cg.addWidget(self.spotify_in_chatbox_checkbox)

        cg.addWidget(QLabel(
            "Chatbox template  —  placeholders:  "
            "{bpm}  {bar}  {tier}  {icon}  {track}  {artist}"))
        self.chatbox_template = QLineEdit(
            self.settings.value("chatbox_template", DEFAULT_CHATBOX_TEMPLATE))
        self.chatbox_template.setPlaceholderText(DEFAULT_CHATBOX_TEMPLATE)
        self.chatbox_template.textChanged.connect(self._preview_chatbox)
        cg.addWidget(self.chatbox_template)

        # VRC Output Preview
        preview_group = QGroupBox("📺 VRChat Output Preview")
        previewg = QVBoxLayout(preview_group)
        previewg.setContentsMargins(8, 8, 8, 8)
        previewg.setSpacing(6)

        info = QLabel(
            "This is how your chatbox will appear in VRChat (at 90 BPM as example):")
        info.setStyleSheet("color: #888888; font-size: 12px;")
        previewg.addWidget(info)

        self.vrc_preview = QLabel("")
        self.vrc_preview.setStyleSheet(
            "color: #446688; background: #0a0a0a; border: 1px solid #330000; "
            "border-radius: 3px; padding: 8px; font-size: 12px; font-family: Consolas;")
        self.vrc_preview.setWordWrap(True)
        self.vrc_preview.setMinimumHeight(60)
        previewg.addWidget(self.vrc_preview)

        chars_row = QHBoxLayout()
        chars_row.addWidget(QLabel("Characters:"))
        self.vrc_char_count = QLabel("0")
        self.vrc_char_count.setFixedWidth(40)
        chars_row.addWidget(self.vrc_char_count)
        chars_row.addWidget(QLabel("/144 (max)"))
        chars_row.addStretch()
        previewg.addLayout(chars_row)

        layout.addWidget(chatbox_group)
        layout.addWidget(preview_group, stretch=1)
        layout.addStretch()
        return w

    # ---- Spotify sub-tab -------------------------------------
    def _build_spotify_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        if not SPOTIPY_OK:
            note = QLabel(
                "spotipy is not installed.\n\n"
                "Run:  pip install spotipy\n\n"
                "Then restart the overlay.")
            note.setStyleSheet("color: #886600; font-size: 12px;")
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setWordWrap(True)
            layout.addWidget(note)
            layout.addStretch()
            return w

        info_lbl = QLabel(
            "Create a Spotify app at  developer.spotify.com/dashboard\n"
            "and paste your credentials below.  Redirect URI must match\n"
            "exactly what you set in the Spotify app settings.")
        info_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        creds_group = QGroupBox("Spotify API Credentials")
        cg = QVBoxLayout(creds_group)
        cg.setContentsMargins(8, 4, 8, 8)
        cg.setSpacing(6)

        self.spotify_checkbox = QCheckBox("Enable Spotify Now Playing")
        self.spotify_checkbox.setChecked(self._bool_setting("spotify_enabled", False))
        cg.addWidget(self.spotify_checkbox)

        cg.addWidget(QLabel("Client ID:"))
        self.spotify_client_id = QLineEdit(self.settings.value("spotify_client_id", ""))
        self.spotify_client_id.setPlaceholderText("e.g. 4a1b2c3d4e5f…")
        self.spotify_client_id.setEchoMode(QLineEdit.EchoMode.Password)
        cg.addWidget(self.spotify_client_id)

        cg.addWidget(QLabel("Client Secret:"))
        self.spotify_client_secret = QLineEdit(self.settings.value("spotify_client_secret", ""))
        self.spotify_client_secret.setPlaceholderText("e.g. 9z8y7x…")
        self.spotify_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        cg.addWidget(self.spotify_client_secret)

        cg.addWidget(QLabel("Redirect URI:"))
        self.spotify_redirect = QLineEdit(
            self.settings.value("spotify_redirect", "http://127.0.0.1:8888/callback"))
        cg.addWidget(self.spotify_redirect)

        show_btn = QPushButton("👁  Show / hide credentials")
        show_btn.setFixedHeight(26)
        show_btn.clicked.connect(self._toggle_spotify_echo)
        cg.addWidget(show_btn)

        layout.addWidget(creds_group)

        display_group = QGroupBox("Overlay Display & OSC")
        dg = QVBoxLayout(display_group)
        dg.setContentsMargins(8, 4, 8, 8)
        dg.setSpacing(6)
        note2 = QLabel(
            "When Spotify is enabled, the current track is shown\n"
            "on the desktop overlay in green below the BPM stats.\n"
            "You can also embed it in the chatbox using {track} / {artist}.")
        note2.setStyleSheet("color: #666666; font-size: 12px;")
        note2.setWordWrap(True)
        dg.addWidget(note2)

        self.spotify_osc_checkbox = QCheckBox(
            "Send track/artist as OSC avatar parameters\n"
            "  → /avatar/parameters/SpotifyTrack\n"
            "  → /avatar/parameters/SpotifyArtist")
        self.spotify_osc_checkbox.setChecked(self._bool_setting("spotify_osc_enabled", True))
        dg.addWidget(self.spotify_osc_checkbox)

        layout.addWidget(display_group)
        layout.addStretch()
        return w

    # ---- Status sub-tab --------------------------------------
    def _build_status_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        info_lbl = QLabel(
            "Add VRChat chatbox lines you want to cycle through.\n"
            "When auto-rotate is on, the active status is appended to\n"
            "your HR chatbox line  ( e.g.  ❤️ 95 BPM  •  your status here )\n"
            "so it never conflicts with or cancels the HR message.\n"
            "Supports the same placeholders as the chatbox template.")
        info_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        list_group = QGroupBox("Favourited Statuses")
        lg = QVBoxLayout(list_group)
        lg.setContentsMargins(8, 4, 8, 8)
        lg.setSpacing(6)

        self.status_list = QListWidget()
        self.status_list.setMinimumHeight(120)
        saved_statuses = self.settings.value("status_entries", DEFAULT_STATUS_ENTRIES)
        if isinstance(saved_statuses, str):
            saved_statuses = [saved_statuses] if saved_statuses else []
        for s in saved_statuses:
            self.status_list.addItem(QListWidgetItem(s))
        lg.addWidget(self.status_list)

        entry_row = QHBoxLayout()
        self.status_entry = QLineEdit()
        self.status_entry.setPlaceholderText(
            "e.g.  💀 {bpm} BPM  •  {icon} heart rate  •  playing: {track}")
        add_btn = QPushButton("Add")
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(self._add_status)
        del_btn = QPushButton("Remove")
        del_btn.setFixedWidth(80)
        del_btn.clicked.connect(self._remove_status)
        entry_row.addWidget(self.status_entry)
        entry_row.addWidget(add_btn)
        entry_row.addWidget(del_btn)
        lg.addLayout(entry_row)

        up_btn = QPushButton("▲ Up")
        down_btn = QPushButton("▼ Down")
        up_btn.setFixedHeight(24)
        down_btn.setFixedHeight(24)
        up_btn.clicked.connect(self._move_status_up)
        down_btn.clicked.connect(self._move_status_down)
        reorder_row = QHBoxLayout()
        reorder_row.addWidget(up_btn)
        reorder_row.addWidget(down_btn)
        reorder_row.addStretch()
        lg.addLayout(reorder_row)

        layout.addWidget(list_group)

        rotate_group = QGroupBox("Auto-Rotate")
        rg = QVBoxLayout(rotate_group)
        rg.setContentsMargins(8, 4, 8, 8)
        rg.setSpacing(6)

        self.rotate_checkbox = QCheckBox("Auto-rotate through favourited statuses")
        self.rotate_checkbox.setChecked(self._bool_setting("rotate_enabled", False))
        if not OSC_OK:
            self.rotate_checkbox.setChecked(False)
            self.rotate_checkbox.setEnabled(False)
            self.rotate_checkbox.setText("Auto-rotate  (requires python-osc)")
        self.rotate_checkbox.stateChanged.connect(self._preview_chatbox)
        rg.addWidget(self.rotate_checkbox)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("Rotate every"))
        self.rotate_interval = QSpinBox()
        self.rotate_interval.setMinimum(5)
        self.rotate_interval.setMaximum(3600)
        self.rotate_interval.setValue(int(self.settings.value("rotate_sec", STATUS_ROTATE_SEC)))
        self.rotate_interval.setSuffix("  seconds")
        self.rotate_interval.setFixedWidth(120)
        interval_row.addWidget(self.rotate_interval)
        interval_row.addStretch()
        rg.addLayout(interval_row)

        layout.addWidget(rotate_group)
        layout.addStretch()
        return w

    # ===========================================================
    #  VIEWER TAB
    # ===========================================================
    def _build_viewer_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addStretch()

        lbl = QLabel("Watch a friend's heart rate")
        lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #cc0000;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

        sub = QLabel("Ask them to enable \"Broadcast HR\" and share their IP.")
        sub.setStyleSheet("color: #666666; font-size: 12px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        layout.addWidget(sub)

        layout.addSpacing(8)

        ip_group = QGroupBox("Host IP Address")
        ip_layout = QVBoxLayout(ip_group)
        ip_layout.setContentsMargins(10, 6, 10, 10)
        ip_layout.setSpacing(6)

        self.viewer_ip_input = QLineEdit()
        self.viewer_ip_input.setPlaceholderText("e.g. 192.168.1.42  or  73.12.34.56")
        self.viewer_ip_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_ip_input.setFont(QFont("Consolas", 12))
        self.viewer_ip_input.setText(self.settings.value("viewer_ip", ""))
        ip_layout.addWidget(self.viewer_ip_input)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port:"))
        self.viewer_port_input = QLineEdit(
            str(self.settings.value("viewer_port", str(SHARE_PORT))))
        self.viewer_port_input.setFixedWidth(60)
        port_row.addWidget(self.viewer_port_input)
        port_row.addStretch()
        ip_layout.addLayout(port_row)
        layout.addWidget(ip_group)

        watch_btn = QPushButton("👁   CONNECT & WATCH")
        watch_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        watch_btn.setFixedHeight(42)
        watch_btn.setStyleSheet(
            "QPushButton {"
            "  background: #330000; border: 1px solid #cc0000; border-radius: 8px;"
            "  color: #ff4444; font-weight: bold; letter-spacing: 1px;"
            "}"
            "QPushButton:hover { background: #550000; color: #ff6666; border-color: #ff2222; }"
            "QPushButton:pressed { background: #220000; }"
        )
        watch_btn.clicked.connect(self._launch_viewer)
        layout.addWidget(watch_btn)

        layout.addSpacing(12)

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

    # ===========================================================
    #  HELPERS
    # ===========================================================
    def _make_slider(self, layout, label_text, lo, hi, default, unit, key=None):
        row = QHBoxLayout(); row.setSpacing(6)
        lbl = QLabel(label_text); lbl.setFixedWidth(58)
        lbl.setStyleSheet("color: #bbbbbb; font-size: 13px;")
        val_lbl = QLabel(f"{default}{unit}"); val_lbl.setFixedWidth(46)
        val_lbl.setStyleSheet("color: #cc6666; font-size: 13px; font-weight: bold;")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(lo); slider.setMaximum(hi)
        key = key or label_text.lower().replace(" ", "_")
        slider.setValue(int(self.settings.value(key, default)))
        slider.valueChanged.connect(lambda v, vl=val_lbl, u=unit: vl.setText(f"{v}{u}"))
        row.addWidget(lbl); row.addWidget(slider); row.addWidget(val_lbl)
        layout.addLayout(row)
        return slider

    def _bool_setting(self, key: str, default: bool) -> bool:
        v = self.settings.value(key, default)
        if v is None: return default
        if isinstance(v, str): return v.lower() == "true"
        return bool(v)

    def _verify_dev_key(self):
        from constants import _DEV_KEY_ACTUAL
        key = self.dev_key_input.text().strip()
        if key == _DEV_KEY_ACTUAL:
            self.settings.setValue("beta_removed", True)
            self.dev_status.setText("✓ Beta banner removed! Restart overlay to apply.")
            self.dev_status.setStyleSheet("color: #88ff88; font-size: 12px;")
            self.dev_key_input.setEnabled(False)
            self.findChild(QPushButton, "dev_btn").setEnabled(False)
        else:
            self.dev_status.setText("✗ Invalid key")
            self.dev_status.setStyleSheet("color: #ff6666; font-size: 12px;")
            self.dev_key_input.clear()

    @staticmethod
    def _get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]; s.close(); return ip
        except Exception:
            return "unavailable"

    def _reset_osc_params(self):
        self.hr_param_input.setText(VRC_OSC_HR_PARAM)
        self.pct_param_input.setText(VRC_OSC_PCT_PARAM)

    def _preview_chatbox(self):
        from threads import _build_chatbox_line, _truncate_text
        from constants import VRC_STATUS_MAX_LENGTH, VRC_CHATBOX_MAX_LENGTH
        
        template = self.chatbox_template.text().strip() or DEFAULT_CHATBOX_TEMPLATE
        spotify  = {"track": "Redbone", "artist": "Childish Gambino"} \
                   if self.spotify_in_chatbox_checkbox.isChecked() else {}
        try:
            hr_line = _build_chatbox_line(90, template, spotify)
            
            # Show HR line + example status if applicable
            status_list = []
            if self.status_list is not None:
                status_list = [self.status_list.item(i).text() for i in range(self.status_list.count())]
            
            if status_list and self.rotate_checkbox and self.rotate_checkbox.isChecked():
                status = status_list[0]
                try:
                    status = status.format(
                        bpm=90, bar="█████░░░░░", tier="MED", icon="🧡",
                        track="Redbone", artist="Childish Gambino")
                except (KeyError, ValueError):
                    pass
                status = _truncate_text(status, VRC_STATUS_MAX_LENGTH)
                combined = f"{hr_line}  •  {status}"
                final = _truncate_text(combined, VRC_CHATBOX_MAX_LENGTH)
                char_color = "#88ff88" if len(final) <= 144 else "#ffaa44"
                self.vrc_preview.setText(f"📤  {final}")
                self.vrc_char_count.setText(str(len(final)))
                self.vrc_char_count.setStyleSheet(f"color: {char_color};")
            else:
                char_color = "#88ff88" if len(hr_line) <= 144 else "#ffaa44"
                self.vrc_preview.setText(f"📤  {hr_line}")
                self.vrc_char_count.setText(str(len(hr_line)))
                self.vrc_char_count.setStyleSheet(f"color: {char_color};")
        except KeyError as e:
            self.vrc_preview.setText(f"⚠  Unknown placeholder {e}")
            self.vrc_char_count.setText("—")

    def _on_chatbox_settings_changed(self):
        self._preview_chatbox()

    def _toggle_spotify_echo(self):
        normal = QLineEdit.EchoMode.Normal
        pwd    = QLineEdit.EchoMode.Password
        new_mode = normal if self.spotify_client_id.echoMode() == pwd else pwd
        self.spotify_client_id.setEchoMode(new_mode)
        self.spotify_client_secret.setEchoMode(new_mode)

    # ---- Status list helpers ---------------------------------
    def _add_status(self):
        text = self.status_entry.text().strip()
        if text:
            self.status_list.addItem(QListWidgetItem(text))
            self.status_entry.clear()

    def _remove_status(self):
        row = self.status_list.currentRow()
        if row >= 0:
            self.status_list.takeItem(row)

    def _move_status_up(self):
        row = self.status_list.currentRow()
        if row > 0:
            item = self.status_list.takeItem(row)
            self.status_list.insertItem(row - 1, item)
            self.status_list.setCurrentRow(row - 1)

    def _move_status_down(self):
        row = self.status_list.currentRow()
        if row < self.status_list.count() - 1:
            item = self.status_list.takeItem(row)
            self.status_list.insertItem(row + 1, item)
            self.status_list.setCurrentRow(row + 1)

    def _launch_viewer(self):
        host = self.viewer_ip_input.text().strip()
        if not host: return
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

    # ===========================================================
    #  START (broadcaster)
    # ===========================================================
    def start_overlay(self):
        self.settings.setValue("last_tab", self.mode_tabs.currentIndex())

        # Collect status list
        statuses = [self.status_list.item(i).text()
                    for i in range(self.status_list.count())]

        cfg = {
            # Core
            "token":         self.token_input.text().strip(),
            "overlay_scale": self.overlay_slider.value() / 100,
            "heart_size":    self.heart_slider.value(),
            "bpm_size":      self.bpm_size_slider.value(),
            "opacity":       self.opacity_slider.value() / 100,
            "shake_enabled": self.shake_checkbox.isChecked(),
            # VR
            "vr_enabled":    self.vr_checkbox.isChecked() and OPENVR_OK,
            # Share
            "share_enabled": self.share_checkbox.isChecked(),
            # OSC
            "osc_enabled":   self.osc_checkbox.isChecked() and OSC_OK,
            "osc_ip":        self.osc_ip.text().strip() or VRC_OSC_IP,
            "osc_port":      int(self.osc_port.text().strip() or VRC_OSC_PORT),
            "hr_param":      self.hr_param_input.text().strip() or VRC_OSC_HR_PARAM,
            "pct_param":     self.pct_param_input.text().strip() or VRC_OSC_PCT_PARAM,
            "chatbox_enabled":    self.chatbox_checkbox.isChecked() and OSC_OK,
            "chatbox_template":   self.chatbox_template.text().strip() or DEFAULT_CHATBOX_TEMPLATE,
            "spotify_in_chatbox": self.spotify_in_chatbox_checkbox.isChecked(),
            # Spotify
            "spotify_osc_enabled":   self.spotify_osc_checkbox.isChecked() if SPOTIPY_OK else False,
            "spotify_enabled":       self.spotify_checkbox.isChecked() if SPOTIPY_OK else False,
            "spotify_client_id":     self.spotify_client_id.text().strip() if SPOTIPY_OK else "",
            "spotify_client_secret": self.spotify_client_secret.text().strip() if SPOTIPY_OK else "",
            "spotify_redirect":      self.spotify_redirect.text().strip() if SPOTIPY_OK else "",
            # Status rotator
            "rotate_enabled": self.rotate_checkbox.isChecked() and OSC_OK,
            "statuses":       statuses,
            "rotate_sec":     self.rotate_interval.value(),
        }

        # Persist
        for k, v in {
            "token":              cfg["token"],
            "overlay_scale":      self.overlay_slider.value(),
            "heart_size":         self.heart_slider.value(),
            "bpm_size":           self.bpm_size_slider.value(),
            "opacity":            self.opacity_slider.value(),
            "shake":              cfg["shake_enabled"],
            "vr_enabled":         cfg["vr_enabled"],
            "share_enabled":      cfg["share_enabled"],
            "osc_enabled":        cfg["osc_enabled"],
            "osc_ip":             cfg["osc_ip"],
            "osc_port":           cfg["osc_port"],
            "hr_param":           cfg["hr_param"],
            "pct_param":          cfg["pct_param"],
            "chatbox_enabled":    cfg["chatbox_enabled"],
            "chatbox_template":   cfg["chatbox_template"],
            "spotify_in_chatbox":  cfg["spotify_in_chatbox"],
            "spotify_osc_enabled": cfg["spotify_osc_enabled"],
            "spotify_enabled":     cfg["spotify_enabled"],
            "spotify_client_id":  cfg["spotify_client_id"],
            "spotify_client_secret": cfg["spotify_client_secret"],
            "spotify_redirect":   cfg["spotify_redirect"],
            "rotate_enabled":     cfg["rotate_enabled"],
            "status_entries":     statuses,
            "rotate_sec":         cfg["rotate_sec"],
        }.items():
            self.settings.setValue(k, v)

        # Launch overlay
        overlay = Overlay(cfg)
        overlay._settings_window = self
        QApplication.instance()._overlay = overlay
        overlay.show()

        import threading as _t
        _t.Thread(target=threads.websocket_thread,      args=(cfg["token"],), daemon=True).start()

        if cfg["osc_enabled"]:
            _t.Thread(target=threads.osc_thread,        args=(cfg,), daemon=True).start()

        if cfg["vr_enabled"]:
            _t.Thread(target=threads.steamvr_watcher_thread, args=(cfg,), daemon=True).start()

        if cfg["share_enabled"]:
            _t.Thread(target=threads.share_server_thread, daemon=True).start()

        if cfg["spotify_enabled"] and cfg["spotify_client_id"] and cfg["spotify_client_secret"]:
            _t.Thread(
                target=threads.spotify_thread,
                args=(cfg["spotify_client_id"],
                      cfg["spotify_client_secret"],
                      cfg["spotify_redirect"]),
                daemon=True,
            ).start()

        if cfg["rotate_enabled"] and statuses:
            _t.Thread(
                target=threads.status_rotator_thread,
                args=(cfg,),
                daemon=True,
            ).start()

        self.hide()
