"""Business meaning regressions: label scope, distinct posts/people and missing data."""
import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock
import numpy as np
import pandas as pd

from database import SQLiteDatabase
from marketing_data import MarketingDatabase
from agents.query_agent import QueryAgent
from business_analysis import BusinessAnalysis
from forecasting import forecast_series


class TestBusinessAnalysis(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        path = Path(self.folder.name) / "fixture.db"
        with closing(sqlite3.connect(path)) as c, c:
            c.executescript("""
              CREATE TABLE posts(tweet_id TEXT, author_id TEXT, published_at TEXT,
                                 gender TEXT, age_group TEXT, is_org INTEGER);
              CREATE TABLE audience(id TEXT, gender TEXT, age_group TEXT, is_org INTEGER);
              CREATE TABLE labels(tweet_id TEXT, author_id TEXT, published_at TEXT,
                                  gender TEXT, age_group TEXT, is_org INTEGER,
                                  analysis_type TEXT, label TEXT);
            """)
            posts = [("a", "one", "2024-01-01", "female", "18-29", 0),
                     ("b", "one", "2024-02-01", "female", "18-29", 0),
                     ("c", "two", "2024-02-01", "male", "40+", 0),
                     ("d", "three", "2024-03-01", "male", "40+", 0)]
            c.executemany("INSERT INTO posts VALUES(?,?,?,?,?,?)", posts)
            c.executemany("INSERT INTO audience VALUES(?,?,?,?)", [
                ("one", "female", "18-29", 0), ("two", "male", "40+", 0), ("three", "male", "40+", 0)])
            by_id = {p[0]: p for p in posts}
            rows = [("a", "emotion", "ofke"), ("a", "emotion", "ofke"),
                    ("a", "emotion", "notr"), ("b", "emotion", "ofke"),
                    ("c", "emotion", "notr"), ("d", "emotion", "ofke"),
                    ("a", "journey", "Complaint"), ("b", "journey", "Purchase"),
                    ("a", "topic", "Destek"), ("b", "topic", "Teslimat"),
                    ("c", "topic", "Teslimat"), ("d", "topic", "Teslimat"),
                    ("a", "brand", "demo-brand")]
            c.executemany("INSERT INTO labels VALUES(?,?,?,?,?,?,?,?)",
                          [by_id[p] + (kind, label) for p, kind, label in rows])
        self.db = MarketingDatabase.__new__(MarketingDatabase)
        self.db.source = SQLiteDatabase(path)
        self.db.catalog = self.db.source.catalog
        self.db.dialect = "sqlite"
        self.db.cte = ""
        self.db._labels = None
        self.agent = QueryAgent(db=self.db, dialect="sqlite", catalog=self.db.catalog)
        self.service = BusinessAnalysis(self.agent)

    def tearDown(self):
        self.folder.cleanup()

    def test_distributions_separate_types_and_deduplicate_posts(self):
        result = self.service.distribution("emotion", "gender")
        female = {r["label"]: r for r in result["rows"] if r["gender"] == "female"}
        self.assertEqual(female["ofke"]["total"], 2)
        self.assertEqual(female["ofke"]["share"], 100)
        self.assertEqual(female["notr"]["share"], 50)
        self.assertNotIn("demo-brand", female)

    def test_comparison_counts_people_once_not_posts(self):
        result = self.service.compare_people("emotion", "ofke", "gender", "female", "male")
        self.assertEqual((result["n_a"], result["n_b"]), (1, 2))
        self.assertEqual((result["rate_a"], result["rate_b"]), (1, .5))

    def test_missing_scope_including_nested_queries_is_rejected(self):
        plans = [{"table": "labels", "group_by": ["label"]},
                 {"table": "posts", "columns": ["tweet_id"], "filters": [
                     {"column": "tweet_id", "op": "IN", "value": {"table": "labels", "columns": ["tweet_id"]}}]}]
        for plan in plans:
            with self.subTest(plan=plan), self.assertRaisesRegex(ValueError, "analysis_type"):
                self.agent.execute_plan(plan)

    def test_count_of_label_rows_and_invented_labels_are_rejected(self):
        for fields in ({"aggregates": [{"op": "count", "as": "n"}]},
                       {"filters": [{"column": "analysis_type", "op": "EQ", "value": "emotion"},
                                    {"column": "label", "op": "EQ", "value": "Kahve Makinesi"}]}):
            plan = {"table": "labels", "filters": [{"column": "analysis_type", "op": "EQ", "value": "emotion"}], **fields}
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                self.agent.execute_plan(plan)

    def test_each_joined_label_alias_requires_its_own_scope(self):
        plan = {"table": "labels", "alias": "a", "joins": [
            {"table": "labels", "alias": "b", "on": {"left": "a.tweet_id", "right": "b.tweet_id"}}],
            "columns": ["a.label"], "filters": [{"column": "a.analysis_type", "op": "EQ", "value": "emotion"}]}
        with self.assertRaisesRegex(ValueError, "analysis_type"):
            self.agent.execute_plan(plan)

    def test_demographics_are_not_joined_by_gender_instead_of_person(self):
        plan = {"table": "posts", "alias": "p", "joins": [{"table": "audience", "alias": "a",
                "on": {"left": "p.gender", "right": "a.gender"}}],
                "aggregates": [{"op": "count_distinct", "column": "p.tweet_id", "as": "total"}]}
        with self.assertRaisesRegex(ValueError, "veri ilişkisi"):
            self.agent.execute_plan(plan)
        plan["joins"][0]["on"] = {"left": "p.author_id", "right": "a.id"}
        self.assertEqual(self.agent.execute_plan(plan)["result"][0]["total"], 4)

    def test_complaint_topics_use_the_same_posts(self):
        result = self.service.answer("Kadınların şikayet oranı nedir?")
        self.assertIn("%50.0", result["summary"])
        self.assertIn("Destek (1 paylaşım)", result["summary"])
        self.assertNotIn("Teslimat", result["summary"])
        self.assertIn(" IN (", result["distribution"]["sql"][-1])

    def test_specific_product_question_is_not_broadened(self):
        self.agent.execute_nl_query = MagicMock(return_value={"result": [], "sql": "", "json_query": {}})
        question = "Kahve makinesi şikayet oranı nedir?"
        self.service.answer(question)
        self.agent.execute_nl_query.assert_called_once_with(question)

    def test_complaint_by_age_does_not_return_purchase_as_leader(self):
        result = self.service.answer("Yaş gruplarına göre şikayet oranı nedir?")
        self.assertEqual([r["label"] for r in result["distribution"]["rows"]], ["Complaint"])
        self.assertEqual(result["distribution"]["rows"][0]["share"], 50)

    def test_absent_dates_have_friendly_forecast_error(self):
        self.agent.execute_plan = MagicMock(return_value={"result": [{"start": None, "end": None}]})
        with self.assertRaisesRegex(ValueError, "tarihli paylaşım"):
            self.service.forecast()

    def test_clickhouse_decoding_selects_one_topic_family_and_explicit_names(self):
        source = MagicMock()
        source.catalog = {"tweet_predictions": {"category_value": "String"}}
        source.run.return_value = [{"task_name": t} for t in (
            "emotion", "brand_sector", "topic_monthly", "topic_yearly", "consumer_journey")]
        self.db.source = source
        sql = self.db._clickhouse_cte()
        self.assertEqual(self.db.selected_tasks, {"emotion": "emotion", "consumer_journey": "journey", "topic_monthly": "topic"})
        self.assertIn("extractAll(category_value", sql)
        self.assertIn("p.tweet_id AS tweet_id", sql)
        self.assertIn("splitByString('|||'", sql)
        self.assertIn("uniqExactIf(gender", sql)
        self.assertIn("e.published_at < now()", sql)

    def test_count_forecasts_have_nonnegative_intervals(self):
        series = pd.Series(np.random.default_rng(42).poisson(np.linspace(20, 70, 48)),
                           index=pd.date_range("2020-01-01", periods=48, freq="MS"))
        result = forecast_series(series, 3, nonnegative=True)
        self.assertTrue((result["forecast"][["forecast", "lower", "upper"]] >= 0).all().all())
        self.assertTrue((result["forecast"]["lower"] <= result["forecast"]["forecast"]).all())


if __name__ == "__main__":
    unittest.main()
