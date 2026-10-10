"""Prepare the supplied CSV exports, load a local server, and configure Cloud.

No record samples, credentials or raw driver errors are printed. Existing tables
are never truncated or replaced. The preparation command needs only Python's
standard library; loading/checking uses the project's clickhouse-connect driver.
"""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import secrets
import sys
from urllib.parse import urlparse
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local-clickhouse"
DATABASE = "brand_analytics"
SCHEMAS = {
    "users": {
        "id": "String", "location": "Nullable(String)", "province_code": "UInt16",
        "country_code": "String", "created_at": "Nullable(DateTime64(3, 'UTC'))",
        "gender": "String", "age_range": "String", "is_org": "UInt8",
        "data_source": "String", "insertion_date": "DateTime64(3, 'UTC')",
    },
    "tweet_predictions": {
        "id": "String", "tweet_id": "String", "tweet_created_at": "DateTime64(3, 'UTC')",
        "author_id": "String", "data_source": "String", "country_code": "String",
        "task_name": "String", "scope_type": "Nullable(String)",
        "scope_value": "Nullable(String)", "numeric_value": "Nullable(Float64)",
        "category_value": "String", "boolean_value": "Nullable(UInt8)",
        "prediction_created_at": "DateTime64(3, 'UTC')",
        "prediction_month": "UInt32", "tweet_date": "UInt32",
    },
}
FILENAMES = {"users": "demo-brand-users.csv", "tweet_predictions": "demo-brand-tweet-predictions.csv"}


class DatasetError(ValueError):
    """Application-authored messages, safe to show without source values."""


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def convert_value(value, kind):
    if value is None or value in ("", "\\N", "NULL"):
        if kind.startswith("Nullable("):
            return None
        raise DatasetError("Zorunlu değer boş.")
    if kind.startswith("Nullable("):
        kind = kind[len("Nullable("):-1]
    if kind == "String":
        return value  # Never round identifiers through a floating point value.
    if kind.startswith("DateTime64"):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # These exports contain naive timestamps. UTC is an explicit import assumption.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if kind.startswith("UInt"):
        if kind == "UInt8" and value.lower() in {"true", "false"}:
            return int(value.lower() == "true")
        number = int(value)
        bits = int(kind[4:])
        if not 0 <= number < 2 ** bits:
            raise DatasetError("Tamsayı sütun sınırını aşıyor.")
        if kind == "UInt8" and number not in (0, 1):
            raise DatasetError("Boolean yalnızca 0/1 veya true/false olabilir.")
        return number
    if kind == "Float64":
        number = float(value)
        if not math.isfinite(number):
            raise DatasetError("Sonlu sayı gerekli.")
        return number
    raise DatasetError("Desteklenmeyen sütun türü.")


def export_csv(path, table, destination):
    schema = SCHEMAS[table]
    ids, authors = set(), set()
    nulls = dict.fromkeys(schema, 0)
    count = 0
    duplicate_ids = 0
    temp = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as source, \
                gzip.open(temp, "wt", encoding="utf-8", newline="\n") as target:
            reader = csv.DictReader(source)
            if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)) \
                    or set(reader.fieldnames) != set(schema):
                raise DatasetError(f"{table}: CSV başlıkları beklenen şemayla eşleşmiyor.")
            for row_number, raw in enumerate(reader, 2):
                if None in raw or any(value is None for value in raw.values()):
                    raise DatasetError(f"{table}: {row_number}. satırda sütun sayısı hatalı.")
                row = {}
                for column, kind in schema.items():
                    try:
                        row[column] = convert_value(raw[column], kind)
                    except (ValueError, OverflowError):
                        raise DatasetError(f"{table}: {row_number}. satır, {column} sütununda geçersiz değer.") from None
                    nulls[column] += row[column] is None
                if row["id"] in ids:
                    duplicate_ids += 1
                ids.add(row["id"])
                if table == "tweet_predictions":
                    authors.add(row["author_id"])
                target.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                count += 1
        if not count:
            raise DatasetError(f"{table}: CSV boş.")
        temp.replace(destination)
    finally:
        if temp.exists():
            temp.unlink()
    return {"rows": count, "distinct_ids": len(ids), "duplicate_id_rows": duplicate_ids,
            "null_counts": nulls, "sha256": file_hash(destination),
            "source_sha256": file_hash(path)}, ids, authors


