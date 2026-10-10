@echo off
REM counterX POS - full Windows build. Run on Windows 10/11 64-bit with Python 3.10+.
REM Produces: build\counterX POS\  (app folder) and dist\counterX-POS-Setup-1.1.0.exe

setlocal
cd /d %~dp0\..

echo [1/4] Creating virtual environment...
py -3 -m venv .venv-win
call .venv-win\Scripts\activate.bat

echo [2/4] Installing dependencies...
pip install -r requirements.txt pyinstaller

echo [3/4] Building executable with PyInstaller...
pyinstaller installer\counterx.spec --noconfirm

echo [4/4] Building installer with Inno Setup...
where iscc >nul 2>nul
if errorlevel 1 (
    echo ERROR: Inno Setup (iscc) not found. Install it from https://jrsoftware.org/isinfo.php
    echo        then re-run this script. The app folder is ready at build\counterX POS\
    exit /b 1
)
iscc installer\counterx.iss

echo.
echo DONE. Installer: dist\counterX-POS-Setup-1.1.0.exe
endlocal
