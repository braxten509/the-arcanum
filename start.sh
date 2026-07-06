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

is_this_server() {
  local pid cwd command

  for pid in $(listener_pids); do
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    command="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"

    if [[ "$cwd" == "$ROOT" && "$command" == *"python3 server.py $PORT"* ]] &&
       curl --silent --fail --max-time 2 "$URL/" >/dev/null 2>&1; then
      return 0
    fi
  done

  return 1
}

if is_this_server; then
  echo "The candle already burns → $URL"
else
  pids="$(listener_pids)"
  if [[ -n "$pids" ]]; then
    echo "Clearing port $PORT (PID${pids// /,})..."
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
fi

if [[ "${ARCANUM_NO_OPEN:-0}" != "1" ]]; then
  xdg-open "$URL" >/dev/null 2>&1 || true
fi
