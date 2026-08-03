from flask import Blueprint, current_app, jsonify


poses_bp = Blueprint("api_poses", __name__)


def _release_service():
    return current_app.extensions["release_service"]


@poses_bp.route("/releases/<release_id>/pose-index", methods=["GET"])
@poses_bp.route("/datasets/<release_id>/pose-index", methods=["GET"])
def pose_index(release_id):
    payload = _release_service().get_artifact_payload(release_id, "pose_index")
    return jsonify(payload)