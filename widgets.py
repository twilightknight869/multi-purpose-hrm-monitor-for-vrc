# ===========================================================
#  HRM Monitor — Reusable Widgets
# ===========================================================
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtGui  import (
    QPainter, QColor, QPen, QLinearGradient, QBrush,
    QPainterPath, QPolygon, QFont,
)
from PyQt6.QtCore import Qt, QTimer, QPoint

from constants import GRAPH_MAX_POINTS, BPM_HIGH, BPM_MED


# ===========================================================
#  BPM Graph
# ===========================================================
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

        pts = [(int(i / (GRAPH_MAX_POINTS - 1) * w), y_for(v))
               for i, v in enumerate(self.history)]

        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor(200, 0, 0, 120))
        gradient.setColorAt(1.0, QColor(200, 0, 0, 0))

        fill_pts = [QPoint(pts[0][0], h)] + [QPoint(x, y) for x, y in pts] + [QPoint(pts[-1][0], h)]
        p.setBrush(QBrush(gradient))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygon(fill_pts))

        p.setPen(QPen(QColor(255, 60, 60), 2))
        for i in range(1, len(pts)):
            p.drawLine(pts[i-1][0], pts[i-1][1], pts[i][0], pts[i][1])

        lx, ly = pts[-1]
        p.setBrush(QBrush(QColor(255, 80, 80)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(lx - 4, ly - 4, 8, 8)
        p.end()


# ===========================================================
#  Heart Widget  (lub-dub beat + radial glow + ripple rings)
# ===========================================================
class HeartWidget(QWidget):
    def __init__(self, size_px: int, parent=None):
        super().__init__(parent)
        self.size_px = size_px
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.ripples: list[dict] = []

        fixed = size_px + 52
        self.setFixedSize(fixed, fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 60 fps animation tick
        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(16)

        # Beat timer fires once per cardiac cycle
        self._beat_interval = 1000
        self._beat_timer = QTimer()
        self._beat_timer.timeout.connect(self._on_beat)
        self._beat_timer.start(self._beat_interval)

        # Phase state machine:
        # idle → lub_in → lub_out → dub_wait → dub_in → dub_out → idle
        self._sq_phase       = 'idle'
        self._sq_t           = 1.0
        self._sq_speed       = 0.0
        self._lub_amount     = 0.28   # main beat amplitude
        self._dub_amount     = 0.13   # secondary beat amplitude
        self._dub_wait_ticks = 0      # ticks before dub fires

        # Glow
        self._glow_alpha  = 0.0
        self._glow_target = 0.0

        self._color        = QColor(200, 40, 40)
        self._target_color = QColor(200, 40, 40)
        self._path         = self._build_path()

    def set_bpm(self, bpm: int):
        interval = int(60000 / max(30, min(bpm, 220)))
        if interval != self._beat_interval:
            self._beat_interval = interval
            self._beat_timer.start(interval)
        if bpm >= BPM_HIGH:
            self._target_color = QColor(255, 30,  30)
            self._lub_amount = 0.42;  self._dub_amount = 0.21
        elif bpm >= BPM_MED:
            self._target_color = QColor(230, 120, 20)
            self._lub_amount = 0.32;  self._dub_amount = 0.16
        else:
            self._target_color = QColor(200, 40,  40)
            self._lub_amount = 0.24;  self._dub_amount = 0.12

    def _on_beat(self):
        """Fire the lub (main beat)."""
        self._sq_t     = 0.0
        self._sq_phase = 'lub_in'
        beat_frac      = self._beat_interval * 0.28
        self._sq_speed = 1.0 / max(beat_frac / 16.0, 1)

        # dub fires after ~40% of the beat interval
        self._dub_wait_ticks = int(self._beat_interval * 0.40 / 16)

        # Glow burst on lub
        self._glow_target = 90.0

        # Two ripple rings on lub
        self.ripples.append({'r': 0.0, 'alpha': 240, 'delay': 0})
        self.ripples.append({'r': 0.0, 'alpha': 160, 'delay': 10})

    def _tick(self):
        # ── Lub ──────────────────────────────────────────────
        if self._sq_phase == 'lub_in':
            self._sq_t += self._sq_speed * 3.0
            if self._sq_t >= 1.0:
                self._sq_t = 1.0
                self._sq_phase = 'lub_out'
            depth = self._lub_amount * (1.0 - self._sq_t) ** 2   # ease-out
            self.scale_x = 1.0 + depth * 0.65
            self.scale_y = 1.0 - depth * 1.15

        elif self._sq_phase == 'lub_out':
            self._sq_t += self._sq_speed * 1.7
            if self._sq_t >= 2.0:
                self._sq_t = 2.0
                self._sq_phase = 'dub_wait'
                self.scale_x = self.scale_y = 1.0
            else:
                t    = self._sq_t - 1.0
                ease = t * t * (3.0 - 2.0 * t)
                depth = self._lub_amount * (1.0 - ease) * 0.40
                self.scale_x = 1.0 + depth * 0.20
                self.scale_y = 1.0 - depth * 0.35

        # ── Pause between lub and dub ─────────────────────────
        elif self._sq_phase == 'dub_wait':
            self._dub_wait_ticks -= 1
            if self._dub_wait_ticks <= 0:
                self._sq_t     = 0.0
                self._sq_phase = 'dub_in'
                # Smaller ripple on dub
                self.ripples.append({'r': 0.0, 'alpha': 150, 'delay': 0})
                self._glow_target = 50.0

        # ── Dub ──────────────────────────────────────────────
        elif self._sq_phase == 'dub_in':
            self._sq_t += self._sq_speed * 3.8
            if self._sq_t >= 1.0:
                self._sq_t = 1.0
                self._sq_phase = 'dub_out'
            depth = self._dub_amount * (1.0 - self._sq_t) ** 2
            self.scale_x = 1.0 + depth * 0.45
            self.scale_y = 1.0 - depth * 0.80

        elif self._sq_phase == 'dub_out':
            self._sq_t += self._sq_speed * 2.2
            if self._sq_t >= 2.0:
                self._sq_t = 2.0
                self._sq_phase = 'idle'
                self.scale_x = self.scale_y = 1.0
            else:
                t    = self._sq_t - 1.0
                ease = t * t * (3.0 - 2.0 * t)
                depth = self._dub_amount * (1.0 - ease) * 0.28
                self.scale_x = 1.0 + depth * 0.14
                self.scale_y = 1.0 - depth * 0.24

        # ── Ripples ───────────────────────────────────────────
        alive = []
        for rip in self.ripples:
            if rip['delay'] > 0:
                rip['delay'] -= 1; alive.append(rip); continue
            rip['r']     += 2.0
            rip['alpha'] -= 7.5
            if rip['alpha'] > 0:
                alive.append(rip)
        self.ripples = alive

        # ── Glow decay ────────────────────────────────────────
        self._glow_alpha  += (self._glow_target - self._glow_alpha) * 0.22
        self._glow_target  = max(0.0, self._glow_target - 4.0)

        # ── Color lerp ────────────────────────────────────────
        def lc(a, b): return int(a + (b - a) * 0.10)
        self._color = QColor(
            lc(self._color.red(),   self._target_color.red()),
            lc(self._color.green(), self._target_color.green()),
            lc(self._color.blue(),  self._target_color.blue()),
        )
        self.update()

    def paintEvent(self, event):
        p  = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width()  / 2
        cy = self.height() / 2
        r  = self.size_px  / 2

        # ── Radial glow (heart shape drawn at increasing sizes) ──
        ga = int(max(0, min(255, self._glow_alpha)))
        if ga > 4:
            for i in range(5, 0, -1):
                g_scale = 1.0 + i * 0.17
                g_alpha = max(0, int(ga * (0.65 ** i) * 0.7))
                if g_alpha < 3:
                    continue
                gc = QColor(self._color.red(), self._color.green(), self._color.blue(), g_alpha)
                p.save()
                p.translate(cx, cy)
                p.scale(self.scale_x * r * g_scale, self.scale_y * r * g_scale)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(gc))
                p.drawPath(self._path)
                p.restore()

        # ── Ripple rings ─────────────────────────────────────────
        for rip in self.ripples:
            if rip['delay'] > 0:
                continue
            rc = QColor(self._color)
            rc.setAlpha(max(0, min(255, int(rip['alpha']))))
            p.setPen(QPen(rc, 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rad = r + rip['r']
            p.drawEllipse(int(cx - rad), int(cy - rad), int(rad * 2), int(rad * 2))

        # ── Heart body ───────────────────────────────────────────
        p.save()
        p.translate(cx, cy)
        p.scale(self.scale_x * r, self.scale_y * r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._color))
        p.drawPath(self._path)

        # Inner lighter gradient strip (gives depth)
        inner = QColor(
            min(255, self._color.red()   + 60),
            min(255, self._color.green() + 30),
            min(255, self._color.blue()  + 10),
            80,
        )
        p.setBrush(QBrush(inner))
        p.drawPath(self._build_highlight())

        # Specular gloss dot
        p.setBrush(QBrush(QColor(255, 255, 255, 60)))
        p.drawPath(self._build_gloss())
        p.restore()

        p.end()

    @staticmethod
    def _build_path():
        path = QPainterPath()
        path.moveTo(0, 0.9)
        path.cubicTo(-0.05,  0.6, -1.0,  0.4, -1.0, -0.1)
        path.cubicTo(-1.0,  -0.6, -0.5, -0.9,  0.0, -0.3)
        path.cubicTo( 0.5,  -0.9,  1.0, -0.6,  1.0, -0.1)
        path.cubicTo( 1.0,   0.4,  0.05, 0.6,  0.0,  0.9)
        path.closeSubpath()
        return path

    @staticmethod
    def _build_highlight():
        """Soft inner lighter area (left lobe)."""
        path = QPainterPath()
        path.addEllipse(-0.60, -0.60, 0.42, 0.30)
        return path

    @staticmethod
    def _build_gloss():
        """Small specular dot — top-left of left lobe."""
        path = QPainterPath()
        path.addEllipse(-0.52, -0.68, 0.18, 0.13)
        return path


