#!/usr/bin/env bash
# ARCANUM launcher
set -u

cd "$(dirname "$0")"
PORT="${1:-8777}"
ROOT="$PWD"
URL="http://localhost:$PORT"

listener_pids() {
  fuser -n tcp "$PORT" 2>/dev/null | xargs || true
}

# A desktop relaunch must never sever a live author session. When the existing server reports
# an active build, keep it intact; ordinary idle relaunches still restart to pick up new code.
pids="$(listener_pids)"
if [[ -n "$pids" ]]; then
  active_jobs="$(curl --silent --fail --max-time 2 "$URL/api/buildtome/active" 2>/dev/null |
    python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("jobs", [])))' 2>/dev/null || true)"
  if [[ "$active_jobs" =~ ^[1-9][0-9]*$ ]]; then
    echo "ARCANUM is already lit with $active_jobs active author session(s) → $URL"
    exit 0
  fi

  echo "Restarting ARCANUM — clearing port $PORT (PID${pids// /,})..."
  kill -TERM $pids 2>/dev/null || true

  for _ in {1..30}; do
    [[ -z "$(listener_pids)" ]] && break
    sleep 0.1
  done

  pids="$(listener_pids)"
  if [[ -n "$pids" ]]; then
    kill -KILL $pids 2>/dev/null || true
  fi
fi

mkdir -p .cache
setsid python3 server.py "$PORT" >>.cache/server.log 2>&1 </dev/null &
server_pid=$!

for _ in {1..50}; do
  if curl --silent --fail --max-time 1 "$URL/" >/dev/null 2>&1; then
    echo "The candle is lit → $URL"
    break
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "ARCANUM failed to start. See $ROOT/.cache/server.log" >&2
    exit 1
  fi
  sleep 0.1
done

if ! curl --silent --fail --max-time 2 "$URL/" >/dev/null 2>&1; then
  echo "ARCANUM did not become ready. See $ROOT/.cache/server.log" >&2
  exit 1
fi

# The server opens the browser itself (server.py, cross-platform, honors ARCANUM_NO_OPEN) —
# don't open it here too or you get a duplicate/blank tab.
