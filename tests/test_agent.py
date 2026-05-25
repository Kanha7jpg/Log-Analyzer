import os
import tempfile
import unittest

import agent


class AgentTests(unittest.TestCase):
    def test_parse_log_line_parses_expected_format(self):
        line = "2026-05-13 12:00:01 INFO [AuthService] User logged in (#1)"

        parsed = agent.parse_log_line(line)

        self.assertEqual(
            parsed,
            {
                "timestamp": "2026-05-13 12:00:01",
                "level": "INFO",
                "service": "AuthService",
                "message": "User logged in (#1)",
            },
        )

    def test_parse_log_line_rejects_invalid_format(self):
        self.assertIsNone(agent.parse_log_line("invalid log line"))

    def test_process_file_sync_produces_stats_and_rca_without_external_services(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "app.log")
            with open(log_file, "w", encoding="utf-8") as file:
                file.write("2026-05-13 12:00:01 INFO [AuthService] User logged in (#1)\n")
                file.write("2026-05-13 12:00:02 WARNING [OrderService] Order processing delayed (#2)\n")
                file.write("2026-05-13 12:00:03 ERROR [PaymentService] Payment failed for ID 123 (#3)\n")

            state = agent.process_file_sync(log_file, job_id="test-job", persist=False)

        self.assertEqual(state["total_count"], 3)
        self.assertEqual(state["stats"]["parsed_count"], 3)
        self.assertEqual(state["job_id"], "test-job")
        self.assertEqual(state["job_status"], "pending")
        self.assertIn("rca_report", state)
        self.assertEqual(state["rca_report"]["severity"], "CRITICAL")
        self.assertEqual(len(state["classified_logs"]), 3)


if __name__ == "__main__":
    unittest.main()
