from flask import Blueprint, current_app, jsonify


molecules_bp = Blueprint("api_molecules", __name__)


def _release_service():
    return current_app.extensions["release_service"]


@molecules_bp.route("/releases/<release_id>/molecules", methods=["GET"])
@molecules_bp.route("/datasets/<release_id>/molecules", methods=["GET"])
def list_molecules(release_id):
    payload = _release_service().get_artifact_payload(release_id, "molecules")
    return jsonify(payload)