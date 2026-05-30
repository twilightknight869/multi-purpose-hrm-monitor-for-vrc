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
for /f "tokens=3 delims=><" %%v in ('findstr /i "<Version>" HRMMonitor.csproj') do set VERSION=%%v
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
set NOTES=## HRM Monitor v%VERSION% - Major Release^

^

### What's New^

^

**VR Wrist Overlay - Apple Watch Style**^

- Anchors to your hand controller and moves with your real wrist in VR^

- Raise your wrist to view an expanded info panel (room code, group HRs, status)^

- Switch between left and right hand in settings - changes instantly^

- Adjustable watch size from 4cm to 16cm^

^

**Group Watch - Horror Game Mode**^

- Watch up to 5 friends heart rates at once^

- All friend HRs show in your VR wrist panel colour-coded by tier^

- Perfect for horror games - see who is scared in real time^

^

**VRChat Chatbox**^

- Unicode symbols now work correctly (fixed ASCII encoding bug)^

- Prettier output with progress bar and tier indicators^

- Invisible background mode - text floats with no grey bubble (Premium)^

- All pronouns: His, Her, Their, Our, Xe, Ze, Ey, Fae and more^

^

**UI and Quality of Life**^

- New Help tab with full setup guide and feature explanations^

- Safety and transparency section with source code and VirusTotal links^

- UI Customization for Premium users - accent colors and dark themes^

- Spotify and SteamVR sections collapsed by default to reduce clutter^

- Heartbeat sound effects synced to BPM - toggleable^

- Viewer overlay now colour-coded and shakes at high BPM^

^

**Reliability**^

- Fixed room code bug that broke friend sharing^

- Spotify token saved - no re-auth needed after updates^

- Fixed tray menu and exit behaviour^

- Open source - build from source with build.bat^

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

gh release create v%VERSION% "dist\HRMMonitor.exe#HRMMonitor.exe" --repo twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC --title "HRM Monitor v%VERSION%" --notes "%NOTES%" --target v2

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
