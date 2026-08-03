#!/usr/bin/env python3

import argparse
import json
import re
import shutil
from pathlib import Path


def extract_json_const(text, const_name):
    token = f"const {const_name}="
    start = text.find(token)
    if start < 0:
        raise ValueError(f"Could not find {const_name} in report HTML")
    payload = text[start + len(token):]
    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(payload)
    return value


def build_scaffold_payload(export_data, render_payload):
    central_cards = render_payload.get("centralCards") or []
    card_by_scaffold = {str(card.get("scaffold") or ""): card for card in central_cards}
    items = []
    for scaffold_name, export_entry in export_data.items():
        all_members = list(export_entry.get("all_members") or [])
        display_members = list(export_entry.get("display_members") or [])
        unique_keys = {
            str(member.get("canonical_smiles") or member.get("smiles") or member.get("mol_id") or "")
            for member in all_members
        }
        card = card_by_scaffold.get(scaffold_name, {})
        items.append(
            {
                "scaffold_id": scaffold_name,
                "scaffold_name": scaffold_name,
                "display_name": scaffold_name,
                "n_members": len(all_members),
                "n_display_members": len(display_members),
                "n_unique_members": len([key for key in unique_keys if key]),
                "top15": bool(card.get("isTop15", False)),
                "card_html": card.get("html", ""),
                "prop_ranges": card.get("propRanges") or {},
            }
        )
    items.sort(key=lambda row: (-row["n_members"], row["scaffold_name"]))
    return {"items": items, "count": len(items)}


