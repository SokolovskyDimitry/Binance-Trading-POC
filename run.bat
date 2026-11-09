@echo off
title Binance Market Dashboard
echo ===================================================
echo Starting Binance Market Dashboard...
echo ===================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://www.python.org/
    pause
    exit /b 1
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing / verifying dependencies...
pip install -r requirements.txt --quiet

echo Launching Dashboard on http://localhost:5001
start "" http://localhost:5001
python app.py 5001

pause
