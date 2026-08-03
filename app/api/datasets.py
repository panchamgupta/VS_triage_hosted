from pathlib import Path

from flask import Blueprint, current_app, jsonify


datasets_bp = Blueprint("api_datasets", __name__)


def _release_service():
    return current_app.extensions["release_service"]


@datasets_bp.route("/health", methods=["GET"])
def api_health():
    service = _release_service()
    release_root = Path(current_app.config["HOSTED_PORTAL_RELEASE_ROOT"])
    releases = service.list_releases(include_invalid=True)
    valid_count = sum(1 for release in releases if release.get("status") == "published")
    invalid_count = sum(1 for release in releases if release.get("status") != "published")
    return jsonify(
        {
            "status": "ok",
            "environment": current_app.config.get("HOSTED_PORTAL_ENV", "development"),
            "log_level": current_app.config.get("HOSTED_PORTAL_LOG_LEVEL", "INFO"),
            "release_root_configured": bool(str(release_root).strip()),
            "release_root_exists": release_root.exists() and release_root.is_dir(),
            "active_release": current_app.config.get("HOSTED_PORTAL_ACTIVE_RELEASE") or None,
            "available_release_count": valid_count,
            "invalid_release_count": invalid_count,
        }
    )


@datasets_bp.route("/datasets/<release_id>/summary", methods=["GET"])
def dataset_summary(release_id):
    summary = _release_service().get_release_summary(release_id)
    return jsonify(summary)