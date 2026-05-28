# ===========================================================
#  HRM Monitor — Background Threads
# ===========================================================
import base64
import json
import math
import pathlib
import random
import subprocess
import threading
import time
import urllib.parse
import urllib.request

import websocket

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
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIPY_OK = True
except ImportError:
    SPOTIPY_OK = False

from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPainterPath
from PyQt6.QtCore import QRect, Qt

import signals as sig
from constants import (
    WS_URL, VRC_OSC_HR_PARAM, VRC_OSC_PCT_PARAM, VRC_HR_MAX,
    VRC_CHATBOX_INPUT, CHATBOX_INTERVAL_SEC,
    VR_OVERLAY_KEY, VR_OVERLAY_NAME, VR_OVERLAY_WIDTH,
    VR_TEXTURE_SIZE, STEAMVR_POLL_SEC,
    ABLY_CHANNEL_PREFIX,
    SPOTIFY_POLL_SEC, STATUS_ROTATE_SEC,
    BPM_HIGH, BPM_MED,
    VRC_CHATBOX_MAX_LENGTH, VRC_STATUS_MAX_LENGTH, VRC_HLINE_MAX_LENGTH,
    CHATBOX_TRACK_MAX_LEN, CHATBOX_ARTIST_MAX_LEN,
)


# ===========================================================
#  Pulsoid WebSocket
# ===========================================================
_ws_instance = None

def websocket_thread(token: str):
    global _ws_instance

    def on_open(ws):
        sig.bus.status_signal.emit("connected")

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "data" in data:
                sig.bus.bpm_signal.emit(data["data"]["heart_rate"])
        except Exception as e:
            print("WS message error:", e)

    def on_error(ws, error):
        sig.bus.status_signal.emit("error")
        print("WebSocket error:", error)

    def on_close(ws, code, msg):
        sig.bus.status_signal.emit("disconnected")
        print("Disconnected — reconnecting in 5 s…")
        time.sleep(5)
        websocket_thread(token)

    url = f"{WS_URL}?access_token={token}"
    _ws_instance = websocket.WebSocketApp(
        url,
        on_open=on_open, on_message=on_message,
        on_error=on_error, on_close=on_close,
    )
    _ws_instance.run_forever()


