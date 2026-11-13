#!/bin/sh
# Render start command: migrate, first-run setup, background jobs, then the API.
set -e

alembic upgrade head
python -m app.bootstrap

# Celery worker with embedded beat: sends the Friday weekly Excel report and queued emails.
celery -A app.core.celery_app worker -B --loglevel=info --concurrency=1 \
  --schedule /tmp/celerybeat-schedule &

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
