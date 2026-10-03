import unittest
from agents.query_validation import validate_query_plan
from agents.sql_compiler import compile_json_to_sql
from agents.prompts.query_prompts import QUERY_GENERATOR_SYSTEM_PROMPT

CATALOG = {"tweets": {"id": "Int64", "author_id": "Int64", "created_at": "DateTime"},
           "users": {"id": "Int64", "gender": "String"}}


class TestSharedValidation(unittest.TestCase):
    def test_catalog_checks_nested_queries_and_columns(self):
        for plan in ({"table": "twitter_tweets"}, {"table": "tweets", "columns": ["missing"]},
                     {"table": "tweets", "filters": [{"column": "id", "op": "IN", "value": {
                         "table": "secret", "columns": ["id"]}}]}):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                validate_query_plan(plan, catalog=CATALOG)

    def test_alias_join_and_array_free_schema(self):
        plan = {"table": "tweets", "alias": "t", "joins": [{"table": "users", "alias": "u",
                "on": {"left": "t.author_id", "right": "u.id"}}], "group_by": ["u.gender"],
                "aggregates": [{"op": "count", "as": "n"}], "order_by": [{"column": "n", "dir": "desc"}]}
        validate_query_plan(plan, catalog=CATALOG)
        plan["group_by"] = ["id"]
        with self.assertRaises(ValueError):
            validate_query_plan(plan, catalog=CATALOG)

    def test_compiler_never_drops_invalid_filters(self):
        for filters in ([{"column": "id", "op": "WRONG", "value": 1}],
                        [{"column": "id", "op": "IN", "value": []}],
                        [{"column": "id", "op": "BETWEEN", "value": [1]}], ["wrong"]):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                compile_json_to_sql({"table": "tweets", "filters": filters})
        with self.assertRaises(ValueError):
            compile_json_to_sql({"table": "tweets", "joins": [{"table": "users", "on": "1=1"}]})

    def test_time_buckets_are_dialect_specific(self):
        plan = {"table": "tweets", "time_bucket": {"column": "created_at", "grain": "month", "as": "period"},
                "group_by": ["period"], "aggregates": [{"op": "count", "as": "value"}]}
        self.assertIn("toStartOfMonth(`created_at`)", compile_json_to_sql(plan, "clickhouse"))
        self.assertIn('date("created_at", \'start of month\')', compile_json_to_sql(plan, "sqlite"))

    def test_prompt_does_not_force_old_demo_schema(self):
        self.assertNotIn("twitter_tweets", QUERY_GENERATOR_SYSTEM_PROMPT)
        self.assertNotIn("demo_brand_users", QUERY_GENERATOR_SYSTEM_PROMPT)
        self.assertIn("{dialect}", QUERY_GENERATOR_SYSTEM_PROMPT)
