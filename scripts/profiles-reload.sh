#!/usr/bin/env bash
# Invoked by hermes-profiles.path. Restart only when the direct profile
# directory set changes; session, memory, and cron writes must not restart it.
set -euo pipefail
ROOT="${HERMES_ROOT:-/srv/hermes}"
SNAP="$ROOT/.profiles-snapshot"
cur=$(find "$ROOT/data/profiles" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort)
old=$(cat "$SNAP" 2>/dev/null || true)
[ "$cur" = "$old" ] && exit 0
sleep 10   # allow the profile creator to finish its writes
cur=$(find "$ROOT/data/profiles" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort)
printf '%s\n' "$cur" > "$SNAP"
logger -t hermes-profiles "profiles changed -> gateway restart: $(echo "$cur" | tr '\n' ' ')"
exec /usr/bin/docker exec hermes /opt/hermes/bin/hermes gateway restart
