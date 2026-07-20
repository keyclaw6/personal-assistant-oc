#!/usr/bin/env bash
# Manage the loopback-only Cognee API service.
# Usage: scripts/cognee-server.sh {install|run|start|stop|restart|status|health}

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${COGNEE_VENV:-/home/kab/cognee-venv}"
PYTHON="$VENV/bin/python3"
ENV_FILE="${COGNEE_ENV_FILE:-$REPO_ROOT/.env.cognee}"
KEY_FILE="${DOTENVX_KEY_FILE:-$HOME/.config/dotenvx/.env.keys}"
HOST="${COGNEE_HOST:-127.0.0.1}"
PORT="${COGNEE_PORT:-8001}"
UNIT_NAME="cognee-server.service"
UNIT_SOURCE="$REPO_ROOT/systemd/user/$UNIT_NAME"
UNIT_DEST="$HOME/.config/systemd/user/$UNIT_NAME"
LEGACY_PIDFILE="${COGNEE_LEGACY_PIDFILE:-/tmp/cognee-server.pid}"
LEGACY_LOGFILE="${COGNEE_LEGACY_LOGFILE:-/tmp/cognee-server.log}"

die() {
  echo "Cognee server: $*" >&2
  exit 1
}

validate_address() {
  case "$HOST" in
    127.0.0.1|::1) ;;
    *) die "host must be a loopback address (127.0.0.1 or ::1)" ;;
  esac
  case "$PORT" in
    ''|*[!0-9]*) die "port must be an integer from 1024 through 65535" ;;
  esac
  [ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] || \
    die "port must be an integer from 1024 through 65535"
}

validate_runtime() {
  validate_address
  command -v dotenvx >/dev/null 2>&1 || die "dotenvx is required"
  [ -x "$PYTHON" ] || die "Cognee Python is missing at $PYTHON"
  [ -r "$ENV_FILE" ] || die "encrypted environment file is missing"
  [ -r "$KEY_FILE" ] || die "dotenvx key file is missing"

  local system_root data_root
  system_root=$(dotenvx get SYSTEM_ROOT_DIRECTORY --strict --no-armor --no-native \
    -f "$ENV_FILE" -fk "$KEY_FILE") || die "cannot read SYSTEM_ROOT_DIRECTORY"
  data_root=$(dotenvx get DATA_ROOT_DIRECTORY --strict --no-armor --no-native \
    -f "$ENV_FILE" -fk "$KEY_FILE") || die "cannot read DATA_ROOT_DIRECTORY"
  [ -n "$system_root" ] || die "SYSTEM_ROOT_DIRECTORY is empty"
  [ -n "$data_root" ] || die "DATA_ROOT_DIRECTORY is empty"
  mkdir -p -- "$system_root" "$data_root"
}

port_is_open() {
  "$PYTHON" - "$HOST" "$PORT" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
family = socket.AF_INET6 if ":" in host else socket.AF_INET
with socket.socket(family, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.5)
    raise SystemExit(0 if sock.connect_ex((host, port)) == 0 else 1)
PY
}

