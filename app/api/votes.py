import csv
import io

from flask import Blueprint, Response, current_app, jsonify, request

from app.services.vote_service import VoteValidationError


votes_bp = Blueprint("api_votes", __name__)


def _vote_service():
    return current_app.extensions["vote_service"]


def _json_payload():
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return {}


def _comma_separated_list(raw_value):
    text = str(raw_value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _reaction_label(vote_type):
    mapping = {
        "LIKE": "Like",
        "PRIORITY": "High Priority",
        "REJECT": "Reject",
    }
    return mapping.get(str(vote_type or "").upper(), str(vote_type or ""))


def _csv_response(filename, fieldnames, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    payload = buf.getvalue()
    return Response(
        payload,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@votes_bp.route("/votes/scaffold", methods=["POST"])
def cast_scaffold_vote():
    payload = _json_payload()
    try:
        vote = _vote_service().cast_scaffold_vote(
            release_id=payload.get("release_id"),
            scaffold_id=payload.get("scaffold_id"),
            username=payload.get("username"),
            vote_type=payload.get("vote_type"),
        )
        summary = _vote_service().get_scaffold_summary(
            release_id=vote["release_id"],
            scaffold_id=vote["scaffold_id"],
            username=vote["username"],
        )
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"vote": vote, "summary": summary}), 200


@votes_bp.route("/votes/molecule", methods=["POST"])
def cast_molecule_vote():
    payload = _json_payload()
    try:
        vote = _vote_service().cast_molecule_vote(
            release_id=payload.get("release_id"),
            molecule_id=payload.get("molecule_id"),
            username=payload.get("username"),
            vote_type=payload.get("vote_type"),
        )
        summary = _vote_service().get_molecule_summary(
            release_id=vote["release_id"],
            molecule_id=vote["molecule_id"],
            username=vote["username"],
        )
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"vote": vote, "summary": summary}), 200


@votes_bp.route("/votes/scaffold/<scaffold_id>", methods=["GET"])
def get_scaffold_votes(scaffold_id):
    release_id = request.args.get("release_id", "")
    username = request.args.get("username", "")
    try:
        summary = _vote_service().get_scaffold_summary(
            release_id=release_id,
            scaffold_id=scaffold_id,
            username=username or None,
        )
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(summary)


@votes_bp.route("/votes/molecule/<molecule_id>", methods=["GET"])
def get_molecule_votes(molecule_id):
    release_id = request.args.get("release_id", "")
    username = request.args.get("username", "")
    try:
        summary = _vote_service().get_molecule_summary(
            release_id=release_id,
            molecule_id=molecule_id,
            username=username or None,
        )
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(summary)


@votes_bp.route("/votes/release/<release_id>", methods=["GET"])
def get_release_votes(release_id):
    username = request.args.get("username", "")
    scaffold_ids = _comma_separated_list(request.args.get("scaffold_ids", ""))
    molecule_ids = _comma_separated_list(request.args.get("molecule_ids", ""))
    try:
        payload = _vote_service().get_release_summary(
            release_id=release_id,
            username=username or None,
            scaffold_ids=scaffold_ids,
            molecule_ids=molecule_ids,
        )
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload)


@votes_bp.route("/votes/users/<username>", methods=["GET"])
def get_user_votes(username):
    release_id = str(request.args.get("release_id", "")).strip() or None
    limit = request.args.get("limit", 200)
    try:
        payload = _vote_service().get_user_votes(
            username=username,
            release_id=release_id,
            limit=limit,
        )
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload)


