# ===========================================================
#  HRM Monitor — Signal Bus & Shared State
# ===========================================================
import threading

from PyQt6.QtCore import QObject, pyqtSignal


class _Bus(QObject):
    bpm_signal      = pyqtSignal(int)        # new BPM reading
    status_signal   = pyqtSignal(str)        # "connected" / "disconnected" / "error"
    mode_signal     = pyqtSignal(str)        # "desktop" / "vr"
    spotify_signal  = pyqtSignal(dict)       # {"track": ..., "artist": ..., "playing": bool}
    chatbox_signal  = pyqtSignal(str)        # fully-rendered chatbox line (for preview)
    friend_signal   = pyqtSignal(dict)       # {"type": "connected"/"disconnected", "ip": str}

bus = _Bus()


# -------------------------------------------------------
#  Thread-safe shared values (read by OSC / VR threads)
# -------------------------------------------------------
_lock               = threading.Lock()
_shared_bpm: int    = 0
_shared_spotify: dict = {"track": "", "artist": "", "playing": False}
_shared_osc_cfg: dict = {}   # live OSC config — updated from UI without restart


def get_bpm() -> int:
    with _lock:
        return _shared_bpm

def set_bpm(bpm: int) -> None:
    global _shared_bpm
    with _lock:
        _shared_bpm = bpm

def get_spotify() -> dict:
    with _lock:
        return dict(_shared_spotify)

def set_spotify(info: dict) -> None:
    global _shared_spotify
    with _lock:
        _shared_spotify = dict(info)

def get_osc_cfg() -> dict:
    with _lock:
        return dict(_shared_osc_cfg)

def set_osc_cfg(cfg: dict) -> None:
    global _shared_osc_cfg
    with _lock:
        _shared_osc_cfg = dict(cfg)


# Wire Qt signal → shared state so threads always have the latest value
def _on_bpm(bpm: int):       set_bpm(bpm)
def _on_spotify(info: dict): set_spotify(info)

bus.bpm_signal.connect(_on_bpm)
bus.spotify_signal.connect(_on_spotify)
