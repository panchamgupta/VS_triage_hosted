from flask import Blueprint, current_app, jsonify, request

from app.services.job_service import JobValidationError


jobs_bp = Blueprint("api_jobs", __name__)


def _job_service():
    return current_app.extensions["job_service"]


@jobs_bp.route("/jobs", methods=["POST"])
def create_job():
    service = _job_service()
    try:
        job = service.create_job(request.form, request.files)
    except JobValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Failed to create upload job")
        return jsonify({"error": "Unable to submit job at this time."}), 500
    return jsonify({"job": job}), 202


@jobs_bp.route("/jobs", methods=["GET"])
def list_jobs():
    jobs = _job_service().list_jobs()
    return jsonify({"jobs": jobs})


@jobs_bp.route("/jobs/history", methods=["GET"])
def list_jobs_history():
    service = _job_service()
    payload = service.list_jobs_history(
        status=str(request.args.get("status", "")).strip() or None,
        project=str(request.args.get("project", "")).strip() or None,
        target=str(request.args.get("target", "")).strip() or None,
        date_from=str(request.args.get("date_from", "")).strip() or None,
        date_to=str(request.args.get("date_to", "")).strip() or None,
        page=request.args.get("page", 1),
        per_page=request.args.get("per_page", 25),
    )
    return jsonify(payload)


@jobs_bp.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    job = _job_service().get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found."}), 404
    return jsonify({"job": job})


@jobs_bp.route("/jobs/<job_id>/log", methods=["GET"])
def get_job_log(job_id):
    max_lines = request.args.get("max_lines", 200)
    payload = _job_service().get_job_log(job_id, max_lines=max_lines)
    if payload is None:
        return jsonify({"error": "Job not found."}), 404
    return jsonify(payload)


@jobs_bp.route("/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    job = _job_service().cancel_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found."}), 404
    return jsonify({"job": job})
