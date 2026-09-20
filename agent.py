import os
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_core.tools import Tool
from langchain_core.prompts import PromptTemplate
import streamlit as st

from agents.query_agent import QueryAgent, CLICKHOUSE_CORE_TABLES
from agents.rewrite_nl_agent import RewriteNLAgent
from logger import logger, log_db_fallback

try:
    from agents.prompts.domain_prompts import (
        get_domain_context_prompt,
        build_hypothesis_synthesis_prompt,
        MARKETING_CONCEPT_DEFINITIONS,
        BUSINESS_HEURISTIC_RULES,
    )
except ImportError:
    def get_domain_context_prompt() -> str:
        return "Pazarlama hunisinde Consideration düşüşü funnel daralmasını gösterir. Kök neden için topics/products sütunlarına odaklan."
    def build_hypothesis_synthesis_prompt(h: str, e: str) -> str:
        return f"Hipotez: {h}\nKanıtlar: {e}\nLütfen hipotezi doğrula ve açıkla."


def get_secret(key: str, default: str = "") -> str:
    """Streamlit secrets veya ortam değişkenlerinden güvenli değer okur."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


# --- 1. API ANAHTARLARI & ORTAM DEĞİŞKENLERİ ---
for key in ["OPENAI_API_KEY", "PINECONE_API_KEY", "OPENAI_MODEL_NAME"]:
    val = get_secret(key)
    if val:
        os.environ[key] = val


from agents.prompts.query_prompts import SQL_AGENT_PREFIX
from agents.prompts.synthesis_prompts import (
    EXECUTIVE_SUMMARY_PROMPT,
    COMPETING_HYPOTHESES_EVALUATION_PROMPT,
    PREDICTIVE_INSIGHT_PROMPT,
)


# --- 2. SENTEZ MOTORU (SYNTHESIS ENGINE) ---

class SynthesisEngine:
    def __init__(self, llm_instance: ChatOpenAI):
        self.llm = llm_instance

    def synthesize_executive_summary(self, question: str, sql_evidence: str) -> str:
        prompt = PromptTemplate.from_template(EXECUTIVE_SUMMARY_PROMPT)
        chain = prompt | self.llm
        return chain.invoke({
            "question": question,
            "evidence": sql_evidence,
            "domain_rules": get_domain_context_prompt()
        }).content.strip()

    def evaluate_competing_hypotheses(self, hypotheses: Dict[str, str], sql_evidence: str) -> str:
        """
        H0, H1 ve H2 hipotezlerini toplanan SQL verisi karşısında eşzamanlı yarıştırır.
        Varsayımsal konuşmaz; verideki reel sayıları kanıt göstererek karne üretir.
        """
        prompt = PromptTemplate.from_template(COMPETING_HYPOTHESES_EVALUATION_PROMPT)
        chain = prompt | self.llm
        return chain.invoke({
            "h0": hypotheses.get("H0", "Sıfır hipotezi"),
            "h1": hypotheses.get("H1", "Birincil hipotez"),
            "h2": hypotheses.get("H2", "Rakip hipotez"),
            "evidence": sql_evidence,
            "domain_rules": get_domain_context_prompt()
        }).content.strip()

    def verify_hypothesis(self, hypothesis: str, sql_evidence: str) -> str:
        prompt_text = build_hypothesis_synthesis_prompt(hypothesis, sql_evidence)
        response = self.llm.invoke(prompt_text)
        return response.content.strip()

    def synthesize_predictive_insight(self, topic: str, time_series_evidence: str) -> str:
        prompt = PromptTemplate.from_template(PREDICTIVE_INSIGHT_PROMPT)
        chain = prompt | self.llm
        return chain.invoke({
            "topic": topic,
            "evidence": time_series_evidence
        }).content.strip()


# --- 3. VERİTABANI BAĞLANTISI VE YEDEKLEME (CLICKHOUSE -> SQLITE FALLBACK) ---

def get_database_connection(custom_uri: Optional[str] = None) -> Tuple[SQLDatabase, str, str]:
    """
    ClickHouse veya özel veritabanı bağlantısını dener;
    Ulaşılamazsa log_db_fallback çağırarak güvenle SQLite'a geçer.
    Dönüş: (db_instance, db_uri, dialect)
    """
    if custom_uri:
        dialect = "clickhouse" if "clickhouse" in custom_uri.lower() else "sqlite"
        try:
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


# --- 4. HİBRİT VE KADEMELİ MOTOR (2-TIER ROUTING) ---

def get_hybrid_agent(
    db_uri: Optional[str] = None,
    fast_model: str = "gpt-4o-mini",
    reasoning_model: str = "gpt-4o"
):
    # 1. SQL Bağlantısı (ClickHouse -> SQLite Yedekli & Loglu)
    db, active_uri, dialect = get_database_connection(custom_uri=db_uri)
    
    # 2. Kademe Modeller
    llm_fast = ChatOpenAI(model=fast_model, temperature=0)
    llm_reasoning = ChatOpenAI(model=reasoning_model, temperature=0)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    # 3. RAG Bağlantısı
    index_name = "pazarlama-verileri" 
    extra_tools = []
    try:
        vectorstore = PineconeVectorStore(index_name=index_name, embedding=embeddings)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
        rag_tool = Tool(
            name="dokuman_arama_araci",
            description="Markanın iade politikaları, PDF strateji raporları veya SQL veritabanında olmayan yapılandırılmamış metinleri araştırmak için bu aracı kullan.",
            func=retriever.invoke
        )
        extra_tools.append(rag_tool)
        logger.info(
            "RAG tool integrated successfully.",
            extra={"event_type": "rag_init", "status": "success", "index_name": index_name}
        )
    except Exception as e:
        logger.warning(
            f"RAG sistemine bağlanılamadı: {e}",
            extra={"event_type": "rag_init", "status": "failed", "error": str(e)}
        )

    # 4. Hibrit Ajan (SQL + RAG)
    agent_executor = create_sql_agent(
        llm=llm_fast,
        db=db,
        agent_type="openai-tools",
        extra_tools=extra_tools,
        prefix=SQL_AGENT_PREFIX,
        verbose=False
    )
    
    # 5. Alt Ajanlar & Sentez Motoru
    query_agent = QueryAgent(db_uri=active_uri, model_name=fast_model, dialect=dialect, db=db)
    rewrite_agent = RewriteNLAgent(model_name=fast_model)
    synthesis_engine = SynthesisEngine(llm_reasoning)
    
    # 6 elemanı tam olarak döndürür
    return db, llm_reasoning, agent_executor, query_agent, rewrite_agent, synthesis_engine