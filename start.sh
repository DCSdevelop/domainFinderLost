#!/usr/bin/env bash
# Start the Domain Finder web viewer on port 8090.

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PORT=${1:-8090}

# Check if already running
if lsof -ti:"$PORT" > /dev/null 2>&1; then
    echo "Port $PORT is already in use."
    echo "Run ./stop.sh first, or use a different port: ./start.sh 9000"
    exit 1
fi

# Check if results exist
if [ ! -f domain_results.json ]; then
    echo "No domain_results.json found. Run ./scan.sh first."
    exit 1
fi

echo "Starting Domain Finder web viewer on port $PORT..."
python3 -m http.server "$PORT" --directory "$DIR" > /dev/null 2>&1 &
PID=$!
echo "$PID" > .server.pid

sleep 1

if kill -0 "$PID" 2>/dev/null; then
    echo "Server running at: http://localhost:$PORT"
    echo "PID: $PID (saved to .server.pid)"
    echo ""
    echo "Run ./stop.sh to stop the server."
    open "http://localhost:$PORT"
else
    echo "Failed to start server."
    exit 1
fi
