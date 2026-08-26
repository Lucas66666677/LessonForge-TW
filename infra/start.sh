#!/bin/sh
set -e
python -m alembic -c services/api/alembic.ini upgrade head
python scripts/seed.py

# Render's free tier only grants one service (no separate Background Worker), so the
# generation-job worker runs alongside the API in this same container -- but only once
# IN_PROCESS_JOBS=false, since worker.py connects to Redis unconditionally on startup
# (no retry/backoff) and would otherwise crash the whole container the moment REDIS_URL
# isn't a real broker (e.g. still the localhost default). Until that env var is flipped
# (see FINAL_OPERATING_CHECKPOINT.md), this runs the API alone, exactly as before.
# Portable `sh` (not bash) since Render's Docker Command override may not invoke bash.
if [ "$IN_PROCESS_JOBS" = "false" ]; then
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
else
    exec uvicorn lessonforge.main:app --host 0.0.0.0 --port "${PORT:-8000}"
fi
