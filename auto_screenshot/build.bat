@echo off
setlocal

cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt -r requirements-build.txt

python assets.py
pyinstaller --noconfirm auto_screenshot.spec

echo.
echo Build complete: dist\AutoScreenshot.exe
echo.
pause
