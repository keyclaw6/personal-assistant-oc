#!/usr/bin/env bash
# Start/stop/status the local Cognee API server for Companion.
# Usage: scripts/cognee-server.sh {start|stop|status|restart}

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="/home/kab/cognee-venv"
PIDFILE="/tmp/cognee-server.pid"
LOGFILE="/tmp/cognee-server.log"

start() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Cognee server already running (PID $(cat "$PIDFILE"))"
    return 0
  fi

  # Load env
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env.cognee"
  set +a

  mkdir -p "$SYSTEM_ROOT_DIRECTORY" "$DATA_ROOT_DIRECTORY"

  nohup "$VENV/bin/python3" -m uvicorn cognee.api.client:app \
    --host 127.0.0.1 --port 8000 --log-level info \
    > "$LOGFILE" 2>&1 &

  echo $! > "$PIDFILE"
  sleep 3

  if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Cognee server started (PID $(cat "$PIDFILE")), log: $LOGFILE"
  else
    echo "Cognee server failed to start. Check $LOGFILE"
    return 1
  fi
}

stop() {
  if [ -f "$PIDFILE" ]; then
    local pid
    pid=$(cat "$PIDFILE")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
      echo "Cognee server stopped (PID $pid)"
    else
      echo "Cognee server not running (stale PID file)"
    fi
    rm -f "$PIDFILE"
  else
    # Try to find and kill by process
    pkill -f "uvicorn cognee.api.client:app" 2>/dev/null || true
    echo "Cognee server stopped"
  fi
}

status() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Cognee server running (PID $(cat "$PIDFILE"))"
    curl -s http://127.0.0.1:8000/health 2>/dev/null || echo "(health check failed)"
  else
    echo "Cognee server not running"
  fi
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 1; start ;;
  status)  status ;;
  *)       echo "Usage: $0 {start|stop|status|restart}"; exit 1 ;;
esac
