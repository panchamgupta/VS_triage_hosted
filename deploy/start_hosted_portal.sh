#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${APP_DIR}"

# These defaults prevent Flask SERVER_NAME mismatches that cause route-wide 404s.
export HOSTED_PORTAL_ENV="${HOSTED_PORTAL_ENV:-production}"
export HOSTED_PORTAL_HOST="${HOSTED_PORTAL_HOST:-0.0.0.0}"
export HOSTED_PORTAL_PORT="${HOSTED_PORTAL_PORT:-8866}"
export HOSTED_PORTAL_BASE_URL="${HOSTED_PORTAL_BASE_URL:-http://10.17.7.88:8866}"
export HOSTED_PORTAL_RELEASE_ROOT="${HOSTED_PORTAL_RELEASE_ROOT:-/data/docking-portal/releases}"
export HOSTED_PORTAL_UPLOAD_ROOT="${HOSTED_PORTAL_UPLOAD_ROOT:-/var/lib/hosted-docking-portal/uploads}"
export HOSTED_PORTAL_JOB_ROOT="${HOSTED_PORTAL_JOB_ROOT:-/var/lib/hosted-docking-portal/jobs}"
export HOSTED_PORTAL_CACHE_DIR="${HOSTED_PORTAL_CACHE_DIR:-/var/cache/hosted-docking-portal}"
export HOSTED_PORTAL_LOG_LEVEL="${HOSTED_PORTAL_LOG_LEVEL:-INFO}"
export HOSTED_PORTAL_GUNICORN_BIND="${HOSTED_PORTAL_GUNICORN_BIND:-0.0.0.0:8866}"

mkdir -p \
  "${HOSTED_PORTAL_RELEASE_ROOT}" \
  "${HOSTED_PORTAL_UPLOAD_ROOT}" \
  "${HOSTED_PORTAL_JOB_ROOT}" \
  "${HOSTED_PORTAL_CACHE_DIR}"

if [[ -x "${APP_DIR}/.venv/bin/gunicorn" ]]; then
  exec "${APP_DIR}/.venv/bin/gunicorn" -c deploy/gunicorn.conf.py wsgi:app
fi

if command -v gunicorn >/dev/null 2>&1; then
  exec gunicorn -c deploy/gunicorn.conf.py wsgi:app
fi

echo "gunicorn not found; falling back to Flask development server" >&2
exec python -m flask --app wsgi:app run --host "${HOSTED_PORTAL_HOST}" --port "${HOSTED_PORTAL_PORT}"