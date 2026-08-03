#!/usr/bin/env python3

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli_config import prefixed_output_name


def _sanitize_release_token(text):
    value = str(text or "").strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe or "hosted_release"


def _build_process_command(args, passthrough_args):
    command = [
        args.python_executable,
        str(REPO_ROOT / "process_docking_IF_show_docking.py"),
        "--input",
        str(args.input),
        "--interaction-csv",
        str(args.interaction_csv),
        "--interaction-id-col",
        args.interaction_id_col,
        "--interaction-count-col",
        args.interaction_count_col,
        "--outdir",
        str(args.report_outdir),
        "--file-prefix",
        args.file_prefix,
        "--top-per-scaffold",
        str(args.top_per_scaffold),
        "--max-scaffolds-in-report",
        str(args.max_scaffolds_in_report),
        "--n-workers",
        str(args.n_workers),
    ]

    optional_pairs = [
        ("--protein-pdb", args.protein_pdb),
        ("--ref-ligand-sdf", args.ref_ligand_sdf),
        ("--exclude-smiles-file", args.exclude_smiles_file),
        ("--id-prop", args.id_prop),
        ("--cluster-prop", args.cluster_prop),
    ]
    for flag, value in optional_pairs:
        if value:
            command.extend([flag, str(value)])

    optional_numeric = [
        ("--max-molecular-weight", args.max_molecular_weight),
        ("--max-rotatable-bonds", args.max_rotatable_bonds),
        ("--max-hbond-donors", args.max_hbond_donors),
        ("--max-hbond-acceptors", args.max_hbond_acceptors),
    ]
    for flag, value in optional_numeric:
        if value is not None:
            command.extend([flag, str(value)])

    if args.generate_all_mol_images:
        command.append("--generate-all-mol-images")
    if args.auto_detect_score:
        command.append("--auto-detect-score")

    command.extend(passthrough_args)
    return command


def _run(command, *, cwd):
    print("RUN:", " ".join(shlex.quote(str(token)) for token in command))
    subprocess.run(command, cwd=str(cwd), check=True)


def _run_with_env(command, *, cwd, env):
    print("RUN:", " ".join(shlex.quote(str(token)) for token in command))
    subprocess.run(command, cwd=str(cwd), env=env, check=True)


def _portal_base_url(args):
    configured = os.getenv("HOSTED_PORTAL_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    return f"http://{args.serve_host}:{args.serve_port}"


def _release_url(base_url, release_id):
    return urljoin(base_url.rstrip("/") + "/", f"release/{release_id}")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Generate a docking report from a new SDF and interaction CSV, "
            "package it as a hosted release, and validate the release manifest."
        )
    )
    parser.add_argument("--input", required=True, help="Input docking SDF file")
    parser.add_argument("--interaction-csv", required=True, help="Interaction count or IF CSV file")
    parser.add_argument("--release-id", required=True, help="Hosted release ID to create")
    parser.add_argument(
        "--release-root",
        default=str(REPO_ROOT / "releases"),
        help="Root directory where hosted releases are written",
    )
    parser.add_argument(
        "--report-outdir",
        default=None,
        help="Directory for the generated static report artifacts before packaging",
    )
    parser.add_argument(
        "--file-prefix",
        default=None,
        help="Prefix for generated report filenames. Defaults to a sanitized release ID.",
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python interpreter used to run the pipeline and helper scripts",
    )
    parser.add_argument("--interaction-id-col", default="Title")
    parser.add_argument("--interaction-count-col", default="interaction_count")
    parser.add_argument("--protein-pdb", default=None)
    parser.add_argument("--ref-ligand-sdf", default=None)
    parser.add_argument("--exclude-smiles-file", default=None)
    parser.add_argument("--id-prop", default=None)
    parser.add_argument("--cluster-prop", default=None)
    parser.add_argument("--max-molecular-weight", type=float, default=None)
    parser.add_argument("--max-rotatable-bonds", type=float, default=None)
    parser.add_argument("--max-hbond-donors", type=float, default=None)
    parser.add_argument("--max-hbond-acceptors", type=float, default=None)
    parser.add_argument("--top-per-scaffold", type=int, default=10)
    parser.add_argument("--max-scaffolds-in-report", type=int, default=500)
    parser.add_argument("--n-workers", type=int, default=8)
    parser.add_argument("--generate-all-mol-images", action="store_true")
    parser.add_argument("--auto-detect-score", action="store_true")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="After build and validation, start the hosted Flask app.",
    )
    parser.add_argument(
        "--serve-host",
        default=os.getenv("HOSTED_PORTAL_HOST", "127.0.0.1"),
        help="Host for Flask when --serve is enabled.",
    )
    parser.add_argument(
        "--serve-port",
        type=int,
        default=int(os.getenv("HOSTED_PORTAL_PORT", "5005")),
        help="Port for Flask when --serve is enabled.",
    )

    args, passthrough_args = parser.parse_known_args(argv)
    args.release_id = _sanitize_release_token(args.release_id)
    args.file_prefix = args.file_prefix or args.release_id
    if args.report_outdir is None:
        args.report_outdir = str(REPO_ROOT / "hosted_builds" / args.release_id)

    args.input = Path(args.input).expanduser().resolve()
    args.interaction_csv = Path(args.interaction_csv).expanduser().resolve()
    args.release_root = Path(args.release_root).expanduser().resolve()
    args.report_outdir = Path(args.report_outdir).expanduser().resolve()
    if args.protein_pdb:
        args.protein_pdb = Path(args.protein_pdb).expanduser().resolve()
    if args.ref_ligand_sdf:
        args.ref_ligand_sdf = Path(args.ref_ligand_sdf).expanduser().resolve()
    if args.exclude_smiles_file:
        args.exclude_smiles_file = Path(args.exclude_smiles_file).expanduser().resolve()

    return args, passthrough_args


