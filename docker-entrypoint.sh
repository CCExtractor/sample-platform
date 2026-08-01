#!/bin/sh
set -e

# /app is a git repo created at build time; run.py reads a build commit from
# it. safe.directory guards against ownership mismatches under a bind mount.
git config --global --add safe.directory /app 2>/dev/null || true

python install/wait_for_db.py

# Creates the schema on an empty database, applies pending migrations on an
# existing one. See install/init_schema.py for why it is not just an upgrade.
python install/init_schema.py

exec gunicorn \
    --workers "${GUNICORN_WORKERS:-3}" \
    --bind 0.0.0.0:5000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    ${GUNICORN_RELOAD:+--reload} \
    run:app
