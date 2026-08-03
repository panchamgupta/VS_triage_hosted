from pathlib import Path
from urllib.parse import urljoin

from flask import Flask, jsonify, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app.api import register_api_blueprints
from app.config import HostedPortalConfig
from app.routes import pages_bp
from app.services.cache_service import SimpleCache
from app.services.job_service import JobService
from app.services.operations_service import OperationsService
from app.services.project_service import ProjectService
from app.services.release_service import ReleaseService
from app.services.retention_service import RetentionService
from app.storage.filesystem import FilesystemReleaseStore


def create_app(config_object=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    if config_object is None:
        config_object = HostedPortalConfig.from_env()

    app.config.from_mapping(config_object.as_flask_mapping())
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

    cache_dir = Path(app.config["HOSTED_PORTAL_CACHE_DIR"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    upload_root = Path(app.config["HOSTED_PORTAL_UPLOAD_ROOT"])
    upload_root.mkdir(parents=True, exist_ok=True)
    job_root = Path(app.config["HOSTED_PORTAL_JOB_ROOT"])
    job_root.mkdir(parents=True, exist_ok=True)

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
    project_service = ProjectService(release_service=release_service, job_service=job_service)
    operations_service = OperationsService(
        release_service=release_service,
        job_service=job_service,
        project_service=project_service,
    )
    retention_service = RetentionService(config=config_object, job_service=job_service)

    app.extensions["release_store"] = release_store
    app.extensions["release_cache"] = release_cache
    app.extensions["release_service"] = release_service
    app.extensions["job_service"] = job_service
    app.extensions["project_service"] = project_service
    app.extensions["operations_service"] = operations_service
    app.extensions["retention_service"] = retention_service

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
        }

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"status": "ok"})

    @app.route("/readyz", methods=["GET"])
    def readyz():
        release_root = Path(app.config["HOSTED_PORTAL_RELEASE_ROOT"])
        ready = release_root.exists() and release_root.is_dir()
        status = 200 if ready else 503
        return (
            jsonify(
                {
                    "status": "ok" if ready else "degraded",
                    "release_root_exists": ready,
                }
            ),
            status,
        )

    return app