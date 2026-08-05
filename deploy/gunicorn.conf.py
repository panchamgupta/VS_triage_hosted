import os


bind = os.getenv("HOSTED_PORTAL_GUNICORN_BIND", "127.0.0.1:8000")
# IMPORTANT: the current job scheduler is in-process; multiple workers can produce
# split-brain job state and duplicate queue ownership. Keep one worker by default.
workers = int(os.getenv("HOSTED_PORTAL_GUNICORN_WORKERS", "1"))
threads = int(os.getenv("HOSTED_PORTAL_GUNICORN_THREADS", "8"))
worker_class = os.getenv("HOSTED_PORTAL_GUNICORN_WORKER_CLASS", "gthread")
timeout = int(os.getenv("HOSTED_PORTAL_GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("HOSTED_PORTAL_GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("HOSTED_PORTAL_GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.getenv("HOSTED_PORTAL_GUNICORN_MAX_REQUESTS", "500"))
max_requests_jitter = int(os.getenv("HOSTED_PORTAL_GUNICORN_MAX_REQUESTS_JITTER", "100"))
worker_tmp_dir = os.getenv("HOSTED_PORTAL_GUNICORN_WORKER_TMP_DIR", "/dev/shm")
accesslog = os.getenv("HOSTED_PORTAL_GUNICORN_ACCESSLOG", "-")
errorlog = os.getenv("HOSTED_PORTAL_GUNICORN_ERRORLOG", "-")
loglevel = os.getenv("HOSTED_PORTAL_GUNICORN_LOGLEVEL", "info")
capture_output = True
preload_app = False