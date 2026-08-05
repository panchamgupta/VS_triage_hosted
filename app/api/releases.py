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


@releases_bp.route("/releases/batch-delete", methods=["POST"])
def batch_delete_releases():
    body = request.get_json(silent=True) or {}
    release_ids = body.get("release_ids")
    if not isinstance(release_ids, list):
        return jsonify({"error": "release_ids must be a list."}), 400

    normalized = []
    seen = set()
    for value in release_ids:
        release_id = str(value or "").strip()
        if not release_id or release_id in seen:
            continue
        seen.add(release_id)
        normalized.append(release_id)

    if not normalized:
        return jsonify({"error": "No releases selected."}), 400

    service = _release_service()
    allow_delete = bool(current_app.config.get("HOSTED_PORTAL_ALLOW_RELEASE_DELETE", False))
    deleted = []

    for release_id in normalized:
        try:
            service.validate_release_delete(
                release_id,
                allow_delete=allow_delete,
                confirm_release_id=release_id,
            )
        except PermissionError as exc:
            return jsonify({"error": str(exc)}), 403
        except FileNotFoundError:
            return jsonify({"error": f"Release not found: {release_id}."}), 404

    for release_id in normalized:
        payload = service.delete_release(
            release_id,
            allow_delete=allow_delete,
            confirm_release_id=release_id,
        )
        deleted.append(payload)

    return jsonify(
        {
            "requested": len(normalized),
            "deleted": deleted,
            "failed": [],
        }
    )