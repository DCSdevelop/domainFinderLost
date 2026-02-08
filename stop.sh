#!/usr/bin/env bash
# Stop the Domain Finder web viewer.

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PORT=${1:-8090}

# Try PID file first
if [ -f .server.pid ]; then
    PID=$(cat .server.pid)
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "Stopped server (PID $PID)."
    else
        echo "PID $PID not running."
    fi
    rm -f .server.pid
# Fallback: kill by port
elif lsof -ti:"$PORT" > /dev/null 2>&1; then
    kill $(lsof -ti:"$PORT")
    echo "Stopped server on port $PORT."
else
    echo "No server running on port $PORT."
fi
