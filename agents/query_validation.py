"""Shared, fail-closed validation for every query execution path."""
import copy
import math
import re

MAX_ROWS = 1000
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
FILTER_OPS = {"EQ", "NEQ", "GT", "GTE", "LT", "LTE", "LIKE", "ILIKE", "IN", "NOT_IN",
              "BETWEEN", "HAS", "HAS_ANY", "HAS_ALL", "IS_NULL", "IS_NOT_NULL"}
AGG_OPS = {"count", "count_distinct", "sum", "avg", "min", "max", "group_array", "stddev_samp"}


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("Geçersiz tablo veya sütun tanımlayıcısı.")
    return value


def _fields(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj) - set(allowed) or not set(required) <= set(obj):
        raise ValueError("Sorgu planında eksik veya desteklenmeyen alan var.")


def validate_query_plan(plan, dialect="sqlite", catalog=None, default_limit=None,
                        allowed_tables=None, depth=0):
    if dialect not in {"sqlite", "clickhouse"}:
        raise ValueError("Desteklenmeyen SQL lehçesi.")
    if depth > 4 or not isinstance(plan, dict):
        raise ValueError("Geçersiz veya fazla iç içe sorgu planı.")
    if plan.get("error"):
        raise ValueError(str(plan["error"]))
    if "table" not in plan:
        raise ValueError("JSON sorgusunda zorunlu 'table' alanı eksik.")
    _fields(plan, {"table", "alias", "columns", "joins", "aggregates", "filters", "group_by",
                   "order_by", "limit", "array_joins", "time_bucket"}, {"table"})
    plan = copy.deepcopy(plan)
    table = identifier(plan["table"])
    allowed = set(catalog) if catalog is not None else set(allowed_tables or ())
    if (catalog is not None or allowed_tables is not None) and table not in allowed:
        raise ValueError("Sorgu tablosu izin verilen şemada yok.")
    if depth == 0 and default_limit is not None:
        plan.setdefault("limit", default_limit)
    if "limit" in plan and (type(plan["limit"]) is not int or not 1 <= plan["limit"] <= MAX_ROWS):
        raise ValueError("Satır limiti 1–1000 arasında olmalı.")
    for key in ("columns", "joins", "aggregates", "filters", "group_by", "order_by", "array_joins"):
        if key in plan and not isinstance(plan[key], list):
            raise ValueError(f"{key} bir liste olmalı.")
    scope = {table: table}
    if "alias" in plan:
        scope[identifier(plan["alias"])] = table
    for join in plan.get("joins", []):
        _fields(join, {"table", "alias", "type", "on"}, {"table"})
        jt = identifier(join["table"])
        if (catalog is not None or allowed_tables is not None) and jt not in allowed:
            raise ValueError("JOIN tablosu izin verilen şemada yok.")
        scope[jt] = jt
        if "alias" in join:
            alias = identifier(join["alias"])
            if alias in scope:
                raise ValueError("Tekrarlanan tablo takma adı.")
            scope[alias] = jt
        if not isinstance(join.get("type", "INNER"), str):
            raise ValueError("Geçersiz JOIN türü.")
        kind = join.get("type", "INNER").upper()
        if kind not in {"INNER", "LEFT", "RIGHT", "FULL", "CROSS"}:
            raise ValueError("Geçersiz JOIN türü.")
        join["type"] = kind
        on = join.get("on")
        if kind == "CROSS" and on is None:
            continue
        if not isinstance(on, dict) or set(on) != {"left", "right"}:
            raise ValueError("JOIN koşulu yalnızca iki sütunun eşitliği olabilir.")

    array_aliases, result_aliases = set(), set()

    def column(value, output=False):
        identifier(value)
        if value in array_aliases or (output and value in result_aliases):
            return
        if catalog is None:
            return
        parts = value.split(".")
        if len(parts) == 2:
            if parts[0] not in scope or parts[1] not in catalog[scope[parts[0]]]:
                raise ValueError("Sütun izin verilen şemada yok.")
        elif len(parts) == 1:
            matches = [t for t in set(scope.values()) if value in catalog[t]]
            if len(matches) != 1:
                raise ValueError("Sütun şemada yok veya belirsiz; tablo adıyla belirtin.")
        else:
            raise ValueError("Sütun tablo.sütun biçiminde olmalı.")

    for join in plan.get("joins", []):
        if join.get("on"):
            column(join["on"]["left"])
            column(join["on"]["right"])
    if plan.get("array_joins") and dialect != "clickhouse":
        raise ValueError("ARRAY JOIN yalnızca ClickHouse ile desteklenir.")
    for item in plan.get("array_joins", []):
        if isinstance(item, str):
            column(item)
        else:
            _fields(item, {"column", "as"}, {"column"})
            column(item["column"])
            if "as" in item:
                array_aliases.add(identifier(item["as"]))
    if "time_bucket" in plan:
        bucket = plan["time_bucket"]
        _fields(bucket, {"column", "grain", "as"}, {"column", "grain", "as"})
        column(bucket["column"])
        if bucket["grain"] not in {"day", "week", "month"}:
            raise ValueError("Zaman kırılımı day/week/month olmalı.")
        result_aliases.add(identifier(bucket["as"]))
    for agg in plan.get("aggregates", []):
        _fields(agg, {"op", "column", "as"}, {"op"})
        if agg["op"] not in AGG_OPS:
            raise ValueError("Desteklenmeyen toplama işlemi.")
        if agg.get("column") is not None:
            column(agg["column"])
        elif agg["op"] != "count":
            raise ValueError("Bu toplama işlemi için sütun gerekli.")
        alias = agg.get("as") or f"{agg['op']}_{str(agg.get('column') or agg['op']).replace('.', '_')}"
        identifier(alias)
        if alias in result_aliases:
            raise ValueError("Tekrarlanan sonuç sütunu adı.")
        result_aliases.add(alias)
    for item in plan.get("columns", []):
        column(item)
    for item in plan.get("group_by", []):
        if not plan.get("time_bucket") or item != plan["time_bucket"]["as"]:
            column(item)
    if plan.get("time_bucket") and plan["time_bucket"]["as"] not in plan.get("group_by", []):
        raise ValueError("Zaman kırılımı takma adı group_by içinde bulunmalı.")
    for item in plan.get("order_by", []):
        _fields(item, {"column", "dir"}, {"column"})
        column(item["column"], output=True)
        if not isinstance(item.get("dir", "asc"), str) or item.get("dir", "asc").lower() not in {"asc", "desc"}:
            raise ValueError("Geçersiz sıralama yönü.")
    for item in plan.get("filters", []):
        _fields(item, {"column", "op", "value"}, {"column", "op"})
        column(item["column"])
        if not isinstance(item["op"], str):
            raise ValueError("Geçersiz filtre işlemi.")
        op = item["op"].upper()
        item["op"] = op
        if op not in FILTER_OPS:
            raise ValueError("Desteklenmeyen filtre işlemi.")
        if op in {"IS_NULL", "IS_NOT_NULL"}:
            continue
        if "value" not in item:
            raise ValueError("Filtre değeri gerekli.")
        value = item["value"]
        if isinstance(value, dict):
            if op not in {"IN", "NOT_IN"}:
                raise ValueError("Alt sorgu yalnızca IN/NOT_IN ile kullanılabilir.")
            nested = validate_query_plan(value, dialect, catalog, None, allowed_tables, depth + 1)
            outputs = len(nested.get("group_by", [])) + len(nested.get("aggregates", []))
            if not outputs:
                outputs = len(nested.get("columns", []))
            if outputs != 1:
                raise ValueError("IN alt sorgusu tam bir sütun döndürmeli.")
            item["value"] = nested
        else:
            values = value if isinstance(value, list) else [value]
            for scalar in values:
                if type(scalar) not in {str, int, float, bool, type(None)}:
                    raise ValueError("Geçersiz filtre değeri.")
                if isinstance(scalar, float) and not math.isfinite(scalar):
                    raise ValueError("Geçersiz sayısal değer.")
            if op in {"IN", "NOT_IN", "HAS_ANY", "HAS_ALL"} and (not isinstance(value, list) or not value):
                raise ValueError("Filtre boş olmayan bir değer listesi gerektirir.")
            if op == "BETWEEN" and (not isinstance(value, list) or len(value) != 2):
                raise ValueError("BETWEEN iki değer gerektirir.")
            if isinstance(value, list) and op not in {"IN", "NOT_IN", "HAS", "HAS_ANY", "HAS_ALL", "BETWEEN"}:
                raise ValueError("Bu filtre tek bir değer gerektirir.")
            if value is None:
                raise ValueError("NULL için IS_NULL/IS_NOT_NULL kullanın.")
    return plan
