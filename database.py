"""Read-only database adapters and schema catalogs shared by all modes."""
import json
import math
from pathlib import Path
import sqlite3
from contextlib import closing

CORE_TABLES = ("tweet_predictions", "tweets", "users", "user_factors")
QUERY_SETTINGS = {"readonly": 1, "max_execution_time": 30, "max_result_rows": 1000,
                  "max_result_bytes": 10_000_000, "result_overflow_mode": "throw"}


class _SampleStddev:
    def __init__(self):
        self.n, self.mean, self.m2 = 0, 0.0, 0.0

    def step(self, value):
        if value is None:
            return
        x = float(value)
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)

    def finalize(self):
        return math.sqrt(max(self.m2, 0) / (self.n - 1)) if self.n > 1 else None


class SQLiteDatabase:
    dialect = "sqlite"

    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise ValueError("SQLite dosyası bulunamadı.")
        with closing(self._connect()) as connection:
            names = connection.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                       "AND name NOT LIKE 'sqlite_%'").fetchall()
            self.catalog = {}
            for (name,) in names:
                escaped = name.replace('"', '""')
                rows = connection.execute(f'PRAGMA table_info("{escaped}")').fetchall()
                self.catalog[name] = {row[1]: row[2] for row in rows}

    def _connect(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        connection.execute("PRAGMA query_only=ON")
        connection.create_aggregate("stddev_samp", 1, _SampleStddev)
        # Protect local interactive queries too: roughly 1 million VM instructions.
        calls = 0

        def budget():
            nonlocal calls
            calls += 1
            return int(calls > 1000)

        connection.set_progress_handler(budget, 1000)
        return connection

    def get_table_info(self):
        return schema_text(self.catalog)

    def get_usable_table_names(self):
        return list(self.catalog)

    def run(self, sql):
        with closing(self._connect()) as connection:
            cursor = connection.execute(sql)
            rows = cursor.fetchmany(1001)
            if len(rows) > 1000:
                raise ValueError("Sorgu 1000 satır sınırını aşıyor.")
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]


def schema_text(catalog):
    # Column metadata only; never include sample values in an LLM prompt.
    return "\n".join(f"{table}: " + ", ".join(f"{name} {kind}" for name, kind in columns.items())
                     for table, columns in catalog.items())


class ClickHouseDatabase:
    dialect = "clickhouse"

    def __init__(self, client, tables=CORE_TABLES):
        from agents.query_validation import identifier
        self.client = client
        self.catalog = {}
        for table in tables:
            identifier(table)
            result = client.query(f"DESCRIBE TABLE `{table}`", settings=QUERY_SETTINGS)
            self.catalog[table] = {row[0]: row[1] for row in result.result_rows}
        if not self.catalog:
            raise ValueError("Kullanılabilir ClickHouse tablosu yok.")

    def get_table_info(self):
        return schema_text(self.catalog)

    def get_usable_table_names(self):
        return list(self.catalog)

    def run(self, sql):
        result = self.client.query(sql, settings=QUERY_SETTINGS)
        if len(result.result_rows) > 1000:
            raise ValueError("Sorgu 1000 satır sınırını aşıyor.")
        return [dict(zip(result.column_names, row)) for row in result.result_rows]


def connect_clickhouse(get_config):
    import clickhouse_connect
    host = get_config("CLICKHOUSE_HOST")
    if not host:
        raise ValueError("CLICKHOUSE_HOST tanımlanmalı.")
    secure = get_config("CLICKHOUSE_SECURE", "false").lower() in {"true", "1", "yes"}
    client = clickhouse_connect.get_client(
        host=host, port=int(get_config("CLICKHOUSE_PORT", "8443" if secure else "8123")),
        username=get_config("CLICKHOUSE_USERNAME", "default"),
        password=get_config("CLICKHOUSE_PASSWORD"), database=get_config("CLICKHOUSE_DB", "default"),
        secure=secure, connect_timeout=10, send_receive_timeout=35, autogenerate_session_id=False)
    try:
        configured = get_config("CLICKHOUSE_TABLES", ",".join(CORE_TABLES))
        tables = tuple(t.strip() for t in configured.split(",") if t.strip())
        return ClickHouseDatabase(client, tables)
    except Exception:
        client.close()
        raise