def main(argv=None):
    args, passthrough_args = _parse_args(argv)

    args.release_root.mkdir(parents=True, exist_ok=True)
    args.report_outdir.mkdir(parents=True, exist_ok=True)

    report_filename = prefixed_output_name(args.file_prefix, "report.html")
    report_html_path = args.report_outdir / report_filename

    process_command = _build_process_command(args, passthrough_args)
    create_release_command = [
        args.python_executable,
        str(REPO_ROOT / "scripts" / "create_example_release_from_report.py"),
        "--report-html",
        str(report_html_path),
        "--release-id",
        args.release_id,
        "--release-root",
        str(args.release_root),
    ]
    validate_command = [
        args.python_executable,
        str(REPO_ROOT / "scripts" / "validate_release_manifest.py"),
        str(args.release_root / args.release_id),
    ]

    _run(process_command, cwd=REPO_ROOT)

    if not report_html_path.exists():
        raise FileNotFoundError(
            f"Expected generated report was not found: {report_html_path}"
        )

    _run(create_release_command, cwd=REPO_ROOT)
    _run(validate_command, cwd=REPO_ROOT)

    print()
    print("Hosted release build complete.")
    print(f"Release ID: {args.release_id}")
    print(f"Release directory: {args.release_root / args.release_id}")
    print(f"Generated report: {report_html_path}")
    print()
    print("To serve the hosted portal locally:")
    print("  export HOSTED_PORTAL_RELEASE_ROOT=\"$PWD/releases\"")
    print("  export HOSTED_PORTAL_BASE_URL=http://127.0.0.1:5005")
    print("  FLASK_APP=wsgi:app python -m flask run --host 127.0.0.1 --port 5005")
    print()
    base_url = _portal_base_url(args)
    print(f"Hosted release URL: {_release_url(base_url, args.release_id)}")

    if args.serve:
        print()
        print("Starting hosted Flask app because --serve was requested.")
        print("Press Ctrl+C to stop the server.")
        flask_command = [
            args.python_executable,
            "-m",
            "flask",
            "run",
            "--host",
            args.serve_host,
            "--port",
            str(args.serve_port),
        ]
        flask_env = os.environ.copy()
        flask_env["FLASK_APP"] = "wsgi:app"
        flask_env["HOSTED_PORTAL_RELEASE_ROOT"] = str(args.release_root)
        flask_env["HOSTED_PORTAL_HOST"] = args.serve_host
        flask_env["HOSTED_PORTAL_PORT"] = str(args.serve_port)
        flask_env.setdefault("HOSTED_PORTAL_BASE_URL", f"http://{args.serve_host}:{args.serve_port}")
        _run_with_env(flask_command, cwd=REPO_ROOT, env=flask_env)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())