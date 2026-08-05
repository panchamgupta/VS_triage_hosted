# Hosted Portal Reliability Runbook (10.17.7.88:8866)

## Scope

This runbook covers always-on operation for:
- release browsing
- report viewing
- voting
- deep-dive review
- upload-driven report generation

## 1. Failure Modes and Mitigations

### Process and Service Failures
- Flask/Gunicorn exit: mitigated with systemd `Restart=always` and `RestartSec=5`.
- Worker restart churn: mitigated with `max_requests` + jitter and graceful timeouts.
- Host mismatch 404s from `SERVER_NAME` drift: mitigated by defaulting `HOSTED_PORTAL_ENFORCE_SERVER_NAME=false`.

### Application-Level Failures
- Unhealthy vote DB: detected through `/api/health` vote DB quick check.
- Invalid release payloads: surfaced as degraded release status, not silent failure.
- Running job interrupted by restart: recovered as `orphaned` with durable state and explicit job status.

### Capacity and Resource Risks
- Disk pressure: surfaced via `/api/health` disk usage checks with healthy/degraded/unhealthy thresholds.
- Stale running jobs: surfaced via `/api/health` job queue stale heartbeat detection.

## 2. Production systemd Unit (8866)

Use [deploy/hosted-portal-8866.service.template](deploy/hosted-portal-8866.service.template).

Key settings:
- `Restart=always`
- `RestartSec=5`
- `StartLimitIntervalSec=0`
- `KillMode=mixed`
- `LimitNOFILE=65535`
- `TasksMax=infinity`
- `ReadWritePaths` includes releases, uploads/jobs/cache, and logs
- `WantedBy=multi-user.target` for start-on-boot behavior

## 3. Gunicorn Runtime Guidance

Use [deploy/gunicorn.conf.py](deploy/gunicorn.conf.py).

Current safe defaults for in-process job model:
- `workers=1`
- `threads=8`
- `worker_class=gthread`
- `timeout=120`
- `graceful_timeout=30`
- `max_requests=500`
- `max_requests_jitter=100`

Reason: current in-process job queue is not multi-worker safe.

## 4. Job Isolation Recommendation

Current state:
- upload/report jobs execute from web workers via in-process scheduler + subprocess commands.

Recommendation:
- Near term: keep one Gunicorn worker and preserve subprocess job execution (already isolated from request threads).
- Medium term: move to dedicated worker process + queue (Celery/RQ/Arq or custom supervisor queue) with DB-backed job state.
- Long term: ensure web tier is stateless and never owns job execution concurrency.

## 5. Startup Validation

Startup now validates:
- release root exists
- upload/job roots exist
- vote DB path exists/connects
- releases are loadable
- job runtime rehydration snapshot is available

Strict mode available:
- `HOSTED_PORTAL_STARTUP_STRICT=true` fails startup when unhealthy.

## 6. Health Monitoring

Use [app/api/datasets.py](app/api/datasets.py) endpoint:
- `GET /api/health`

Status model:
- `healthy`
- `degraded`
- `unhealthy`

Coverage:
- release status
- vote database status
- job queue/runtime status
- disk usage
- upload/release/job directory checks
- gunicorn runtime context
- worker process metadata
- startup validation summary

## 7. Logging and Rotation

Configured in [app/__init__.py](app/__init__.py):
- rotating app log: `portal.log`
- rotating error log: `portal-error.log`
- controlled by env:
  - `HOSTED_PORTAL_LOG_DIR`
  - `HOSTED_PORTAL_LOG_MAX_BYTES`
  - `HOSTED_PORTAL_LOG_BACKUP_COUNT`

Service-level events logged:
- jobs
- votes
- releases
- cleanup tasks

## 8. Backup Strategy

Protect:
- release root (`HOSTED_PORTAL_RELEASE_ROOT`)
- vote database (`HOSTED_PORTAL_VOTE_DB_PATH`)
- job state (`HOSTED_PORTAL_JOB_ROOT/*/job.json`)

Recommended schedule:
- Hourly: vote DB + job JSON snapshots.
- Daily: release root + manifests.
- Weekly: full archive and restore test.

Retention:
- 30 daily
- 12 weekly
- 6 monthly

## 9. Production Checklist

1. Deploy latest code and templates.
2. Ensure env file sets 8866 values and log dir.
3. `sudo systemctl daemon-reload`
4. `sudo systemctl enable --now hosted-portal-8866`
5. Verify:
   - `curl -sSf http://10.17.7.88:8866/healthz`
   - `curl -sS http://10.17.7.88:8866/api/health | jq .status`
6. Confirm port and service:
   - `ss -ltnp | grep 8866`
   - `systemctl status hosted-portal-8866 --no-pager`
7. Confirm logs rotating under log dir.

## 10. Recovery Validation Plan

1. Crash test:
   - kill gunicorn master process
   - verify service auto-restores in <= 10s
2. Worker recycle test:
   - send load and verify no 5xx spikes during worker recycling
3. Reboot test:
   - reboot host and verify service is active after boot
4. Functional checks after restart:
   - home page loads
   - default release loads
   - report page loads
   - votes API returns data
   - jobs list/history readable
