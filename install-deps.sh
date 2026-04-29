#!/bin/bash
# Installation script for moceansms_auth.py dependencies on macOS

PYTHON3="/Library/Developer/CommandLineTools/usr/bin/python3"

echo "[*] Installing curl-cffi..."
$PYTHON3 -m pip install --upgrade curl-cffi

echo "[*] Installing anticaptchaofficial..."
$PYTHON3 -m pip install --upgrade anticaptchaofficial

echo "[*] Installing python-dotenv (optional, but recommended)..."
$PYTHON3 -m pip install --upgrade python-dotenv

echo "[✓] All dependencies installed successfully!"
echo ""
echo "You can now run the script with:"
echo "  $PYTHON3 moceansms_auth.py --username USERNAME --password PASSWORD"
