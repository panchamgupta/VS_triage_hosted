from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import time
from urllib.parse import urljoin

from flask import Flask, jsonify, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app.api import register_api_blueprints
from app.config import HostedPortalConfig
from app.routes import pages_bp
from app.services.cache_service import SimpleCache
from app.services.health_service import HealthService
from app.services.job_service import JobService
from app.services.operations_service import OperationsService
from app.services.project_service import ProjectService
from app.services.release_service import ReleaseService
from app.services.retention_service import RetentionService
from app.services.vote_service import VoteService
from app.storage.filesystem import FilesystemReleaseStore


def _configure_logging(app):
    level_name = str(app.config.get("HOSTED_PORTAL_LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    log_dir = Path(app.config.get("HOSTED_PORTAL_LOG_DIR"))
    log_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = int(app.config.get("HOSTED_PORTAL_LOG_MAX_BYTES", 20 * 1024 * 1024))
    backup_count = int(app.config.get("HOSTED_PORTAL_LOG_BACKUP_COUNT", 14))

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not any(isinstance(handler, RotatingFileHandler) for handler in root_logger.handlers):
        app_handler = RotatingFileHandler(
            str(log_dir / "portal.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        app_handler.setFormatter(formatter)
        app_handler.setLevel(level)
        root_logger.addHandler(app_handler)

        err_handler = RotatingFileHandler(
            str(log_dir / "portal-error.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        err_handler.setFormatter(formatter)
        err_handler.setLevel(logging.WARNING)
        root_logger.addHandler(err_handler)

    app.logger.setLevel(level)
    app.logger.info("Logging configured", extra={"event": "logging_configured", "log_dir": str(log_dir)})


def _run_startup_validation(app):
    release_root = Path(app.config["HOSTED_PORTAL_RELEASE_ROOT"])
    upload_root = Path(app.config["HOSTED_PORTAL_UPLOAD_ROOT"])
    job_root = Path(app.config["HOSTED_PORTAL_JOB_ROOT"])
    vote_db_path = Path(app.config["HOSTED_PORTAL_VOTE_DB_PATH"])

    checks = {
        "release_root_exists": release_root.exists() and release_root.is_dir(),
        "upload_root_exists": upload_root.exists() and upload_root.is_dir(),
        "job_root_exists": job_root.exists() and job_root.is_dir(),
        "vote_db_parent_exists": vote_db_path.parent.exists() and vote_db_path.parent.is_dir(),
        "vote_db_exists": vote_db_path.exists(),
        "release_load_status": "healthy",
        "vote_load_status": "healthy",
        "job_rehydrate_status": "healthy",
        "available_release_count": 0,
        "invalid_release_count": 0,
        "rehydrated_jobs": 0,
        "error": "",
    }

    try:
        releases = app.extensions["release_service"].list_releases(include_invalid=True)
        checks["available_release_count"] = sum(
            1 for item in releases if item.get("status") == "published"
        )
        checks["invalid_release_count"] = sum(
            1 for item in releases if item.get("status") != "published"
        )
        if checks["invalid_release_count"]:
            checks["release_load_status"] = "degraded"
    except Exception as exc:
        checks["release_load_status"] = "unhealthy"
        checks["error"] = str(exc)

    vote_health = app.extensions["vote_service"].health_snapshot()
    if vote_health.get("status") == "unhealthy":
        checks["vote_load_status"] = "unhealthy"
        checks["error"] = checks["error"] or vote_health.get("error", "vote database unavailable")
    elif vote_health.get("status") == "degraded":
        checks["vote_load_status"] = "degraded"

    job_stats = app.extensions["job_service"].get_runtime_stats(
        stale_after_seconds=int(app.config.get("HOSTED_PORTAL_JOB_HEARTBEAT_STALE_SECONDS", 900))
    )
    checks["rehydrated_jobs"] = int(job_stats.get("rehydrated_jobs") or 0)
    if job_stats.get("executor_shutdown"):
        checks["job_rehydrate_status"] = "unhealthy"

    statuses = [
        checks["release_load_status"],
        checks["vote_load_status"],
        checks["job_rehydrate_status"],
        "healthy" if checks["release_root_exists"] else "unhealthy",
        "healthy" if checks["upload_root_exists"] else "unhealthy",
        "healthy" if checks["job_root_exists"] else "unhealthy",
        "healthy" if checks["vote_db_parent_exists"] else "unhealthy",
    ]
    if "unhealthy" in statuses:
        overall = "unhealthy"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    payload = {
        "status": overall,
        "generated_at": time.time(),
        "checks": checks,
    }
    app.extensions["startup_validation"] = payload
    app.logger.info("Startup validation complete", extra={"event": "startup_validation", "status": overall})

    if app.config.get("HOSTED_PORTAL_STARTUP_STRICT") and overall != "healthy":
        raise RuntimeError("Startup validation failed in strict mode")

    return payload


def create_app(config_object=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    if config_object is None:
        config_object = HostedPortalConfig.from_env()

    app.config.from_mapping(config_object.as_flask_mapping())
    app.config.setdefault("HOSTED_PORTAL_ASSET_VERSION", str(int(time.time())))
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
    _configure_logging(app)

    cache_dir = Path(app.config["HOSTED_PORTAL_CACHE_DIR"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    upload_root = Path(app.config["HOSTED_PORTAL_UPLOAD_ROOT"])
    upload_root.mkdir(parents=True, exist_ok=True)
    job_root = Path(app.config["HOSTED_PORTAL_JOB_ROOT"])
    job_root.mkdir(parents=True, exist_ok=True)
    vote_db_path = Path(app.config["HOSTED_PORTAL_VOTE_DB_PATH"])
    vote_db_path.parent.mkdir(parents=True, exist_ok=True)

    release_store = FilesystemReleaseStore(app.config["HOSTED_PORTAL_RELEASE_ROOT"])
    release_cache = SimpleCache()
    release_service = ReleaseService(
        store=release_store,
        cache=release_cache,
        active_release=app.config.get("HOSTED_PORTAL_ACTIVE_RELEASE") or None,
    )
    job_service = JobService(
        repo_root=config_object.base_dir,
        release_root=app.config["HOSTED_PORTAL_RELEASE_ROOT"],
        upload_root=app.config["HOSTED_PORTAL_UPLOAD_ROOT"],
        job_root=app.config["HOSTED_PORTAL_JOB_ROOT"],
        max_upload_mb=app.config["HOSTED_PORTAL_MAX_UPLOAD_MB"],
        max_workers=app.config["HOSTED_PORTAL_JOB_MAX_WORKERS"],
        default_n_workers=app.config["HOSTED_PORTAL_PIPELINE_DEFAULT_N_WORKERS"],
        max_n_workers=app.config["HOSTED_PORTAL_PIPELINE_MAX_N_WORKERS"],
    )
    job_service._flask_app = app
    project_service = ProjectService(release_service=release_service, job_service=job_service)
    vote_service = VoteService(db_path=vote_db_path)
    operations_service = OperationsService(
        release_service=release_service,
        job_service=job_service,
        project_service=project_service,
        vote_service=vote_service,
    )
    retention_service = RetentionService(config=config_object, job_service=job_service)

    app.extensions["release_store"] = release_store
    app.extensions["release_cache"] = release_cache
    app.extensions["release_service"] = release_service
    app.extensions["job_service"] = job_service
    app.extensions["project_service"] = project_service
    app.extensions["vote_service"] = vote_service
    app.extensions["operations_service"] = operations_service
    app.extensions["retention_service"] = retention_service

    startup_validation = _run_startup_validation(app)
    health_service = HealthService(
        release_service=release_service,
        vote_service=vote_service,
        job_service=job_service,
        app_config=app.config,
        startup_validation=startup_validation,
    )
    app.extensions["health_service"] = health_service

    app.register_blueprint(pages_bp)
    register_api_blueprints(app)

    @app.context_processor
    def inject_portal_context():
        base_url = str(app.config.get("HOSTED_PORTAL_BASE_URL", "")).rstrip("/")

        def absolute_url_for(endpoint, **values):
            route_url = url_for(endpoint, **values)
            if not base_url:
                return route_url
            return urljoin(base_url + "/", route_url.lstrip("/"))

        return {
            "portal_base_url": base_url,
            "absolute_url_for": absolute_url_for,
            "static_asset_version": app.config.get("HOSTED_PORTAL_ASSET_VERSION", "1"),
        }

    @app.route("/healthz", methods=["GET"])
    def healthz():
        payload = app.extensions["health_service"].build_snapshot()
        status = 200 if payload.get("status") == "healthy" else 503
        return jsonify({"status": payload.get("status"), "generated_at": payload.get("generated_at")}), status

    @app.route("/readyz", methods=["GET"])
    def readyz():
        payload = app.extensions["health_service"].build_snapshot()
        status = 200 if payload.get("status") == "healthy" else 503
        return jsonify(payload), status

    return app