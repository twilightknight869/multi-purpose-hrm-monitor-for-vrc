@echo off
title HRM Monitor - Install Dependencies
color 0C

echo.
echo  ==========================================
echo   HRM Monitor - Dependency Installer
echo   Made by CRIMSON  ^|  Discord: crimsondreamz
echo  ==========================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Python not found!
    echo.
    echo  Please install Python 3.10 or newer from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: Check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Found %PYVER%
echo.

:: Upgrade pip silently
echo  Upgrading pip...
python -m pip install --upgrade pip --quiet

echo.
echo  ==========================================
echo   Installing core dependencies...
echo  ==========================================
echo.

echo  Installing PyQt6 (UI framework)...
pip install "PyQt6>=6.6.0"
echo.

echo  Installing websocket-client (Pulsoid connection)...
pip install "websocket-client>=1.7.0"
echo.

echo.
echo  ==========================================
echo   Installing optional dependencies...
echo  ==========================================
echo.

echo  Installing python-osc (VRChat OSC / chatbox)...
pip install "python-osc>=1.8.0"
echo.

echo  Installing spotipy (Spotify Now Playing)...
pip install "spotipy>=2.23.0"
echo.

echo  Installing openvr (SteamVR wrist overlay)...
pip install "openvr>=1.26.701"
echo.

echo.
echo  ==========================================
echo   All done!
echo  ==========================================
echo.
echo  Run the app with:
echo    python main.py
echo.
echo  Friend HR Sharing uses Ably Realtime (no install needed).
echo  Get a free API key at https://ably.com and paste it
echo  in Settings once the app is running.
echo.
pause
