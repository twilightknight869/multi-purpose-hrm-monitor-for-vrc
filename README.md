# HRM Monitor — Multi-Purpose Heart Rate Monitor for VRChat


THE PYTHON VERSION IS NOW DEPRECATED PLEASE LOCATE TO V2



A real-time heart rate overlay built for VRChat users. Connects to Pulsoid, displays your BPM on a desktop overlay, sends it to VRChat via OSC, shows it in the VRChat chatbox, streams it to friends, and integrates with Spotify — all in one app.

> **Questions or support?** Discord: `crimsondreamz`

---

## Features

- **Real-time BPM display** — Connects to Pulsoid via WebSocket for live heart rate data
- **Animated heart overlay** — Lub-dub double-beat animation with radial glow and ripple rings that react to your BPM
- **BPM graph** — Scrolling history graph showing your heart rate over time
- **Resizable overlay** — Drag the corner to make the overlay any size you want
- **VRChat OSC integration** — Sends your BPM and HRPercent as avatar parameters so your avatar can react to your heart rate
- **VRChat chatbox** — Fully customizable chatbox template with live preview; supports placeholders for BPM, block bar, tier, emoji, and Spotify track info
- **Status rotation** — Cycle through custom chatbox status lines that append to your HR line on a timer
- **SteamVR wrist overlay** — Shows your BPM on your in-game left wrist when SteamVR is running; auto-switches back to desktop when SteamVR closes
- **Spotify Now Playing** — Displays the current track and artist on the overlay and optionally embeds it in the VRChat chatbox
- **Friend HR sharing** — Broadcast your heart rate over TCP so friends can open a viewer overlay and watch your BPM live
- **Friend connection notifications** — A toast notification pops up whenever a friend connects or disconnects from your stream
- **Detailed viewer error reports** — If a viewer can't connect, the reason is shown (refused, timed out, unreachable, etc.)
- **Adjustable appearance** — Scale, opacity, heart size, and BPM font size all controlled by sliders
- **Screen shake** — The overlay shakes at configurable intensities as your BPM rises
- **Polished dark UI** — MagicChatbox-inspired flat navigation, clean groupboxes, and a dark red horror theme

---

## Requirements

- Python 3.10 or newer
- A [Pulsoid](https://pulsoid.net) account and a compatible heart rate monitor

See **SETUP.txt** for full installation and configuration instructions.

---

## Quick Start

```bash
pip install PyQt6 websocket-client python-osc
python main.py
```

---

## License

This project is provided as-is for personal use.

---

*Made by CRIMSON — Discord: `crimsondreamz`*
