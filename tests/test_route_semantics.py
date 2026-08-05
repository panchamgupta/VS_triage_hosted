import json
import os
import tempfile
import unittest

from app import create_app


class RouteSemanticsTestCase(unittest.TestCase):
    def setUp(self):
        self._env_backup = {
            "HOSTED_PORTAL_VOTE_DB_PATH": os.environ.get("HOSTED_PORTAL_VOTE_DB_PATH"),
            "HOSTED_PORTAL_RELEASE_ROOT": os.environ.get("HOSTED_PORTAL_RELEASE_ROOT"),
            "HOSTED_PORTAL_UPLOAD_ROOT": os.environ.get("HOSTED_PORTAL_UPLOAD_ROOT"),
            "HOSTED_PORTAL_JOB_ROOT": os.environ.get("HOSTED_PORTAL_JOB_ROOT"),
            "HOSTED_PORTAL_CACHE_DIR": os.environ.get("HOSTED_PORTAL_CACHE_DIR"),
            "HOSTED_PORTAL_BASE_URL": os.environ.get("HOSTED_PORTAL_BASE_URL"),
        }
        self.tmpdir = tempfile.TemporaryDirectory()

        os.environ["HOSTED_PORTAL_VOTE_DB_PATH"] = os.path.join(self.tmpdir.name, "votes.sqlite3")
        os.environ["HOSTED_PORTAL_RELEASE_ROOT"] = os.path.join(self.tmpdir.name, "releases")
        os.environ["HOSTED_PORTAL_UPLOAD_ROOT"] = os.path.join(self.tmpdir.name, "uploads")
        os.environ["HOSTED_PORTAL_JOB_ROOT"] = os.path.join(self.tmpdir.name, "jobs")
        os.environ["HOSTED_PORTAL_CACHE_DIR"] = os.path.join(self.tmpdir.name, "cache")
        os.environ["HOSTED_PORTAL_BASE_URL"] = "http://127.0.0.1:5005"

        self.release_id = "release_20260803_001"
        release_root = os.environ["HOSTED_PORTAL_RELEASE_ROOT"]
        release_dir = os.path.join(release_root, self.release_id)
        os.makedirs(release_dir, exist_ok=True)

        for name in ("scaffolds.json", "molecules.json", "pose_index.json"):
            with open(os.path.join(release_dir, name), "w", encoding="utf-8") as handle:
                json.dump([], handle)

        with open(os.path.join(release_dir, "report.html"), "w", encoding="utf-8") as handle:
            handle.write(
                "<html><head><title>Report</title></head>"
                "<body><div class=\"idea-card\" data-scaffold=\"S1\"></div>"
                "<div class=\"moltile\" data-mol-id=\"M1\"></div></body></html>"
            )

        manifest = {
            "release_id": self.release_id,
            "display_name": "Route Semantics Release",
            "created_at": "2026-08-03T00:00:00Z",
            "program": "PPI",
            "target": "Target",
            "description": "Route semantics validation fixture",
            "files": {
                "scaffolds": "scaffolds.json",
                "molecules": "molecules.json",
                "pose_index": "pose_index.json",
                "static_report": "report.html",
            },
        }
        with open(os.path.join(release_dir, "manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)

        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmpdir.cleanup()

    def test_report_shell_contains_iframe_vote_bootstrap(self):
        response = self.client.get(f"/release/{self.release_id}/report")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('id="hosted-report-shell"', body)
        self.assertIn("hosted-report-vote-bootstrap", body)
        self.assertIn("data-vote-surface=\"iframe\"", body)

    def test_report_query_raw_and_posepopup_keep_legacy_payload(self):
        for query in ("raw=1", "posePopup=1", "posePopup=1&raw=1"):
            response = self.client.get(f"/release/{self.release_id}/report?{query}")
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertIn("data-scaffold=\"S1\"", body)
            self.assertNotIn("hosted-report-vote-bootstrap", body)
            self.assertNotIn('id="hosted-report-shell"', body)
            response.close()

    def test_explicit_raw_route_is_collaborative_augmented_payload(self):
        response = self.client.get(f"/release/{self.release_id}/report/raw")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("hosted-report-vote-bootstrap", body)
        self.assertIn("Collaborative Report Review", body)
        self.assertIn("data-scaffold=\"S1\"", body)

    def test_release_vote_endpoint_returns_200_for_existing_and_missing_release_ids(self):
        existing = self.client.get(f"/api/votes/release/{self.release_id}")
        self.assertEqual(existing.status_code, 200)
        existing_payload = existing.get_json()
        self.assertEqual(existing_payload["release_id"], self.release_id)

        missing = self.client.get("/api/votes/release/release_missing")
        self.assertEqual(missing.status_code, 200)
        missing_payload = missing.get_json()
        self.assertEqual(missing_payload["release_id"], "release_missing")
        self.assertEqual(missing_payload["scaffold_votes"], {})
        self.assertEqual(missing_payload["molecule_votes"], {})


if __name__ == "__main__":
    unittest.main()