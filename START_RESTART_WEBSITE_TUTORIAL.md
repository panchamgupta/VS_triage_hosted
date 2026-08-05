# Website Start and Restart Tutorial

This tutorial explains how to start, stop, and restart the hosted portal safely.

## Quick Guide for Non-Technical Users

If you only want simple STOP, DEPLOY, and RESTART steps, use this section.

### 1) STOP the website

Run:

    sudo systemctl stop hosted-portal-8866

Check:

    sudo systemctl status hosted-portal-8866 --no-pager -l

What you should see:

- Service shows as inactive (stopped).

### 2) DEPLOY website updates (script-only)

Run from repository root:

    bash deploy/start_portal_8866.sh service

What this does automatically:

- Syncs the environment file.
- Writes/updates the systemd service unit.
- Reloads systemd.
- Enables service on boot.
- Starts/restarts the website.

### 3) RESTART after a new change

Use either command below:

    bash deploy/start_portal_8866.sh service

or

    sudo systemctl restart hosted-portal-8866

### 4) Confirm website is healthy

Run:

    sudo systemctl status hosted-portal-8866 --no-pager -l
    curl -sS http://10.17.7.88:8866/healthz
    curl -sS http://10.17.7.88:8866/api/health | python -m json.tool

What good output looks like:

- systemctl status shows active (running)
- /healthz returns OK-style response
- /api/health returns JSON with healthy or degraded status

If it fails, check logs:

    sudo journalctl -u hosted-portal-8866 -n 200 --no-pager

## Scope

This tutorial covers:

1. local development startup
2. same-server production startup on port 8866
3. systemd service restart workflow
4. post-restart validation checks

## Prerequisites

1. Repository is checked out.
2. Python environment is installed.
3. Required environment variables are available (or env file is present).
4. Release directory exists and is readable.

## A. Start Website Locally (Development)

From repository root:

    export HOSTED_PORTAL_RELEASE_ROOT="$PWD/releases"
    export HOSTED_PORTAL_HOST=127.0.0.1
    export HOSTED_PORTAL_PORT=5005
    export HOSTED_PORTAL_BASE_URL=http://127.0.0.1:5005
    export FLASK_APP=wsgi:app
    python -m flask run --host "$HOSTED_PORTAL_HOST" --port "$HOSTED_PORTAL_PORT"

Open in browser:

    http://127.0.0.1:5005

Stop process:

- Press Ctrl+C in terminal.

## B. Start Website in Foreground (Production-like)

Use the prepared launcher script:

    bash deploy/start_portal_8866.sh foreground

This mode is useful for immediate debugging with live logs in the terminal.

Stop process:

- Press Ctrl+C in terminal.

## C. Start Website as a systemd Service

Install or sync environment and service files:

    sudo install -m 0644 deploy/hosted-portal-8866.env /etc/default/hosted-portal-8866
    sudo cp deploy/hosted-portal-8866.service.template /etc/systemd/system/hosted-portal-8866.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now hosted-portal-8866

Check service status:

    sudo systemctl status hosted-portal-8866 --no-pager -l

## D. Restart Website

Restart only:

    sudo systemctl restart hosted-portal-8866

Then verify service is healthy:

    sudo systemctl status hosted-portal-8866 --no-pager -l

## E. Stop Website

    sudo systemctl stop hosted-portal-8866

## F. Start Website After Stop

    sudo systemctl start hosted-portal-8866

## G. Validate After Start/Restart

1. Network listener:

       ss -ltnp | grep 8866 || true

2. Liveness endpoint:

       curl -sS http://10.17.7.88:8866/healthz

3. Detailed API health:

       curl -sS http://10.17.7.88:8866/api/health | python -m json.tool

4. Main pages:

       curl -I http://10.17.7.88:8866/
       curl -I http://10.17.7.88:8866/operations

## H. Troubleshooting

If service fails to start:

1. Read recent logs:

       sudo journalctl -u hosted-portal-8866 -n 200 --no-pager

2. Confirm env file exists and has correct values:

       sudo ls -l /etc/default/hosted-portal-8866

3. Confirm release root exists and is readable.

4. Confirm gunicorn is available in selected runtime environment.

5. Retry:

       sudo systemctl daemon-reload
       sudo systemctl restart hosted-portal-8866

## I. Useful One-Liners

Service lifecycle:

    sudo systemctl stop hosted-portal-8866
    sudo systemctl start hosted-portal-8866
    sudo systemctl restart hosted-portal-8866
    sudo systemctl status hosted-portal-8866 --no-pager -l

Live logs:

    sudo journalctl -u hosted-portal-8866 -f