@votes_bp.route("/votes/release/<release_id>/csv", methods=["GET"])
def get_release_votes_csv(release_id):
    try:
        rows = _vote_service().list_release_votes(release_id)
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    fieldnames = [
        "release_id",
        "object_type",
        "object_id",
        "reaction",
        "username",
        "created_at",
        "updated_at",
    ]
    csv_rows = [
        {
            "release_id": row["release_id"],
            "object_type": row["object_type"],
            "object_id": row["object_id"],
            "reaction": _reaction_label(row["vote_type"]),
            "username": row["username"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
    return _csv_response(f"{release_id}_votes.csv", fieldnames, csv_rows)


@votes_bp.route("/votes/release/<release_id>/summary.csv", methods=["GET"])
def get_release_votes_summary_csv(release_id):
    threshold_n = request.args.get("consensus_threshold_n", 3)
    try:
        consensus_payload = _vote_service().get_release_consensus(release_id, threshold_n=threshold_n)
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    fieldnames = [
        "release_id",
        "object_type",
        "object_id",
        "like_count",
        "high_priority_count",
        "reject_count",
        "positive_unique_user_count",
        "reject_unique_user_count",
        "consensus_positive",
        "consensus_threshold_n",
    ]

    rows = []
    for _, row in sorted((consensus_payload.get("scaffolds") or {}).items()):
        rows.append(
            {
                "release_id": release_id,
                "object_type": "scaffold",
                "object_id": row.get("object_id", ""),
                "like_count": row.get("like_count", 0),
                "high_priority_count": row.get("high_priority_count", 0),
                "reject_count": row.get("reject_count", 0),
                "positive_unique_user_count": row.get("positive_unique_user_count", 0),
                "reject_unique_user_count": row.get("reject_unique_user_count", 0),
                "consensus_positive": str(bool(row.get("consensus_positive", False))).lower(),
                "consensus_threshold_n": row.get("consensus_threshold_n", 3),
            }
        )

    for _, row in sorted((consensus_payload.get("molecules") or {}).items()):
        rows.append(
            {
                "release_id": release_id,
                "object_type": "molecule",
                "object_id": row.get("object_id", ""),
                "like_count": row.get("like_count", 0),
                "high_priority_count": row.get("high_priority_count", 0),
                "reject_count": row.get("reject_count", 0),
                "positive_unique_user_count": row.get("positive_unique_user_count", 0),
                "reject_unique_user_count": row.get("reject_unique_user_count", 0),
                "consensus_positive": str(bool(row.get("consensus_positive", False))).lower(),
                "consensus_threshold_n": row.get("consensus_threshold_n", 3),
            }
        )

    return _csv_response(f"{release_id}_vote_summary.csv", fieldnames, rows)


@votes_bp.route("/votes/release/<release_id>/user/<username>.csv", methods=["GET"])
def get_user_votes_csv(release_id, username):
    try:
        payload = _vote_service().get_user_votes(username=username, release_id=release_id, limit=50000)
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    fieldnames = [
        "release_id",
        "username",
        "object_type",
        "object_id",
        "reaction",
        "created_at",
        "updated_at",
    ]
    rows = []
    for row in payload.get("scaffold_votes", []):
        rows.append(
            {
                "release_id": row.get("release_id", ""),
                "username": payload.get("username", ""),
                "object_type": "scaffold",
                "object_id": row.get("scaffold_id", ""),
                "reaction": _reaction_label(row.get("vote_type")),
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
            }
        )
    for row in payload.get("molecule_votes", []):
        rows.append(
            {
                "release_id": row.get("release_id", ""),
                "username": payload.get("username", ""),
                "object_type": "molecule",
                "object_id": row.get("molecule_id", ""),
                "reaction": _reaction_label(row.get("vote_type")),
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
            }
        )

    return _csv_response(f"{release_id}_{username}_votes.csv", fieldnames, rows)


@votes_bp.route("/votes/release/<release_id>/consensus", methods=["GET"])
def get_release_consensus(release_id):
    threshold_n = request.args.get("consensus_threshold_n", 3)
    scaffold_ids = _comma_separated_list(request.args.get("scaffold_ids", ""))
    molecule_ids = _comma_separated_list(request.args.get("molecule_ids", ""))
    try:
        payload = _vote_service().get_release_consensus(
            release_id,
            threshold_n=threshold_n,
            scaffold_ids=scaffold_ids,
            molecule_ids=molecule_ids,
        )
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload)


@votes_bp.route("/votes/release/<release_id>/consensus.csv", methods=["GET"])
def get_release_consensus_csv(release_id):
    threshold_n = request.args.get("consensus_threshold_n", 3)
    try:
        payload = _vote_service().get_release_consensus(release_id, threshold_n=threshold_n)
    except VoteValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    fieldnames = [
        "release_id",
        "object_type",
        "object_id",
        "consensus_positive",
        "consensus_threshold_n",
        "high_priority_count",
        "like_count",
        "reject_count",
        "positive_unique_user_count",
        "reject_unique_user_count",
    ]

    rows = []
    for _, row in sorted((payload.get("scaffolds") or {}).items()):
        rows.append(
            {
                "release_id": release_id,
                "object_type": "scaffold",
                "object_id": row.get("object_id", ""),
                "consensus_positive": str(bool(row.get("consensus_positive", False))).lower(),
                "consensus_threshold_n": row.get("consensus_threshold_n", 3),
                "high_priority_count": row.get("high_priority_count", 0),
                "like_count": row.get("like_count", 0),
                "reject_count": row.get("reject_count", 0),
                "positive_unique_user_count": row.get("positive_unique_user_count", 0),
                "reject_unique_user_count": row.get("reject_unique_user_count", 0),
            }
        )
    for _, row in sorted((payload.get("molecules") or {}).items()):
        rows.append(
            {
                "release_id": release_id,
                "object_type": "molecule",
                "object_id": row.get("object_id", ""),
                "consensus_positive": str(bool(row.get("consensus_positive", False))).lower(),
                "consensus_threshold_n": row.get("consensus_threshold_n", 3),
                "high_priority_count": row.get("high_priority_count", 0),
                "like_count": row.get("like_count", 0),
                "reject_count": row.get("reject_count", 0),
                "positive_unique_user_count": row.get("positive_unique_user_count", 0),
                "reject_unique_user_count": row.get("reject_unique_user_count", 0),
            }
        )

    return _csv_response(f"{release_id}_consensus.csv", fieldnames, rows)
