# ♥ HRM Monitor v2

**A heart rate overlay for VRChat — shows your live BPM in-game, in VR, and to your friends.**

Made by **CRIMSON** · Discord: `crimsondreamz`

---

## What it does

HRM Monitor reads your heart rate from a **Pulsoid** sensor and:

- Shows a floating **desktop overlay** with live BPM, a scrolling graph, and colour-coded tiers
- Sends BPM to your **VRChat avatar** via OSC (avatar parameters + chatbox)
- Lets **friends watch your heart rate** live — no port forwarding, no account needed
- Displays a **VR wrist overlay** (Apple Watch style) when SteamVR is running
- Shows **Spotify now-playing** info alongside your BPM
- Supports **group watching** — see up to 5 friends' heart rates at once (horror game mode)

---

## Is it safe?

**Yes. Here is exactly what the app does and does not do.**

### What it connects to

| Connection | Why | Data sent |
|---|---|---|
| `wss://dev.pulsoid.net` | Reads your live heart rate | Your Pulsoid token (authentication only) |
| `127.0.0.1:9000` (local) | Sends BPM to VRChat via OSC | BPM number, chatbox text |
| `your-relay.railway.app` | Friend HR sharing relay | Room code + BPM number only |
| `api.github.com` | Checks for app updates | App version string only |
| `accounts.spotify.com` | Spotify OAuth (if enabled) | Spotify auth code |

### What it does NOT do

- ❌ Does not access your files, documents, or system
- ❌ Does not collect or store personal data
- ❌ Does not run in the background unless you launch it
- ❌ Does not install drivers, services, or startup entries
- ❌ Does not send your Pulsoid token to anyone except Pulsoid's own servers
- ❌ Does not modify VRChat files

### Verify yourself

- **Source code**: This entire repository is public. Every line of code is readable at  
  `github.com/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC/tree/v2`
- **VirusTotal**: Scan the `.exe` at [virustotal.com](https://www.virustotal.com) before running
- **No obfuscation**: The C# source compiles directly to the distributed `.exe` — build it yourself with `build.bat`
- **Settings stored locally**: All your settings (token, OSC config, etc.) are stored in Windows Registry at `HKCU\Software\HRMMonitor\v2` — you can inspect or delete them any time with `regedit`

### Build it yourself

If you don't trust the pre-built `.exe`, build from source:

```
git clone https://github.com/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC
cd Multi-Purpose-HRM-Monitor-For-VRC
git checkout v2
cd HRM-Monitor-v2
build.bat
```

Requires: [.NET 8 SDK](https://dotnet.microsoft.com/download) · The script installs it automatically if missing.

---

## Features

| Feature | Free | Premium |
|---|---|---|
| Live BPM overlay | ✅ | ✅ |
| VRChat OSC (avatar params) | ✅ | ✅ |
| VRChat chatbox | ✅ | ✅ |
| Friend HR sharing | ✅ | ✅ |
| Spotify now-playing | ✅ | ✅ |
| SteamVR wrist overlay | ✅ | ✅ |
| Group watch (horror mode) | ✅ | ✅ |
| Heartbeat sound effects | ✅ | ✅ |
| Invisible chatbox background | ❌ | ✅ |
| UI accent color + theme | ❌ | ✅ |
| Daily usage limit | 6 hrs | None |

**Premium: $5/month** · Pay via CashApp `DOES NOT WORK YET!!` · Get your key via Discord `/mykey`

---

## Setup

### 1. Get a Pulsoid token
Sign up at [pulsoid.net](https://pulsoid.net) → Settings → Integrations → Manual connection → copy the token.

### 2. Enable OSC in VRChat
Action Menu → Options → OSC → Enable

### 3. Run HRM Monitor
Open `HRMMonitor.exe` → paste your token in **Broadcaster** → click **START OVERLAY**

### 4. (Optional) Share with a friend
Tick **Broadcast my heart rate** → give them your **Room Code** → they enter it in the **Viewer** tab

---

## Supported sensors

Any heart rate monitor supported by Pulsoid — including:
- Polar (H9, H10, Verity Sense)
- Garmin, Wahoo, Coospo
- Apple Watch (via Pulsoid app)
- Android / iOS companion app

---

## Credits

Built with: [Pulsoid API](https://pulsoid.net) · [OpenVR](https://github.com/ValveSoftware/openvr) · [SpotifyAPI.Web](https://github.com/JohnnyCrazy/SpotifyAPI-NET) · [Hardcodet NotifyIcon](https://github.com/hardcodet/wpf-notifyicon) · [Websocket.Client](https://github.com/Marfusios/websocket-client)
