#!/usr/bin/env bash
# Scan all 155 historical domains with HTTP probes and WHOIS lookups.
# Takes ~2.5 minutes. Results saved to domain_results.json.

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

WORKERS=${1:-10}

echo "Scanning domains with $WORKERS workers..."
echo ""
python3 checker.py --workers "$WORKERS"
echo ""
echo "Results written to: $DIR/domain_results.json"
echo "Run ./start.sh to view in browser."
