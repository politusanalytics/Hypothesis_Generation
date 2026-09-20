"""
Sorgu Planlama Ajanı (Query Planning Agent)
Doğal dil sorgularını yapılandırılmış JSON formatına dönüştürür ve deterministik SQL derleyicisini kullanarak çalıştırır.
"""

import os
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
        schema: Optional[str] = None
    ):
        self.db_uri = db_uri
        self.model_name = model_name
        self.dialect = dialect
        self.api_key = api_key
        self._db = db
        self._llm = llm
        self._schema = schema

    @property
    def db(self) -> SQLDatabase:
        if self._db is None:
            if self.dialect == "clickhouse" or "clickhouse" in self.db_uri:
                self._db = SQLDatabase.from_uri(self.db_uri, include_tables=CLICKHOUSE_CORE_TABLES)
            else:
                self._db = SQLDatabase.from_uri(self.db_uri)
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
        """Kullanıcı sorusunu ilişkisel JSON sorgusuna çevirir."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", _QUERY_GENERATOR_SYSTEM_PROMPT),
            ("user", "Bu soruyu yapılandırılmış JSON formatına çevir: {question}")
        ])
        chain = prompt | self.llm
        response = chain.invoke({"schema": self.schema, "question": question})
        raw_text = response.content.strip()

        # Markdown işaretlerini temizle
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text).strip()

        try:
            query_json = json.loads(raw_text)
            return query_json
        except json.JSONDecodeError as e:
            logger.error(f"LLM çıktısı JSON olarak ayrıştırılamadı: {raw_text}")
            raise ValueError(f"Geçersiz JSON formatı: {e}") from e

    def execute_nl_query(self, question: str, dialect: Optional[str] = None) -> dict[str, Any]:
        """Doğal dil sorusunu JSON ve SQL derleme adımlarından geçirip veritabanında çalıştırır."""
        active_dialect = dialect or self.dialect
        query_json = self.generate_query_json(question)
        sql = compile_json_to_sql(query_json, dialect=active_dialect)
        result = self.db.run(sql)
        return {
            "question": question,
            "json_query": query_json,
            "sql": sql,
            "result": result
        }


def get_query_agent(db_uri: str = "sqlite:///insight_generation_bot.db", model_name: str = "gpt-4o", dialect: str = "sqlite") -> QueryAgent:
    """Kolay erişim için fabrika fonksiyonu."""
    return QueryAgent(db_uri=db_uri, model_name=model_name, dialect=dialect)