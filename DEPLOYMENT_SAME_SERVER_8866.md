# Same-Server Deployment (Dash + Hosted Portal)

This guide deploys the hosted portal on `10.17.7.88:8866` while keeping the existing Dash app on `10.17.7.88:8865` unchanged.

## Safety Goal

- Existing Dash app (`8865`) remains untouched.
- Hosted portal is launched as a separate process on `8866`.
- No shared service name is reused.

## 1. Pre-checks

```bash
# Check that Dash is currently listening as expected
ss -ltnp | grep 8865 || true

# Check target port is free before deploy
ss -ltnp | grep 8866 || true
```

If `8866` is busy, pick another unused port and update:

- `.env.production`
- `deploy/hosted-portal-8866.service.template`

## 2. Copy Code

```bash
rsync -av --delete ./ /opt/hosted-docking-portal/
cd /opt/hosted-docking-portal
```

## 3. Python Environment

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip wheel
pip install flask gunicorn werkzeug
```

## 4. Production Environment

Use `.env.production` values for the same-server profile:

- `HOSTED_PORTAL_HOST=0.0.0.0`
- `HOSTED_PORTAL_PORT=8866`
- `HOSTED_PORTAL_BASE_URL=http://10.17.7.88:8866`
- `HOSTED_PORTAL_GUNICORN_BIND=0.0.0.0:8866`

## 5. Gunicorn Manual Start (optional validation)

```bash
export HOSTED_PORTAL_ENV=production
export HOSTED_PORTAL_HOST=0.0.0.0
export HOSTED_PORTAL_PORT=8866
export HOSTED_PORTAL_BASE_URL=http://10.17.7.88:8866
export HOSTED_PORTAL_RELEASE_ROOT=/data/docking-portal/releases
export HOSTED_PORTAL_CACHE_DIR=/var/cache/hosted-docking-portal
export HOSTED_PORTAL_GUNICORN_BIND=0.0.0.0:8866

/opt/hosted-docking-portal/.venv/bin/gunicorn -c deploy/gunicorn.conf.py wsgi:app
```

## 6. systemd Activation

```bash
chmod +x deploy/start_hosted_portal.sh
sudo cp deploy/hosted-portal-8866.service.template /etc/systemd/system/hosted-portal-8866.service

# Optional: centralized overrides for this host (recommended)
sudo tee /etc/default/hosted-portal-8866 >/dev/null <<'EOF'
HOSTED_PORTAL_ENV=production
HOSTED_PORTAL_HOST=0.0.0.0
HOSTED_PORTAL_PORT=8866
HOSTED_PORTAL_BASE_URL=http://10.17.7.88:8866
HOSTED_PORTAL_RELEASE_ROOT=/data/docking-portal/releases
HOSTED_PORTAL_UPLOAD_ROOT=/var/lib/hosted-docking-portal/uploads
HOSTED_PORTAL_JOB_ROOT=/var/lib/hosted-docking-portal/jobs
HOSTED_PORTAL_CACHE_DIR=/var/cache/hosted-docking-portal
HOSTED_PORTAL_GUNICORN_BIND=0.0.0.0:8866
HOSTED_PORTAL_GUNICORN_WORKERS=1
HOSTED_PORTAL_GUNICORN_THREADS=8
HOSTED_PORTAL_LOG_DIR=/var/log/hosted-docking-portal
HOSTED_PORTAL_STARTUP_STRICT=false
EOF

sudo mkdir -p \
	/var/lib/hosted-docking-portal/uploads \
	/var/lib/hosted-docking-portal/jobs \
	/var/cache/hosted-docking-portal \
	/var/log/hosted-docking-portal \
	/data/docking-portal/releases
sudo chown -R hostedportal:hostedportal /var/lib/hosted-docking-portal /var/cache/hosted-docking-portal /var/log/hosted-docking-portal /data/docking-portal/releases

sudo systemctl daemon-reload
sudo systemctl enable --now hosted-portal-8866
sudo systemctl status hosted-portal-8866 --no-pager
```

## 7. Firewall Rule

```bash
# Example with ufw
sudo ufw allow 8866/tcp
```

## 8. Smoke Test

```bash
curl -sSf http://10.17.7.88:8866/healthz
curl -sS http://10.17.7.88:8866/api/health | jq .status
```

Then open in browser:

- `http://10.17.7.88:8866`

## 9. Coexistence Checks

```bash
# Dash still running
ss -ltnp | grep 8865 || true

# Hosted portal running on separate port
ss -ltnp | grep 8866 || true
```

This confirms side-by-side deployment without modifying Dash.
