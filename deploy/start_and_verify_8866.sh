#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RELEASE_ID="${1:-release_20260803_001}"
MODE="${2:-service}"
BASE_URL="${HOSTED_PORTAL_BASE_URL:-http://10.17.7.88:8866}"
READY_TIMEOUT_SECONDS="${HOSTED_PORTAL_READY_TIMEOUT_SECONDS:-30}"

print_failure_diagnostics() {
  if [[ "${MODE}" == "service" ]] && command -v systemctl >/dev/null 2>&1; then
    echo "[verify] Service startup failed; current status"
    sudo systemctl status hosted-portal-8866 --no-pager -l || true
    echo "[verify] Recent service logs"
    sudo journalctl -u hosted-portal-8866 -n 60 --no-pager || true
  fi
}

trap print_failure_diagnostics ERR

wait_for_ready() {
  local waited=0
  echo "[verify] Waiting up to ${READY_TIMEOUT_SECONDS}s for ${BASE_URL}/healthz"
  while (( waited < READY_TIMEOUT_SECONDS )); do
    if curl -sS -m 3 -o /dev/null -w '%{http_code}' "${BASE_URL}/healthz" 2>/dev/null | grep -q '^200$'; then
      echo "[verify] Portal is responding after ${waited}s"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  echo "[verify] Portal did not respond within ${READY_TIMEOUT_SECONDS}s" >&2
  return 1
}

cd "${APP_DIR}"

chmod +x "${SCRIPT_DIR}/start_portal_8866.sh" "${SCRIPT_DIR}/post_deploy_smoke_8866.sh"

echo "[verify] Starting hosted portal in ${MODE} mode"
"${SCRIPT_DIR}/start_portal_8866.sh" "${MODE}"

if [[ "${MODE}" == "service" ]] && command -v systemctl >/dev/null 2>&1; then
  echo "[verify] Recent service logs"
  sudo journalctl -u hosted-portal-8866 -n 30 --no-pager || true
fi

wait_for_ready

echo "[verify] Running smoke test for ${RELEASE_ID}"
HOSTED_PORTAL_BASE_URL="${HOSTED_PORTAL_BASE_URL:-http://10.17.7.88:8866}" \
  "${SCRIPT_DIR}/post_deploy_smoke_8866.sh" "${RELEASE_ID}"

echo "[verify] PASS: service start and post-deploy smoke checks succeeded."