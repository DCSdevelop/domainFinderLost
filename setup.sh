#!/usr/bin/env bash
# Setup script — install Python dependencies (run once)

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "Installing Python dependencies..."
pip3 install -r requirements.txt

echo ""
echo "Setup complete. Run ./scan.sh to scan domains."
