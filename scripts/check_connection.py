"""Check schema access without OpenAI calls or printing secrets/data samples."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import get_database_connection, get_secret
from database import DatabaseInitializationError, connect_clickhouse


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clickhouse", action="store_true", help="Require ClickHouse, irrespective of the local profile")
    args = parser.parse_args()
    try:
        if args.clickhouse:
            db = connect_clickhouse(get_secret)
            dialect = "clickhouse"
        else:
            db, _, dialect = get_database_connection()
        print(f"Connection OK: {dialect}")
        for table, columns in db.catalog.items():
            print(f"  {table}: {len(columns)} columns")
        if hasattr(db, "client"):
            db.client.close()
    except DatabaseInitializationError as error:
        print(str(error))
        sys.exit(1)
    except Exception as error:
        print(f"Connection failed ({type(error).__name__}). Check the configured host, port, database and read permissions.")
        sys.exit(1)
