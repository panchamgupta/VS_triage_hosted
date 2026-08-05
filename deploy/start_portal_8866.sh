#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/hosted-portal-8866.env"
SYSTEM_ENV_FILE="/etc/default/hosted-portal-8866"
SYSTEMD_UNIT="/etc/systemd/system/hosted-portal-8866.service"

MODE="${1:-service}"

load_env_file() {
  local candidate="$1"
  if [[ -f "${candidate}" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "${candidate}"
    set +a
  fi
}

ensure_runtime_dirs() {
  mkdir -p \
    "${HOSTED_PORTAL_RELEASE_ROOT:-/data/docking-portal/releases}" \
    "${HOSTED_PORTAL_UPLOAD_ROOT:-/var/lib/hosted-docking-portal/uploads}" \
    "${HOSTED_PORTAL_JOB_ROOT:-/var/lib/hosted-docking-portal/jobs}" \
    "${HOSTED_PORTAL_CACHE_DIR:-/var/cache/hosted-docking-portal}" \
    "${HOSTED_PORTAL_LOG_DIR:-/var/log/hosted-docking-portal}"

  local vote_db_path="${HOSTED_PORTAL_VOTE_DB_PATH:-/var/lib/hosted-docking-portal/votes/votes.sqlite3}"
  mkdir -p "$(dirname "${vote_db_path}")"
}

write_systemd_unit() {
  local service_user service_group read_write_paths

  service_user="${HOSTED_PORTAL_SERVICE_USER:-$(id -u)}"
  service_group="${HOSTED_PORTAL_SERVICE_GROUP:-$(id -g)}"
  read_write_paths="${HOSTED_PORTAL_CACHE_DIR:-/var/cache/hosted-docking-portal} ${HOSTED_PORTAL_UPLOAD_ROOT:-/var/lib/hosted-docking-portal/uploads} ${HOSTED_PORTAL_JOB_ROOT:-/var/lib/hosted-docking-portal/jobs} ${HOSTED_PORTAL_RELEASE_ROOT:-/data/docking-portal/releases} ${HOSTED_PORTAL_LOG_DIR:-/var/log/hosted-docking-portal} $(dirname "${HOSTED_PORTAL_VOTE_DB_PATH:-/var/lib/hosted-docking-portal/votes/votes.sqlite3}")"

  sudo tee "${SYSTEMD_UNIT}" >/dev/null <<EOF
[Unit]
Description=Hosted Docking Portal (Port 8866)
After=network.target
StartLimitIntervalSec=0

[Service]
User=${service_user}
Group=${service_group}
WorkingDirectory=${APP_DIR}
EnvironmentFile=-${SYSTEM_ENV_FILE}
Environment=HOSTED_PORTAL_ENV=production
Environment=HOSTED_PORTAL_HOST=0.0.0.0
Environment=HOSTED_PORTAL_PORT=8866
Environment=HOSTED_PORTAL_BASE_URL=http://10.17.7.88:8866
ExecStart=${APP_DIR}/deploy/start_hosted_portal.sh
Restart=always
RestartSec=5
TimeoutStopSec=30
KillMode=mixed
LimitNOFILE=65535
TasksMax=infinity
StandardOutput=journal
StandardError=journal
PrivateTmp=true
NoNewPrivileges=true
ReadWritePaths=${read_write_paths} ${APP_DIR}
UMask=0027

[Install]
WantedBy=multi-user.target
EOF
}

ensure_runtime_dirs_with_sudo() {
  local service_user service_group vote_db_path

  service_user="${HOSTED_PORTAL_SERVICE_USER:-$(id -u)}"
  service_group="${HOSTED_PORTAL_SERVICE_GROUP:-$(id -g)}"
  vote_db_path="${HOSTED_PORTAL_VOTE_DB_PATH:-/var/lib/hosted-docking-portal/votes/votes.sqlite3}"

  sudo mkdir -p \
    "${HOSTED_PORTAL_RELEASE_ROOT:-/data/docking-portal/releases}" \
    "${HOSTED_PORTAL_UPLOAD_ROOT:-/var/lib/hosted-docking-portal/uploads}" \
    "${HOSTED_PORTAL_JOB_ROOT:-/var/lib/hosted-docking-portal/jobs}" \
    "${HOSTED_PORTAL_CACHE_DIR:-/var/cache/hosted-docking-portal}" \
    "${HOSTED_PORTAL_LOG_DIR:-/var/log/hosted-docking-portal}" \
    "$(dirname "${vote_db_path}")"

  sudo chown -R "${service_user}:${service_group}" \
    "${HOSTED_PORTAL_RELEASE_ROOT:-/data/docking-portal/releases}" \
    "${HOSTED_PORTAL_UPLOAD_ROOT:-/var/lib/hosted-docking-portal/uploads}" \
    "${HOSTED_PORTAL_JOB_ROOT:-/var/lib/hosted-docking-portal/jobs}" \
    "${HOSTED_PORTAL_CACHE_DIR:-/var/cache/hosted-docking-portal}" \
    "${HOSTED_PORTAL_LOG_DIR:-/var/log/hosted-docking-portal}" \
    "$(dirname "${vote_db_path}")"
}

start_with_systemd() {
  load_env_file "${ENV_FILE}"

  if ! command -v systemctl >/dev/null 2>&1; then
    echo "[start] systemctl not available; falling back to foreground mode" >&2
    start_foreground
    return
  fi

  if [[ ! -f "${SYSTEM_ENV_FILE}" ]] || ! cmp -s "${ENV_FILE}" "${SYSTEM_ENV_FILE}"; then
    echo "[start] Syncing ${ENV_FILE} to ${SYSTEM_ENV_FILE}"
    sudo install -m 0644 "${ENV_FILE}" "${SYSTEM_ENV_FILE}"
  fi

  echo "[start] Writing ${SYSTEMD_UNIT} for user $(id -un) and repo ${APP_DIR}"
  write_systemd_unit

  sudo chmod +x "${SCRIPT_DIR}/start_hosted_portal.sh"
  ensure_runtime_dirs_with_sudo
  sudo systemctl daemon-reload
  sudo systemctl enable --now hosted-portal-8866
  sudo systemctl restart hosted-portal-8866
  sudo systemctl status hosted-portal-8866 --no-pager -l
}

start_foreground() {
  load_env_file "${ENV_FILE}"
  ensure_runtime_dirs
  cd "${APP_DIR}"
  exec "${SCRIPT_DIR}/start_hosted_portal.sh"
}

case "${MODE}" in
  service)
    start_with_systemd
    ;;
  foreground)
    start_foreground
    ;;
  *)
    echo "Usage: $0 [service|foreground]" >&2
    exit 2
    ;;
esac