"""Lazy exports keep the SQL compiler usable without LLM dependencies."""
from importlib import import_module

_EXPORTS = {
    "QueryAgent": "query_agent", "get_query_agent": "query_agent",
    "RewriteNLAgent": "rewrite_nl_agent", "get_rewrite_agent": "rewrite_nl_agent",
    "compile_json_to_sql": "sql_compiler", "quote_ident": "sql_compiler",
    "_lit": "sql_compiler", "_contains_lit": "sql_compiler", "_compile_join": "sql_compiler",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(f"agents.{_EXPORTS[name]}"), name)
    globals()[name] = value
    return value
