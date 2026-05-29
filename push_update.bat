@echo off
title HRM Monitor v2 - Push + Release
color 0C
echo.
echo  ==========================================
echo   HRM Monitor v2 - Push to GitHub
echo  ==========================================
echo.

cd /d "%~dp0"

:: ── Read version from csproj ─────────────────────────────────────
for /f "tokens=2 delims=><" %%v in ('findstr /i "<Version>" HRMMonitor.csproj') do set VERSION=%%v
echo  Version: v%VERSION%
echo.

:: ── Kill running instance ─────────────────────────────────────────
taskkill /f /im HRMMonitor.exe >nul 2>&1

:: ── Build release exe first ───────────────────────────────────────
echo  Building release exe...
dotnet publish -c Release -r win-x64 --self-contained true ^
    -p:PublishSingleFile=true ^
    -p:IncludeNativeLibrariesForSelfExtract=true ^
    -p:EnableCompressionInSingleFile=true ^
    -o dist >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Build failed - fix errors before pushing.
    pause & exit /b 1
)
echo  [OK] dist\HRMMonitor.exe built
echo.

:: ── Git push ──────────────────────────────────────────────────────
if not exist ".git" (
    git init
    git remote add origin https://github.com/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC.git
)

echo  Staging files...
git add -A

set /p MSG="Commit message (Enter for default 'v%VERSION% update'): "
if "%MSG%"=="" set MSG=v%VERSION% update

git commit -m "%MSG%"
echo.

echo  Pushing to GitHub (branch: v2)...
git push -u origin HEAD:v2
echo.

:: ── Check for gh CLI ─────────────────────────────────────────────
gh --version >nul 2>&1
if errorlevel 1 (
    echo  [!] GitHub CLI not found.
    echo  Install from: https://cli.github.com  then run this script again.
    echo.
    echo  The code has been pushed. Create the release manually at:
    echo  https://github.com/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC/releases/new
    pause & exit /b 0
)

:: ── Build release notes (no dev features) ────────────────────────
set NOTES=## HRM Monitor v%VERSION%^

^

### What's New^

^

**Heart Rate Broadcasting**^

- BPM shared with partner via private relay server — no rate limits, real-time updates^

- Room codes are now stable and persist between sessions^

- Viewer BPM display changes color with host tiers (LOW/MED/HIGH)^

^

**VRChat Integration**^

- Prettier chatbox output with progress bar and tier label^

- Heartbeat sound effect on overlay and viewer — toggleable in Settings^

- Screen shake on both broadcaster and viewer at high BPM^

- Heart pulse speed scales live with BPM^

- All pronouns supported: His, Her, Their, Our, Xe/Xem, Ze/Hir, Ey/Em, Fae/Faer and more^

- Partner HR OSC parameter for couples (both HRs show on avatar simultaneously)^

^

**Settings ^ Persistence**^

- Spotify OAuth token saved — no re-authorization needed after updates^

- All OSC settings, tokens, and customizations persist across updates^

- Live status panel shows Pulsoid, OSC, Chatbox, Sharing, and Spotify status^

^

**Bug Fixes**^

- Fixed room code changing on every BPM publish (sharing now works correctly)^

- Fixed tray menu exit leaving context menu on screen^

- Fixed heartbeat icon showing as ? in VRChat chatbox^

- Fixed update checker triggering when already on latest version^

^

### How to Use^

^

1. Enter your Pulsoid token in the Broadcaster tab^

2. Click **START OVERLAY** — your BPM overlay appears^

3. Share your **Room Code** with your partner^

4. Partner opens Viewer tab, enters code, clicks **CONNECT ^& WATCH**^

^

> Requires Windows 10/11. No Python or additional installs needed.

:: ── Create / update GitHub release ──────────────────────────────
echo  Creating GitHub release v%VERSION%...

:: Delete existing release/tag if present
gh release delete v%VERSION% --yes >nul 2>&1
git push origin :refs/tags/v%VERSION% >nul 2>&1

gh release create v%VERSION% ^
    "dist\HRMMonitor.exe#HRMMonitor.exe" ^
    --repo twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC ^
    --title "HRM Monitor v%VERSION%" ^
    --notes "%NOTES%" ^
    --target v2

if errorlevel 1 (
    echo  [!] Release creation failed. Check GitHub CLI auth: gh auth login
) else (
    echo.
    echo  ==========================================
    echo   Done! Released v%VERSION% on GitHub
    echo   https://github.com/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC/releases/tag/v%VERSION%
    echo  ==========================================
)
echo.
pause
