from flask import Blueprint, current_app, jsonify


operations_bp = Blueprint("api_operations", __name__)


def _operations_service():
    return current_app.extensions["operations_service"]


@operations_bp.route("/operations/metrics", methods=["GET"])
def get_operations_metrics():
    metrics = _operations_service().get_metrics()
    return jsonify(metrics)
