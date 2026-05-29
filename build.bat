@echo off
title HRM Monitor v2 - Build
color 0C
echo.
echo  ==========================================
echo   HRM Monitor v2 - Build Script
echo  ==========================================
echo.

:: Kill any running instance so the exe isn't locked during publish
taskkill /f /im HRMMonitor.exe >nul 2>&1
if not errorlevel 1 echo  [OK] Closed running HRMMonitor.exe

:: Check for .NET 8 SDK
dotnet --version >nul 2>&1
if errorlevel 1 (
    echo  [!] .NET SDK not found.
    echo.
    echo  Installing .NET 8 SDK...
    powershell -Command "Invoke-WebRequest -Uri 'https://dot.net/v1/dotnet-install.ps1' -OutFile '%TEMP%\dotnet-install.ps1'"
    powershell -ExecutionPolicy Bypass -File "%TEMP%\dotnet-install.ps1" -Channel 8.0 -InstallDir "%LOCALAPPDATA%\Microsoft\dotnet"
    set "PATH=%LOCALAPPDATA%\Microsoft\dotnet;%PATH%"
    dotnet --version >nul 2>&1
    if errorlevel 1 (
        echo  [FAIL] Could not install .NET SDK automatically.
        echo  Please download it from: https://dotnet.microsoft.com/download
        pause
        exit /b 1
    )
    echo  [OK] .NET SDK installed.
)

for /f "tokens=*" %%v in ('dotnet --version 2^>^&1') do set DOTNETVER=%%v
echo  [OK] .NET %DOTNETVER% found
echo.

:: Download openvr_api.cs if not present (Valve's official C# binding)
if not exist "openvr_api.cs" (
    echo  Downloading openvr_api.cs from ValveSoftware/openvr...
    powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/ValveSoftware/openvr/master/headers/openvr_api.cs' -OutFile 'openvr_api.cs'"
    if exist "openvr_api.cs" (
        echo  [OK] openvr_api.cs downloaded
    ) else (
        echo  [WARN] Could not download openvr_api.cs - SteamVR overlay will be skipped
    )
) else (
    echo  [OK] openvr_api.cs found
)
echo.

echo  Restoring packages...
dotnet restore
echo.

echo  Building release...
dotnet publish -c Release -r win-x64 --self-contained true ^
    -p:PublishSingleFile=true ^
    -p:IncludeNativeLibrariesForSelfExtract=true ^
    -p:EnableCompressionInSingleFile=true ^
    -o dist

if errorlevel 1 (
    echo.
    echo  [FAIL] Build failed. Check output above.
    pause
    exit /b 1
)

echo.
echo  ==========================================
echo   Build complete!
echo   Output: dist\HRMMonitor.exe
echo  ==========================================
echo.
pause
