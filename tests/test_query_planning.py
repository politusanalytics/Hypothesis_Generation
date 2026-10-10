"""Regressions for malformed model plans, without network or API calls."""
import copy
import json
import unittest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agents.query_agent import QueryAgent
from agents.query_validation import validate_query_plan
from data_analysis import ClickHouseAnalysisEngine
from database import schema_text


CATALOG = {
    "users": {"id": "String", "age_range": "String"},
    "tweet_predictions": {"author_id": "String", "tweet_id": "String",
                          "task_name": "String", "category_value": "String"},
}


class TestGeneratedPlans(unittest.TestCase):
    def planner(self, responses):
        self.requests = []
        iterator = iter(responses)

        def respond(prompt):
            self.requests.append(prompt.to_messages())
            response = next(iterator)
            return AIMessage(content=response if isinstance(response, str) else json.dumps(response))

        self.db = MagicMock()
        self.db.catalog = CATALOG
        return QueryAgent(llm=RunnableLambda(respond), db=self.db, dialect="clickhouse",
                          schema=schema_text(CATALOG), catalog=CATALOG)

    def test_single_aggregate_age_emotion_plan_reaches_clickhouse_once(self):
        source = {
            "table": "tweet_predictions", "alias": "p",
            "joins": [{"table": "users", "alias": "u", "type": "INNER",
                       "on": {"left": "p.author_id", "right": "u.id"}}],
            "group_by": ["u.age_range", "p.category_value"],
            "aggregates": {"op": "count_distinct", "column": "p.tweet_id", "as": "total"},
            "filters": [{"column": "p.task_name", "op": "EQ", "value": "emotion"}],
            "order_by": [{"column": "total", "dir": "desc"}],
        }
        original = copy.deepcopy(source)
        planner = self.planner([source])
        client = MagicMock()
        client.query.return_value.column_names = ["age_range", "category_value", "total"]
        client.query.return_value.result_rows = [("25-34", "joy", 12)]
        result = ClickHouseAnalysisEngine(client, planner, CATALOG).execute(
            "yaş gruplarının baskın duygularını sorgula")
        self.assertIn("count(DISTINCT `p`.`tweet_id`)", result["sql"])
        self.assertIn("`p`.`task_name` = 'emotion'", result["sql"])
        self.assertIn("GROUP BY `u`.`age_range`, `p`.`category_value`", result["sql"])
        self.assertIsInstance(result["json_query"]["aggregates"], list)
        self.assertEqual(source, original)
        self.assertEqual(len(self.requests), 1)
        client.query.assert_called_once()
        self.assertEqual(client.query.call_args.kwargs["settings"]["readonly"], 1)

    def test_null_aggregates_triggers_one_correction(self):
        valid = {"table": "users", "aggregates": [{"op": "count", "as": "total"}]}
        agent = self.planner([{"table": "users", "aggregates": None}, valid])
        result = agent.execute_nl_query("Kaç kullanıcı var?")
        self.assertIn("count(*)", result["sql"])
        self.assertEqual(len(self.requests), 2)
        self.assertIn("aggregates bir liste olmalı", self.requests[1][-1].content)
        self.db.run.assert_called_once()

    def test_json_parse_failure_is_corrected_before_execution(self):
        agent = self.planner(["not JSON", {"table": "users", "columns": ["id"]}])
        agent.execute_nl_query("Kullanıcıları göster")
        self.assertEqual(len(self.requests), 2)
        self.db.run.assert_called_once()

    def test_invalid_plans_never_reach_database_and_retry_is_bounded(self):
        invalids = [
            {"table": "users", "filters": "age_range = '25-34'"},
            {"table": "users", "filters": [{"column": "id", "op": "WRONG", "value": 1}]},
            {"table": "users", "joins": [{"table": "tweet_predictions", "on": "1=1"}]},
            {"table": "system.users"},
            {"table": "users", "aggregates": {"op": "avg", "column": "missing"}},
            {"table": "users", "aggregates": [{"op": {"invalid": "count"}}]},
        ]
        for invalid in invalids:
            with self.subTest(plan=invalid):
                agent = self.planner([invalid, invalid])
                with self.assertRaisesRegex(ValueError, "Geçerli sorgu planı üretilemedi"):
                    agent.execute_nl_query("Sorgula")
                self.assertEqual(len(self.requests), 2)
                self.db.run.assert_not_called()

    def test_explicit_unsupported_response_is_not_retried(self):
        agent = self.planner([{"error": "İstenen sütun şemada bulunmuyor."}])
        with self.assertRaisesRegex(ValueError, "şemada bulunmuyor"):
            agent.execute_nl_query("Eksik alanı göster")
        self.assertEqual(len(self.requests), 1)
        self.db.run.assert_not_called()

    def test_single_aggregate_in_subquery_preserves_filter_and_has_no_nested_limit(self):
        agent = self.planner([{"table": "users", "columns": ["id"], "filters": [
            {"column": "id", "op": "IN", "value": {"table": "tweet_predictions",
             "aggregates": {"op": "max", "column": "author_id", "as": "author"}}}]}])
        result = agent.generate_query_json("Alt sorgu")
        nested = result["filters"][0]["value"]
        self.assertEqual(nested["aggregates"], [{"op": "max", "column": "author_id", "as": "author"}])
        self.assertNotIn("limit", nested)

    def test_manual_plans_still_require_aggregate_lists(self):
        source = {"table": "users", "aggregates": {"op": "count", "as": "total"}}
        with self.assertRaisesRegex(ValueError, "aggregates bir liste olmalı"):
            validate_query_plan(source, dialect="clickhouse", catalog=CATALOG)


if __name__ == "__main__":
    unittest.main()
