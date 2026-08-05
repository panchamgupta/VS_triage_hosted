#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${HOSTED_PORTAL_BASE_URL:-http://10.17.7.88:8866}"
RELEASE_ID="${1:-release_20260803_001}"
SMOKE_USER="smoke-check"
TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-10}"

echo "[smoke] Base URL: ${BASE_URL}"
echo "[smoke] Release ID: ${RELEASE_ID}"

fail() {
  echo "[smoke] FAIL: $1" >&2
  exit 1
}

assert_http_200() {
  local url="$1"
  local code
  code="$(curl -sS -m "${TIMEOUT_SECONDS}" -o /tmp/hosted_portal_smoke_body.txt -w '%{http_code}' "${url}")"
  if [[ "${code}" != "200" ]]; then
    fail "Expected HTTP 200 for ${url}, got ${code}"
  fi
}

assert_json_field_equals() {
  local file_path="$1"
  local field_name="$2"
  local expected="$3"
  python - "$file_path" "$field_name" "$expected" <<'PY'
import json
import sys
path, field_name, expected = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
value = data.get(field_name)
if str(value) != expected:
    raise SystemExit(1)
PY
}

echo "[smoke] 1/5 healthz"
assert_http_200 "${BASE_URL}/healthz"

echo "[smoke] 2/5 api health"
curl -sS -m "${TIMEOUT_SECONDS}" "${BASE_URL}/api/health" -o /tmp/hosted_portal_api_health.json
python - /tmp/hosted_portal_api_health.json <<'PY'
import json
import sys
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)
status = str(data.get('status', '')).lower()
if status == 'unhealthy' or status == '':
    raise SystemExit(1)
PY


echo "[smoke] 3/5 release page"
assert_http_200 "${BASE_URL}/release/${RELEASE_ID}"

echo "[smoke] 4/5 report page"
assert_http_200 "${BASE_URL}/release/${RELEASE_ID}/report"

echo "[smoke] 5/5 vote release endpoint"
curl -sS -m "${TIMEOUT_SECONDS}" "${BASE_URL}/api/votes/release/${RELEASE_ID}?username=${SMOKE_USER}" -o /tmp/hosted_portal_votes_release.json
assert_json_field_equals /tmp/hosted_portal_votes_release.json release_id "${RELEASE_ID}"

echo "[smoke] PASS: health, release, report, and vote API checks succeeded."
