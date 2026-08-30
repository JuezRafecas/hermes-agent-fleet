#!/usr/bin/env bash
# Destructive local end-to-end smoke for a disposable root. This builds and
# runs Docker; do not use it where Docker execution is out of scope.
set -euo pipefail

PORT="${SMOKE_PORT:-9131}"
CONTAINER="${SMOKE_CONTAINER:-hermes-fleet-smoke}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${SMOKE_ROOT:-$(mktemp -d "${TMPDIR:-/tmp}/hermes-fleet-smoke.XXXXXX")}"
JAR="$ROOT/.dash-cookies"
FAILED=0

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
pass() { printf '\033[32mPASS\033[0m %s\n' "$*"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$*"; FAILED=1; }
ctl()  { HERMES_ROOT="$ROOT" HERMES_CONTAINER="$CONTAINER" HERMES_PORT="$PORT" \
         HERMES_UID="$(id -u)" HERMES_GID="$(id -g)" "$ROOT/agentctl" "$@"; }
hx()   { docker exec "$CONTAINER" /opt/hermes/bin/hermes "$@"; }

cleanup() {
  say "teardown"
  ( cd "$ROOT" && HERMES_CONTAINER="$CONTAINER" HERMES_PORT="$PORT" docker compose down -v ) >/dev/null 2>&1 || true
  [ -n "${SMOKE_ROOT:-}" ] || rm -rf "$ROOT"
}
trap cleanup EXIT

say "1/9 prepare $ROOT"
mkdir -p "$ROOT/data"
cp "$SRC/Dockerfile" "$SRC/docker-compose.yml" "$SRC/agentctl" "$ROOT/"
cp -R "$SRC/s6" "$SRC/config" "$SRC/agents" "$SRC/scripts" "$ROOT/"
chmod +x "$ROOT/agentctl"
PASSWORD="smoke-$(date +%s)"
umask 077
{
  printf 'HERMES_DASHBOARD_BASIC_AUTH_USERNAME=admin\n'
  printf 'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=%s\n' "$PASSWORD"
  printf 'HERMES_DASHBOARD_BASIC_AUTH_SECRET=smoke-session-signing-key\n'
} > "$ROOT/data/.env"
cp "$SRC/config/config.yaml" "$ROOT/data/config.yaml"
cp "$SRC/config/SOUL.default.md" "$ROOT/data/SOUL.md"

say "2/9 build image"
( cd "$ROOT" && HERMES_CONTAINER="$CONTAINER" HERMES_PORT="$PORT" \
  HERMES_UID="$(id -u)" HERMES_GID="$(id -g)" docker compose build ) \
  && pass "image built" || { fail "image build failed"; exit 1; }

say "3/9 start and wait for health"
ctl up >/dev/null
for _ in $(seq 1 90); do
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 \
  && pass "/api/health responded" || { fail "gateway never became healthy"; exit 1; }

say "4/9 dashboard login"
curl -fsS -c "$JAR" -X POST "http://127.0.0.1:$PORT/auth/password-login" \
  -H 'Content-Type: application/json' \
  -d "{\"provider\":\"basic\",\"username\":\"admin\",\"password\":\"$PASSWORD\"}" >/dev/null \
  && pass "password login succeeded" || fail "password login failed"

say "5/9 add research profile from seed"
ctl add demo-research --seed "$ROOT/agents/research-analyst" \
  && pass "profile add completed" || fail "profile add failed"

say "6/9 gateway serves the new profile"
curl -fsS -b "$JAR" "http://127.0.0.1:$PORT/api/profiles" | grep -q 'demo-research' \
  && pass "/api/profiles contains demo-research" || fail "profile is not served"

say "7/9 seed contains identity, empty env names, and MCP"
grep -q 'Research Analyst' "$ROOT/data/profiles/demo-research/SOUL.md" \
  && pass "seed SOUL installed" || fail "seed SOUL missing"
grep -q '^FIRECRAWL_API_KEY=$' "$ROOT/data/profiles/demo-research/.env" \
  && pass "empty secret name installed" || fail "profile env is incorrect"
grep -q 'FIRECRAWL_MCP_URL' "$ROOT/data/profiles/demo-research/config.yaml" \
  && pass "Firecrawl MCP installed" || fail "MCP configuration missing"

say "8/9 profile routine"
hx -p demo-research cron create "0 9 * * 1" "weekly research review" --name smoke-weekly >/dev/null 2>&1 || true
if grep -q 'smoke-weekly' "$ROOT/data/profiles/demo-research/cron/jobs.json" 2>/dev/null \
   || hx -p demo-research cron list 2>&1 | grep -q 'smoke-weekly'; then
  pass "profile routine created"
else
  fail "profile routine unavailable"
fi

say "9/9 display pool and tools"
[ "$(docker exec "$CONTAINER" pgrep -xc Xvfb)" = 10 ] \
  && pass "ten Xvfb processes are running" || fail "Xvfb pool is incomplete"
for display in :100 :101; do
  docker exec "$CONTAINER" xdpyinfo -display "$display" >/dev/null 2>&1 \
    && pass "display $display responds" || fail "display $display is unavailable"
done
for binary in mongosh psql gh jq rg xdotool agent-browser shared-file-upload; do
  docker exec "$CONTAINER" sh -c "command -v $binary" >/dev/null 2>&1 \
    && pass "$binary is present" || fail "$binary is missing"
done

say "result"
[ "$FAILED" = 0 ] && { echo "ALL GREEN"; exit 0; }
echo "SMOKE FAILED"
exit 1
