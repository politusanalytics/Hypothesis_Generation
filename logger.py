"""Structured logs with mandatory payload redaction for local files and Graylog."""
import logging
import logging.handlers
import os
from pathlib import Path
import re
import uuid
import json

_BUILTIN = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}
_SAFE_FIELDS = {"event_type", "duration_ms", "error_type", "status", "dialect", "query_id", "row_count"}
_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]+"), "[API_KEY]"),
    (re.compile(r"(?i)(bearer\s+)[^\s,;]+"), r"\1[TOKEN]"),
    (re.compile(r"(?i)((?:password|api[_-]?key|token)\s*[:=]\s*)[^\s,;]+"), r"\1[SECRET]"),
    (re.compile(r"\b(?:\+?\d[\d ()-]{8,}\d)\b"), "[NUMBER]"),
    (re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/]+@"), r"\1[CREDENTIALS]@"),
]


def redact_text(text):
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, str(text))
    return text


class PrivacyFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact_text(record.getMessage())
        record.args = ()
        # Tracebacks can contain SQL parameters, credentials and raw response bodies.
        if record.exc_info:
            record.error_type = record.exc_info[0].__name__
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        for key in list(record.__dict__):
            if key not in _BUILTIN and key not in _SAFE_FIELDS:
                record.__dict__[key] = "[REDACTED]"
            elif key in _SAFE_FIELDS and isinstance(record.__dict__[key], str):
                if key == "query_id":
                    try:
                        record.__dict__[key] = str(uuid.UUID(record.__dict__[key]))
                    except ValueError:
                        record.__dict__[key] = "[REDACTED]"
                else:
                    record.__dict__[key] = redact_text(record.__dict__[key])
        return True


class StructuredExtraFormatter(logging.Formatter):
    def format(self, record):
        # Also protect direct formatter calls, not only configured handlers.
        PrivacyFilter().filter(record)
        base = super().format(record)
        extra = {key: value for key, value in record.__dict__.items() if key not in _BUILTIN}
        return base + (" | EXTRA: " + json.dumps(extra, ensure_ascii=False, default=str) if extra else "")


def setup_logging():
    def config(key, default=""):
        try:
            import streamlit as st
            if key in st.secrets:
                return str(st.secrets[key])
        except Exception:
            pass
        return os.getenv(key, default)

    app_logger = logging.getLogger("hypothesis-engine")
    app_logger.setLevel(getattr(logging, config("LOG_LEVEL", "INFO").upper(), logging.INFO))
    app_logger.propagate = False
    if app_logger.handlers:
        return app_logger
    folder = Path(__file__).resolve().parent / "logs"
    folder.mkdir(exist_ok=True)
    formatter = StructuredExtraFormatter("%(asctime)s - %(levelname)s - %(message)s")
    handlers = [logging.handlers.RotatingFileHandler(folder / "app.log", maxBytes=10 * 1024 * 1024,
                                                     backupCount=5, encoding="utf-8"),
                logging.StreamHandler()]
    if config("GRAYLOG_ENABLED", "false").lower() in {"true", "1", "yes"}:
        import graypy
        handler_class = graypy.GELFTCPHandler if config("GRAYLOG_PROTOCOL", "udp") == "tcp" else graypy.GELFUDPHandler
        handlers.append(handler_class(config("GRAYLOG_HOST", "localhost"), int(config("GRAYLOG_PORT", "12201"))))
    for handler in handlers:
        handler.addFilter(PrivacyFilter())
        handler.setFormatter(formatter)
        app_logger.addHandler(handler)
    return app_logger


logger = setup_logging()


def log_query(question, json_query, sql, result=None, duration_ms=None, error=None):
    # Intentionally omit questions, filter values, SQL and data samples.
    payload = {"event_type": "query_execution", "query_id": str(uuid.uuid4()),
               "duration_ms": duration_ms, "status": "failed" if error else "success"}
    if isinstance(result, list):
        payload["row_count"] = len(result)
    if error:
        payload["error_type"] = "QueryError"
        logger.error("Query Failed", extra=payload)
    else:
        logger.info("Query Executed", extra=payload)


def log_db_fallback(target_db, fallback_db="sqlite", reason=None):
    logger.warning("Database fallback requested.", extra={"event_type": "database_fallback",
                                                          "status": "fallback"})
