# Hosted Docking Portal for STAT6 PPI

This repository powers a hosted medicinal chemistry review portal and its upstream docking-report workflows.

## Key Features

1. Hosted release browser for docking campaigns.
2. Release-backed dataset pages and report pages.
3. Collaborative scaffold and molecule voting.
4. Operations page with CSV and SDF exports.
5. Health and readiness endpoints for production monitoring.
6. Batch pipeline scripts for generating report artifacts.
7. Production service templates for always-on deployment.

## Repository Layout

- [app](app): Flask app (routes, templates, APIs, services).
- [deploy](deploy): startup scripts, systemd templates, environment files.
- [scripts](scripts): release build and validation helpers.
- [releases](releases): hosted release manifests and payloads.
- [tests](tests): regression and API behavior tests.

## Installation

### Recommended: Conda environment

    conda create -n rdkit-env python=3.11 -y
    conda activate rdkit-env
    conda install -c conda-forge rdkit pandas numpy matplotlib pyarrow mdtraj flask gunicorn -y

### Alternative: existing Python environment

Install equivalent packages so these imports work:

- rdkit
- pandas
- numpy
- matplotlib
- flask
- gunicorn

## Quick Start (Local Website)

From repository root:

    export HOSTED_PORTAL_RELEASE_ROOT="$PWD/releases"
    export HOSTED_PORTAL_HOST=127.0.0.1
    export HOSTED_PORTAL_PORT=5005
    export HOSTED_PORTAL_BASE_URL=http://127.0.0.1:5005
    export FLASK_APP=wsgi:app
    python -m flask run --host "$HOSTED_PORTAL_HOST" --port "$HOSTED_PORTAL_PORT"

Open:

    http://127.0.0.1:5005

## Production Start and Restart (Port 8866)

This project includes a production-oriented launcher:

- [deploy/start_hosted_portal.sh](deploy/start_hosted_portal.sh)

Use this helper script when you want script-only deploy/start behavior:

- [deploy/start_portal_8866.sh](deploy/start_portal_8866.sh)

Script-only workflow (recommended):

1. Deploy or refresh service files and start website:

    bash deploy/start_portal_8866.sh service

2. Restart website after code/config changes:

    bash deploy/start_portal_8866.sh service

3. Run in foreground for quick debugging (no systemd):

    bash deploy/start_portal_8866.sh foreground

What these scripts do for you:

- `service` mode syncs env file, writes service unit, reloads systemd, enables service, and starts/restarts it.
- `foreground` mode loads env and starts the app in the current terminal.

For managed service startup on same host:

    sudo install -m 0644 deploy/hosted-portal-8866.env /etc/default/hosted-portal-8866
    sudo cp deploy/hosted-portal-8866.service.template /etc/systemd/system/hosted-portal-8866.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now hosted-portal-8866

What these commands do:

- Copies the production environment file to the system location used by systemd.
- Copies the service template so Linux knows how to run this website as a service.
- Reloads systemd after adding or changing service files.
- Enables auto-start on boot and starts the service immediately.

Restart service:

    sudo systemctl restart hosted-portal-8866

What this command does:

- Stops and starts the service again. Use this after code or config changes.

Check status and logs:

    sudo systemctl status hosted-portal-8866 --no-pager -l
    sudo journalctl -u hosted-portal-8866 -n 200 --no-pager

What these commands do:

- Shows if the service is running and prints full status details.
- Shows the latest 200 log lines for troubleshooting startup/runtime issues.

Health checks:

    curl -sS http://10.17.7.88:8866/healthz
    curl -sS http://10.17.7.88:8866/api/health | python -m json.tool

What these commands do:

- Checks basic liveness of the website.
- Checks detailed API health and formats JSON output for easy reading.

## Website Start/Restart Tutorial

See the dedicated operational tutorial:

- [START_RESTART_WEBSITE_TUTORIAL.md](START_RESTART_WEBSITE_TUTORIAL.md)

It includes:

1. local start
2. foreground production start
3. systemd start/restart
4. verification checklist
5. common failure recovery

## Common Routes

- / : release landing page
- /operations : operations and exports
- /jobs : job history
- /healthz : liveness
- /readyz : readiness
- /api/health : diagnostics

## Additional Docs

- [DEPLOYMENT.md](DEPLOYMENT.md)
- [DEPLOYMENT_SAME_SERVER_8866.md](DEPLOYMENT_SAME_SERVER_8866.md)
- [RELIABILITY_RUNBOOK_8866.md](RELIABILITY_RUNBOOK_8866.md)
- [HOSTED_PORTAL_TECHNICAL_DESIGN.md](HOSTED_PORTAL_TECHNICAL_DESIGN.md)
- [COLLABORATIVE_VOTING_ARCHITECTURE.md](COLLABORATIVE_VOTING_ARCHITECTURE.md)