# ===========================================================
#  OSC Thread  (VRChat HR params + chatbox)
# ===========================================================
def _truncate_text(text: str, max_len: int) -> str:
    """Truncate text and add ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def _build_chatbox_line(bpm: int, template: str, spotify: dict) -> str:
    """Render the chatbox string from a user-editable template.

    Supported placeholders:
        {bpm}    – numeric BPM
        {bar}    – 10-segment block bar
        {tier}   – LOW / MED / HIGH
        {icon}   – tier heart emoji
        {track}  – Spotify track name (or empty)
        {artist} – Spotify artist name (or empty)
    """
    if bpm >= BPM_HIGH:
        icon, tier = "❤️", "HIGH"
    elif bpm >= BPM_MED:
        icon, tier = "🧡", "MED"
    else:
        icon, tier = "💚", "LOW"

    filled = round((min(bpm, VRC_HR_MAX) / VRC_HR_MAX) * 10)
    bar    = "█" * filled + "░" * (10 - filled)

    # Truncate Spotify names before plugging into the template
    raw_track  = spotify.get("track",  "")
    raw_artist = spotify.get("artist", "")
    track  = _truncate_text(raw_track,  CHATBOX_TRACK_MAX_LEN)  if raw_track  else ""
    artist = _truncate_text(raw_artist, CHATBOX_ARTIST_MAX_LEN) if raw_artist else ""

    # Sanitise the template so unknown/malformed braces don't crash str.format().
    # Strategy: walk through the string char-by-char, escape any { } that
    # don't belong to one of our known placeholders.
    known = {'bpm', 'bar', 'tier', 'icon', 'track', 'artist'}
    safe: list[str] = []
    i, n = 0, len(template)
    while i < n:
        ch = template[i]
        if ch == '{':
            # Find matching closing brace
            j = template.find('}', i + 1)
            if j == -1:
                # Unclosed brace — escape it
                safe.append('{{')
                i += 1
            else:
                inner = template[i + 1:j]
                if inner in known:
                    safe.append('{' + inner + '}')
                else:
                    safe.append('{{' + inner + '}}')
                i = j + 1
        elif ch == '}':
            # Lone closing brace — escape it
            safe.append('}}')
            i += 1
        else:
            safe.append(ch)
            i += 1
    safe_template = ''.join(safe)

    try:
        rendered = safe_template.format(
            bpm    = bpm,
            bar    = bar,
            tier   = tier,
            icon   = icon,
            track  = track,
            artist = artist,
        )
    except (KeyError, ValueError):
        rendered = f"{icon} {bpm} BPM [{bar}]"
    return _truncate_text(rendered, VRC_HLINE_MAX_LENGTH)


def osc_thread(cfg: dict):
    """
    Sends to VRChat OSC every second:
      • /avatar/parameters/<hr_param>         (float — numeric BPM)
      • /avatar/parameters/<pct_param>        (float 0-1)
      • /avatar/parameters/SpotifyTrack       (string, if spotify enabled)
      • /avatar/parameters/SpotifyArtist      (string, if spotify enabled)
      • /chatbox/input                        (if chatbox enabled)

    Statuses from the rotator are appended to each chatbox send on their
    own rotation timer — they never fire as a separate OSC call, so they
    cannot cancel the HR chatbox line.

    cfg keys:
        osc_ip, osc_port,
        hr_param, pct_param,
        chatbox_enabled (bool),
        chatbox_template (str),
        spotify_in_chatbox (bool),
        spotify_osc_enabled (bool),   ← send track/artist as OSC params
        rotate_enabled (bool),
        statuses (list[str]),
        rotate_sec (int),
    """
    # Seed the live shared config so the UI can update it without restart
    sig.set_osc_cfg(cfg)

    # Fixed at startup — changing these requires a restart
    client    = osc_udp.SimpleUDPClient(cfg["osc_ip"], cfg["osc_port"])
    hr_param  = cfg.get("hr_param",  VRC_OSC_HR_PARAM)
    pct_param = cfg.get("pct_param", VRC_OSC_PCT_PARAM)
    spotify_osc = cfg.get("spotify_osc_enabled", True)

    # Rotation bookkeeping (persists across config updates)
    status_idx       = 0
    last_status_swap = time.time()

    last_chatbox_send = 0.0
    _last_spotify     = {"track": "", "artist": ""}

    while True:
        try:
            # Re-read mutable config every tick so UI changes take effect immediately
            live        = sig.get_osc_cfg()
            chatbox_enabled = live.get("chatbox_enabled", False)
            template        = live.get("chatbox_template", "{icon} {bpm} BPM  [{bar}]")
            spotify_in_box  = live.get("spotify_in_chatbox", False)
            statuses        = live.get("statuses", [])
            rotate_enabled  = live.get("rotate_enabled", False) and bool(statuses)
            rotate_sec      = max(int(live.get("rotate_sec", STATUS_ROTATE_SEC)),
                                  int(CHATBOX_INTERVAL_SEC) + 1)

            bpm     = sig.get_bpm()
            spotify = sig.get_spotify()

            if bpm > 0:
                # ── HR avatar parameters ──────────────────────────────
                client.send_message(hr_param,  float(bpm))
                client.send_message(pct_param, float(min(bpm, VRC_HR_MAX) / VRC_HR_MAX))

                # ── Spotify avatar parameters (string OSC) ───────────
                if spotify_osc and spotify.get("track"):
                    track  = spotify["track"]
                    artist = spotify["artist"]
                    if track != _last_spotify["track"] or artist != _last_spotify["artist"]:
                        client.send_message("/avatar/parameters/SpotifyTrack",  track)
                        client.send_message("/avatar/parameters/SpotifyArtist", artist)
                        _last_spotify = {"track": track, "artist": artist}

                # ── Chatbox (HR line + optional status suffix) ────────
                if chatbox_enabled:
                    now = time.time()
                    if now - last_chatbox_send >= CHATBOX_INTERVAL_SEC:
                        # Clamp status_idx in case the list shrank
                        if statuses:
                            status_idx = status_idx % len(statuses)

                        if rotate_enabled:
                            if now - last_status_swap >= rotate_sec:
                                status_idx       = (status_idx + 1) % len(statuses)
                                last_status_swap = now
                            active_status = statuses[status_idx]
                        else:
                            active_status = ""

                        # ── Build each section independently then join ────
                        # Line 1: HR line from template (track/artist NOT
                        #         embedded here — they get their own line below
                        #         so they never collide with the bar or status).
                        hr_line = _build_chatbox_line(bpm, template, {})
                        parts = [hr_line]

                        # Line 2 (optional): Spotify now-playing
                        if spotify_in_box and spotify.get("track"):
                            _st = _truncate_text(spotify["track"],
                                                 CHATBOX_TRACK_MAX_LEN)
                            _sa = spotify.get("artist", "")
                            _sa = _truncate_text(_sa, CHATBOX_ARTIST_MAX_LEN) if _sa else ""
                            spotify_line = f"\U0001f3b5 {_st}"
                            if _sa:
                                spotify_line += f" — {_sa}"
                            parts.append(spotify_line)

                        # Line 3 (optional): rotating status
                        if active_status:
                            _st = spotify.get("track",  "")
                            _sa = spotify.get("artist", "")
                            try:
                                rendered_status = active_status.format(
                                    bpm    = bpm,
                                    tier   = ("HIGH" if bpm >= BPM_HIGH
                                              else "MED" if bpm >= BPM_MED else "LOW"),
                                    icon   = ("❤️" if bpm >= BPM_HIGH
                                              else "🧡" if bpm >= BPM_MED else "💚"),
                                    track  = _truncate_text(_st, CHATBOX_TRACK_MAX_LEN)  if _st else "",
                                    artist = _truncate_text(_sa, CHATBOX_ARTIST_MAX_LEN) if _sa else "",
                                )
                            except (KeyError, ValueError):
                                rendered_status = active_status
                            parts.append(_truncate_text(rendered_status, VRC_STATUS_MAX_LENGTH))

                        line = _truncate_text("\n".join(parts), VRC_CHATBOX_MAX_LENGTH)

                        client.send_message(VRC_CHATBOX_INPUT, [line, True, False])
                        sig.bus.chatbox_signal.emit(line)
                        last_chatbox_send = now

        except Exception as e:
            print("OSC error:", e)
        time.sleep(1)


# ===========================================================
#  SteamVR Wrist Overlay
# ===========================================================
def _steamvr_running() -> bool:
    try:
        # CREATE_NO_WINDOW prevents the cmd flash every poll cycle on Windows
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq vrserver.exe", "/NH"],
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        ).decode()
        return "vrserver.exe" in out
    except Exception:
        return False


def _render_vr_texture(bpm: int) -> bytes:
    from PyQt6.QtGui import QImage
    size = VR_TEXTURE_SIZE
    img  = QImage(size, size, QImage.Format.Format_RGBA8888)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setBrush(QBrush(QColor(12, 0, 0, 210)))
    p.setPen(QPen(QColor(120, 0, 0, 160), 2))
    p.drawRoundedRect(4, 4, size-8, size-8, 20, 20)

    p.save()
    p.translate(size * 0.28, size * 0.42)
    r = size * 0.22
    p.scale(r, r)
    fill = (QColor(255,30,30)  if bpm >= BPM_HIGH
            else QColor(230,120,20) if bpm >= BPM_MED
            else QColor(200,40,40))
    p.setBrush(QBrush(fill)); p.setPen(Qt.PenStyle.NoPen)
    path = QPainterPath()
    path.moveTo(0, 0.9)
    path.cubicTo(-0.05, 0.6, -1.0,  0.4, -1.0, -0.1)
    path.cubicTo(-1.0, -0.6, -0.5, -0.9,  0.0, -0.3)
    path.cubicTo( 0.5, -0.9,  1.0, -0.6,  1.0, -0.1)
    path.cubicTo( 1.0,  0.4,  0.05, 0.6,  0.0,  0.9)
    path.closeSubpath()
    p.drawPath(path)
    p.restore()

    tc = (QColor(255,60,60)   if bpm >= BPM_HIGH
          else QColor(255,170,0) if bpm >= BPM_MED
          else QColor(0,255,153))
    p.setPen(tc)
    p.setFont(QFont("Consolas", 36, QFont.Weight.Bold))
    p.drawText(QRect(size//2-10, size//2-28, size//2, 48),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               str(bpm) if bpm > 0 else "--")
    p.setPen(QColor(150, 150, 150))
    p.setFont(QFont("Consolas", 14))
    p.drawText(QRect(size//2-10, size//2+22, size//2, 28),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "BPM")
    p.end()

    ptr = img.bits()
    ptr.setsize(size * size * 4)
    return bytes(ptr)


def steamvr_watcher_thread(cfg: dict):
    vr_system = vr_overlay = overlay_handle = None
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
            print("OpenVR init error:", e); return False

    def _shutdown_vr():
        nonlocal vr_system, vr_overlay, overlay_handle
        try:
            if vr_overlay and overlay_handle:
                vr_overlay.destroyOverlay(overlay_handle)
        except Exception: pass
        try: openvr.shutdown()
        except Exception: pass
        vr_system = vr_overlay = overlay_handle = None

    def _update_wrist_transform():
        try:
            poses = vr_system.getDeviceToAbsoluteTrackingPose(
                openvr.TrackingUniverseStanding, 0, openvr.k_unMaxTrackedDeviceCount)
            idx = vr_system.getTrackedDeviceIndexForControllerRole(
                openvr.TrackedControllerRole_LeftHand)
            if idx == openvr.k_unTrackedDeviceIndexInvalid: return
            pose = poses[idx]
            if not pose.bPoseIsValid: return
            mat = pose.mDeviceToAbsoluteTracking
            transform = openvr.HmdMatrix34_t()
            for i in range(3):
                for j in range(4):
                    transform[i][j] = mat[i][j]
            transform[1][3] += 0.06
            vr_overlay.setOverlayTransformAbsolute(
                overlay_handle, openvr.TrackingUniverseStanding, transform)
        except Exception: pass

    while True:
        running = _steamvr_running()
        if running and not was_running:
            if _init_vr():
                was_running = True
                sig.bus.mode_signal.emit("vr")
        elif not running and was_running:
            _shutdown_vr()
            was_running = False
            sig.bus.mode_signal.emit("desktop")

        if was_running and vr_overlay and overlay_handle:
            try:
                _update_wrist_transform()
                raw = _render_vr_texture(sig.get_bpm())
                vr_overlay.setOverlayRaw(overlay_handle, raw, VR_TEXTURE_SIZE, VR_TEXTURE_SIZE, 4)
            except Exception as e:
                print("VR render error:", e)
            time.sleep(1 / 30)
        else:
            time.sleep(STEAMVR_POLL_SEC)


# ===========================================================
#  Spotify Poller
# ===========================================================
def spotify_thread(client_id: str, client_secret: str, redirect_uri: str):
    """
    Polls the Spotify Web API every SPOTIFY_POLL_SEC seconds.
    Emits spotify_signal with {"track": ..., "artist": ..., "playing": bool}.

    Fixes vs original:
    - Uses a persistent token cache in the user's home directory so the browser auth only
      happens once even across restarts.
    - Calls sp.current_playback() with a fresh auth manager reference on
      every poll so the access token is always refreshed when it expires —
      the old code held a single sp object that never re-checked the token,
      causing it to silently return the last cached response indefinitely.
    - Properly detects when nothing is playing and clears the signal.

    Requires spotipy: pip install spotipy
    """
    if not SPOTIPY_OK:
        print("spotipy not installed — Spotify disabled"); return

    scope = "user-read-playback-state"
    cache_path = str(pathlib.Path.home() / ".spotify_cache")
    try:
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            open_browser=True,
            cache_path=cache_path,
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
    except Exception as e:
        print("Spotify auth error:", e); return

    _last_track  = None
    _last_artist = None

    while True:
        try:
            # Explicitly refresh the token if it's expired before every call.
            # This is the key fix — without it spotipy silently returns stale
            # data after the 1-hour access token expires.
            token_info = auth_manager.get_cached_token()
            if token_info and auth_manager.is_token_expired(token_info):
                auth_manager.refresh_access_token(token_info["refresh_token"])
                sp = spotipy.Spotify(auth_manager=auth_manager)

            pb = sp.current_playback()

            if pb and pb.get("item"):
                item    = pb["item"]
                track   = item.get("name", "")
                artists = ", ".join(a["name"] for a in item.get("artists", []))
                playing = pb.get("is_playing", False)
                info    = {"track": track, "artist": artists, "playing": playing}
            else:
                # Nothing playing or playback paused with no item
                info = {"track": "", "artist": "", "playing": False}

            # Only emit when something actually changed to reduce noise
            if info["track"] != _last_track or info["artist"] != _last_artist:
                _last_track  = info["track"]
                _last_artist = info["artist"]
                sig.bus.spotify_signal.emit(info)
            elif pb is not None:
                # Still emit playing-state changes (play/pause) even if track is same
                sig.bus.spotify_signal.emit(info)

        except Exception as e:
            print("Spotify poll error:", e)
            # On error emit empty so the overlay doesn't show a stale track
            sig.bus.spotify_signal.emit({"track": "", "artist": "", "playing": False})
            _last_track = _last_artist = None

        time.sleep(SPOTIFY_POLL_SEC)


# ===========================================================
#  Status Auto-Rotator  (VRChat chatbox status lines)
# ===========================================================
def status_rotator_thread(cfg: dict):
    """
    DEPRECATED — status rotation is now handled directly inside osc_thread
    so that statuses and the HR chatbox line share the same /chatbox/input
    send and can never cancel each other out.

    This function intentionally does nothing; it exists only so that
    settings_window.py can still call it without errors.
    """
    return


# ===========================================================
#  Friend HR Sharing — Ably Realtime  (no port forwarding needed)
# ===========================================================
def ably_share_thread(room_code: str, api_key: str):
    """
    Publishes live BPM to Ably Realtime so friends can connect from
    anywhere without port forwarding. Uses port 443 (HTTPS) so it is
    never blocked by firewalls or NAT. No extra library required.

    Get a free API key at https://ably.com (free tier: 6M msgs/month).
    Enter the key once in Settings → Friend HR Sharing.

    Channel: hrm-monitor-v1/{room_code}
    """
    if not api_key:
        print("[Share] No Ably API key set — add one in Settings")
        sig.bus.friend_signal.emit({
            "type": "error",
            "ip":   "No Ably API key — add one in Settings → Friend HR Sharing",
        })
        return

    channel  = urllib.parse.quote(f"{ABLY_CHANNEL_PREFIX}/{room_code}", safe="")
    url      = f"https://rest.ably.io/channels/{channel}/messages"
    auth_hdr = "Basic " + base64.b64encode(api_key.encode()).decode()
    headers  = {"Authorization": auth_hdr, "Content-Type": "application/json"}

    print(f"[Share] Ably publishing to channel hrm-monitor-v1/{room_code}")

    while True:
        bpm     = sig.get_bpm()
        payload = json.dumps({
            "name": "bpm",
            "data": json.dumps({"bpm": bpm, "alive": True}),
        }).encode()
        try:
            req = urllib.request.Request(url, data=payload,
                                         headers=headers, method="POST")
            urllib.request.urlopen(req, timeout=6)
        except Exception as e:
            print(f"[Share] Ably publish error: {e}")
        time.sleep(2)


# Keep old name as alias so any cached imports don't break
def mqtt_share_thread(room_code: str):
    """Deprecated — replaced by ably_share_thread."""
    print("[Share] mqtt_share_thread called but Ably is now used — use ably_share_thread instead")
    return
