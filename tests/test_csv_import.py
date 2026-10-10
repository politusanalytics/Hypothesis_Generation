import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

from scripts import local_clickhouse as setup


class TestCsvImport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.out = self.folder / "private"
        self.users = {"id": "18446744073709551615", "location": "", "province_code": "34",
            "country_code": "TR", "created_at": "\\N", "gender": "female", "age_range": "25-34",
            "is_org": "false", "data_source": "demo", "insertion_date": "2025-01-01 12:30:00"}
        self.predictions = {"id": "p-1", "tweet_id": "brand:123", "tweet_created_at": "2025-01-01 12:30:00",
            "author_id": self.users["id"], "data_source": "demo", "country_code": "TR", "task_name": "sentiment",
            "scope_type": "", "scope_value": "", "numeric_value": "NULL", "category_value": '["complaint", "purchase"]',
            "boolean_value": "\\N", "prediction_created_at": "2025-01-01 15:30:00+03:00",
            "prediction_month": "202501", "tweet_date": "250101"}

    def source(self, table, row):
        path = self.folder / f"{table}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(setup.SCHEMAS[table]))
            writer.writeheader()
            writer.writerow(row)
        return path

    def prepare(self):
        return setup.prepare(self.source("users", self.users),
                             self.source("tweet_predictions", self.predictions), self.out)

    def test_conversion_preserves_ids_nulls_and_raw_categories(self):
        manifest = self.prepare()
        self.assertEqual(manifest["tables"]["users"]["rows"], 1)
        with gzip.open(self.out / "users.jsonl.gz", "rt", encoding="utf-8") as f:
            user = json.loads(f.readline())
        self.assertEqual(user["id"], self.users["id"])
        self.assertIsNone(user["created_at"])
        self.assertEqual(user["is_org"], 0)
        with gzip.open(self.out / "tweet_predictions.jsonl.gz", "rt", encoding="utf-8") as f:
            pred = json.loads(f.readline())
        self.assertEqual(pred["tweet_id"], "brand:123")
        self.assertEqual(pred["category_value"], self.predictions["category_value"])
        self.assertIsNone(pred["numeric_value"])
        self.assertEqual(pred["prediction_created_at"], "2025-01-01 12:30:00.000")

    def test_settings_are_read_only_grants_and_are_not_rotated(self):
        self.prepare()
        before = (self.out / "settings.json").read_bytes()
        self.prepare()
        self.assertEqual(before, (self.out / "settings.json").read_bytes())
        config = tomllib.loads((self.out / "streamlit-local.toml").read_text())
        self.assertEqual(config["CLICKHOUSE_TABLES"], "users,tweet_predictions")
        self.assertEqual(config["CLICKHOUSE_USERNAME"], "dataset_analyst")
        queries = ET.parse(self.out / "analyst.xml").findall("users/dataset_analyst/grants/query")
        self.assertTrue(all(q.text.startswith("GRANT SELECT") for q in queries))

    def test_duplicate_source_ids_are_preserved_and_reported(self):
        path = self.source("users", self.users)
        with path.open("a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=list(setup.SCHEMAS["users"])).writerow({**self.users, "gender": "unknown"})
        self.out.mkdir()
        info, _, _ = setup.export_csv(path, "users", self.out / "users.jsonl.gz")
        self.assertEqual((info["rows"], info["distinct_ids"], info["duplicate_id_rows"]), (2, 1, 1))

    def test_validation_error_contains_no_record_values_or_valid_manifest(self):
        self.prepare()
        self.users["province_code"] = "private-secret"
        with self.assertRaises(setup.DatasetError) as caught:
            self.prepare()
        self.assertNotIn("private-secret", str(caught.exception))
        self.assertFalse((self.out / "manifest.json").exists())

    def test_changed_export_never_connects_to_server(self):
        self.prepare()
        with (self.out / "users.jsonl.gz").open("ab") as f:
            f.write(b"changed")
        with patch.object(setup, "local_client") as connect:
            with self.assertRaises(setup.DatasetError):
                setup.load(self.out)
        connect.assert_not_called()

    def test_existing_table_is_not_modified(self):
        self.prepare()
        client = MagicMock()
        client.command.return_value = "1"
        with patch.object(setup, "local_client", return_value=client), self.assertRaises(setup.DatasetError):
            setup.load(self.out)
        self.assertEqual(client.command.call_count, 1)
        client.insert.assert_not_called()
        client.close.assert_called_once()

    def test_successful_load_uses_staging_and_typed_dates(self):
        self.prepare()
        client = MagicMock()
        client.command.return_value = "0"
        client.query.return_value.result_rows = [(1,)]
        with patch.object(setup, "local_client", return_value=client):
            self.assertEqual(setup.load(self.out), {"users": 1, "tweet_predictions": 1})
        self.assertEqual(client.insert.call_count, 2)
        commands = [c.args[0] for c in client.command.call_args_list]
        self.assertEqual(sum(c.startswith("RENAME TABLE") for c in commands), 1)
        self.assertTrue(all("_import_" in c for c in commands if c.startswith("DROP")))
        batch = client.insert.call_args_list[1].args[1]
        self.assertIsNotNone(batch[0][2].tzinfo)

    def test_partial_insert_failure_cleans_only_own_staging_table(self):
        self.prepare()
        client = MagicMock()
        client.command.return_value = 0
        client.insert.side_effect = RuntimeError("private-driver-error")
        with patch.object(setup, "local_client", return_value=client), self.assertRaises(RuntimeError):
            setup.load(self.out)
        commands = [c.args[0] for c in client.command.call_args_list]
        self.assertFalse(any(c.startswith("RENAME") for c in commands))
        self.assertEqual(sum(c.startswith("DROP TABLE IF EXISTS `brand_analytics`.`users_import_") for c in commands), 1)

    def test_cloud_settings_require_https_and_separate_analyst_password(self):
        self.prepare()
        for url in ("http://example.test", "https://user:password@example.test", "https://example.test/path"):
            with self.subTest(url=url), self.assertRaises(setup.DatasetError):
                setup.cloud_config(url, self.out)
        output = setup.cloud_config("https://demo.ngrok-free.app", self.out)
        config = tomllib.loads(output.read_text())
        self.assertEqual(config["CLICKHOUSE_HOST"], "demo.ngrok-free.app")
        self.assertEqual(config["CLICKHOUSE_PORT"], "443")
        self.assertNotEqual(config["CLICKHOUSE_PASSWORD"], json.loads((self.out / "settings.json").read_text())["import_password"])

    def test_plain_driver_value_error_is_not_printed(self):
        with patch.object(setup, "load", side_effect=ValueError("private-password")), \
             patch("sys.argv", ["local_clickhouse.py", "load"]), patch("sys.stderr", new_callable=io.StringIO) as errors:
            self.assertEqual(setup.main(), 1)
            self.assertNotIn("private-password", errors.getvalue())
