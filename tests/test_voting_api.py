import os
import tempfile
import unittest

from app import create_app


class VotingApiTestCase(unittest.TestCase):
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

        os.makedirs(os.environ["HOSTED_PORTAL_RELEASE_ROOT"], exist_ok=True)
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmpdir.cleanup()

    def test_scaffold_vote_updates_existing_vote(self):
        payload = {
            "release_id": "release_alpha",
            "scaffold_id": "SCF-001",
            "username": "John Eksterowicz",
            "vote_type": "LIKE",
        }
        response = self.client.post("/api/votes/scaffold", json=payload)
        self.assertEqual(response.status_code, 200)

        payload["vote_type"] = "PRIORITY"
        response = self.client.post("/api/votes/scaffold", json=payload)
        self.assertEqual(response.status_code, 200)

        summary = self.client.get(
            "/api/votes/scaffold/SCF-001",
            query_string={"release_id": "release_alpha", "username": "John Eksterowicz"},
        )
        self.assertEqual(summary.status_code, 200)
        body = summary.get_json()
        self.assertEqual(body["counts"]["LIKE"], 0)
        self.assertEqual(body["counts"]["PRIORITY"], 1)
        self.assertEqual(body["user_vote"], "PRIORITY")
        self.assertGreaterEqual(len(body.get("history", [])), 2)

    def test_cross_user_release_polling_payload(self):
        self.client.post(
            "/api/votes/scaffold",
            json={
                "release_id": "release_beta",
                "scaffold_id": "SCF-015",
                "username": "Scientist A",
                "vote_type": "LIKE",
            },
        )

        response_b = self.client.get(
            "/api/votes/release/release_beta",
            query_string={"username": "Scientist B"},
        )
        self.assertEqual(response_b.status_code, 200)
        payload_b = response_b.get_json()
        self.assertEqual(payload_b["scaffold_votes"]["SCF-015"]["counts"]["LIKE"], 1)

        self.client.post(
            "/api/votes/molecule",
            json={
                "release_id": "release_beta",
                "molecule_id": "EN300-5002668_27207",
                "username": "Scientist B",
                "vote_type": "REJECT",
            },
        )

        response_a = self.client.get(
            "/api/votes/release/release_beta",
            query_string={"username": "Scientist A"},
        )
        self.assertEqual(response_a.status_code, 200)
        payload_a = response_a.get_json()
        self.assertEqual(
            payload_a["molecule_votes"]["EN300-5002668_27207"]["counts"]["REJECT"],
            1,
        )

    def test_molecule_priority_vote_is_accepted(self):
        # Part 7: PRIORITY is now a valid molecule vote type.
        response = self.client.post(
            "/api/votes/molecule",
            json={
                "release_id": "release_delta",
                "molecule_id": "EN300-ABC",
                "username": "Scientist C",
                "vote_type": "PRIORITY",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["vote"]["vote_type"], "PRIORITY")

    def test_votes_persist_across_app_restart(self):
        self.client.post(
            "/api/votes/molecule",
            json={
                "release_id": "release_gamma",
                "molecule_id": "EN300-XYZ",
                "username": "Monika Williams",
                "vote_type": "REJECT",
            },
        )

        app_restarted = create_app()
        client_restarted = app_restarted.test_client()

        response = client_restarted.get(
            "/api/votes/molecule/EN300-XYZ",
            query_string={"release_id": "release_gamma", "username": "Monika Williams"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["counts"]["REJECT"], 1)
        self.assertEqual(payload["user_vote"], "REJECT")


if __name__ == "__main__":
    unittest.main()