def create_settings(folder):
    settings_path = folder / "settings.json"
    if settings_path.exists():
        return json.loads(settings_path.read_text(encoding="utf-8"))
    settings = {"import_password": secrets.token_urlsafe(32), "analyst_password": secrets.token_urlsafe(32)}
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    return settings


def write_settings(folder, settings, host="127.0.0.1", cloud=False):
    config = {"DATABASE_BACKEND": "clickhouse", "CLICKHOUSE_HOST": host,
              "CLICKHOUSE_PORT": "443" if cloud else "8123", "CLICKHOUSE_USERNAME": "dataset_analyst",
              "CLICKHOUSE_PASSWORD": settings["analyst_password"], "CLICKHOUSE_DB": DATABASE,
              "CLICKHOUSE_SECURE": "true" if cloud else "false", "CLICKHOUSE_VERIFY": "true",
              "CLICKHOUSE_TABLES": ",".join(SCHEMAS)}
    path = folder / ("streamlit-cloud.toml" if cloud else "streamlit-local.toml")
    path.write_text("# Keep existing OPENAI_API_KEY and other unrelated settings.\n" +
                    "\n".join(f"{key} = {json.dumps(value)}" for key, value in config.items()) + "\n", encoding="utf-8")
    return path


def prepare(users_path, predictions_path, folder=LOCAL):
    folder.mkdir(parents=True, exist_ok=True)
    # Invalidate an old manifest first; a failed conversion must not load stale files.
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()
    manifest = {"database": DATABASE, "schemas": SCHEMAS, "naive_timestamp_timezone": "UTC", "tables": {}}
    all_ids, all_authors = set(), set()
    for table, source in (("users", users_path), ("tweet_predictions", predictions_path)):
        info, ids, authors = export_csv(source, table, folder / f"{table}.jsonl.gz")
        manifest["tables"][table] = info
        if table == "users":
            all_ids = ids
        else:
            all_authors = authors
    manifest["authors_without_user"] = len(all_authors - all_ids)
    settings = create_settings(folder)
    (folder / "docker.env").write_text(f"LOCAL_CLICKHOUSE_PASSWORD={settings['import_password']}\n", encoding="utf-8")
    root = ET.Element("clickhouse")
    users = ET.SubElement(root, "users")
    user = ET.SubElement(users, "dataset_analyst")
    ET.SubElement(user, "password").text = settings["analyst_password"]
    networks = ET.SubElement(user, "networks")
    ET.SubElement(networks, "ip").text = "::/0"
    ET.SubElement(user, "profile").text = "default"
    ET.SubElement(user, "quota").text = "default"
    grants = ET.SubElement(user, "grants")
    ET.SubElement(grants, "query").text = f"GRANT SELECT ON {DATABASE}.*"
    ET.SubElement(grants, "query").text = "GRANT SELECT ON system.settings"
    ET.ElementTree(root).write(folder / "analyst.xml", encoding="utf-8", xml_declaration=True)
    write_settings(folder, settings)
    sql = f"CREATE DATABASE IF NOT EXISTS `{DATABASE}` ENGINE = Atomic;\n"
    for table, columns in SCHEMAS.items():
        fields = ",\n    ".join(f"`{column}` {kind}" for column, kind in columns.items())
        sql += f"CREATE TABLE `{DATABASE}`.`{table}` (\n    {fields}\n) ENGINE = MergeTree ORDER BY `id`;\n"
    (folder / "schema.sql").write_text(sql, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def iter_batches(path, schema, size=5000):
    batch = []
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            values = []
            for column, kind in schema.items():
                value = row[column]
                if value is not None and "DateTime64" in kind:
                    value = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
                values.append(value)
            batch.append(values)
            if len(batch) >= size:
                yield batch
                batch = []
    if batch:
        yield batch


def local_client(folder, analyst=False):
    import clickhouse_connect
    settings = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
    return clickhouse_connect.get_client(host="127.0.0.1", port=8123, database=DATABASE,
        username="dataset_analyst" if analyst else "dataset_importer",
        password=settings["analyst_password" if analyst else "import_password"],
        connect_timeout=10, send_receive_timeout=60, autogenerate_session_id=False)


def load(folder=LOCAL):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schemas"] != SCHEMAS or manifest["database"] != DATABASE:
        raise DatasetError("Manifest şeması farklı; prepare komutunu tekrar çalıştırın.")
    for table in SCHEMAS:
        if file_hash(folder / f"{table}.jsonl.gz") != manifest["tables"][table]["sha256"]:
            raise DatasetError("Hazırlanan dosya değişmiş; prepare komutunu tekrar çalıştırın.")
    client = local_client(folder)
    staging = {}
    try:
        # Refuse a second load instead of doubling counts or deleting earlier data.
        for table in SCHEMAS:
            if int(client.command(f"EXISTS TABLE `{DATABASE}`.`{table}`")):
                raise DatasetError("Hedef tablo zaten var; mevcut verilere dokunulmadı. check komutunu kullanın.")
        for table, schema in SCHEMAS.items():
            stage = table + "_import_" + uuid.uuid4().hex
            fields = ", ".join(f"`{column}` {kind}" for column, kind in schema.items())
            client.command(f"CREATE TABLE `{DATABASE}`.`{stage}` ({fields}) ENGINE = MergeTree ORDER BY `id`")
            staging[table] = stage
            for batch in iter_batches(folder / f"{table}.jsonl.gz", schema):
                client.insert(f"{DATABASE}.{stage}", batch, column_names=list(schema))
            actual = client.query(f"SELECT count() FROM `{DATABASE}`.`{stage}`").result_rows[0][0]
            if actual != manifest["tables"][table]["rows"]:
                raise DatasetError("Aktarılan satır sayısı CSV ile eşleşmiyor.")
        renames = ", ".join(f"`{DATABASE}`.`{stage}` TO `{DATABASE}`.`{table}`" for table, stage in staging.items())
        client.command("RENAME TABLE " + renames)
    finally:
        # Only scratch tables created by this call are eligible for cleanup.
        for stage in staging.values():
            try:
                client.command(f"DROP TABLE IF EXISTS `{DATABASE}`.`{stage}`")
            except Exception:
                pass
        client.close()
    return {table: info["rows"] for table, info in manifest["tables"].items()}


def check(folder=LOCAL):
    sys.path.insert(0, str(ROOT))
    from database import ClickHouseDatabase
    client = local_client(folder, analyst=True)
    try:
        db = ClickHouseDatabase(client, tables=tuple(SCHEMAS))
        counts = {table: db.run(f"SELECT count() AS total FROM `{table}`")[0]["total"] for table in SCHEMAS}
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if any(counts[table] != manifest["tables"][table]["rows"] for table in SCHEMAS):
            raise DatasetError("ClickHouse satır sayısı hazırlanan dosyalardan farklı.")
        return counts
    finally:
        client.close()


def cloud_config(url, folder=LOCAL):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password \
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.port not in (None, 443):
        raise DatasetError("Tünelin https:// ile başlayan ana adresini girin; yol, parola veya sorgu içermemeli.")
    settings = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
    return write_settings(folder, settings, parsed.hostname, cloud=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preparation = sub.add_parser("prepare")
    preparation.add_argument("--users", type=Path, default=Path.home() / "Downloads" / FILENAMES["users"])
    preparation.add_argument("--predictions", type=Path, default=Path.home() / "Downloads" / FILENAMES["tweet_predictions"])
    sub.add_parser("load")
    sub.add_parser("check")
    cloud = sub.add_parser("cloud-config")
    cloud.add_argument("--url", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.users, args.predictions)
            for table, info in result["tables"].items():
                print(f"{table}: {info['rows']} rows prepared; {info['distinct_ids']} distinct IDs; "
                      f"{info['duplicate_id_rows']} repeated ID rows preserved")
            print(f"Authors without matching user: {result['authors_without_user']}")
            print("Naive source timestamps are interpreted as UTC.")
            print(f"Private data and settings: {LOCAL}")
        elif args.command in ("load", "check"):
            result = load() if args.command == "load" else check()
            for table, count in result.items():
                print(f"{table}: {count} rows OK")
        else:
            print(f"Cloud settings saved: {cloud_config(args.url)}")
    except Exception as error:
        # Own validation errors contain only columns/row numbers; never show driver text.
        if isinstance(error, DatasetError):
            print(str(error), file=sys.stderr)
        else:
            print(f"Operation failed ({type(error).__name__}). Check Docker, paths and connection settings.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
