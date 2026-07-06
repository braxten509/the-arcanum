#!/usr/bin/env bash
# The Arcanum launcher (macOS) — double-click in Finder to play.
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1 && \
   python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "  Lighting the candle... (close this window or press Ctrl+C to stop)"
  python3 server.py
else
  echo
  echo "  Python 3.11 or newer was not found."
  echo "  Install it with:   brew install python"
  echo "  or download from   https://www.python.org/downloads/"
  echo
  open "https://www.python.org/downloads/" 2>/dev/null
  read -n 1 -s -r -p "  Press any key to close..."
fi
