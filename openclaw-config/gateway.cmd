@echo off
rem OpenClaw Gateway (v2026.4.25)
rem NOTE: Update paths for your new machine
set "TMPDIR=<UPDATE_TEMP_DIR>"
set "OPENCLAW_GATEWAY_PORT=18789"
set "OPENCLAW_SYSTEMD_UNIT=openclaw-gateway.service"
set "OPENCLAW_WINDOWS_TASK_NAME=OpenClaw Gateway"
set "OPENCLAW_SERVICE_MARKER=openclaw"
set "OPENCLAW_SERVICE_KIND=gateway"
set "OPENCLAW_SERVICE_VERSION=2026.4.25"
set "OPENCLAW_GATEWAY_STARTUP_TRACE=1"
set "OPENCLAW_SKIP_CHANNELS=1"
"<NODE_PATH>" "<OPENCLAW_INSTALL_PATH>\dist\index.js" gateway --port 18789
