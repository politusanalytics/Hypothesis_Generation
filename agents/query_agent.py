"""
Sorgu Planlama Ajanı (Query Planning Agent)
Doğal dil sorgularını yapılandırılmış JSON formatına dönüştürür ve deterministik SQL derleyicisini kullanarak çalıştırır.
"""

import os
import copy
import json
import logging
import re
from typing import Any, Optional
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import streamlit as st

from agents.sql_compiler import (
    compile_json_to_sql,
    quote_ident,
    _lit,
    _contains_lit,
    _format_array_lit,
    _compile_join,
    _FILTER_OP_TO_SQL,
    _AGG_OPS,
)

logger = logging.getLogger(__name__)

CLICKHOUSE_CORE_TABLES = ["tweet_predictions", "tweets", "users", "user_factors"]

# --- 1. API ANAHTARLARI (Streamlit Secrets & Ortam Değişkenleri ile Uyumlu) ---
try:
    if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
except Exception:
    pass


from agents.prompts.query_prompts import QUERY_GENERATOR_SYSTEM_PROMPT

# Geriye dönük uyumluluk için alias
_QUERY_GENERATOR_SYSTEM_PROMPT = QUERY_GENERATOR_SYSTEM_PROMPT



# --- 3. SORGU PLANLAMA AJANI SINIFI (Lazy-Loaded LLM & DB) ---

import time
from agents.query_validation import validate_query_plan


def _normalize_generated_aggregates(plan):
    """Losslessly wrap singleton aggregate objects only at the LLM boundary."""
    plan = copy.deepcopy(plan)

    def visit(node, depth=0):
        if not isinstance(node, dict) or depth > 4:
            return
        if isinstance(node.get("aggregates"), dict):
            node["aggregates"] = [node["aggregates"]]
        filters = node.get("filters", [])
        if isinstance(filters, list):
            for item in filters:
                if isinstance(item, dict) and isinstance(item.get("op"), str) \
                        and item["op"].upper() in {"IN", "NOT_IN"}:
                    visit(item.get("value"), depth + 1)

    visit(plan)
    return plan

try:
    from logger import log_query
except ImportError:
    try:
        from ..logger import log_query
    except Exception:
        def log_query(*args, **kwargs):
            pass


