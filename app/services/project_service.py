from __future__ import annotations

from collections import defaultdict


class ProjectService:
    def __init__(self, release_service, job_service):
        self.release_service = release_service
        self.job_service = job_service

    def list_projects(self):
        aggregates = defaultdict(lambda: {
            "project_name": "",
            "release_count": 0,
            "job_count": 0,
            "completed_job_count": 0,
            "failed_job_count": 0,
            "orphaned_job_count": 0,
            "targets": set(),
            "last_release_at": "",
            "last_job_at": "",
        })

        for release in self.release_service.list_releases(include_invalid=False):
            name = str(release.get("project_name") or release.get("program") or "Unassigned")
            target = str(release.get("target_name") or release.get("target") or "")
            item = aggregates[name]
            item["project_name"] = name
            item["release_count"] += 1
            if target:
                item["targets"].add(target)
            created = str(release.get("created_at") or "")
            if created and created > item["last_release_at"]:
                item["last_release_at"] = created

        history = self.job_service.list_jobs_history(per_page=100000)
        for job in history.get("items", []):
            metadata = job.get("metadata") or {}
            name = str(metadata.get("project_name") or "Unassigned")
            target = str(metadata.get("target_name") or "")
            status = str(job.get("status") or "")
            item = aggregates[name]
            item["project_name"] = name
            item["job_count"] += 1
            if target:
                item["targets"].add(target)
            if status == "completed":
                item["completed_job_count"] += 1
            elif status == "failed":
                item["failed_job_count"] += 1
            elif status == "orphaned":
                item["orphaned_job_count"] += 1
            created = str(job.get("created_at") or "")
            if created and created > item["last_job_at"]:
                item["last_job_at"] = created

        rows = []
        for value in aggregates.values():
            row = dict(value)
            row["targets"] = sorted(value["targets"])
            rows.append(row)

        rows.sort(key=lambda r: (r.get("release_count", 0), r.get("job_count", 0), r.get("project_name", "")), reverse=True)
        return rows

    def get_project_detail(self, project_name):
        releases = [
            r
            for r in self.release_service.list_releases(include_invalid=False)
            if str(r.get("project_name") or r.get("program") or "Unassigned").lower() == str(project_name).lower()
        ]
        jobs_payload = self.job_service.list_jobs_history(project=project_name, per_page=100000)
        jobs = jobs_payload.get("items", [])
        return {
            "project_name": project_name,
            "releases": releases,
            "jobs": jobs,
        }
