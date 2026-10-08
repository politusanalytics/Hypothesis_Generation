"""Offline tests for ClickHouse-only isolation, validation and compilation."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_analysis import ClickHouseAnalysisEngine, get_analysis_engine, validate_plan

# Load the dependency-free compiler without importing agents' LangChain exports.
spec = importlib.util.spec_from_file_location(
    "analysis_test_compiler", Path(__file__).resolve().parents[1] / "agents" / "sql_compiler.py")
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)


class TestClickHouseAnalysis(unittest.TestCase):
    def test_missing_connection_never_falls_back(self):
        with self.assertRaisesRegex(ValueError, "CLICKHOUSE_HOST"):
            get_analysis_engine("test", lambda key, default="": default)

    def test_plan_is_copied_and_bounded(self):
        source = {"table": "tweets"}
        self.assertEqual(validate_plan(source)["limit"], 1000)
        self.assertNotIn("limit", source)
        for limit in (0, -1, 1001, True, "10"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                validate_plan({"table": "tweets", "limit": limit})

    def test_rejects_other_tables_and_nested_tables(self):
        for plan in (
            {"table": "system.users"},
            {"table": "tweets", "joins": [{"table": "secret"}]},
            {"table": "tweets", "filters": [{"column": "id", "op": "IN",
                "value": {"table": "secret", "columns": ["id"]}}]},
        ):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                validate_plan(plan)

    def test_subquery_membership_is_not_silently_truncated(self):
        plan = validate_plan({"table": "tweets", "filters": [
            {"column": "author_id", "op": "IN", "value": {
                "table": "users", "columns": ["id"]}}]})
        self.assertNotIn("limit", plan["filters"][0]["value"])

    def test_rejects_raw_join_and_unknown_filters(self):
        for plan in (
            {"table": "tweets", "joins": [{"table": "users", "on": "1; DROP TABLE tweets"}]},
            {"table": "tweets", "filters": [{"column": "id", "op": "UNKNOWN"}]},
            {"table": "tweets", "filters": [{"column": "id", "op": "BETWEEN", "value": [1]}]},
            {"table": "tweets", "columns": ["url('https://example.com')"]},
            {"table": "tweets", "filters": "unexpected"},
        ):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                validate_plan(plan)

    def test_executes_native_clickhouse_with_named_columns(self):
        planner = MagicMock()
        planner.generate_query_json.return_value = {
            "table": "tweets", "aggregates": [{"op": "count", "as": "total"}]}
        client = MagicMock()
        client.query.return_value.column_names = ["total"]
        client.query.return_value.result_rows = [(42,)]
        engine = ClickHouseAnalysisEngine(client, planner)
        with patch.dict(sys.modules, {"agents.sql_compiler": compiler}):
            result = engine.execute("Kaç tweet var?")
        self.assertEqual(result["rows"], [(42,)])
        self.assertEqual(result["columns"], ["total"])
        self.assertEqual(result["sql"], "SELECT count(*) AS `total` FROM `tweets` LIMIT 1000")
        self.assertEqual(client.query.call_args.kwargs["settings"]["readonly"], 1)

    def test_invalid_plan_never_reaches_database(self):
        planner = MagicMock()
        planner.generate_query_json.return_value = {"table": "secret"}
        client = MagicMock()
        with patch.dict(sys.modules, {"agents.sql_compiler": compiler}), self.assertRaises(ValueError):
            ClickHouseAnalysisEngine(client, planner).execute("secret")
        client.query.assert_not_called()

    def test_clickhouse_escapes_backslashes_and_quotes(self):
        value = "path\\' OR 1=1"
        self.assertEqual(compiler._lit(value, dialect="clickhouse"), "'path\\\\'' OR 1=1'")
        for op in ("EQ", "LIKE", "HAS", "IN", "HAS_ANY", "BETWEEN"):
            val = [value, value] if op in ("IN", "HAS_ANY", "BETWEEN") else value
            sql = compiler.compile_json_to_sql({"table": "tweets", "filters": [
                {"column": "text", "op": op, "value": val}]}, dialect="clickhouse")
            self.assertIn("path\\\\''", sql)

    def test_connection_failure_propagates(self):
        connector = MagicMock()
        connector.get_client.side_effect = ConnectionError("offline")
        query_module = MagicMock()
        config = {"CLICKHOUSE_HOST": "test-host"}
        with patch.dict(sys.modules, {"clickhouse_connect": connector, "agents.query_agent": query_module}):
            with self.assertRaisesRegex(ValueError, "ClickHouse"):
                get_analysis_engine("test", lambda key, default="": config.get(key, default))
        query_module.QueryAgent.assert_not_called()


if __name__ == "__main__":
    unittest.main()
