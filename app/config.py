import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class HostedPortalConfig:
    base_dir: Path
    environment: str
    host: str
    port: int
    base_url: str
    server_name: str
    enforce_server_name: bool
    preferred_scheme: str
    application_root: str
    release_root: Path
    active_release: str
    cache_dir: Path
    upload_root: Path
    job_root: Path
    max_upload_mb: int
    max_workers: int
    default_n_workers: int
    max_n_workers: int
    job_poll_seconds: int
    vote_poll_seconds: int
    vote_db_path: Path
    retention_upload_days: int
    retention_job_workspace_days: int
    retention_failed_job_days: int
    admin_cleanup_enabled: bool
    allow_release_delete: bool
    admin_token: str
    log_level: str
    log_dir: Path
    log_max_bytes: int
    log_backup_count: int
    startup_strict: bool
    job_heartbeat_stale_seconds: int
    secret_key: str

    @classmethod
    def from_env(cls):
        repo_root = Path(__file__).resolve().parent.parent
        environment = os.getenv("HOSTED_PORTAL_ENV", "development").strip() or "development"
        host = os.getenv("HOSTED_PORTAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = int(os.getenv("HOSTED_PORTAL_PORT", "5005").strip() or "5005")
        default_base_url = f"http://{host}:{port}"
        base_url = os.getenv("HOSTED_PORTAL_BASE_URL", default_base_url).strip() or default_base_url
        parsed = urlparse(base_url)
        scheme = parsed.scheme or "http"
        hostname = parsed.hostname or host
        parsed_port = parsed.port
        if parsed_port is None:
            parsed_port = 443 if scheme == "https" else 80
        default_port = 443 if scheme == "https" else 80
        server_name = hostname if parsed_port == default_port else f"{hostname}:{parsed_port}"
        enforce_server_name = (
            os.getenv("HOSTED_PORTAL_ENFORCE_SERVER_NAME", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        application_root = parsed.path if parsed.path else "/"
        release_root = Path(
            os.getenv("HOSTED_PORTAL_RELEASE_ROOT", str(repo_root / "releases"))
        ).expanduser()
        active_release = os.getenv("HOSTED_PORTAL_ACTIVE_RELEASE", "").strip()
        cache_dir = Path(
            os.getenv("HOSTED_PORTAL_CACHE_DIR", str(repo_root / "tmp" / "hosted_portal_cache"))
        ).expanduser()
        upload_root = Path(
            os.getenv("HOSTED_PORTAL_UPLOAD_ROOT", str(repo_root / "uploads"))
        ).expanduser()
        job_root = Path(
            os.getenv("HOSTED_PORTAL_JOB_ROOT", str(repo_root / "jobs"))
        ).expanduser()
        max_upload_mb = int(os.getenv("HOSTED_PORTAL_MAX_UPLOAD_MB", "512").strip() or "512")
        max_workers = int(os.getenv("HOSTED_PORTAL_JOB_MAX_WORKERS", "2").strip() or "2")
        default_n_workers = int(
            os.getenv("HOSTED_PORTAL_PIPELINE_DEFAULT_N_WORKERS", "8").strip() or "8"
        )
        max_n_workers = int(
            os.getenv("HOSTED_PORTAL_PIPELINE_MAX_N_WORKERS", "32").strip() or "32"
        )
        job_poll_seconds = int(os.getenv("HOSTED_PORTAL_JOB_POLL_SECONDS", "2").strip() or "2")
        vote_poll_seconds = int(
            os.getenv("HOSTED_PORTAL_VOTE_POLL_SECONDS", "5").strip() or "5"
        )
        vote_db_path = Path(
            os.getenv(
                "HOSTED_PORTAL_VOTE_DB_PATH",
                str(repo_root / "tmp" / "hosted_portal_data" / "votes.sqlite3"),
            )
        ).expanduser()
        retention_upload_days = int(os.getenv("HOSTED_PORTAL_RETENTION_UPLOAD_DAYS", "30").strip() or "30")
        retention_job_workspace_days = int(
            os.getenv("HOSTED_PORTAL_RETENTION_JOB_WORKSPACE_DAYS", "30").strip() or "30"
        )
        retention_failed_job_days = int(
            os.getenv("HOSTED_PORTAL_RETENTION_FAILED_JOB_DAYS", "60").strip() or "60"
        )
        admin_cleanup_enabled = (
            os.getenv("HOSTED_PORTAL_ADMIN_CLEANUP_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        )
        allow_release_delete = (
            os.getenv("HOSTED_PORTAL_ALLOW_RELEASE_DELETE", "false").strip().lower() in {"1", "true", "yes", "on"}
        )
        admin_token = os.getenv("HOSTED_PORTAL_ADMIN_TOKEN", "").strip()
        log_level = os.getenv("HOSTED_PORTAL_LOG_LEVEL", "INFO").strip().upper() or "INFO"
        log_dir = Path(
            os.getenv("HOSTED_PORTAL_LOG_DIR", str(repo_root / "logs"))
        ).expanduser()
        log_max_bytes = int(
            os.getenv("HOSTED_PORTAL_LOG_MAX_BYTES", str(20 * 1024 * 1024)).strip()
            or str(20 * 1024 * 1024)
        )
        log_backup_count = int(os.getenv("HOSTED_PORTAL_LOG_BACKUP_COUNT", "14").strip() or "14")
        startup_strict = (
            os.getenv("HOSTED_PORTAL_STARTUP_STRICT", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        job_heartbeat_stale_seconds = int(
            os.getenv("HOSTED_PORTAL_JOB_HEARTBEAT_STALE_SECONDS", "900").strip() or "900"
        )
        secret_key = os.getenv("HOSTED_PORTAL_SECRET_KEY", "hosted-portal-dev-key")
        return cls(
            base_dir=repo_root,
            environment=environment,
            host=host,
            port=port,
            base_url=base_url.rstrip("/"),
            server_name=server_name,
            enforce_server_name=enforce_server_name,
            preferred_scheme=scheme,
            application_root=application_root,
            release_root=release_root,
            active_release=active_release,
            cache_dir=cache_dir,
            upload_root=upload_root,
            job_root=job_root,
            max_upload_mb=max_upload_mb,
            max_workers=max_workers,
            default_n_workers=default_n_workers,
            max_n_workers=max_n_workers,
            job_poll_seconds=job_poll_seconds,
            vote_poll_seconds=vote_poll_seconds,
            vote_db_path=vote_db_path,
            retention_upload_days=retention_upload_days,
            retention_job_workspace_days=retention_job_workspace_days,
            retention_failed_job_days=retention_failed_job_days,
            admin_cleanup_enabled=admin_cleanup_enabled,
            allow_release_delete=allow_release_delete,
            admin_token=admin_token,
            log_level=log_level,
            log_dir=log_dir,
            log_max_bytes=log_max_bytes,
            log_backup_count=log_backup_count,
            startup_strict=startup_strict,
            job_heartbeat_stale_seconds=job_heartbeat_stale_seconds,
            secret_key=secret_key,
        )

    def as_flask_mapping(self):
        return {
            "ENV": self.environment,
            "SECRET_KEY": self.secret_key,
            "SERVER_NAME": self.server_name if self.enforce_server_name else None,
            "PREFERRED_URL_SCHEME": self.preferred_scheme,
            "APPLICATION_ROOT": self.application_root,
            "HOSTED_PORTAL_ENFORCE_SERVER_NAME": self.enforce_server_name,
            "HOSTED_PORTAL_HOST": self.host,
            "HOSTED_PORTAL_PORT": self.port,
            "HOSTED_PORTAL_BASE_URL": self.base_url,
            "HOSTED_PORTAL_ENV": self.environment,
            "HOSTED_PORTAL_RELEASE_ROOT": self.release_root,
            "HOSTED_PORTAL_ACTIVE_RELEASE": self.active_release,
            "HOSTED_PORTAL_CACHE_DIR": self.cache_dir,
            "HOSTED_PORTAL_UPLOAD_ROOT": self.upload_root,
            "HOSTED_PORTAL_JOB_ROOT": self.job_root,
            "HOSTED_PORTAL_MAX_UPLOAD_MB": self.max_upload_mb,
            "HOSTED_PORTAL_JOB_MAX_WORKERS": self.max_workers,
            "HOSTED_PORTAL_PIPELINE_DEFAULT_N_WORKERS": self.default_n_workers,
            "HOSTED_PORTAL_PIPELINE_MAX_N_WORKERS": self.max_n_workers,
            "HOSTED_PORTAL_JOB_POLL_SECONDS": self.job_poll_seconds,
            "HOSTED_PORTAL_VOTE_POLL_SECONDS": self.vote_poll_seconds,
            "HOSTED_PORTAL_VOTE_DB_PATH": self.vote_db_path,
            "HOSTED_PORTAL_RETENTION_UPLOAD_DAYS": self.retention_upload_days,
            "HOSTED_PORTAL_RETENTION_JOB_WORKSPACE_DAYS": self.retention_job_workspace_days,
            "HOSTED_PORTAL_RETENTION_FAILED_JOB_DAYS": self.retention_failed_job_days,
            "HOSTED_PORTAL_ADMIN_CLEANUP_ENABLED": self.admin_cleanup_enabled,
            "HOSTED_PORTAL_ALLOW_RELEASE_DELETE": self.allow_release_delete,
            "HOSTED_PORTAL_ADMIN_TOKEN": self.admin_token,
            "HOSTED_PORTAL_LOG_LEVEL": self.log_level,
            "HOSTED_PORTAL_LOG_DIR": self.log_dir,
            "HOSTED_PORTAL_LOG_MAX_BYTES": self.log_max_bytes,
            "HOSTED_PORTAL_LOG_BACKUP_COUNT": self.log_backup_count,
            "HOSTED_PORTAL_STARTUP_STRICT": self.startup_strict,
            "HOSTED_PORTAL_JOB_HEARTBEAT_STALE_SECONDS": self.job_heartbeat_stale_seconds,
            "TEMPLATES_AUTO_RELOAD": self.environment != "production",
        }