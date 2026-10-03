"""ClickHouse-only analysis using the same validation as every other mode."""
import time
from agents.query_validation import validate_query_plan
from agents.prompts.query_prompts import QUERY_GENERATOR_SYSTEM_PROMPT
from database import CORE_TABLES, QUERY_SETTINGS

TABLES = CORE_TABLES
ANALYSIS_PROMPT = QUERY_GENERATOR_SYSTEM_PROMPT


def validate_plan(plan, tables=TABLES, depth=0):
    return validate_query_plan(plan, dialect="clickhouse", allowed_tables=tables,
                               default_limit=1000, depth=depth)


class ClickHouseAnalysisEngine:
    def __init__(self, client, planner, catalog=None):
        self.client = client
        self.planner = planner
        self.catalog = catalog

    def execute(self, question):
        from agents.sql_compiler import compile_json_to_sql
        from logger import log_query
        start = time.perf_counter()
        plan = validate_query_plan(self.planner.generate_query_json(question), dialect="clickhouse",
                                   catalog=self.catalog, allowed_tables=TABLES if self.catalog is None else None,
                                   default_limit=1000)
        sql = compile_json_to_sql(plan, dialect="clickhouse")
        try:
            result = self.client.query(sql, settings=QUERY_SETTINGS)
            if len(result.result_rows) > 1000:
                raise ValueError("Sorgu 1000 satır sınırını aşıyor.")
        except Exception as error:
            log_query(question, plan, sql, error=type(error).__name__)
            raise
        log_query(question, plan, sql, duration_ms=(time.perf_counter() - start) * 1000)
        return {"question": question, "json_query": plan, "sql": sql,
                "columns": list(result.column_names), "rows": list(result.result_rows)}


def get_analysis_engine(model_name, get_config):
    if not get_config("CLICKHOUSE_HOST"):
        raise ValueError("Veri Analiz Modu için CLICKHOUSE_HOST tanımlanmalı.")
    from database import connect_clickhouse
    from agents.query_agent import QueryAgent
    db = connect_clickhouse(get_config)
    planner = QueryAgent(model_name=model_name, dialect="clickhouse", db=db,
                         schema=db.get_table_info(), catalog=db.catalog,
                         api_key=get_config("OPENAI_API_KEY") or None)
    return ClickHouseAnalysisEngine(db.client, planner, db.catalog)
