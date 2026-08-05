import json
import os
import re
import tempfile
import unittest

from app import create_app


class ReleaseSourceOfTruthTestCase(unittest.TestCase):
    def setUp(self):
        self._env_backup = {
            "HOSTED_PORTAL_VOTE_DB_PATH": os.environ.get("HOSTED_PORTAL_VOTE_DB_PATH"),
            "HOSTED_PORTAL_RELEASE_ROOT": os.environ.get("HOSTED_PORTAL_RELEASE_ROOT"),
            "HOSTED_PORTAL_UPLOAD_ROOT": os.environ.get("HOSTED_PORTAL_UPLOAD_ROOT"),
            "HOSTED_PORTAL_JOB_ROOT": os.environ.get("HOSTED_PORTAL_JOB_ROOT"),
            "HOSTED_PORTAL_CACHE_DIR": os.environ.get("HOSTED_PORTAL_CACHE_DIR"),
            "HOSTED_PORTAL_BASE_URL": os.environ.get("HOSTED_PORTAL_BASE_URL"),
            "HOSTED_PORTAL_ALLOW_RELEASE_DELETE": os.environ.get("HOSTED_PORTAL_ALLOW_RELEASE_DELETE"),
            "HOSTED_PORTAL_ACTIVE_RELEASE": os.environ.get("HOSTED_PORTAL_ACTIVE_RELEASE"),
        }

        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["HOSTED_PORTAL_VOTE_DB_PATH"] = os.path.join(self.tmpdir.name, "votes.sqlite3")
        os.environ["HOSTED_PORTAL_RELEASE_ROOT"] = os.path.join(self.tmpdir.name, "releases")
        os.environ["HOSTED_PORTAL_UPLOAD_ROOT"] = os.path.join(self.tmpdir.name, "uploads")
        os.environ["HOSTED_PORTAL_JOB_ROOT"] = os.path.join(self.tmpdir.name, "jobs")
        os.environ["HOSTED_PORTAL_CACHE_DIR"] = os.path.join(self.tmpdir.name, "cache")
        os.environ["HOSTED_PORTAL_BASE_URL"] = "http://127.0.0.1:5005"
        os.environ["HOSTED_PORTAL_ALLOW_RELEASE_DELETE"] = "true"

        os.makedirs(os.environ["HOSTED_PORTAL_RELEASE_ROOT"], exist_ok=True)

    def tearDown(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmpdir.cleanup()

    def _write_release(self, release_id, created_at):
        release_dir = os.path.join(os.environ["HOSTED_PORTAL_RELEASE_ROOT"], release_id)
        os.makedirs(os.path.join(release_dir, "data"), exist_ok=True)

        for name in ("scaffolds.json", "molecules.json", "pose_index.json"):
            with open(os.path.join(release_dir, "data", name), "w", encoding="utf-8") as handle:
                json.dump([], handle)

        with open(os.path.join(release_dir, "report.html"), "w", encoding="utf-8") as handle:
            handle.write("<html><body>report</body></html>")

        manifest = {
            "release_id": release_id,
            "display_name": release_id,
            "created_at": created_at,
            "program": "PPI",
            "target": "STAT6",
            "description": "fixture",
            "files": {
                "scaffolds": "data/scaffolds.json",
                "molecules": "data/molecules.json",
                "pose_index": "data/pose_index.json",
                "static_report": "report.html",
            },
        }
        with open(os.path.join(release_dir, "manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)

    def _extract_select_option_values(self, html, select_id):
        pattern = re.compile(
            r'<select[^>]*id="%s"[^>]*>(.*?)</select>' % re.escape(select_id),
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(html)
        self.assertIsNotNone(match, f"Missing select id={select_id}")
        options_html = match.group(1)
        return re.findall(r'<option[^>]*value="([^"]*)"', options_html, re.IGNORECASE)

    def test_homepage_and_operations_release_lists_match_api(self):
        self._write_release("release_20260804_001", "2026-08-04T00:00:01Z")
        self._write_release("release_20260804_002", "2026-08-04T00:00:02Z")
        self._write_release("release_20260804_003", "2026-08-04T00:00:03Z")

        app = create_app()
        client = app.test_client()

        api_response = client.get("/api/releases")
        self.assertEqual(api_response.status_code, 200)
        api_payload = api_response.get_json()
        api_release_ids = [item["release_id"] for item in api_payload["releases"]]

        home_response = client.get("/")
        self.assertEqual(home_response.status_code, 200)
        home_html = home_response.get_data(as_text=True)
        home_release_ids = self._extract_select_option_values(home_html, "release-picker")

        operations_response = client.get("/operations")
        self.assertEqual(operations_response.status_code, 200)
        operations_html = operations_response.get_data(as_text=True)
        operations_release_ids = self._extract_select_option_values(operations_html, "ops-release-id")

        self.assertEqual(home_release_ids, api_release_ids)
        self.assertEqual(operations_release_ids, api_release_ids)
        self.assertEqual(len(home_release_ids), len(operations_release_ids))

    def test_shared_frontend_release_sync_uses_single_api(self):
        app = create_app()
        client = app.test_client()

        response = client.get("/static/js/portal.js")
        self.assertEqual(response.status_code, 200)
        js = response.get_data(as_text=True)

        self.assertIn('fetch(apiPath("/api/releases"))', js)
        self.assertIn("function applySharedReleaseState(releases)", js)
        self.assertIn("startReleaseAutoSync", js)


if __name__ == "__main__":
    unittest.main()
