#!/usr/bin/env bash
# Persistent SSH tunnel from macOS to the Hermes dashboard on a VPS.
# The dashboard stays on VPS loopback; this tunnel exposes it on Mac loopback.
set -euo pipefail

HOST="${1:-hermes-vps}"        # alias from ~/.ssh/config
LOCAL_PORT="${LOCAL_PORT:-19119}"
REMOTE_PORT="${REMOTE_PORT:-9119}"
LABEL="com.hermes-agent-fleet.tunnel"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SSH="$(command -v ssh)"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$SSH</string>
    <string>-N</string>
    <string>-o</string><string>ExitOnForwardFailure=yes</string>
    <string>-o</string><string>ServerAliveInterval=30</string>
    <string>-o</string><string>ServerAliveCountMax=3</string>
    <string>-L</string><string>${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}</string>
    <string>$HOST</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ExitTimeOut</key><integer>5</integer>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/$LABEL.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/$LABEL.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
launchctl kickstart -k "gui/$UID/$LABEL"

echo "tunnel active: http://127.0.0.1:${LOCAL_PORT} -> ${HOST}:127.0.0.1:${REMOTE_PORT}"
echo
echo "In Hermes Desktop: Connections -> Add connection"
echo "  URL:      http://127.0.0.1:${LOCAL_PORT}"
echo "  Username: HERMES_DASHBOARD_BASIC_AUTH_USERNAME (default: 'admin')"
echo "  Password: HERMES_DASHBOARD_BASIC_AUTH_PASSWORD from /srv/hermes/data/.env"
echo
echo "Stop:   launchctl bootout gui/$UID/$LABEL"
echo "Logs:   tail -f $HOME/Library/Logs/$LABEL.log"
