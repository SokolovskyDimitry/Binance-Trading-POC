#!/usr/bin/env bash
set -e

echo "==================================================="
echo "Starting Binance Market Dashboard..."
echo "==================================================="

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in PATH."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing / verifying dependencies..."
pip install -r requirements.txt --quiet

echo "Launching Dashboard on http://localhost:5001"
# Attempt to open browser if open/xdg-open exists
if command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:5001" &
elif command -v open &> /dev/null; then
    open "http://localhost:5001" &
fi

python3 app.py 5001