health() {
  validate_address
  [ -x "$PYTHON" ] || die "Cognee Python is missing at $PYTHON"
  "$PYTHON" - "$HOST" "$PORT" <<'PY'
import importlib.metadata
import json
import sys
import urllib.error
import urllib.request

host, port = sys.argv[1], int(sys.argv[2])
address = f"[{host}]" if ":" in host else host
base = f"http://{address}:{port}"

def read_json(path):
    request = urllib.request.Request(path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        content_type = response.headers.get_content_type()
        if content_type != "application/json":
            raise RuntimeError("response is not JSON")
        return json.loads(response.read(64 * 1024))

try:
    root = read_json(base + "/")
    result = read_json(base + "/health")
    installed_version = importlib.metadata.version("cognee")
    valid = (
        root == {"message": "Hello, World, I am alive!"}
        and result.get("status") == "ready"
        and result.get("health") == "healthy"
        and result.get("version") == installed_version
    )
    if not valid:
        raise RuntimeError("endpoint is not the ready installed Cognee service")
except (OSError, ValueError, KeyError, TypeError, RuntimeError, urllib.error.URLError) as exc:
    print(f"Cognee health check failed: {exc}", file=sys.stderr)
    raise SystemExit(1)

print(f"Cognee {installed_version} is ready at {base}")
PY
}

run() {
  validate_runtime
  if port_is_open; then
    die "$HOST:$PORT is already occupied; refusing to start over another service"
  fi
  cd "$REPO_ROOT"
  exec dotenvx run --strict --no-armor --no-native -f "$ENV_FILE" -fk "$KEY_FILE" -- \
    "$PYTHON" "$REPO_ROOT/scripts/cognee-log-redactor.py" -- \
      "$PYTHON" -m uvicorn cognee.api.client:app \
        --host "$HOST" --port "$PORT" --workers 1 --log-level info --no-use-colors
}

unit_is_installed() {
  [ -f "$UNIT_DEST" ] && systemctl --user cat "$UNIT_NAME" >/dev/null 2>&1
}

wait_for_health() {
  local attempt
  for attempt in $(seq 1 60); do
    if health >/dev/null 2>&1; then
      health
      return 0
    fi
    if systemctl --user is-failed --quiet "$UNIT_NAME" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  systemctl --user status "$UNIT_NAME" --no-pager --lines=8 >&2 || true
  die "service did not become ready"
}

install_service() {
  validate_runtime
  [ -r "$UNIT_SOURCE" ] || die "tracked systemd unit is missing"
  stop_legacy
  rm -f -- "$LEGACY_LOGFILE"
  mkdir -p -- "$(dirname "$UNIT_DEST")"
  install -m 0644 "$UNIT_SOURCE" "$UNIT_DEST"
  systemctl --user daemon-reload
  systemctl --user enable "$UNIT_NAME"
  systemctl --user restart "$UNIT_NAME"
  wait_for_health
}

start() {
  unit_is_installed || die "systemd unit is not installed; run '$0 install' first"
  systemctl --user start "$UNIT_NAME"
  wait_for_health
}

legacy_pid() {
  local pid cmdline
  [ -f "$LEGACY_PIDFILE" ] || return 1
  pid=$(tr -d '[:space:]' < "$LEGACY_PIDFILE")
  case "$pid" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ -r "/proc/$pid/cmdline" ] || return 1
  cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline")
  case "$cmdline" in
    *"uvicorn cognee.api.client:app"*"--port $PORT"*) printf '%s\n' "$pid" ;;
    *) return 1 ;;
  esac
}

stop_legacy() {
  local pid
  if pid=$(legacy_pid); then
    kill -TERM "$pid"
    local attempt
    for attempt in $(seq 1 30); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "$pid" 2>/dev/null && [ "$(legacy_pid 2>/dev/null || true)" = "$pid" ]; then
      kill -KILL "$pid"
    fi
  fi
  rm -f -- "$LEGACY_PIDFILE"
}

stop() {
  if unit_is_installed; then
    systemctl --user stop "$UNIT_NAME"
  fi
  stop_legacy
  if port_is_open; then
    die "$HOST:$PORT remains occupied by a process not owned by this service"
  fi
  echo "Cognee server stopped"
}

restart() {
  unit_is_installed || die "systemd unit is not installed; run '$0 install' first"
  stop_legacy
  systemctl --user restart "$UNIT_NAME"
  wait_for_health
}

status() {
  validate_address
  if ! unit_is_installed; then
    echo "Cognee server unit is not installed"
    return 1
  fi
  local enabled active
  enabled=$(systemctl --user is-enabled "$UNIT_NAME" 2>/dev/null || true)
  active=$(systemctl --user is-active "$UNIT_NAME" 2>/dev/null || true)
  echo "Cognee systemd unit: $enabled, $active"
  [ "$enabled" = "enabled" ] && [ "$active" = "active" ] || return 1
  health
}

case "${1:-}" in
  install) install_service ;;
  run) run ;;
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  status) status ;;
  health) health ;;
  *) echo "Usage: $0 {install|run|start|stop|restart|status|health}" >&2; exit 2 ;;
esac
