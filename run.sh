#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
    uv pip install -r requirements.txt
fi

echo "Starting Costco Gas Price Tracker Streamlit App..."
.venv/bin/streamlit run app.py
