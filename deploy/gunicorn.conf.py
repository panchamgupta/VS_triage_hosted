import multiprocessing
import os


bind = os.getenv("HOSTED_PORTAL_GUNICORN_BIND", "127.0.0.1:8000")
workers = int(os.getenv("HOSTED_PORTAL_GUNICORN_WORKERS", str(max(2, min(4, multiprocessing.cpu_count())))))
threads = int(os.getenv("HOSTED_PORTAL_GUNICORN_THREADS", "2"))
timeout = int(os.getenv("HOSTED_PORTAL_GUNICORN_TIMEOUT", "180"))
graceful_timeout = int(os.getenv("HOSTED_PORTAL_GUNICORN_GRACEFUL_TIMEOUT", "45"))
keepalive = int(os.getenv("HOSTED_PORTAL_GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.getenv("HOSTED_PORTAL_GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.getenv("HOSTED_PORTAL_GUNICORN_MAX_REQUESTS_JITTER", "100"))
accesslog = os.getenv("HOSTED_PORTAL_GUNICORN_ACCESSLOG", "-")
errorlog = os.getenv("HOSTED_PORTAL_GUNICORN_ERRORLOG", "-")
loglevel = os.getenv("HOSTED_PORTAL_GUNICORN_LOGLEVEL", "info")
capture_output = True
preload_app = False