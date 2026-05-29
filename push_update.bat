@echo off
title HRM Monitor v2 - Push to GitHub
color 0C
echo.
echo  ==========================================
echo   HRM Monitor v2 - Push to GitHub
echo  ==========================================
echo.

:: Make sure we're in the right folder
cd /d "%~dp0"

:: Init git if not already
if not exist ".git" (
    echo  Initializing git repo...
    git init
    git remote add origin https://github.com/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC.git
    echo  [OK] Git initialized
) else (
    echo  [OK] Git already initialized
)
echo.

:: Stage everything (respects .gitignore)
echo  Staging files...
git add -A
echo.

:: Ask for commit message
set /p MSG="Enter commit message (or press Enter for default): "
if "%MSG%"=="" set MSG=HRM Monitor v2 update

:: Commit
git commit -m "%MSG%"
echo.

:: Push to v2 branch
echo  Pushing to GitHub (branch: v2)...
git push -u origin HEAD:v2
if errorlevel 1 (
    echo.
    echo  [!] Push failed. If this is the first push, trying with --force...
    git push -u origin HEAD:v2 --force
)

echo.
echo  ==========================================
echo   Done! Check: github.com/twilightknight869/Multi-Purpose-HRM-Monitor-For-VRC/tree/v2
echo  ==========================================
echo.
pause
