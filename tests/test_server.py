import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        server.REPORTS_INDEX.clear()
        server.UPLOADS_INDEX.clear()

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "log-analyzer", "version": "1.0.0"})

    def test_upsert_and_get_report(self):
        payload = {
            "job_id": "job-123",
            "job_status": "completed",
            "stats": {"parsed_count": 5},
            "rca_report": {"severity": "CRITICAL"},
        }

        upsert = self.client.post("/logs/report/job-123", json=payload)
        fetch = self.client.get("/logs/report/job-123")
        status = self.client.get("/logs/status/job-123")

        self.assertEqual(upsert.status_code, 200)
        self.assertEqual(fetch.status_code, 200)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(fetch.json()["data"]["job_id"], "job-123")
        self.assertEqual(status.json()["data"]["job_status"], "completed")

    def test_summary_endpoint_uses_db_summary(self):
        with patch("server.get_summary", return_value={"NORMAL": 2, "CRITICAL": 1}):
            response = self.client.get("/summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], {"NORMAL": 2, "CRITICAL": 1})

    def test_upload_endpoint_accepts_file_and_registers_job(self):
        with patch.object(server, "_start_job_background", return_value=None):
            response = self.client.post(
                "/logs/upload",
                files={"file": ("app.log", b"2026-05-13 12:00:01 INFO [AuthService] User logged in (#1)\n", "text/plain")},
            )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "accepted")
        self.assertIn(body["job_id"], server.UPLOADS_INDEX)


if __name__ == "__main__":
    unittest.main()
