"""Verify Cloud TLS options and connection routing without network access."""
import unittest
from unittest.mock import MagicMock, patch

from database import connect_clickhouse
from agent import get_database_connection


class TestDatabaseConnection(unittest.TestCase):
    def test_https_options_reach_native_client(self):
        cases = [
            ({}, 8123, False, True),
            ({"CLICKHOUSE_PORT": "443"}, 443, True, True),
            ({"CLICKHOUSE_SECURE": "true"}, 8443, True, True),
            ({"CLICKHOUSE_PORT": "443", "CLICKHOUSE_VERIFY": "false"}, 443, True, False),
        ]
        for settings, port, secure, verify in cases:
            with self.subTest(settings=settings):
                connector = MagicMock()
                connector.get_client.return_value.query.return_value.result_rows = [("id", "UInt64")]
                config = {"CLICKHOUSE_HOST": "example.test", "CLICKHOUSE_TABLES": "tweets", **settings}
                with patch("clickhouse_connect.get_client", connector.get_client):
                    db = connect_clickhouse(lambda key, default="": config.get(key, default))
                args = connector.get_client.call_args.kwargs
                self.assertEqual((args["port"], args["secure"], args["verify"]), (port, secure, verify))
                self.assertEqual(db.catalog, {"tweets": {"id": "UInt64"}})

    def test_main_connection_uses_native_clickhouse_adapter(self):
        db = MagicMock()
        with patch("agent.get_secret", side_effect=lambda key, default="":
                   "clickhouse" if key == "DATABASE_BACKEND" else default), \
             patch("agent.connect_clickhouse", return_value=db) as connect:
            self.assertEqual(get_database_connection(), (db, "clickhouse", "clickhouse"))
        connect.assert_called_once()

    def test_clickhouse_error_never_routes_to_sqlite(self):
        with patch("agent.get_secret", side_effect=lambda key, default="":
                   "clickhouse" if key == "DATABASE_BACKEND" else default), \
             patch("agent.connect_clickhouse", side_effect=ConnectionError("offline")), \
             patch("agent.SQLiteDatabase") as sqlite:
            with self.assertRaisesRegex(ValueError, "ClickHouse"):
                get_database_connection()
        sqlite.assert_not_called()
