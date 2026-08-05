import json
import os
import tempfile
import unittest

from app import create_app


class ReleaseDeleteApiTestCase(unittest.TestCase):
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
        os.makedirs(os.environ["HOSTED_PORTAL_RELEASE_ROOT"], exist_ok=True)

    def tearDown(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmpdir.cleanup()

    def _write_release(self, release_id):
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
            "created_at": "2026-08-04",
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

        return release_dir

    def test_index_hides_delete_controls_when_disabled(self):
        os.environ["HOSTED_PORTAL_ALLOW_RELEASE_DELETE"] = "false"
        self._write_release("release_alpha")

        app = create_app()
        client = app.test_client()
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertNotIn("Delete Selected Reports", body)
        self.assertIn("Release deletion disabled by configuration.", body)

    def test_batch_delete_removes_release_dir_when_enabled(self):
        os.environ["HOSTED_PORTAL_ALLOW_RELEASE_DELETE"] = "true"
        release_dir = self._write_release("release_alpha")

        app = create_app()
        client = app.test_client()
        response = client.post("/api/releases/batch-delete", json={"release_ids": ["release_alpha"]})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["requested"], 1)
        self.assertEqual(len(payload["deleted"]), 1)
        self.assertFalse(os.path.exists(release_dir))

    def test_batch_delete_preflight_blocks_partial_delete(self):
        os.environ["HOSTED_PORTAL_ALLOW_RELEASE_DELETE"] = "true"
        release_a_dir = self._write_release("release_alpha")
        self._write_release("release_beta")

        app = create_app()
        client = app.test_client()
        response = client.post(
            "/api/releases/batch-delete",
            json={"release_ids": ["release_alpha", "release_missing"]},
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(os.path.exists(release_a_dir))

    def test_configured_default_release_cannot_be_deleted(self):
        os.environ["HOSTED_PORTAL_ALLOW_RELEASE_DELETE"] = "true"
        os.environ["HOSTED_PORTAL_ACTIVE_RELEASE"] = "release_alpha"
        release_dir = self._write_release("release_alpha")

        app = create_app()
        client = app.test_client()
        response = client.post("/api/releases/batch-delete", json={"release_ids": ["release_alpha"]})

        self.assertEqual(response.status_code, 403)
        payload = response.get_json()
        self.assertIn("configured default release", payload["error"])
        self.assertTrue(os.path.exists(release_dir))


if __name__ == "__main__":
    unittest.main()