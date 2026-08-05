from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import shutil


LOGGER = logging.getLogger("hosted_portal.cleanup")


class RetentionService:
    def __init__(self, config, job_service):
        self.config = config
        self.job_service = job_service
        self.upload_root = Path(config.upload_root).resolve()
        self.job_root = Path(config.job_root).resolve()

    @staticmethod
    def _parse_iso(ts):
        if not ts:
            return None
        value = str(ts).strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def preview_cleanup(self):
        now = datetime.now(timezone.utc)
        upload_cutoff = now - timedelta(days=max(1, self.config.retention_upload_days))
        workspace_cutoff = now - timedelta(days=max(1, self.config.retention_job_workspace_days))
        failed_cutoff = now - timedelta(days=max(1, self.config.retention_failed_job_days))

        history = self.job_service.list_jobs_history(per_page=100000)
        upload_candidates = []
        workspace_candidates = []

        for job in history.get("items", []):
            completed = self._parse_iso(job.get("completed_at"))
            created = self._parse_iso(job.get("created_at"))
            status = str(job.get("status") or "")
            upload_dir = str(job.get("upload_dir") or "")
            workspace_dir = str(job.get("workspace_dir") or "")
            if not upload_dir:
                uploads = job.get("uploads") or {}
                if uploads:
                    first_upload = next(iter(uploads.values()))
                    upload_dir = str(Path(first_upload).parent)

            if upload_dir and ((completed and completed < upload_cutoff) or (created and created < upload_cutoff)):
                upload_candidates.append(upload_dir)

            failed_expired = status in {"failed", "orphaned", "canceled"} and created and created < failed_cutoff
            generic_expired = created and created < workspace_cutoff
            if workspace_dir and (failed_expired or generic_expired):
                workspace_candidates.append(workspace_dir)

        return {
            "upload_candidates": sorted(set(upload_candidates)),
            "workspace_candidates": sorted(set(workspace_candidates)),
            "upload_cutoff": upload_cutoff.isoformat(),
            "workspace_cutoff": workspace_cutoff.isoformat(),
            "failed_cutoff": failed_cutoff.isoformat(),
        }

    def execute_cleanup(self, dry_run=True):
        plan = self.preview_cleanup()
        removed_uploads = []
        removed_workspaces = []

        LOGGER.info(
            "Retention cleanup requested",
            extra={
                "event": "cleanup_requested",
                "dry_run": bool(dry_run),
                "upload_candidates": len(plan.get("upload_candidates", [])),
                "workspace_candidates": len(plan.get("workspace_candidates", [])),
            },
        )

        if dry_run:
            return {
                "dry_run": True,
                **plan,
                "removed_uploads": removed_uploads,
                "removed_workspaces": removed_workspaces,
            }

        for path in plan["upload_candidates"]:
            p = Path(path)
            if p.exists() and self._under_root(p, self.upload_root):
                shutil.rmtree(p, ignore_errors=True)
                removed_uploads.append(path)

        for path in plan["workspace_candidates"]:
            p = Path(path)
            if p.exists() and self._under_root(p, self.job_root):
                shutil.rmtree(p, ignore_errors=True)
                removed_workspaces.append(path)

        LOGGER.info(
            "Retention cleanup completed",
            extra={
                "event": "cleanup_completed",
                "dry_run": False,
                "removed_uploads": len(removed_uploads),
                "removed_workspaces": len(removed_workspaces),
            },
        )

        return {
            "dry_run": False,
            **plan,
            "removed_uploads": removed_uploads,
            "removed_workspaces": removed_workspaces,
        }

    @staticmethod
    def _under_root(path, root):
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except Exception:
            return False
