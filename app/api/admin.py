from flask import Blueprint, current_app, jsonify, request


admin_bp = Blueprint("api_admin", __name__)


def _release_service():
    return current_app.extensions["release_service"]


def _retention_service():
    return current_app.extensions["retention_service"]


def _admin_authorized():
    expected = str(current_app.config.get("HOSTED_PORTAL_ADMIN_TOKEN") or "").strip()
    if not expected:
        return True
    supplied = str(request.headers.get("X-Admin-Token") or "").strip()
    return supplied == expected


@admin_bp.route("/admin/cleanup", methods=["POST"])
def run_cleanup():
    if not _admin_authorized():
        return jsonify({"error": "Unauthorized."}), 401
    if not current_app.config.get("HOSTED_PORTAL_ADMIN_CLEANUP_ENABLED", False):
        return jsonify({"error": "Cleanup is disabled by configuration."}), 403

    body = request.get_json(silent=True) or {}
    dry_run = bool(body.get("dry_run", True))
    payload = _retention_service().execute_cleanup(dry_run=dry_run)
    return jsonify(payload)


@admin_bp.route("/admin/releases/<release_id>", methods=["DELETE"])
def delete_release(release_id):
    if not _admin_authorized():
        return jsonify({"error": "Unauthorized."}), 401

    body = request.get_json(silent=True) or {}
    confirm_release_id = str(body.get("confirm_release_id") or "")
    try:
        payload = _release_service().delete_release(
            release_id,
            allow_delete=bool(current_app.config.get("HOSTED_PORTAL_ALLOW_RELEASE_DELETE", False)),
            confirm_release_id=confirm_release_id,
        )
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except FileNotFoundError:
        return jsonify({"error": "Release not found."}), 404

    return jsonify(payload)
