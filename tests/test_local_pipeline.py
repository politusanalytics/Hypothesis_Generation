from pathlib import Path
import tempfile
import unittest

from database import SQLiteDatabase
from agents.query_agent import QueryAgent
from scripts.create_demo import create_demo
from statistical_analysis import test_database_groups
from forecasting import regular_series, forecast_series


class TestLocalPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        path = create_demo(Path(cls.folder.name) / "demo.db")
        cls.db = SQLiteDatabase(path)
        cls.agent = QueryAgent(db=cls.db, dialect="sqlite", catalog=cls.db.catalog)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_full_population_statistics_exceed_row_limit(self):
        result = test_database_groups(self.agent, "tweets", "issue", "delivery", "service", "engagement", "welch")
        self.assertGreater(result["n_a"] + result["n_b"], 1000)
        self.assertEqual(result["decision"], "H0 reddedildi")
        self.assertGreater(result["n_a"], result["n_b"])
        binary = test_database_groups(self.agent, "tweets", "issue", "delivery", "service", "sentiment",
                                       "fisher", "positive")
        self.assertLess(binary["p_value"], 0.05)

    def test_time_aggregation_and_forecast_from_database(self):
        result = self.agent.execute_plan({"table": "tweets", "time_bucket": {
            "column": "created_at", "grain": "month", "as": "period"}, "group_by": ["period"],
            "aggregates": [{"op": "count", "as": "value"}],
            "order_by": [{"column": "period", "dir": "asc"}]})
        series = regular_series(result["result"], "month")
        forecast = forecast_series(series, 3)
        self.assertEqual(len(forecast["forecast"]), 3)
        self.assertEqual(len(series), 30)

    def test_readonly_and_schema_rejection(self):
        with self.assertRaises(Exception):
            self.db.run("DELETE FROM tweets")
        with self.assertRaises(ValueError):
            self.agent.execute_plan({"table": "tweets", "columns": ["unknown"]})
        with self.assertRaises(ValueError):
            self.agent.execute_plan({"table": "sqlite_master"})
