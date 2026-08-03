from flask import Blueprint, current_app, jsonify


projects_bp = Blueprint("api_projects", __name__)


def _project_service():
    return current_app.extensions["project_service"]


@projects_bp.route("/projects", methods=["GET"])
def list_projects():
    projects = _project_service().list_projects()
    return jsonify({"projects": projects})


@projects_bp.route("/projects/<path:project_name>", methods=["GET"])
def get_project(project_name):
    payload = _project_service().get_project_detail(project_name)
    return jsonify(payload)
