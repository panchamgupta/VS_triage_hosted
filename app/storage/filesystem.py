import json
from pathlib import Path

from app.storage.base import ReleaseStore


class FilesystemReleaseStore(ReleaseStore):
    def __init__(self, release_root):
        self.release_root = Path(release_root)

    def list_release_dirs(self):
        if not self.release_root.exists() or not self.release_root.is_dir():
            return []
        return [path for path in self.release_root.iterdir() if path.is_dir()]

    def resolve_release_dir(self, release_id):
        release_dir = (self.release_root / str(release_id)).resolve()
        if not release_dir.exists() or not release_dir.is_dir():
            raise FileNotFoundError(f"Release directory not found: {release_id}")
        try:
            release_dir.relative_to(self.release_root.resolve())
        except ValueError as exc:
            raise FileNotFoundError(f"Release directory escapes configured root: {release_id}") from exc
        return release_dir

    def load_manifest(self, release_dir):
        manifest_path = Path(release_dir) / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        return self.load_json(manifest_path)

    def resolve_release_file(self, release_dir, relative_path):
        release_dir = Path(release_dir).resolve()
        resolved = (release_dir / relative_path).resolve()
        try:
            resolved.relative_to(release_dir)
        except ValueError as exc:
            raise FileNotFoundError(
                f"Resolved file escapes release directory: {relative_path}"
            ) from exc
        return resolved

    def load_json(self, path):
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)