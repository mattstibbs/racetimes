#!/usr/bin/env bash
# Regenerates the user manual's screenshots (manual/images/).
#
# Needs Node.js with Playwright and its Chromium, which are only for this
# script (not a Python dependency of the app):
#   npm install -g playwright && npx playwright install chromium
#
# It builds its own throwaway SQLite database of sample data (seed.py), so it
# never touches a real one, runs the app on a spare port, photographs it
# (shots.js), and cleans up.
set -o errexit -o nounset

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/scripts/manual_screenshots"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
PORT="${PORT:-8799}"
WORK="$(mktemp -d)"
trap 'kill "${SERVER:-}" 2>/dev/null || true; rm -rf "$WORK"' EXIT

export DATABASE_URL="sqlite:///$WORK/manual.sqlite3"
export DJANGO_DEBUG=1
# 127.0.0.1 names no club, so the pages are Demo Club's (slice 11).
export SINGLE_CLUB=demo
# Where seed.py leaves the link of the invitation shots.js photographs.
export INVITATION_FILE="$WORK/invitation-link"
cd "$ROOT"
"$PYTHON" manage.py migrate --verbosity 0
"$PYTHON" manage.py createcachetable
"$PYTHON" manage.py shell --verbosity 0 < "$HERE/seed.py"
"$PYTHON" manage.py runserver "$PORT" --noreload > "$WORK/server.log" 2>&1 &
SERVER=$!
# Slice 27: a second copy of the app with no SINGLE_CLUB, for the service's own
# address (localhost) and its club addresses (demo.localhost, which Chromium
# finds on this machine by itself), on the same throwaway database.
SERVICE_PORT=$((PORT + 1))
SINGLE_CLUB="" "$PYTHON" manage.py runserver "$SERVICE_PORT" --noreload > "$WORK/service.log" 2>&1 &
SERVICE_SERVER=$!
trap 'kill "${SERVER:-}" "${SERVICE_SERVER:-}" 2>/dev/null || true; rm -rf "$WORK"' EXIT
for _ in $(seq 30); do curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 0.5; done
for _ in $(seq 30); do curl -s -o /dev/null "http://localhost:$SERVICE_PORT/" && break; sleep 0.5; done

BASE_URL="http://127.0.0.1:$PORT" SERVICE_URL="http://localhost:$SERVICE_PORT" \
  OUT_DIR="$ROOT/manual/images" \
  NODE_PATH="${NODE_PATH:-$(npm root -g)}" node "$HERE/shots.js"
