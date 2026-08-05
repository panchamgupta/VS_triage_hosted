from pathlib import Path


class ManifestValidationError(ValueError):
    pass


REQUIRED_MANIFEST_FIELDS = (
    "release_id",
    "display_name",
    "created_at",
    "program",
    "description",
    "files",
)

# Fields that must be present but may be empty strings.
OPTIONAL_STRING_FIELDS = (
    "target",
)

REQUIRED_FILE_KEYS = (
    "scaffolds",
    "molecules",
    "pose_index",
)


def validate_manifest(manifest, release_dir=None):
    if not isinstance(manifest, dict):
        raise ManifestValidationError("Manifest content must be a JSON object.")

    missing_fields = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    missing_optional = [field for field in OPTIONAL_STRING_FIELDS if field not in manifest]
    if missing_fields or missing_optional:
        all_missing = sorted(set(missing_fields) | set(missing_optional))
        raise ManifestValidationError(
            "Manifest is missing required fields: " + ", ".join(all_missing)
        )

    if not isinstance(manifest.get("files"), dict):
        raise ManifestValidationError("Manifest field 'files' must be an object.")

    missing_file_keys = [key for key in REQUIRED_FILE_KEYS if key not in manifest["files"]]
    if missing_file_keys:
        raise ManifestValidationError(
            "Manifest 'files' is missing required keys: " + ", ".join(sorted(missing_file_keys))
        )

    release_id = str(manifest.get("release_id", "")).strip()
    if not release_id:
        raise ManifestValidationError("Manifest field 'release_id' must be a non-empty string.")

    for field in REQUIRED_MANIFEST_FIELDS:
        if field == "files":
            continue
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ManifestValidationError(
                f"Manifest field '{field}' must be a non-empty string."
            )

    if release_dir is not None:
        release_dir = Path(release_dir)
        for logical_name, relative_path in manifest["files"].items():
            if not isinstance(relative_path, str) or not relative_path.strip():
                raise ManifestValidationError(
                    f"Manifest file reference '{logical_name}' must be a non-empty string."
                )
            resolved = (release_dir / relative_path).resolve()
            try:
                resolved.relative_to(release_dir.resolve())
            except ValueError as exc:
                raise ManifestValidationError(
                    f"Manifest file reference '{logical_name}' escapes the release directory."
                ) from exc
            if not resolved.exists():
                raise ManifestValidationError(
                    f"Manifest file reference '{logical_name}' does not exist: {relative_path}"
                )

    return manifest