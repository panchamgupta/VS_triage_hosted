from flask import Blueprint, current_app, jsonify


scaffolds_bp = Blueprint("api_scaffolds", __name__)


def _release_service():
    return current_app.extensions["release_service"]


@scaffolds_bp.route("/releases/<release_id>/scaffolds", methods=["GET"])
@scaffolds_bp.route("/datasets/<release_id>/scaffolds", methods=["GET"])
def list_scaffolds(release_id):
    payload = _release_service().get_artifact_payload(release_id, "scaffolds")
    return jsonify(payload)