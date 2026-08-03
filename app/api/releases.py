from flask import Blueprint, current_app, jsonify, request


releases_bp = Blueprint("api_releases", __name__)


def _release_service():
    return current_app.extensions["release_service"]


@releases_bp.route("/releases", methods=["GET"])
def list_releases():
    releases = _release_service().list_releases()
    return jsonify({"releases": releases})


@releases_bp.route("/releases/<release_id>/manifest", methods=["GET"])
def get_release_manifest(release_id):
    manifest = _release_service().get_manifest(release_id)
    return jsonify({"manifest": manifest})


@releases_bp.route("/releases/search", methods=["GET"])
def search_releases():
    payload = _release_service().search_releases(
        project=str(request.args.get("project", "")).strip() or None,
        target=str(request.args.get("target", "")).strip() or None,
        release_id=str(request.args.get("release_id", "")).strip() or None,
        created_from=str(request.args.get("created_from", "")).strip() or None,
        created_to=str(request.args.get("created_to", "")).strip() or None,
        page=request.args.get("page", 1),
        per_page=request.args.get("per_page", 25),
    )
    return jsonify(payload)


@releases_bp.route("/releases/<release_id>", methods=["DELETE"])
def delete_release(release_id):
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