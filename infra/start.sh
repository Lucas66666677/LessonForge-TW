#!/bin/sh
set -e
python -m alembic -c services/api/alembic.ini upgrade head
python scripts/seed.py

# Render's free tier only grants one service (no separate Background Worker), so the
# generation-job worker runs alongside the API in this same container. This only takes
# effect once IN_PROCESS_JOBS=false and a working REDIS_URL are set -- until then,
# worker.py idles on a Redis connection that isn't configured and the API behaves exactly
# as before (in-process jobs). Portable `sh` (not bash) since Render's Docker Command
# override may not invoke this via bash.
python -m lessonforge.worker &
WORKER_PID=$!

uvicorn lessonforge.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
API_PID=$!

while kill -0 "$WORKER_PID" 2>/dev/null && kill -0 "$API_PID" 2>/dev/null; do
    sleep 5
done

kill "$WORKER_PID" "$API_PID" 2>/dev/null
wait
exit 1
