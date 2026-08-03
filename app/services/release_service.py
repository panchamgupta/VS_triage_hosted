from pathlib import Path
import shutil
from datetime import datetime, timezone

from flask import abort

from app.services.manifest_service import ManifestValidationError, validate_manifest


class ReleaseService:
    def __init__(self, store, cache, active_release=""):
        self.store = store
        self.cache = cache
        self.active_release = str(active_release or "").strip()

    def list_releases(self, include_invalid=False):
        releases = []
        for release_dir in self.store.list_release_dirs():
            release_id = release_dir.name
            try:
                manifest = self._load_manifest(release_id)
                release_record = self._release_record_from_manifest(manifest)
                release_record["status"] = "published"
            except (FileNotFoundError, ManifestValidationError) as exc:
                if not include_invalid:
                    continue
                release_record = {
                    "release_id": release_id,
                    "display_name": release_id,
                    "program": None,
                    "target": None,
                    "created_at": None,
                    "description": None,
                    "status": "invalid",
                    "error": str(exc),
                    "default": False,
                }
            releases.append(release_record)

        releases.sort(key=lambda item: (item.get("created_at") or "", item["release_id"]), reverse=True)

        default_release = self.get_default_release_id(releases)
        for release in releases:
            release["default"] = release["release_id"] == default_release
        return releases

    def get_default_release_id(self, releases=None):
        if self.active_release:
            return self.active_release
        releases = releases if releases is not None else self.list_releases()
        if releases:
            return releases[0]["release_id"]
        return ""

    def get_manifest(self, release_id):
        cache_key = f"manifest:{release_id}"
        try:
            return self.cache.get_or_set(cache_key, lambda: self._load_manifest(release_id))
        except FileNotFoundError:
            abort(404, description=f"Release '{release_id}' was not found.")
        except ManifestValidationError as exc:
            abort(500, description=str(exc))

    def get_release_summary(self, release_id):
        manifest = self.get_manifest(release_id)
        counts = manifest.get("counts") or {}
        features = manifest.get("features") or {}
        return {
            "release": manifest["release_id"],
            "title": manifest.get("display_name", manifest["release_id"]),
            "program": manifest.get("program"),
            "target": manifest.get("target"),
            "project_name": manifest.get("project_name") or manifest.get("program"),
            "target_name": manifest.get("target_name") or manifest.get("target"),
            "description": manifest.get("description"),
            "kpis": {
                "molecules": counts.get("molecules"),
                "scaffolds": counts.get("scaffolds"),
                "poses": counts.get("poses"),
            },
            "capabilities": {
                "structure_search": bool(features.get("structure_search", False)),
                "motif_exclusion": bool(features.get("motif_exclusion", False)),
                "pose_viewer": bool(features.get("pose_viewer", True)),
                "exports": bool(features.get("exports", False)),
            },
        }

    def has_static_report(self, release_id):
        return self.get_static_report_path(release_id) is not None

    def get_static_report_path(self, release_id):
        manifest = self.get_manifest(release_id)
        release_dir = self.store.resolve_release_dir(release_id)
        relative_path = manifest.get("files", {}).get("static_report")
        if not relative_path:
            return None
        report_path = self.store.resolve_release_file(release_dir, relative_path)
        if not report_path.exists():
            return None
        return report_path

    def get_artifact_payload(self, release_id, artifact_key):
        manifest = self.get_manifest(release_id)
        release_dir = self.store.resolve_release_dir(release_id)
        relative_path = manifest["files"].get(artifact_key)
        if not relative_path:
            return self._placeholder_payload(release_id, artifact_key, "Manifest key is not defined.")

        cache_key = f"artifact:{release_id}:{artifact_key}"
        return self.cache.get_or_set(
            cache_key,
            lambda: self._load_artifact_payload(release_id, artifact_key, release_dir, relative_path),
        )

    def _load_manifest(self, release_id):
        release_dir = self.store.resolve_release_dir(release_id)
        manifest = self.store.load_manifest(release_dir)
        return validate_manifest(manifest, release_dir=release_dir)

    def _load_artifact_payload(self, release_id, artifact_key, release_dir, relative_path):
        artifact_path = self.store.resolve_release_file(release_dir, relative_path)
        if not artifact_path.exists():
            return self._placeholder_payload(
                release_id,
                artifact_key,
                f"Referenced file is missing: {relative_path}",
            )

        payload = self.store.load_json(artifact_path)
        if isinstance(payload, list):
            return {
                "release_id": release_id,
                "artifact": artifact_key,
                "count": len(payload),
                "items": payload,
                "status": "ok",
            }

        if isinstance(payload, dict):
            if "items" in payload and isinstance(payload["items"], list):
                merged = dict(payload)
                merged.setdefault("release_id", release_id)
                merged.setdefault("artifact", artifact_key)
                merged.setdefault("count", len(payload["items"]))
                merged.setdefault("status", "ok")
                return merged
            return {
                "release_id": release_id,
                "artifact": artifact_key,
                "count": len(payload),
                "data": payload,
                "status": "ok",
            }

        return self._placeholder_payload(
            release_id,
            artifact_key,
            f"Unsupported JSON payload type: {type(payload).__name__}",
        )

    def _placeholder_payload(self, release_id, artifact_key, message):
        collection_key = "entries" if artifact_key == "pose_index" else "items"
        return {
            "release_id": release_id,
            "artifact": artifact_key,
            collection_key: [],
            "count": 0,
            "status": "placeholder",
            "message": message,
        }

    def _release_record_from_manifest(self, manifest):
        counts = manifest.get("counts") or {}
        return {
            "release_id": manifest["release_id"],
            "display_name": manifest["display_name"],
            "program": manifest.get("program"),
            "target": manifest.get("target"),
            "project_name": manifest.get("project_name") or manifest.get("program"),
            "target_name": manifest.get("target_name") or manifest.get("target"),
            "created_at": manifest.get("created_at"),
            "description": manifest.get("description"),
            "molecule_count": counts.get("molecules"),
            "scaffold_count": counts.get("scaffolds"),
        }

    def search_releases(self, *, project=None, target=None, release_id=None, created_from=None, created_to=None, page=1, per_page=25):
        releases = self.list_releases(include_invalid=False)

        def include(row):
            project_name = str(row.get("project_name") or row.get("program") or "")
            target_name = str(row.get("target_name") or row.get("target") or "")
            rid = str(row.get("release_id") or "")
            created = str(row.get("created_at") or "")
            if project and project_name.lower() != str(project).lower():
                return False
            if target and target_name.lower() != str(target).lower():
                return False
            if release_id and str(release_id).lower() not in rid.lower():
                return False
            if created_from and created and created[:10] < str(created_from):
                return False
            if created_to and created and created[:10] > str(created_to):
                return False
            return True

        filtered = [row for row in releases if include(row)]
        filtered.sort(key=lambda item: (item.get("created_at") or "", item.get("release_id") or ""), reverse=True)

        page = max(1, int(page))
        per_page = max(1, min(100, int(per_page)))
        total = len(filtered)
        start = (page - 1) * per_page
        end = start + per_page
        items = filtered[start:end]
        total_pages = (total + per_page - 1) // per_page if total else 1
        return {
            "items": items,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "filters": {
                "project": project or "",
                "target": target or "",
                "release_id": release_id or "",
                "created_from": created_from or "",
                "created_to": created_to or "",
            },
        }

    def delete_release(self, release_id, *, allow_delete=False, confirm_release_id=""):
        if not allow_delete:
            raise PermissionError("Release deletion is disabled.")
        if str(confirm_release_id or "").strip() != str(release_id):
            raise PermissionError("Confirmation release id mismatch.")

        release_dir = self.store.resolve_release_dir(release_id)
        quarantine_root = Path(self.store.release_root) / ".trash"
        quarantine_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantine_dir = quarantine_root / f"{release_id}_{timestamp}"
        shutil.move(str(release_dir), str(quarantine_dir))

        self.cache.invalidate_prefix(f"manifest:{release_id}")
        self.cache.invalidate_prefix(f"artifact:{release_id}:")
        return {
            "release_id": release_id,
            "deleted": True,
            "quarantine_dir": str(quarantine_dir),
        }