from __future__ import annotations

from datetime import datetime, timezone


class OperationsService:
    def __init__(self, release_service, job_service, project_service):
        self.release_service = release_service
        self.job_service = job_service
        self.project_service = project_service

    def get_metrics(self):
        releases = self.release_service.list_releases(include_invalid=True)
        jobs_payload = self.job_service.list_jobs_history(per_page=100000)
        jobs = jobs_payload.get("items", [])
        projects = self.project_service.list_projects()

        status_counts = {}
        latest_job = ""
        for job in jobs:
            status = str(job.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            created = str(job.get("created_at") or "")
            if created and created > latest_job:
                latest_job = created

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "release_count": len(releases),
            "valid_release_count": len([r for r in releases if r.get("status") == "valid"]),
            "invalid_release_count": len([r for r in releases if r.get("status") != "valid"]),
            "job_count": len(jobs),
            "job_status_counts": status_counts,
            "project_count": len(projects),
            "latest_job_created_at": latest_job,
        }
