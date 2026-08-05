from flask import Blueprint, Response, abort, current_app, render_template, request, send_file, url_for


pages_bp = Blueprint("pages", __name__)


def _release_service():
    return current_app.extensions["release_service"]


def _job_service():
    return current_app.extensions["job_service"]


def _project_service():
    return current_app.extensions["project_service"]


def _operations_service():
    return current_app.extensions["operations_service"]


def _vote_bootstrap_context(release_id, surface):
    return {
        "release_id": release_id,
        "vote_surface": surface,
        "vote_poll_seconds": current_app.config.get("HOSTED_PORTAL_VOTE_POLL_SECONDS", 5),
    }


def _build_augmented_raw_report(release_id):
    service = _release_service()
    report_path = service.get_static_report_path(release_id)
    if report_path is None:
        abort(404)

    report_html = report_path.read_text(encoding="utf-8")
    head_injection = render_template(
        "_raw_report_voting_head.html",
        **_vote_bootstrap_context(release_id, surface="inline"),
    )
    body_injection = render_template(
        "_raw_report_voting_body.html",
        **_vote_bootstrap_context(release_id, surface="inline"),
    )

    if "</head>" in report_html:
        report_html = report_html.replace("</head>", head_injection + "</head>", 1)
    else:
        report_html = head_injection + report_html

    if "<body" in report_html and ">" in report_html.split("<body", 1)[1]:
        body_start = report_html.index("<body")
        body_open_end = report_html.index(">", body_start) + 1
        report_html = report_html[:body_open_end] + body_injection + report_html[body_open_end:]
    else:
        report_html = body_injection + report_html

    return Response(report_html, mimetype="text/html")


def _render_release_shell(release_id, report_mode):
    service = _release_service()
    try:
        manifest = service.get_manifest(release_id)
    except Exception:
        abort(404)
    summary = service.get_release_summary(release_id)
    raw_report_url = None
    if service.has_static_report(release_id):
        raw_report_url = url_for("pages.embedded_report_file", release_id=release_id)
    return render_template(
        "release.html" if report_mode == "overview" else "report_view.html",
        manifest=manifest,
        release_id=release_id,
        summary=summary,
        static_report_url=raw_report_url,
        releases=service.list_releases(),
        report_mode=report_mode,
    )


@pages_bp.route("/", methods=["GET"])
def index():
    service = _release_service()
    releases = service.list_releases()
    selected_release = service.get_default_release_id(releases)
    allow_release_delete = bool(current_app.config.get("HOSTED_PORTAL_ALLOW_RELEASE_DELETE", False))
    return render_template(
        "index.html",
        releases=releases,
        selected_release=selected_release,
        active_release=current_app.config.get("HOSTED_PORTAL_ACTIVE_RELEASE") or "",
        allow_release_delete=allow_release_delete,
        max_upload_mb=current_app.config.get("HOSTED_PORTAL_MAX_UPLOAD_MB", 512),
        default_n_workers=current_app.config.get("HOSTED_PORTAL_PIPELINE_DEFAULT_N_WORKERS", 8),
        max_n_workers=current_app.config.get("HOSTED_PORTAL_PIPELINE_MAX_N_WORKERS", 32),
        job_poll_seconds=current_app.config.get("HOSTED_PORTAL_JOB_POLL_SECONDS", 2),
    )


@pages_bp.route("/release/<release_id>", methods=["GET"])
@pages_bp.route("/dataset/<release_id>", methods=["GET"])
def release_view(release_id):
    return _render_release_shell(release_id, report_mode="overview")


@pages_bp.route("/release/<release_id>/report", methods=["GET"])
def static_report_view(release_id):
    if request.args.get("posePopup") or request.args.get("raw"):
        return embedded_report_file(release_id)

    return _render_release_shell(release_id, report_mode="report")


@pages_bp.route("/release/<release_id>/report/raw", methods=["GET"])
def raw_report_file(release_id):
    return _build_augmented_raw_report(release_id)


@pages_bp.route("/release/<release_id>/report/payload", methods=["GET"])
def embedded_report_file(release_id):
    service = _release_service()
    report_path = service.get_static_report_path(release_id)
    if report_path is None:
        abort(404)
    return send_file(report_path)


@pages_bp.route("/jobs", methods=["GET"])
def jobs_history_view():
    service = _job_service()
    status = str(request.args.get("status", "")).strip() or None
    project = str(request.args.get("project", "")).strip() or None
    target = str(request.args.get("target", "")).strip() or None
    date_from = str(request.args.get("date_from", "")).strip() or None
    date_to = str(request.args.get("date_to", "")).strip() or None
    page = request.args.get("page", 1)
    per_page = request.args.get("per_page", 20)

    history = service.list_jobs_history(
        status=status,
        project=project,
        target=target,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )
    return render_template("jobs.html", history=history)


@pages_bp.route("/job/<job_id>", methods=["GET"])
def job_detail_view(job_id):
    service = _job_service()
    job = service.get_job(job_id)
    if job is None:
        abort(404)
    log_payload = service.get_job_log(job_id, max_lines=500)
    return render_template("job_detail.html", job=job, log_payload=log_payload)


@pages_bp.route("/projects", methods=["GET"])
def projects_view():
    projects = _project_service().list_projects()
    return render_template("projects.html", projects=projects)


@pages_bp.route("/operations", methods=["GET"])
def operations_view():
    metrics = _operations_service().get_metrics()
    releases = _release_service().list_releases()
    return render_template("operations.html", metrics=metrics, releases=releases)