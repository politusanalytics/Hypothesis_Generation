import os
from pathlib import Path
from urllib.parse import unquote

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
import streamlit as st

from agents.query_agent import QueryAgent
from agents.rewrite_nl_agent import RewriteNLAgent
from database import SQLiteDatabase, connect_clickhouse
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
        raise ValueError("DATABASE_BACKEND auto/clickhouse/sqlite olmalı.")
    if backend == "clickhouse" or (backend == "auto" and get_secret("CLICKHOUSE_HOST")):
        try:
<<<<<<< HEAD
            if dialect == "clickhouse":
                db = SQLDatabase.from_uri(custom_uri, include_tables=CLICKHOUSE_CORE_TABLES)
            else:
                db = SQLDatabase.from_uri(custom_uri)
            db.get_table_info()
            return db, custom_uri, dialect
        except Exception as e:
            log_db_fallback(target_db=custom_uri, fallback_db="sqlite:///insight_generation_bot.db", reason=str(e))
            sqlite_uri = "sqlite:///insight_generation_bot.db"
            return SQLDatabase.from_uri(sqlite_uri), sqlite_uri, "sqlite"

    ch_host = get_secret("CLICKHOUSE_HOST")
    if ch_host:
        ch_port = get_secret("CLICKHOUSE_PORT", "8123")
        ch_user = get_secret("CLICKHOUSE_USERNAME", "default")
        ch_pass = get_secret("CLICKHOUSE_PASSWORD", "")
        ch_db = get_secret("CLICKHOUSE_DB", "default")
        ch_secure = get_secret("CLICKHOUSE_SECURE", "")
        ch_verify = get_secret("CLICKHOUSE_VERIFY", "")
        
        auth = f"{ch_user}:{ch_pass}@" if (ch_user or ch_pass) else ""

        params = []
        if ch_secure.lower() in ("true", "1", "yes") or str(ch_port) == "443":
            params.append("secure=True")
        if ch_verify.lower() in ("false", "0", "no"):
            params.append("verify=False")
        query_str = f"?{'&'.join(params)}" if params else ""

        # clickhouse-connect official SQLAlchemy dialect is clickhousedb://
        ch_uri = f"clickhousedb://{auth}{ch_host}:{ch_port}/{ch_db}{query_str}"
        sanitized_target = f"clickhousedb://{ch_host}:{ch_port}/{ch_db}{query_str}"
        
        try:
            db = SQLDatabase.from_uri(ch_uri, include_tables=CLICKHOUSE_CORE_TABLES)
            db.get_table_info()  # Şema derleme doğrulaması
            logger.info(
                "Connected to ClickHouse successfully.",
                extra={"event_type": "database_connection", "dialect": "clickhouse", "host": ch_host}
            )
            return db, ch_uri, "clickhouse"
        except Exception as e:
            # Fallback attempt with legacy clickhouse+http if clickhouse-sqlalchemy is present
            try:
                legacy_uri = f"clickhouse+http://{auth}{ch_host}:{ch_port}/{ch_db}{query_str}"
                db = SQLDatabase.from_uri(legacy_uri, include_tables=CLICKHOUSE_CORE_TABLES)
                db.get_table_info()
                logger.info(
                    "Connected to ClickHouse via clickhouse+http successfully.",
                    extra={"event_type": "database_connection", "dialect": "clickhouse", "host": ch_host}
                )
                return db, legacy_uri, "clickhouse"
            except Exception:
                pass
            log_db_fallback(target_db=sanitized_target, fallback_db="sqlite:///insight_generation_bot.db", reason=str(e))

    # SQLite Varsayılan Veritabanı
    sqlite_uri = "sqlite:///insight_generation_bot.db"
    return SQLDatabase.from_uri(sqlite_uri), sqlite_uri, "sqlite"
=======
            db = connect_clickhouse(get_secret)
            logger.info("ClickHouse connection established.", extra={"event_type": "database_connection"})
            return db, "clickhouse", "clickhouse"
        except Exception as error:
            logger.error("ClickHouse connection failed.", extra={"error_type": type(error).__name__})
            raise ValueError("ClickHouse bağlantısı kurulamadı; bağlantı ve tablo izinlerini kontrol edin.") from None
    path = get_secret("SQLITE_DB_PATH", str(Path(__file__).parent / "insight_generation_bot.db"))
    return SQLiteDatabase(path), "sqlite:///" + path, "sqlite"
>>>>>>> 855fba7 (5. mod eklendi)


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
