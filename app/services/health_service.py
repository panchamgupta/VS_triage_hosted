from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import threading


class HealthService:
    def __init__(self, *, release_service, vote_service, job_service, app_config, startup_validation=None):
        self.release_service = release_service
        self.vote_service = vote_service
        self.job_service = job_service
        self.app_config = app_config
        self.startup_validation = startup_validation or {}

    def build_snapshot(self):
        checks = {}

        release_root = Path(self.app_config.get("HOSTED_PORTAL_RELEASE_ROOT"))
        upload_root = Path(self.app_config.get("HOSTED_PORTAL_UPLOAD_ROOT"))
        job_root = Path(self.app_config.get("HOSTED_PORTAL_JOB_ROOT"))
        vote_db_path = Path(self.app_config.get("HOSTED_PORTAL_VOTE_DB_PATH"))

        checks["release_directory"] = self._path_check(release_root)
        checks["upload_directory"] = self._path_check(upload_root)
        checks["job_directory"] = self._path_check(job_root)

        vote_status = self.vote_service.health_snapshot()
        checks["vote_database"] = vote_status

        release_component = {
            "status": "healthy",
            "error": "",
            "available_release_count": 0,
            "invalid_release_count": 0,
            "active_release": self.app_config.get("HOSTED_PORTAL_ACTIVE_RELEASE") or "",
        }
        try:
            releases = self.release_service.list_releases(include_invalid=True)
            release_component["available_release_count"] = sum(
                1 for item in releases if item.get("status") == "published"
            )
            release_component["invalid_release_count"] = sum(
                1 for item in releases if item.get("status") != "published"
            )
            if release_component["invalid_release_count"] > 0:
                release_component["status"] = "degraded"
        except Exception as exc:
            release_component["status"] = "unhealthy"
            release_component["error"] = str(exc)
        checks["release_status"] = release_component

        stale_after_seconds = int(self.app_config.get("HOSTED_PORTAL_JOB_HEARTBEAT_STALE_SECONDS", 900))
        job_stats = self.job_service.get_runtime_stats(stale_after_seconds=stale_after_seconds)
        job_status = "healthy"
        if job_stats.get("executor_shutdown"):
            job_status = "unhealthy"
        elif int(job_stats.get("stale_running_jobs") or 0) > 0:
            job_status = "degraded"
        checks["job_queue"] = {
            "status": job_status,
            "stale_after_seconds": stale_after_seconds,
            **job_stats,
        }

        checks["disk_usage"] = self._disk_usage_snapshot([release_root, upload_root, job_root, vote_db_path.parent])

        server_software = str(os.getenv("SERVER_SOFTWARE", "")).lower()
        running_under_gunicorn = "gunicorn" in server_software
        checks["gunicorn"] = {
            "status": "healthy" if running_under_gunicorn else "degraded",
            "running_under_gunicorn": running_under_gunicorn,
            "server_software": os.getenv("SERVER_SOFTWARE", ""),
            "bind": self.app_config.get("HOSTED_PORTAL_GUNICORN_BIND") or "",
            "configured_workers": int(self.app_config.get("HOSTED_PORTAL_GUNICORN_WORKERS", 0) or 0),
            "configured_threads": int(self.app_config.get("HOSTED_PORTAL_GUNICORN_THREADS", 0) or 0),
        }

        checks["worker"] = {
            "status": "healthy",
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "threads": threading.active_count(),
        }

        if self.startup_validation:
            checks["startup_validation"] = self.startup_validation

        overall = self._overall_status(checks)
        return {
            "status": overall,
            "environment": self.app_config.get("HOSTED_PORTAL_ENV", "development"),
            "base_url": self.app_config.get("HOSTED_PORTAL_BASE_URL", ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        }

    def _path_check(self, path):
        exists = path.exists()
        is_dir = path.is_dir()
        writable = os.access(str(path), os.W_OK) if exists else False
        status = "healthy" if exists and is_dir else "unhealthy"
        if exists and is_dir and not writable:
            status = "degraded"
        return {
            "status": status,
            "path": str(path),
            "exists": exists,
            "is_directory": is_dir,
            "writable": writable,
        }

    def _disk_usage_snapshot(self, paths):
        entries = []
        worst = "healthy"
        seen = set()
        for path in paths:
            resolved = str(Path(path).resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                usage = shutil.disk_usage(resolved)
                free_pct = (float(usage.free) / float(usage.total) * 100.0) if usage.total else 0.0
                status = "healthy"
                if free_pct < 10.0:
                    status = "unhealthy"
                elif free_pct < 20.0:
                    status = "degraded"
                if status == "unhealthy":
                    worst = "unhealthy"
                elif status == "degraded" and worst == "healthy":
                    worst = "degraded"
                entries.append(
                    {
                        "path": resolved,
                        "status": status,
                        "total_bytes": usage.total,
                        "used_bytes": usage.used,
                        "free_bytes": usage.free,
                        "free_percent": round(free_pct, 2),
                    }
                )
            except Exception as exc:
                worst = "unhealthy"
                entries.append(
                    {
                        "path": resolved,
                        "status": "unhealthy",
                        "error": str(exc),
                    }
                )
        return {
            "status": worst,
            "entries": entries,
        }

    def _overall_status(self, checks):
        worst = "healthy"
        for payload in checks.values():
            status = str((payload or {}).get("status", "healthy"))
            if status == "unhealthy":
                return "unhealthy"
            if status == "degraded":
                worst = "degraded"
        return worst