class QueryAgent:
    """
    Doğal dil sorularını yapılandırılmış JSON formatına çeviren ve deterministik SQL üreten sorgu ajanı.
    """
    def __init__(
        self,
        db_uri: str = "sqlite:///insight_generation_bot.db",
        model_name: str = "gpt-4o",
        dialect: str = "sqlite",
        api_key: Optional[str] = None,
        llm: Optional[Any] = None,
        db: Optional[Any] = None,
        schema: Optional[str] = None,
        system_prompt: Optional[str] = None,
        catalog: Optional[dict] = None
    ):
        self.db_uri = db_uri
        self.model_name = model_name
        self.dialect = dialect
        self.api_key = api_key
        self._db = db
        self._llm = llm
        self._schema = schema
        self.system_prompt = system_prompt or _QUERY_GENERATOR_SYSTEM_PROMPT
        self.catalog = catalog if catalog is not None else getattr(db, "catalog", None)
        if self.catalog is not None and not isinstance(self.catalog, dict):
            self.catalog = None

    @property
    def db(self) -> SQLDatabase:
        if self._db is None:
            from agent import get_database_connection
            self._db, _, self.dialect = get_database_connection(self.db_uri)
            self.catalog = self._db.catalog
        return self._db

    @property
    def schema(self) -> str:
        if self._schema is None:
            self._schema = self.db.get_table_info()
        return self._schema

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            key = self.api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                try:
                    if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
                        key = st.secrets["OPENAI_API_KEY"]
                        os.environ["OPENAI_API_KEY"] = key
                except Exception:
                    pass
            if not key:
                raise ValueError("OPENAI_API_KEY bulunamadı. Lütfen ortam değişkeni veya st.secrets üzerinden tanımlayın.")
            self._llm = ChatOpenAI(model=self.model_name, temperature=0, api_key=key)
        return self._llm

    def generate_query_json(self, question: str) -> dict[str, Any]:
        """Generate and validate a plan; allow one correction before failing closed."""
        messages = [
            ("system", self.system_prompt),
            ("user", "Bu soruyu yapılandırılmış JSON formatına çevir: {question}")
        ]
        context = {"schema": self.schema, "question": question, "dialect": self.dialect}
        last_error = ""
        for attempt in range(2):
            active_messages = messages
            if attempt:
                active_messages = messages + [("user",
                    "Önceki plan doğrulanamadı: {validation_error}\n"
                    "Aynı soruyu ve kapsamını koruyarak geçerli JSON planını yeniden üret. "
                    "Filtreleri kaldırma. Liste alanlarında tek öğe için bile [] kullan. "
                    "SQL yazma; desteklenmeyen sorgu için error alanı döndür.")]
            chain = ChatPromptTemplate.from_messages(active_messages) | self.llm
            response = chain.invoke({**context, "validation_error": last_error})
            if not isinstance(response.content, str):
                last_error = "Model yanıtı JSON metni olmalı."
                continue
            raw_text = response.content.strip()
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text).strip()
            try:
                query_json = json.loads(raw_text)
            except json.JSONDecodeError:
                last_error = "Geçersiz JSON formatı."
                continue
            # An explicit unsupported-query response is not a formatting failure.
            if isinstance(query_json, dict) and query_json.get("error"):
                raise ValueError(str(query_json["error"]))
            try:
                query_json = _normalize_generated_aggregates(query_json)
                return validate_query_plan(query_json, dialect=self.dialect,
                                           catalog=self.catalog, default_limit=1000)
            except ValueError as error:
                last_error = str(error)
            except TypeError:
                last_error = "Sorgu planındaki alan türleri geçersiz."
        raise ValueError("Geçerli sorgu planı üretilemedi. " + last_error) from None

    def execute_nl_query(self, question: str, dialect: Optional[str] = None) -> dict[str, Any]:
        """Doğal dil sorusunu JSON ve SQL derleme adımlarından geçirip veritabanında çalıştırır."""
        start_time = time.perf_counter()
        active_dialect = dialect or self.dialect
        if active_dialect != self.dialect:
            raise ValueError("Bağlı veritabanından farklı SQL lehçesi kullanılamaz.")
        query_json = {}
        sql = ""

        try:
            query_json = self.generate_query_json(question)
        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_query(
                question=question,
                json_query={},
                sql="",
                duration_ms=duration_ms,
                error=f"JSON Generation Failed: {e}"
            )
            raise

        try:
            # Ensure lazy DB/catalog initialization precedes schema validation.
            self.db
            query_json = validate_query_plan(query_json, dialect=active_dialect,
                                              catalog=self.catalog, default_limit=1000)
            sql = compile_json_to_sql(query_json, dialect=active_dialect)
        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_query(
                question=question,
                json_query=query_json,
                sql="",
                duration_ms=duration_ms,
                error=f"SQL Compilation Failed: {e}"
            )
            raise

        try:
            result = self.db.run(sql)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_query(
                question=question,
                json_query=query_json,
                sql=sql,
                result=result,
                duration_ms=duration_ms
            )
            return {
                "question": question,
                "json_query": query_json,
                "sql": sql,
                "result": result
            }
        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_query(
                question=question,
                json_query=query_json,
                sql=sql,
                duration_ms=duration_ms,
                error=f"Database Execution Failed: {e}"
            )
            raise


    def execute_plan(self, plan):
        """Execute a user-configured statistical plan through the same guardrails."""
        self.db
        plan = validate_query_plan(plan, dialect=self.dialect, catalog=self.catalog, default_limit=1000)
        sql = compile_json_to_sql(plan, dialect=self.dialect)
        start = time.perf_counter()
        try:
            result = self.db.run(sql)
        except Exception as error:
            log_query("structured_analysis", plan, sql, error=type(error).__name__)
            raise
        log_query("structured_analysis", plan, sql, result=result,
                  duration_ms=(time.perf_counter() - start) * 1000)
        return {"json_query": plan, "sql": sql, "result": result}


def get_query_agent(db_uri: str = "sqlite:///insight_generation_bot.db", model_name: str = "gpt-4o", dialect: str = "sqlite") -> QueryAgent:
    """Kolay erişim için fabrika fonksiyonu."""
    return QueryAgent(db_uri=db_uri, model_name=model_name, dialect=dialect)
