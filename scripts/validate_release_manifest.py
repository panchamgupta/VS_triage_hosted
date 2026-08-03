#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.manifest_service import ManifestValidationError, validate_manifest


def _resolve_manifest_input(raw_path):
    path = Path(raw_path).expanduser().resolve()
    if path.is_dir():
        return path / "manifest.json", path
    return path, path.parent


def main():
    parser = argparse.ArgumentParser(
        description="Validate a hosted docking portal release manifest."
    )
    parser.add_argument(
        "path",
        help="Path to a release directory or a manifest.json file",
    )
    args = parser.parse_args()

    manifest_path, release_dir = _resolve_manifest_input(args.path)
    if not manifest_path.exists():
        print(f"FAIL: manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        validate_manifest(manifest, release_dir=release_dir)
    except json.JSONDecodeError as exc:
        print(f"FAIL: invalid JSON in {manifest_path}: {exc}", file=sys.stderr)
        return 1
    except ManifestValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"PASS: valid manifest for release '{manifest['release_id']}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())