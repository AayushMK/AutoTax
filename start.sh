#!/usr/bin/env bash
# Migrate, start the API on localhost, then the web server on $PORT. If either exits, the dyno restarts.
set -euo pipefail
cd /app/backend
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8010 --proxy-headers &
cd /app/web
PORT="${PORT:-3000}" HOSTNAME=0.0.0.0 node server.js &
wait -n
exit 1
