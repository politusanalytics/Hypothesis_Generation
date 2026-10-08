import os
from pathlib import Path
from urllib.parse import unquote

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
import streamlit as st

from agents.query_agent import QueryAgent
from agents.rewrite_nl_agent import RewriteNLAgent
from database import DatabaseInitializationError, SQLiteDatabase, connect_clickhouse
from logger import logger
from agents.prompts.domain_prompts import get_domain_context_prompt
from agents.prompts.synthesis_prompts import EXECUTIVE_SUMMARY_PROMPT


def get_secret(key: str, default: str = "") -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


class SynthesisEngine:
    def __init__(self, llm_instance):
        self.llm = llm_instance

    def synthesize_executive_summary(self, question, sql_evidence):
        return (PromptTemplate.from_template(EXECUTIVE_SUMMARY_PROMPT) | self.llm).invoke({
            "question": question, "evidence": sql_evidence,
            "domain_rules": get_domain_context_prompt()
        }).content.strip()

    def evaluate_competing_hypotheses(self, hypotheses, statistical_result):
        from statistical_analysis import hypothesis_report
        if not isinstance(statistical_result, dict) or "p_value" not in statistical_result:
            raise ValueError("Hipotez kararı hesaplanmış istatistiksel test sonucu gerektirir.")
        return hypothesis_report(statistical_result)

    def verify_hypothesis(self, hypothesis, statistical_result):
        return self.evaluate_competing_hypotheses({"H1": hypothesis}, statistical_result)

    def synthesize_predictive_insight(self, topic, forecast_result):
        from forecasting import forecast_report
        if not isinstance(forecast_result, dict) or "metrics" not in forecast_result:
            raise ValueError("Projeksiyon hesaplanmış zaman serisi tahmini gerektirir.")
        return forecast_report(forecast_result)


def get_database_connection(custom_uri=None):
    """Configured ClickHouse fails closed; SQLite is an explicit local profile."""
    if custom_uri:
        if not custom_uri.startswith("sqlite:///"):
            raise ValueError("Özel URI yalnızca SQLite içindir; ClickHouse için CLICKHOUSE_* ayarlarını kullanın.")
        path = unquote(custom_uri[len("sqlite:///"):])
        db = SQLiteDatabase(path)
        return db, custom_uri, "sqlite"
    backend = get_secret("DATABASE_BACKEND", "auto").lower()
    if backend not in {"auto", "clickhouse", "sqlite"}:
        raise DatabaseInitializationError("DATABASE_BACKEND auto/clickhouse/sqlite olmalı.")
    if backend == "clickhouse" or (backend == "auto" and get_secret("CLICKHOUSE_HOST")):
        try:
            db = connect_clickhouse(get_secret)
            logger.info("ClickHouse connection established.", extra={"event_type": "database_connection"})
            return db, "clickhouse", "clickhouse"
        except Exception as error:
            logger.error("ClickHouse connection failed.", extra={"error_type": type(error).__name__})
            if isinstance(error, DatabaseInitializationError):
                raise
            raise ValueError("ClickHouse bağlantısı kurulamadı; bağlantı ve tablo izinlerini kontrol edin.") from None
    path = get_secret("SQLITE_DB_PATH", str(Path(__file__).parent / "insight_generation_bot.db"))
    return SQLiteDatabase(path), "sqlite:///" + path, "sqlite"


class ValidatedExecutor:
    """Legacy executor interface; natural language always goes through validation."""
    def __init__(self, query_agent):
        self.query_agent = query_agent

    def invoke(self, inputs):
        result = self.query_agent.execute_nl_query(inputs["input"])
        return {"output": str(result["result"]), **result}


def get_hybrid_agent(db_uri=None, fast_model="gpt-4o-mini", reasoning_model="gpt-4o"):
    db, active_uri, dialect = get_database_connection(db_uri)
    key = get_secret("OPENAI_API_KEY")
    llm = ChatOpenAI(model=reasoning_model, temperature=0, api_key=key) if key else None
    query_agent = QueryAgent(db_uri=active_uri, model_name=fast_model, dialect=dialect,
                             db=db, catalog=db.catalog, api_key=key or None)
    rewrite_agent = RewriteNLAgent(model_name=fast_model)
    return db, llm, ValidatedExecutor(query_agent), query_agent, rewrite_agent, SynthesisEngine(llm)
