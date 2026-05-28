# ===========================================================
#  HRM Monitor — Floating Overlay Windows
# ===========================================================
import threading
import time

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizeGrip, QApplication
from PyQt6.QtGui  import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSettings

import signals as sig
from constants import (
    BPM_HIGH, BPM_MED,
    SHAKE_HIGH_BPM, SHAKE_HIGH_INT,
    SHAKE_MED_BPM,  SHAKE_MED_INT,
    SHAKE_LOW_BPM,  SHAKE_LOW_INT,
    MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_PREFIX,
    OVERLAY_TRACK_MAX_LEN, OVERLAY_ARTIST_MAX_LEN,
)
from widgets import HeartWidget, BPMGraph


# ===========================================================
#  Notification Toast  (friend connect / disconnect)
# ===========================================================
class NotificationToast(QWidget):
    """Frameless popup that fades in, lingers, then fades out."""

    def __init__(self, message: str, icon: str = "🫀"):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(0.0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 18))
        icon_lbl.setStyleSheet("background: transparent; color: #ff4444;")
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)

        title_lbl = QLabel("HR Share")
        title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title_lbl.setStyleSheet("background: transparent; color: #888888;")
        text_col.addWidget(title_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        msg_lbl.setStyleSheet("background: transparent; color: #ffffff;")
        text_col.addWidget(msg_lbl)

        layout.addLayout(text_col)
        self.adjustSize()
        self.setFixedSize(max(self.width(), 280), max(self.height(), 58))

        # Position: bottom-right of primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 16,
                  screen.bottom() - self.height() - 16)

        # Fade in/out via window opacity
        self._opacity   = 0.0
        self._phase     = 'in'          # 'in' → 'hold' → 'out'
        self._hold_ms   = 4500
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_tick)
        self._fade_timer.start(20)
        self.show()

    def _fade_tick(self):
        if self._phase == 'in':
            self._opacity = min(1.0, self._opacity + 0.07)
            self.setWindowOpacity(self._opacity)
            if self._opacity >= 1.0:
                self._phase = 'hold'
                QTimer.singleShot(self._hold_ms, self._start_fadeout)
        elif self._phase == 'out':
            self._opacity = max(0.0, self._opacity - 0.05)
            self.setWindowOpacity(self._opacity)
            if self._opacity <= 0.0:
                self._fade_timer.stop()
                self.close()

    def _start_fadeout(self):
        self._phase = 'out'

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(14, 0, 0, 230)))
        p.setPen(QPen(QColor(140, 0, 0, 180), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.end()


# ===========================================================
#  Main (broadcaster) overlay window
# ===========================================================
class Overlay(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg           = cfg
        self.overlay_scale = cfg["overlay_scale"]
        self.heart_size    = cfg["heart_size"]
        self.bpm_size      = cfg.get("bpm_size", 64)
        self.shake_enabled = cfg["shake_enabled"]

        self.session_min   = None
        self.session_max   = None
        self.old_pos       = None
        self.shake_int     = 0
        self._settings_window = None
        self._toasts: list[NotificationToast] = []   # keep refs so GC won't collect them

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(cfg["opacity"])

        sc = self.overlay_scale
        self.setMinimumSize(int(260 * sc), int(160 * sc))
        self.resize(int(520 * sc), int(310 * sc))
        self._resize_edge  = None   # tracks which edge is being dragged for resize

        # ---- Layout ----
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(6)

        # Beta banner (if not removed)
        settings = QSettings("HRMMonitor", "Settings")
        if not settings.value("beta_removed", False):
            beta_banner = QLabel("🔴 BETA")
            beta_banner.setFont(QFont("Segoe UI", int(9 * sc), QFont.Weight.Bold))
            beta_banner.setStyleSheet("color: #ff4444; background: transparent;")
            beta_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(beta_banner)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        self.heart_widget = HeartWidget(int(self.heart_size * sc * 1.3))
        top_row.addWidget(self.heart_widget)

        right_col = QVBoxLayout()
        right_col.setSpacing(3)

        self.bpm_lbl = QLabel("-- BPM")
        self.bpm_lbl.setFont(QFont("Consolas", int(self.bpm_size * sc), QFont.Weight.Bold))
        self.bpm_lbl.setStyleSheet("color: #00ff99; background: transparent;")
        right_col.addWidget(self.bpm_lbl)

        self.minmax_lbl = QLabel("min: --   max: --")
        self.minmax_lbl.setFont(QFont("Segoe UI", int(10 * sc)))
        self.minmax_lbl.setStyleSheet("color: #555555; background: transparent;")
        right_col.addWidget(self.minmax_lbl)

        self.conn_lbl = QLabel("● disconnected")
        self.conn_lbl.setFont(QFont("Segoe UI", int(10 * sc)))
        self.conn_lbl.setStyleSheet("color: #444444; background: transparent;")
        right_col.addWidget(self.conn_lbl)

        self.spotify_lbl = QLabel("")
        self.spotify_lbl.setFont(QFont("Segoe UI", int(9 * sc)))
        self.spotify_lbl.setStyleSheet("color: #1DB954; background: transparent;")
        self.spotify_lbl.setVisible(False)
        right_col.addWidget(self.spotify_lbl)

        self.mode_lbl = QLabel("mode: desktop")
        self.mode_lbl.setFont(QFont("Segoe UI", int(9 * sc)))
        self.mode_lbl.setStyleSheet("color: #3a3a4a; background: transparent;")
        right_col.addWidget(self.mode_lbl)

        self.mode_btn = QPushButton("⇄ Force Desktop")
        self.mode_btn.setFont(QFont("Segoe UI", int(9 * sc)))
        self.mode_btn.setFixedHeight(24)
        self.mode_btn.setStyleSheet(
            "QPushButton { background: #1a0000; border: 1px solid #550000; border-radius: 6px;"
            "  color: #884444; padding: 2px 10px; font-size: 10px; }"
            "QPushButton:hover { background: #2a0000; border-color: #880000; color: #cc6666; }"
        )
        self.mode_btn.clicked.connect(self._toggle_mode)
        right_col.addWidget(self.mode_btn)

        right_col.addStretch()
        top_row.addLayout(right_col)
        root.addLayout(top_row)

        self.graph = BPMGraph()
        self.graph.setFixedHeight(int(64 * sc))
        root.addWidget(self.graph)

        # Resize grip (bottom-right corner — works on frameless windows)
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch()
        self._grip = QSizeGrip(self)
        self._grip.setStyleSheet("background: transparent;")
        self._grip.setFixedSize(14, 14)
        grip_row.addWidget(self._grip)
        root.addLayout(grip_row)

        self.shake_timer = QTimer()
        self.shake_timer.timeout.connect(self._shake_tick)
        self.base_pos = self.pos()

        self._current_mode = "desktop"
        self._force_mode   = None
        self._last_bpm     = 0
        self._settings_window = None

        sig.bus.bpm_signal.connect(self._on_bpm)
        sig.bus.status_signal.connect(self._on_status)
        sig.bus.mode_signal.connect(self._on_mode)
        sig.bus.spotify_signal.connect(self._on_spotify)
        sig.bus.friend_signal.connect(self._on_friend)

    # ---- Handlers ----
    def _on_bpm(self, bpm: int):
        color = "#ff2222" if bpm >= BPM_HIGH else "#ffaa00" if bpm >= BPM_MED else "#00ff99"
        self.bpm_lbl.setText(f"{bpm} BPM")
        self.bpm_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self.graph.push(bpm)

        if self.session_min is None or bpm < self.session_min: self.session_min = bpm
        if self.session_max is None or bpm > self.session_max: self.session_max = bpm
        self.minmax_lbl.setText(f"min: {self.session_min}   max: {self.session_max}")

        self.heart_widget.set_bpm(bpm)
        self._last_bpm = bpm

        if self.shake_enabled:
            if   bpm >= SHAKE_HIGH_BPM: self._start_shake(SHAKE_HIGH_INT)
            elif bpm >= SHAKE_MED_BPM:  self._start_shake(SHAKE_MED_INT)
            elif bpm >= SHAKE_LOW_BPM:  self._start_shake(SHAKE_LOW_INT)
            else: self.shake_int = 0

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

    def _on_mode(self, mode: str):
        if self._force_mode is not None: return
        self._apply_mode(mode)

    def _on_spotify(self, info: dict):
        if info.get("track"):
            status = "▶" if info["playing"] else "⏸"
            track  = info["track"]
            artist = info["artist"]
            if len(track) > OVERLAY_TRACK_MAX_LEN:
                track = track[:OVERLAY_TRACK_MAX_LEN - 1] + "…"
            if len(artist) > OVERLAY_ARTIST_MAX_LEN:
                artist = artist[:OVERLAY_ARTIST_MAX_LEN - 1] + "…"
            self.spotify_lbl.setText(f"{status} {track}  —  {artist}")
            self.spotify_lbl.setVisible(True)
        else:
            self.spotify_lbl.setVisible(False)

    def _on_friend(self, info: dict):
        """Show a toast when a friend connects or disconnects from the HR share stream."""
        if info["type"] == "connected":
            msg  = f"Friend connected  •  {info['ip']}"
            icon = "🫀"
        else:
            msg  = f"Friend disconnected  •  {info['ip']}"
            icon = "💔"
        toast = NotificationToast(msg, icon)
        self._toasts.append(toast)
        # Clean up old closed toasts to avoid unbounded growth
        self._toasts = [t for t in self._toasts if t.isVisible()]

    def _toggle_mode(self):
        if self._force_mode == "desktop":
            self._force_mode = None
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

    # ---- Shake ----
    def _start_shake(self, intensity: int):
        self.base_pos  = self.pos()
        self.shake_int = intensity
        if not self.shake_timer.isActive():
            self.shake_timer.start(20)

    def _shake_tick(self):
        if self.shake_int <= 0:
            self.move(self.base_pos); self.shake_timer.stop(); return
        self.move(
            self.base_pos.x() + random.randint(-self.shake_int, self.shake_int),
            self.base_pos.y() + random.randint(-self.shake_int, self.shake_int),
        )

    # ---- Drag ----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.old_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self.old_pos:
            d = e.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + d.x(), self.y() + d.y())
            self.old_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self.old_pos = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
            if self._settings_window:
                self._settings_window.show()
                self._settings_window.raise_()
                self._settings_window.activateWindow()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(10, 0, 0, 210)))
        p.setPen(QPen(QColor(120, 0, 0, 160), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.end()


# ===========================================================
#  Viewer Overlay  (friend's minimal readout)
# ===========================================================
class ViewerOverlay(QWidget):
    _bpm_ready   = pyqtSignal(int)
    _status_ready = pyqtSignal(str, str)   # (text, css-color)

    def __init__(self, room_code: str):
        super().__init__()
        self.room_code  = room_code.strip().upper()
        self._mqtt_client = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(270, 140)

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

        self.name_lbl = QLabel(f"room: {self.room_code}")
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

        credit = QLabel("CRIMSON  •  crimsondreamz")
        credit.setFont(QFont("Segoe UI", 8))
        credit.setStyleSheet("color: #2a0000; background: transparent;")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        root.addWidget(credit)

        self._bpm_ready.connect(self._on_bpm)
        self._status_ready.connect(self._on_status)
        self.old_pos = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # needed so keyPressEvent fires
        threading.Thread(target=self._mqtt_thread, daemon=True).start()

    def _mqtt_thread(self):
        import json as _json, uuid as _uuid
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self._status_ready.emit(
                "● install paho-mqtt first",
                "color: #cc4400; background: transparent;")
            return

        topic = f"{MQTT_TOPIC_PREFIX}/{self.room_code}/bpm"

        def on_connect(c, userdata, flags, rc):
            if rc == 0:
                c.subscribe(topic, qos=0)
                self._status_ready.emit(
                    "● connected",
                    "color: #00cc44; background: transparent;")
            else:
                self._status_ready.emit(
                    f"● broker refused (rc={rc})",
                    "color: #cc4400; background: transparent;")

        def on_message(c, userdata, msg):
            try:
                data = _json.loads(msg.payload.decode())
                self._bpm_ready.emit(int(data["bpm"]))
            except Exception:
                pass

        def on_disconnect(c, userdata, rc):
            self._status_ready.emit(
                "● disconnected — reconnecting…",
                "color: #cc4400; background: transparent;")

        client_id = f"hrm-viewer-{_uuid.uuid4().hex[:8]}"
        self._mqtt_client = mqtt.Client(client_id=client_id)
        self._mqtt_client.on_connect    = on_connect
        self._mqtt_client.on_message    = on_message
        self._mqtt_client.on_disconnect = on_disconnect
        self._mqtt_client.reconnect_delay_set(min_delay=2, max_delay=30)

        try:
            self._mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self._mqtt_client.loop_forever()   # blocks; auto-reconnects on drop
        except Exception as e:
            self._status_ready.emit(
                f"● error: {e}",
                "color: #cc4400; background: transparent;")

    def _on_bpm(self, bpm: int):
        color = "#ff2222" if bpm >= BPM_HIGH else "#ffaa00" if bpm >= BPM_MED else "#00ff99"
        self.bpm_lbl.setText(f"{bpm} BPM")
        self.bpm_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self.heart_widget.set_bpm(bpm)

    def _on_status(self, text: str, style: str):
        self.conn_lbl.setText(text)
        self.conn_lbl.setStyleSheet(style)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._mqtt_client:
            try:
                self._mqtt_client.disconnect()
                self._mqtt_client.loop_stop()
            except Exception:
                pass
        super().closeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(10, 0, 0, 210)))
        p.setPen(QPen(QColor(120, 0, 0, 160), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.old_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self.old_pos:
            d = e.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + d.x(), self.y() + d.y())
            self.old_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self.old_pos = None
