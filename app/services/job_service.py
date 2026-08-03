import csv
import json
import re
import subprocess
import sys
import threading
import uuid
from rdkit import Chem
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from cli_config import prefixed_output_name


class JobValidationError(Exception):
    pass


class JobCancelledError(Exception):
    pass


_ALLOWED_EXTENSIONS = {
    "docking_sdf": {".sdf"},
    "interaction_csv": {".csv"},
    "property_csv": {".csv"},
    "protein_pdb": {".pdb"},
}

# Read up to 1 MB during SDF header validation to avoid false negatives
# when the first record is large and '$$$$' appears after the first 4 KB.
_SDF_VALIDATION_SCAN_BYTES = 1024 * 1024

_STATUS_ORDER = {
    "queued": 0,
    "running": 1,
    "orphaned": 2,
    "failed": 2,
    "canceled": 3,
    "completed": 4,
}

_TERMINAL_STATUS = {"completed", "failed", "canceled", "orphaned"}


class JobService:
    def __init__(
        self,
        *,
        repo_root,
        release_root,
        upload_root,
        job_root,
        max_upload_mb,
        max_workers,
        default_n_workers,
        max_n_workers,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.release_root = Path(release_root).resolve()
        self.upload_root = Path(upload_root).resolve()
        self.job_root = Path(job_root).resolve()
        self.max_upload_bytes = int(max_upload_mb) * 1024 * 1024
        self.max_workers = max(1, int(max_workers))
        self.default_n_workers = max(1, int(default_n_workers))
        self.max_n_workers = max(self.default_n_workers, int(max_n_workers))
        self.schema_version = 2

        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.job_root.mkdir(parents=True, exist_ok=True)
        self.release_root.mkdir(parents=True, exist_ok=True)

        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="portal-job")
        self._lock = threading.Lock()
        self._release_lock = threading.Lock()
        self._jobs = {}
        self._reserved_release_ids = set()
        self._rehydrate_jobs_from_disk()

    def create_job(self, form, files):
        normalized = self._normalize_form(form)
        upload_file_map = self._store_uploads(files)
        release_id = self._allocate_release_id()

        now = self._utcnow()
        job_id = str(uuid.uuid4())
        job_dir = self.job_root / job_id
        workspace_dir = job_dir / "workspace"
        report_out_dir = workspace_dir / "report_build"
        log_path = job_dir / "job.log"

        job_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        report_out_dir.mkdir(parents=True, exist_ok=True)

        job = {
            "job_id": job_id,
            "status": "queued",
            "stage": "Uploading Files",
            "progress": 0,
            "message": "Job accepted and queued.",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "release_id": release_id,
            "release_url": f"/release/{release_id}/report",
            "cancel_requested": False,
            "error": None,
            "log_path": str(log_path),
            "workspace_dir": str(workspace_dir),
            "report_out_dir": str(report_out_dir),
            "uploads": upload_file_map,
            "upload_dir": str(Path(next(iter(upload_file_map.values()))).parent) if upload_file_map else "",
            "inputs": normalized,
            "metadata": {
                "report_name": normalized["report_name"],
                "project_name": normalized["project_name"],
                "target_name": normalized["target_name"],
                "uploader_username": normalized["uploader_username"],
                "uploader_email": normalized["uploader_email"],
                "uploader_group": normalized["uploader_group"],
            },
            "pipeline": {
                "interaction_id_col": normalized["interaction_id_col"],
                "interaction_count_col": normalized["interaction_count_col"],
                "top_per_scaffold": normalized["top_per_scaffold"],
                "max_scaffolds_in_report": normalized["max_scaffolds_in_report"],
                "n_workers": normalized["n_workers"],
                "auto_detect_score": normalized["auto_detect_score"],
                "report_max_width": normalized["report_max_width"],
                "generate_all_mol_images": normalized["generate_all_mol_images"],
            },
            "schema_version": self.schema_version,
            "runner_id": None,
            "pid": None,
            "heartbeat_at": None,
            "lease_expires_at": None,
            "recovery_count": 0,
            "interrupted_reason": None,
            "failure_stage": None,
            "_process": None,
        }

        with self._lock:
            self._jobs[job_id] = job
            self._persist_job(job)

        future = self._executor.submit(self._run_job, job_id)
        with self._lock:
            job["_future"] = future

        return self.get_job(job_id)

    def list_jobs(self):
        with self._lock:
            jobs = [self._public_job_dict(job) for job in self._jobs.values()]
        jobs.sort(
            key=lambda row: (
                _STATUS_ORDER.get(row.get("status", "queued"), 99),
                row.get("created_at") or "",
            ),
            reverse=True,
        )
        return jobs

    def list_jobs_history(self, *, status=None, project=None, target=None, date_from=None, date_to=None, page=1, per_page=25):
        with self._lock:
            rows = [self._public_job_dict(job) for job in self._jobs.values()]

        def include(row):
            if status and row.get("status") != status:
                return False
            metadata = row.get("metadata") or {}
            if project and (metadata.get("project_name") or "") != project:
                return False
            if target and (metadata.get("target_name") or "") != target:
                return False
            created_at = str(row.get("created_at") or "")
            if date_from and created_at[:10] < date_from:
                return False
            if date_to and created_at[:10] > date_to:
                return False
            return True

        filtered = [row for row in rows if include(row)]
        filtered.sort(key=lambda item: item.get("created_at") or "", reverse=True)

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
                "status": status or "",
                "project": project or "",
                "target": target or "",
                "date_from": date_from or "",
                "date_to": date_to or "",
            },
        }

    def get_job(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return self._public_job_dict(job)

    def get_job_log(self, job_id, max_lines=200):
        try:
            max_lines = max(10, min(2000, int(max_lines)))
        except Exception:
            max_lines = 200
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            log_path = job.get("log_path")
        return {
            "job_id": job_id,
            "log_tail": self._tail_log(log_path, max_lines=max_lines),
            "log_path_present": bool(log_path and Path(log_path).exists()),
            "truncated": True,
        }

    def cancel_job(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if job["status"] in _TERMINAL_STATUS:
                return self._public_job_dict(job)

            job["cancel_requested"] = True
            if job["status"] == "queued":
                job["status"] = "canceled"
                job["stage"] = "Canceled"
                job["progress"] = job.get("progress", 0)
                job["message"] = "Job was canceled before execution."
                job["completed_at"] = self._utcnow()
                job["updated_at"] = self._utcnow()

            process = job.get("_process")
            if process is not None and process.poll() is None:
                process.terminate()

            self._persist_job(job)
            return self._public_job_dict(job)

    def _normalize_form(self, form):
        report_name = str(form.get("report_name", "")).strip()
        project_name = str(form.get("project_name", "")).strip()
        target_name = str(form.get("target_name", "")).strip()
        uploader_username = str(form.get("uploader_username", "")).strip()
        uploader_email = str(form.get("uploader_email", "")).strip()
        uploader_group = str(form.get("uploader_group", "")).strip()
        interaction_id_col = str(form.get("interaction_id_col", "Title")).strip() or "Title"
        interaction_count_col = str(form.get("interaction_count_col", "interaction_count")).strip() or "interaction_count"
        property_csv_id_col = str(form.get("property_csv_id_col", "ID")).strip() or "ID"
        sdf_id_field = str(form.get("sdf_id_field", "_Name")).strip() or "_Name"
        top_per_scaffold = self._coerce_int(form.get("top_per_scaffold", 10), "top_per_scaffold", 1, 100)
        max_scaffolds_in_report = self._coerce_int(
            form.get("max_scaffolds_in_report", 500),
            "max_scaffolds_in_report",
            10,
            5000,
        )
        n_workers = self._coerce_int(
            form.get("n_workers", self.default_n_workers),
            "n_workers",
            1,
            self.max_n_workers,
        )
        report_size = str(form.get("report_size", "wide")).strip().lower() or "wide"
        report_max_width = self._resolve_report_width(report_size, form.get("report_max_width"))
        auto_detect_score = self._coerce_bool(form.get("auto_detect_score", "true"))
        generate_all_mol_images = self._coerce_bool(form.get("generate_all_mol_images", "false"))

        if not report_name:
            raise JobValidationError("Report Name is required.")
        if not project_name:
            raise JobValidationError("Project Name is required.")
        if not target_name:
            raise JobValidationError("Target Name is required.")

        return {
            "report_name": report_name,
            "project_name": project_name,
            "target_name": target_name,
            "uploader_username": uploader_username,
            "uploader_email": uploader_email,
            "uploader_group": uploader_group,
            "interaction_id_col": interaction_id_col,
            "interaction_count_col": interaction_count_col,
            "property_csv_id_col": property_csv_id_col,
            "sdf_id_field": sdf_id_field,
            "top_per_scaffold": top_per_scaffold,
            "max_scaffolds_in_report": max_scaffolds_in_report,
            "n_workers": n_workers,
            "report_size": report_size,
            "report_max_width": report_max_width,
            "auto_detect_score": auto_detect_score,
            "generate_all_mol_images": generate_all_mol_images,
        }

    def _resolve_report_width(self, report_size, raw_width):
        width_by_size = {
            "compact": 1600,
            "standard": 1800,
            "wide": 2200,
            "ultra": 2600,
        }
        if report_size in width_by_size:
            return width_by_size[report_size]
        if report_size == "custom":
            return self._coerce_int(raw_width or 2200, "report_max_width", 1200, 3800)
        raise JobValidationError("Invalid report_size. Allowed values: compact, standard, wide, ultra, custom.")

    def _store_uploads(self, files):
        docking_sdf = files.get("docking_sdf")
        interaction_csv = files.get("interaction_csv")
        property_csv = files.get("property_csv")
        protein_pdb = files.get("protein_pdb")

        if docking_sdf is None or docking_sdf.filename == "":
            raise JobValidationError("Docking SDF is required.")
        if interaction_csv is None or interaction_csv.filename == "":
            raise JobValidationError("Interaction CSV is required.")

        raw_upload_dir = self.upload_root / datetime.now(timezone.utc).strftime("%Y%m%d") / str(uuid.uuid4())
        raw_upload_dir.mkdir(parents=True, exist_ok=True)

        stored = {
            "docking_sdf": self._save_upload(docking_sdf, raw_upload_dir, "docking_sdf"),
            "interaction_csv": self._save_upload(interaction_csv, raw_upload_dir, "interaction_csv"),
        }

        if property_csv is not None and property_csv.filename:
            stored["property_csv"] = self._save_upload(property_csv, raw_upload_dir, "property_csv")
        if protein_pdb is not None and protein_pdb.filename:
            stored["protein_pdb"] = self._save_upload(protein_pdb, raw_upload_dir, "protein_pdb")

        self._validate_file_schemas(stored)
        return stored

    def _save_upload(self, upload, output_dir, field_name):
        self._validate_extension(upload, field_name)
        safe_name = secure_filename(upload.filename or "")
        if not safe_name:
            suffix = next(iter(_ALLOWED_EXTENSIONS[field_name]))
            safe_name = f"{field_name}{suffix}"

        target_path = (output_dir / safe_name).resolve()
        try:
            target_path.relative_to(output_dir.resolve())
        except ValueError as exc:
            raise JobValidationError("Invalid upload path.") from exc

        total = 0
        with target_path.open("wb") as handle:
            while True:
                chunk = upload.stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.max_upload_bytes:
                    raise JobValidationError(
                        f"{field_name} exceeds max upload size of {self.max_upload_bytes // (1024 * 1024)} MB."
                    )
                handle.write(chunk)

        if total == 0:
            raise JobValidationError(f"{field_name} upload is empty.")

        return str(target_path)

    def _validate_extension(self, upload, field_name):
        ext = Path(upload.filename or "").suffix.lower().strip()
        allowed = _ALLOWED_EXTENSIONS.get(field_name, set())
        if not ext or ext not in allowed:
            expected = ", ".join(sorted(allowed))
            raise JobValidationError(f"{field_name} must be one of: {expected}")

    def _validate_file_schemas(self, uploaded):
        docking_sdf = Path(uploaded["docking_sdf"])
        if docking_sdf.stat().st_size < 32:
            raise JobValidationError("Docking SDF file is too small to be valid.")

        # Robust SDF gate:
        # 1) Scan up to 1 MB for record delimiters to avoid short-head false negatives.
        # 2) If none found, accept single-record MOL-like input only when RDKit can parse one molecule.
        with docking_sdf.open("r", encoding="utf-8", errors="ignore") as handle:
            sdf_prefix = handle.read(_SDF_VALIDATION_SCAN_BYTES)

        has_record_delimiter = "$$$$" in sdf_prefix
        if not has_record_delimiter:
            mol = Chem.MolFromMolBlock(sdf_prefix, removeHs=False, sanitize=False)
            if mol is None:
                raise JobValidationError(
                    "Docking SDF does not appear to contain valid SDF records. "
                    "Expected at least one '$$$$' record delimiter or a parseable MOL block."
                )

        interaction_csv = Path(uploaded["interaction_csv"])
        with interaction_csv.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
        if not headers:
            raise JobValidationError("Interaction CSV is missing a header row.")

        required_headers = {"Title", "interaction_count"}
        missing = sorted(name for name in required_headers if name not in headers)
        if missing:
            raise JobValidationError(
                "Interaction CSV is missing required columns: " + ", ".join(missing)
            )

        property_csv = uploaded.get("property_csv")
        if property_csv:
            with Path(property_csv).open("r", encoding="utf-8", errors="ignore", newline="") as handle:
                prop_reader = csv.reader(handle)
                prop_header = next(prop_reader, None)
            if not prop_header:
                raise JobValidationError("Property CSV is missing a header row.")

        protein_pdb = uploaded.get("protein_pdb")
        if protein_pdb:
            with Path(protein_pdb).open("r", encoding="utf-8", errors="ignore") as handle:
                pdb_head = handle.read(2048)
            if not re.search(r"\b(ATOM|HETATM|HEADER|TITLE)\b", pdb_head):
                raise JobValidationError("Protein PDB appears invalid. Expected ATOM/HETATM/HEADER records.")

    def _allocate_release_id(self):
        with self._release_lock:
            date_token = datetime.now(timezone.utc).strftime("%Y%m%d")
            prefix = f"release_{date_token}_"
            existing = set()
            if self.release_root.exists():
                for path in self.release_root.iterdir():
                    if path.is_dir() and path.name.startswith(prefix):
                        existing.add(path.name)

            serial = 1
            while True:
                candidate = f"{prefix}{serial:03d}"
                if candidate not in existing and candidate not in self._reserved_release_ids:
                    self._reserved_release_ids.add(candidate)
                    return candidate
                serial += 1

    def _run_job(self, job_id):
        try:
            self._set_state(
                job_id,
                status="running",
                stage="Validating Inputs",
                progress=10,
                message="Validating input files.",
                runner_id=str(uuid.uuid4()),
            )
            self._check_canceled(job_id)

            job = self._get_internal_job(job_id)
            workspace_dir = Path(job["workspace_dir"])
            report_out_dir = Path(job["report_out_dir"])
            uploads = job["uploads"]
            inputs = job["inputs"]

            input_sdf_path = Path(uploads["docking_sdf"])
            if uploads.get("property_csv"):
                self._set_state(
                    job_id,
                    stage="Validating Inputs",
                    progress=20,
                    message="Merging optional property CSV into SDF.",
                )
                merged_sdf = workspace_dir / "merged_input.sdf"
                merge_command = [
                    sys.executable,
                    str(self.repo_root / "add_csv_props_to_sdf.py"),
                    "-sdf",
                    str(input_sdf_path),
                    "-csv",
                    str(uploads["property_csv"]),
                    "-out",
                    str(merged_sdf),
                    "--sdf_id_field",
                    inputs["sdf_id_field"],
                    "--csv_id_field",
                    inputs["property_csv_id_col"],
                ]
                self._run_command(job_id, merge_command)
                input_sdf_path = merged_sdf

            self._set_state(
                job_id,
                stage="Computing Interaction Summaries",
                progress=35,
                message="Running canonical docking workflow.",
            )
            file_prefix = self._sanitize_release_token(job["release_id"])
            report_filename = prefixed_output_name(file_prefix, "report.html")
            report_html = report_out_dir / report_filename

            process_command = [
                sys.executable,
                str(self.repo_root / "process_docking_IF_show_docking.py"),
                "--input",
                str(input_sdf_path),
                "--interaction-csv",
                str(uploads["interaction_csv"]),
                "--interaction-id-col",
                inputs["interaction_id_col"],
                "--interaction-count-col",
                inputs["interaction_count_col"],
                "--outdir",
                str(report_out_dir),
                "--file-prefix",
                file_prefix,
                "--top-per-scaffold",
                str(inputs["top_per_scaffold"]),
                "--max-scaffolds-in-report",
                str(inputs["max_scaffolds_in_report"]),
                "--n-workers",
                str(inputs["n_workers"]),
            ]
            if uploads.get("protein_pdb"):
                process_command.extend(["--protein-pdb", str(uploads["protein_pdb"])])
            if inputs["auto_detect_score"]:
                process_command.append("--auto-detect-score")
            if inputs["generate_all_mol_images"]:
                process_command.append("--generate-all-mol-images")

            self._run_command(job_id, process_command)
            if not report_html.exists():
                raise RuntimeError(f"Expected report HTML is missing: {report_html}")

            self._set_state(
                job_id,
                stage="Generating Scaffold Analytics",
                progress=55,
                message="Preparing scaffold analytics and report assets.",
            )
            self._set_state(
                job_id,
                stage="Building Report",
                progress=70,
                message="Building hosted report package.",
            )
            package_command = [
                sys.executable,
                str(self.repo_root / "scripts" / "create_example_release_from_report.py"),
                "--report-html",
                str(report_html),
                "--release-id",
                job["release_id"],
                "--release-root",
                str(self.release_root),
                "--report-max-width",
                str(inputs["report_max_width"]),
            ]
            self._run_command(job_id, package_command)

            self._set_state(
                job_id,
                stage="Packaging Release",
                progress=85,
                message="Packaging immutable release payload.",
            )
            self._set_state(
                job_id,
                stage="Publishing Release",
                progress=95,
                message="Validating manifest and finalizing publication.",
            )
            validate_command = [
                sys.executable,
                str(self.repo_root / "scripts" / "validate_release_manifest.py"),
                str(self.release_root / job["release_id"]),
            ]
            self._run_command(job_id, validate_command)

            self._write_release_metadata(job)
            self._set_state(
                job_id,
                status="completed",
                stage="Completed",
                progress=100,
                completed_at=self._utcnow(),
                message="Report generated successfully.",
                failure_stage=None,
            )
        except JobCancelledError:
            self._set_state(
                job_id,
                status="canceled",
                stage="Canceled",
                completed_at=self._utcnow(),
                message="Job canceled.",
            )
        except Exception as exc:
            failure_stage = "Unknown"
            with self._lock:
                current_job = self._jobs.get(job_id)
                if current_job is not None:
                    failure_stage = str(current_job.get("stage") or "Unknown")
            self._set_state(
                job_id,
                status="failed",
                completed_at=self._utcnow(),
                failure_stage=failure_stage,
                error=self._format_public_error(str(exc)),
                message="Report generation failed.",
            )
        finally:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    self._reserved_release_ids.discard(job.get("release_id"))
                    job["_process"] = None
                    self._persist_job(job)

    def _run_command(self, job_id, command):
        self._check_canceled(job_id)
        job = self._get_internal_job(job_id)
        log_path = Path(job["log_path"])
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with log_path.open("a", encoding="utf-8") as log_handle:
            log_handle.write("\n$ " + " ".join(command) + "\n")
            log_handle.flush()

            process = subprocess.Popen(
                command,
                cwd=str(self.repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["_process"] = process
                    job["pid"] = process.pid
                    now = self._utcnow()
                    job["heartbeat_at"] = now
                    job["lease_expires_at"] = now
                    self._persist_job(job)

            output_lines = []
            try:
                while True:
                    line = process.stdout.readline() if process.stdout is not None else ""
                    if line:
                        output_lines.append(line.rstrip())
                        log_handle.write(line)
                        log_handle.flush()
                        self._set_state(job_id, heartbeat_at=self._utcnow(), lease_expires_at=self._utcnow())

                    if self._is_cancel_requested(job_id):
                        process.terminate()
                        raise JobCancelledError()

                    if process.poll() is not None:
                        break

                if process.stdout is not None:
                    for line in process.stdout.read().splitlines():
                        output_lines.append(line)
                        log_handle.write(line + "\n")
                    log_handle.flush()

                if process.returncode != 0:
                    tail = "\n".join(output_lines[-20:])
                    raise RuntimeError(
                        "Pipeline command failed. Check job logs for details."
                        + (f"\nRecent output:\n{tail}" if tail else "")
                    )
            finally:
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        job["_process"] = None
                        job["pid"] = None

    def _write_release_metadata(self, job):
        release_dir = self.release_root / job["release_id"]
        manifest_path = release_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("Release manifest is missing after build.")

        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        manifest["display_name"] = job["metadata"]["report_name"]
        manifest["program"] = job["metadata"]["project_name"]
        manifest["target"] = job["metadata"]["target_name"]
        manifest["report_name"] = job["metadata"]["report_name"]
        manifest["project_name"] = job["metadata"]["project_name"]
        manifest["target_name"] = job["metadata"]["target_name"]
        manifest["uploader"] = {
            "username": job["metadata"].get("uploader_username") or "",
            "email": job["metadata"].get("uploader_email") or "",
            "group": job["metadata"].get("uploader_group") or "",
        }
        manifest["source_files"] = {
            "docking_sdf": Path(job["uploads"]["docking_sdf"]).name,
            "interaction_csv": Path(job["uploads"]["interaction_csv"]).name,
            "property_csv": Path(job["uploads"].get("property_csv", "")).name if job["uploads"].get("property_csv") else "",
            "protein_pdb": Path(job["uploads"].get("protein_pdb", "")).name if job["uploads"].get("protein_pdb") else "",
        }
        manifest["pipeline_version"] = "process_docking_IF_show_docking.py"
        manifest["report_version"] = "hosted_portal_v1"
        manifest["created_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        manifest.setdefault("source", {})
        manifest["source"]["generated_by"] = "hosted_portal_upload"
        manifest["source"]["job_id"] = job["job_id"]
        manifest.setdefault("build", {})
        manifest["build"]["inputs"] = {
            "interaction_id_col": job["pipeline"]["interaction_id_col"],
            "interaction_count_col": job["pipeline"]["interaction_count_col"],
            "top_per_scaffold": job["pipeline"]["top_per_scaffold"],
            "max_scaffolds_in_report": job["pipeline"]["max_scaffolds_in_report"],
            "n_workers": job["pipeline"]["n_workers"],
            "auto_detect_score": job["pipeline"]["auto_detect_score"],
            "report_max_width": job["pipeline"]["report_max_width"],
        }

        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)

    def _set_state(self, job_id, **changes):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in changes.items():
                job[key] = value
            if job.get("status") == "running" and not job.get("started_at"):
                job["started_at"] = self._utcnow()
            job["updated_at"] = self._utcnow()
            self._persist_job(job)

    def _persist_job(self, job):
        out = self._public_job_dict(job)
        job_state_path = self.job_root / job["job_id"] / "job.json"
        job_state_path.parent.mkdir(parents=True, exist_ok=True)
        with job_state_path.open("w", encoding="utf-8") as handle:
            json.dump(out, handle, indent=2)

    def _public_job_dict(self, job):
        log_tail = self._tail_log(job.get("log_path"), max_lines=25)
        return {
            "job_id": job.get("job_id"),
            "schema_version": job.get("schema_version", self.schema_version),
            "status": job.get("status"),
            "stage": job.get("stage"),
            "progress": job.get("progress"),
            "message": job.get("message"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "release_id": job.get("release_id"),
            "release_url": job.get("release_url"),
            "cancel_requested": bool(job.get("cancel_requested")),
            "error": job.get("error"),
            "inputs": job.get("inputs"),
            "uploads": job.get("uploads"),
            "metadata": job.get("metadata") or {},
            "pipeline": job.get("pipeline") or {},
            "runner_id": job.get("runner_id"),
            "pid": job.get("pid"),
            "heartbeat_at": job.get("heartbeat_at"),
            "lease_expires_at": job.get("lease_expires_at"),
            "recovery_count": int(job.get("recovery_count") or 0),
            "interrupted_reason": job.get("interrupted_reason"),
            "failure_stage": job.get("failure_stage"),
            "log_tail": log_tail,
        }

    def _tail_log(self, log_path, max_lines=25):
        if not log_path:
            return []
        path = Path(log_path)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
        return [line.rstrip("\n") for line in lines[-max_lines:]]

    def _scan_job_state_files(self):
        return sorted(self.job_root.glob("*/job.json"))

    def _rehydrate_jobs_from_disk(self):
        loaded = 0
        for state_path in self._scan_job_state_files():
            try:
                with state_path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                continue
            job_id = str(data.get("job_id") or "").strip()
            if not job_id:
                continue
            job_dir = state_path.parent
            job = {
                "job_id": job_id,
                "status": data.get("status") or "failed",
                "stage": data.get("stage") or "Recovered",
                "progress": data.get("progress") or 0,
                "message": data.get("message") or "Recovered from durable state.",
                "created_at": data.get("created_at") or self._utcnow(),
                "updated_at": data.get("updated_at") or data.get("created_at") or self._utcnow(),
                "started_at": data.get("started_at"),
                "completed_at": data.get("completed_at"),
                "release_id": data.get("release_id") or "",
                "release_url": data.get("release_url") or "",
                "cancel_requested": bool(data.get("cancel_requested")),
                "error": data.get("error"),
                "log_path": str(job_dir / "job.log"),
                "workspace_dir": str(job_dir / "workspace"),
                "report_out_dir": str(job_dir / "workspace" / "report_build"),
                "uploads": data.get("uploads") or {},
                "inputs": data.get("inputs") or {},
                "metadata": data.get("metadata") or {},
                "pipeline": data.get("pipeline") or {},
                "schema_version": int(data.get("schema_version") or self.schema_version),
                "runner_id": data.get("runner_id"),
                "pid": data.get("pid"),
                "heartbeat_at": data.get("heartbeat_at"),
                "lease_expires_at": data.get("lease_expires_at"),
                "recovery_count": int(data.get("recovery_count") or 0),
                "interrupted_reason": data.get("interrupted_reason"),
                "failure_stage": data.get("failure_stage"),
                "_process": None,
            }
            status = str(job.get("status") or "").strip().lower()
            if status == "running":
                job["status"] = "orphaned"
                job["stage"] = "Orphaned"
                job["error"] = "Portal restart interrupted this running job."
                job["message"] = "Job recovered as orphaned after restart."
                job["interrupted_reason"] = "interrupted_on_restart"
                job["completed_at"] = self._utcnow()
                job["recovery_count"] = int(job.get("recovery_count") or 0) + 1
            with self._lock:
                self._jobs[job_id] = job
                if job.get("status") not in _TERMINAL_STATUS and job.get("status") != "queued":
                    job["status"] = "failed"
            loaded += 1

        if loaded:
            with self._lock:
                for job in self._jobs.values():
                    self._persist_job(job)

    def _get_internal_job(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise RuntimeError("Job not found.")
            return dict(job)

    def _is_cancel_requested(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return bool(job and job.get("cancel_requested"))

    def _check_canceled(self, job_id):
        if self._is_cancel_requested(job_id):
            raise JobCancelledError()

    def _coerce_int(self, value, field_name, min_value, max_value):
        try:
            cast = int(str(value).strip())
        except Exception as exc:
            raise JobValidationError(f"{field_name} must be an integer.") from exc
        if cast < min_value or cast > max_value:
            raise JobValidationError(f"{field_name} must be between {min_value} and {max_value}.")
        return cast

    def _coerce_bool(self, value):
        normalized = str(value).strip().lower()
        return normalized in {"1", "true", "yes", "on"}

    def _sanitize_release_token(self, text):
        value = str(text or "").strip()
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
        return safe or "hosted_release"

    def _format_public_error(self, text):
        clean = str(text or "").strip()
        if not clean:
            return "Unknown pipeline error."
        clean = clean.replace(str(self.repo_root), "<workspace>")
        return clean

    def _utcnow(self):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
