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
cd "$ROOT"
"$PYTHON" manage.py migrate --verbosity 0
"$PYTHON" manage.py shell --verbosity 0 < "$HERE/seed.py"
"$PYTHON" manage.py runserver "$PORT" --noreload > "$WORK/server.log" 2>&1 &
SERVER=$!
for _ in $(seq 30); do curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 0.5; done

BASE_URL="http://127.0.0.1:$PORT" OUT_DIR="$ROOT/manual/images" \
  NODE_PATH="${NODE_PATH:-$(npm root -g)}" node "$HERE/shots.js"