def build_molecule_payload(export_data):
    items = []
    seen = set()
    for scaffold_name, export_entry in export_data.items():
        for member in export_entry.get("all_members") or []:
            key = (
                scaffold_name,
                str(member.get("mol_id") or ""),
                str(member.get("mol_index") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            payload = dict(member)
            payload["scaffold_name"] = scaffold_name
            payload["molecule_id"] = str(member.get("mol_id") or member.get("mol_index") or "")
            payload["pose_id"] = str(member.get("mol_index") or "")
            items.append(payload)
    items.sort(key=lambda row: (row.get("scaffold_name", ""), row.get("molecule_id", "")))
    return {"items": items, "count": len(items)}


def build_pose_payload(pose_map, pose_interactions):
    items = []
    for pose_id, sdf_block in pose_map.items():
        title = ""
        if isinstance(sdf_block, str) and sdf_block:
            title = sdf_block.splitlines()[0].strip()
        items.append(
            {
                "pose_id": str(pose_id),
                "title": title,
                "interaction_count": len(pose_interactions.get(str(pose_id), []) or []),
            }
        )
    items.sort(key=lambda row: int(row["pose_id"]) if str(row["pose_id"]).isdigit() else row["pose_id"])
    return {"items": items, "count": len(items)}


ASSET_VERSION = "20260802a"


def patch_report_html(text, report_max_width):
    replacements = {
        "report_assets/rdkit/RDKit_minimal.js": f"/static/vendor/rdkit/RDKit_minimal.js?v={ASSET_VERSION}",
        "report_assets/rdkit/RDKit_minimal.wasm": f"/static/vendor/rdkit/RDKit_minimal.wasm?v={ASSET_VERSION}",
        "https://3Dmol.org/build/3Dmol-min.js": f"/static/vendor/3dmol/3Dmol-min.js?v={ASSET_VERSION}",
        "https://cdn.plot.ly/plotly-2.26.0.min.js": f"/static/vendor/plotly/plotly-2.26.0.min.js?v={ASSET_VERSION}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    width_token = f".wrap {{ max-width: {int(report_max_width)}px;"
    text = text.replace(".wrap { max-width: 1400px;", width_token)

    override = (
        "<style id='hosted-width-override'>"
        "html,body{min-width:0;}"
        f".wrap{{max-width:{int(report_max_width)}px !important;width:calc(100% - 24px);}}"
        "</style>"
    )
    text = text.replace("</head>", override + "</head>")

    return "<!-- Hosted report payload: asset references patched for local delivery. -->\n" + text


def extract_title(text):
    match = re.search(r"<section class='hero'><h1>([^<]+)</h1><p class='small'>([^<]+)</p>", text)
    if not match:
        return "R-group Docking Insight Report", "Hosted example release built from the generated report"
    return match.group(1).strip(), match.group(2).strip()


def _extract_optional_json_const(text, const_name, fallback):
    try:
        return extract_json_const(text, const_name)
    except ValueError:
        return fallback


def main():
    parser = argparse.ArgumentParser(description="Create a hosted example release from the generated static report.")
    parser.add_argument("--report-html", default="VS_PPI_Leo_Bicyclic_headgroup_screen_06052026_report.html")
    parser.add_argument("--release-id", default="example_release")
    parser.add_argument("--release-root", default="releases")
    parser.add_argument("--report-max-width", type=int, default=2200)
    args = parser.parse_args()

    report_path = Path(args.report_html).resolve()
    release_root = Path(args.release_root).resolve()
    release_dir = release_root / args.release_id
    data_dir = release_dir / "data"
    poses_dir = release_dir / "poses"
    exports_dir = release_dir / "exports"
    static_payload_dir = release_dir / "static_payload"

    for path in (data_dir, poses_dir, exports_dir, static_payload_dir):
        path.mkdir(parents=True, exist_ok=True)

    html_text = report_path.read_text(encoding="utf-8", errors="replace")
    export_data = extract_json_const(html_text, "_EXPORT")
    render_payload = extract_json_const(html_text, "_REPORT_RENDER_PAYLOAD")
    pose_map = extract_json_const(html_text, "_POSE_SDF_BY_INDEX")
    try:
        pose_interactions = extract_json_const(html_text, "_POSE_INTERACTIONS_BY_INDEX")
    except ValueError:
        pose_interactions = {}

    scaffold_payload = build_scaffold_payload(export_data, render_payload)
    molecule_payload = build_molecule_payload(export_data)
    pose_payload = build_pose_payload(pose_map, pose_interactions)
    report_title, report_subtitle = extract_title(html_text)

    (data_dir / "scaffolds.json").write_text(json.dumps(scaffold_payload, indent=2), encoding="utf-8")
    (data_dir / "molecules.json").write_text(json.dumps(molecule_payload, indent=2), encoding="utf-8")
    (data_dir / "pose_index.json").write_text(json.dumps(pose_payload, indent=2), encoding="utf-8")
    (static_payload_dir / "report.html").write_text(
        patch_report_html(html_text, report_max_width=args.report_max_width),
        encoding="utf-8",
    )

    protein_payload = _extract_optional_json_const(html_text, "_PROTEIN_PDB", "")
    protein_sources = _extract_optional_json_const(html_text, "_PROTEIN_SOURCE_LIST", [])
    diagnostics = {
        "release_id": args.release_id,
        "report_html": str(report_path),
        "report_max_width": int(args.report_max_width),
        "counts": {
            "scaffolds": scaffold_payload["count"],
            "molecules": molecule_payload["count"],
            "poses": pose_payload["count"],
        },
        "viewer_payload_checks": {
            "has_pose_entries": pose_payload["count"] > 0,
            "has_protein_payload": bool(str(protein_payload or "").strip()),
            "protein_source_count": len(protein_sources) if isinstance(protein_sources, list) else 0,
            "uses_local_3dmol": "https://3Dmol.org/build/3Dmol-min.js" not in patch_report_html(html_text, report_max_width=args.report_max_width),
            "uses_local_plotly": "https://cdn.plot.ly/plotly-2.26.0.min.js" not in patch_report_html(html_text, report_max_width=args.report_max_width),
        },
        "known_limitations": [
            "Current local 3Dmol/Plotly/RDKit files are compatibility shims; full rendering requires real vendored upstream libraries.",
        ],
    }
    (release_dir / "build_diagnostics.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")

    manifest = {
        "release_id": args.release_id,
        "display_name": report_title,
        "created_at": "2026-08-02",
        "program": "PPI",
        "target": "STAT6",
        "description": report_subtitle,
        "files": {
            "scaffolds": "data/scaffolds.json",
            "molecules": "data/molecules.json",
            "pose_index": "data/pose_index.json",
            "static_report": "static_payload/report.html"
        },
        "counts": {
            "scaffolds": scaffold_payload["count"],
            "molecules": molecule_payload["count"],
            "poses": pose_payload["count"]
        },
        "features": {
            "structure_search": True,
            "motif_exclusion": True,
            "pose_viewer": True,
            "exports": True
        },
        "source": {
            "report_html": str(report_path.name),
            "build_script": "scripts/create_example_release_from_report.py"
        },
        "diagnostics": {
            "build_diagnostics": "build_diagnostics.json"
        },
        "frontend_migration": {
            "overview": "preserved_via_static_payload",
            "central_ideas": "preserved_via_static_payload",
            "deep_dive": "preserved_via_static_payload",
            "hosted_shell": "template_extracted"
        }
    }
    (release_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    source_copy = release_dir / "source_report.html"
    if source_copy.exists():
        source_copy.unlink()
    shutil.copy2(report_path, source_copy)

    print(f"Created example release at {release_dir}")
    print(f"Wrote diagnostics: {release_dir / 'build_diagnostics.json'}")


if __name__ == "__main__":
    main()