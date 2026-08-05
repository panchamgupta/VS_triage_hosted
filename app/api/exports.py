from flask import Blueprint, Response, current_app, jsonify, request


exports_bp = Blueprint("api_exports", __name__)


def _release_service():
    return current_app.extensions["release_service"]


def _vote_service():
    return current_app.extensions["vote_service"]


def _request_payload():
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return {}


def _request_value(name, default=None):
    payload = _request_payload()
    if name in payload:
        return payload.get(name)
    return request.args.get(name, default)


def _request_list(name):
    payload = _request_payload()
    value = payload.get(name)
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(request.args.get(name, "") or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _require_release_id(value):
    release_id = str(value or "").strip()
    if not release_id:
        raise ValueError("release_id is required")
    return release_id


def _normalize_reaction(value):
    reaction = str(value or "").strip().upper()
    if reaction not in {"LIKE", "PRIORITY", "REJECT"}:
        raise ValueError("reaction_type must be LIKE, PRIORITY, or REJECT")
    return reaction


def _normalize_mode(value):
    mode = str(value or "top10").strip().lower()
    if mode not in {"top10", "all_members", "selected_members"}:
        raise ValueError("mode must be top10, all_members, or selected_members")
    return mode


def _normalize_threshold(value):
    try:
        threshold = int(value)
    except Exception:
        threshold = 3
    return max(1, min(100, threshold))


def _split_sdf_entries(text):
    src = str(text or "").replace("\r\n", "\n")
    if not src.strip():
        return []
    parts = src.split("$$$$")
    entries = []
    for part in parts:
        chunk = part.strip("\n\r\t ")
        if not chunk:
            continue
        entries.append(chunk + "\n$$$$\n")
    return entries


def _extract_release_export_data(release_id):
    data = _release_service().get_embedded_export_payload(release_id)
    if not isinstance(data, dict) or not data:
        raise ValueError("Release does not contain embedded scaffold export payload.")
    return data


def _build_molecule_block_map(export_data):
    mol_map = {}
    for scaffold_id, payload in export_data.items():
        members = payload.get("all_members") or []
        blocks = _split_sdf_entries(payload.get("all_members_sdf_text") or payload.get("sdf_text") or "")
        limit = min(len(members), len(blocks))
        for idx in range(limit):
            member = members[idx] or {}
            mol_id = str(member.get("mol_id") or "").strip()
            if not mol_id:
                continue
            mol_map[mol_id] = {
                "block": blocks[idx],
                "scaffold_id": scaffold_id,
                "member": member,
            }
    return mol_map


def _reaction_scaffold_ids(release_id, reaction_type):
    summary = _vote_service().get_release_summary(release_id, username=None)
    scaffold_votes = summary.get("scaffold_votes") or {}
    out = []
    for scaffold_id, payload in scaffold_votes.items():
        counts = payload.get("counts") or {}
        if int(counts.get(reaction_type) or 0) > 0:
            out.append(scaffold_id)
    return sorted(out)


def _reaction_molecule_ids(release_id, reaction_type):
    summary = _vote_service().get_release_summary(release_id, username=None)
    molecule_votes = summary.get("molecule_votes") or {}
    out = []
    for molecule_id, payload in molecule_votes.items():
        counts = payload.get("counts") or {}
        if int(counts.get(reaction_type) or 0) > 0:
            out.append(molecule_id)
    return sorted(out)


def _consensus_ids(release_id, threshold_n):
    payload = _vote_service().get_release_consensus(release_id, threshold_n=threshold_n)
    return {
        "scaffolds": payload.get("consensus_scaffold_ids") or [],
        "molecules": payload.get("consensus_molecule_ids") or [],
    }


def _scaffold_sdf_from_export(export_data, scaffold_ids, mode):
    blocks = []
    for scaffold_id in scaffold_ids:
        payload = export_data.get(scaffold_id) or {}
        if mode == "all_members":
            text = payload.get("all_members_sdf_text") or ""
            blocks.extend(_split_sdf_entries(text))
        else:
            # top10 and selected_members use canonical display set
            text = payload.get("sdf_text") or ""
            blocks.extend(_split_sdf_entries(text))
    return "".join(blocks)


def _molecule_sdf_from_export(export_data, molecule_ids):
    block_map = _build_molecule_block_map(export_data)
    blocks = []
    for molecule_id in molecule_ids:
        payload = block_map.get(molecule_id)
        if payload:
            blocks.append(payload["block"])
    return "".join(blocks)


def _sdf_response(filename, sdf_text):
    if not str(sdf_text or "").strip():
        return jsonify({"error": "No matching molecules found for export."}), 404
    return Response(
        sdf_text,
        mimetype="chemical/x-mdl-sdfile",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _resolve_scaffold_ids_for_request(release_id, object_ids, reaction_type, threshold_n, consensus=False):
    if object_ids:
        return sorted(set(object_ids))
    if consensus:
        return _consensus_ids(release_id, threshold_n).get("scaffolds", [])
    return _reaction_scaffold_ids(release_id, reaction_type)


def _resolve_molecule_ids_for_request(release_id, object_ids, reaction_type, threshold_n, consensus=False):
    if object_ids:
        return sorted(set(object_ids))
    if consensus:
        return _consensus_ids(release_id, threshold_n).get("molecules", [])
    return _reaction_molecule_ids(release_id, reaction_type)


@exports_bp.route("/exports/reaction/scaffolds", methods=["GET", "POST"])
def export_reaction_scaffolds():
    try:
        release_id = _require_release_id(_request_value("release_id", ""))
        reaction_type = _normalize_reaction(_request_value("reaction_type", "LIKE"))
        mode = _normalize_mode(_request_value("mode", "top10"))
        threshold_n = _normalize_threshold(_request_value("consensus_threshold_n", 3))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    scaffold_ids = _resolve_scaffold_ids_for_request(
        release_id,
        _request_list("object_ids"),
        reaction_type,
        threshold_n,
        consensus=False,
    )
    if not scaffold_ids:
        return jsonify({"error": f"No {reaction_type.title()} scaffolds found."}), 404

    try:
        export_data = _extract_release_export_data(release_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    sdf_text = _scaffold_sdf_from_export(export_data, scaffold_ids, mode)
    return _sdf_response(f"{release_id}_{reaction_type.lower()}_scaffolds_{mode}.sdf", sdf_text)


@exports_bp.route("/exports/reaction/molecules", methods=["GET", "POST"])
def export_reaction_molecules():
    try:
        release_id = _require_release_id(_request_value("release_id", ""))
        reaction_type = _normalize_reaction(_request_value("reaction_type", "LIKE"))
        threshold_n = _normalize_threshold(_request_value("consensus_threshold_n", 3))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    molecule_ids = _resolve_molecule_ids_for_request(
        release_id,
        _request_list("object_ids"),
        reaction_type,
        threshold_n,
        consensus=False,
    )
    if not molecule_ids:
        return jsonify({"error": f"No {reaction_type.title()} molecules found."}), 404

    try:
        export_data = _extract_release_export_data(release_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    sdf_text = _molecule_sdf_from_export(export_data, molecule_ids)
    return _sdf_response(f"{release_id}_{reaction_type.lower()}_molecules.sdf", sdf_text)


@exports_bp.route("/exports/consensus/scaffolds", methods=["GET", "POST"])
def export_consensus_scaffolds():
    try:
        release_id = _require_release_id(_request_value("release_id", ""))
        mode = _normalize_mode(_request_value("mode", "top10"))
        threshold_n = _normalize_threshold(_request_value("consensus_threshold_n", 3))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    scaffold_ids = _resolve_scaffold_ids_for_request(
        release_id,
        _request_list("object_ids"),
        reaction_type="LIKE",
        threshold_n=threshold_n,
        consensus=True,
    )
    if not scaffold_ids:
        return jsonify({"error": f"No consensus scaffolds found for n = {threshold_n}."}), 404

    try:
        export_data = _extract_release_export_data(release_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    sdf_text = _scaffold_sdf_from_export(export_data, scaffold_ids, mode)
    return _sdf_response(f"{release_id}_consensus_scaffolds_n{threshold_n}_{mode}.sdf", sdf_text)


@exports_bp.route("/exports/consensus/molecules", methods=["GET", "POST"])
def export_consensus_molecules():
    try:
        release_id = _require_release_id(_request_value("release_id", ""))
        threshold_n = _normalize_threshold(_request_value("consensus_threshold_n", 3))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    molecule_ids = _resolve_molecule_ids_for_request(
        release_id,
        _request_list("object_ids"),
        reaction_type="LIKE",
        threshold_n=threshold_n,
        consensus=True,
    )
    if not molecule_ids:
        return jsonify({"error": f"No consensus molecules found for n = {threshold_n}."}), 404

    try:
        export_data = _extract_release_export_data(release_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    sdf_text = _molecule_sdf_from_export(export_data, molecule_ids)
    return _sdf_response(f"{release_id}_consensus_molecules_n{threshold_n}.sdf", sdf_text)
