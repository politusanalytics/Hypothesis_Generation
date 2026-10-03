"""Generate deterministic, synthetic data; never overwrite an existing database."""
import argparse
from datetime import date, timedelta
from pathlib import Path
import random
import sqlite3


def create_demo(path):
    path = Path(path).resolve()
    if path.exists():
        raise ValueError("Dosya zaten var; üzerine yazılmadı. Yeni bir çıktı yolu seçin.")
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, gender TEXT, age_range TEXT, is_org INTEGER);
        CREATE TABLE tweets (id INTEGER PRIMARY KEY, author_id INTEGER, created_at TEXT,
                             brand TEXT, engagement REAL, sentiment TEXT, issue TEXT);
        CREATE TABLE tweet_predictions (tweet_id INTEGER, task_name TEXT, category_value TEXT);
        CREATE TABLE user_factors (author_id INTEGER, factor_name TEXT, factor_value TEXT);
        """)
        rows, users, predictions = [], [], []
        idx = 0
        first = date(2024, 1, 1)
        for day in range(912):  # Ends 2026-06-30: complete months before the current date.
            count = 10 + day // 60 + rng.randrange(0, 5)
            for _ in range(count):
                idx += 1
                gender = "female" if idx % 2 else "male"
                engagement = max(0, rng.gauss(25 if gender == "female" else 20, 5))
                sentiment = "positive" if rng.random() < (0.7 if gender == "female" else 0.5) else "negative"
                users.append((idx, gender, "18-29" if idx % 3 else "30-44", 0))
                rows.append((idx, idx, str(first + timedelta(days=day)) + " 12:00:00", "demo",
                             engagement, sentiment, "delivery" if idx % 4 else "service"))
                predictions.append((idx, "sentiment", '["' + sentiment + '"]'))
        connection.executemany("INSERT INTO users VALUES (?, ?, ?, ?)", users)
        connection.executemany("INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        connection.executemany("INSERT INTO tweet_predictions VALUES (?, ?, ?)", predictions)
        connection.executescript("CREATE INDEX tweets_created_at ON tweets(created_at); "
                                 "CREATE INDEX tweets_author_id ON tweets(author_id);")
        connection.commit()
    finally:
        connection.close()
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/demo_analytics.db")
    args = parser.parse_args()
    print(create_demo(args.output))
