import unittest
import os
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import logger, log_query, StructuredExtraFormatter


class TestLogger(unittest.TestCase):

    def test_sensitive_payloads_and_traceback_are_masked(self):
        record = logging.LogRecord("test", logging.ERROR, __file__, 1,
                                   "Failed for %s with sk-secret-key", ("person@example.com",), None)
        record.question = "Alice's private question"
        record.sql = "SELECT 'private'"
        record.result_sample = "Alice"
        record.error = "password=secret"
        formatted = StructuredExtraFormatter("%(message)s").format(record)
        for secret in ("person@example.com", "sk-secret-key", "Alice", "SELECT", "password=secret"):
            self.assertNotIn(secret, formatted)
        self.assertIn("REDACTED", formatted)

    def setUp(self):
        self.log_dir = Path(__file__).parent.parent / "logs"
        self.log_file = self.log_dir / "app.log"

    def test_logger_instance(self):
        self.assertIsNotNone(logger)
        self.assertTrue(self.log_dir.exists())

    def test_structured_extra_formatter(self):
        formatter = StructuredExtraFormatter("%(asctime)s - %(levelname)s - %(message)s")
        record = logging.LogRecord(
            name="test_record",
            level=logging.INFO,
            pathname=__file__,
            lineno=25,
            msg="Custom test message",
            args=(),
            exc_info=None
        )
        record.event_type = "test_event"
        record.duration_ms = 12.5

        formatted = formatter.format(record)
        self.assertIn("Custom test message", formatted)
        self.assertIn("EXTRA:", formatted)
        self.assertIn('"event_type": "test_event"', formatted)
        self.assertIn('"duration_ms": 12.5', formatted)

    def test_log_query_success_and_error(self):
        log_query(
            question="Trendyol duygu analizi",
            json_query={"table": "demographics", "limit": 5},
            sql='SELECT * FROM "demographics" LIMIT 5',
            result=[(1, "18-29")],
            duration_ms=25.4
        )

        self.assertTrue(self.log_file.exists())
        with open(self.log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last_line = lines[-1]
        self.assertNotIn("Trendyol duygu analizi", last_line)
        self.assertNotIn("18-29", last_line)
        self.assertNotIn("SELECT", last_line)
        self.assertIn("query_execution", last_line)

        log_query(
            question="Hatalı tablo sorgusu",
            json_query={"table": "non_existent"},
            sql='SELECT * FROM "non_existent"',
            error="no such table: non_existent"
        )
        with open(self.log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last_line = lines[-1]
        self.assertIn("Query Failed", last_line)
        self.assertNotIn("Hatalı tablo sorgusu", last_line)
        self.assertNotIn("no such table", last_line)


if __name__ == "__main__":
    unittest.main()
