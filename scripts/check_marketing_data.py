"""Read-only business-view smoke check, optionally against the original CSVs.

Outputs aggregate counts only. No IDs, credentials, source samples or driver errors.
"""
import argparse
import ast
from collections import defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import ClickHouseDatabase, connect_clickhouse
from marketing_data import marketing_database
from agents.query_agent import QueryAgent
from business_analysis import BusinessAnalysis


def compare_csv(service, folder):
    """Independent Python reference: no reuse of SQL label decoding or grouping."""
    users = defaultdict(list)
    with (folder / "demo-brand-users.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            users[row["id"]].append(row)
    audience = {}
    for key, rows in users.items():
        person = {}
        for source, target in (("gender", "gender"), ("age_range", "age_group"), ("is_org", "is_org")):
            values = {r[source] for r in rows if r[source] not in ("", "unknown", "Unknown")}
            value = next(iter(values)) if len(values) == 1 else None
            if source == "is_org" and value is not None:
                value = int(value.lower() in ("true", "1"))
            elif source == "age_range" and value is not None:
                value = value.replace("40>", "40+")
            person[target] = value
        audience[key] = person
    events, source_labels = defaultdict(set), []
    with (folder / "demo-brand-tweet-predictions.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            stamp = datetime.fromisoformat(row["tweet_created_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            events[row["tweet_id"]].add((row["author_id"], stamp))
            source_labels.append((row["tweet_id"], row["task_name"], ast.literal_eval(row["category_value"])))
    now = datetime.now(timezone.utc)
    posts = {key: next(iter(values)) for key, values in events.items() if len(values) == 1
             and next(iter(values))[1] < now}
    profile = service.profile()
    assert profile["posts"] == len(posts), "Benzersiz paylaşım sayımı uyuşmuyor."
    assert profile["people"] == len({r[0] for r in posts.values()}), "Kişi sayımı uyuşmuyor."
    decoded = set()
    for tweet_id, task, values in source_labels:
        if tweet_id not in posts or task not in service.db.selected_tasks:
            continue
        for value in values:
            label = value.split("|||", 1)[0].strip()
            if label:
                decoded.add((tweet_id, service.db.selected_tasks[task], label))
    comparisons = 0
    for analysis in service.choices:
        for group in (None, "gender", "age_group"):
            counts, totals = defaultdict(set), defaultdict(set)
            for tweet_id, kind, label in decoded:
                if kind != analysis:
                    continue
                author = posts[tweet_id][0]
                cohort = audience.get(author, {}).get(group) if group else None
                if group and cohort is None:
                    continue
                counts[(cohort, label)].add(tweet_id)
                totals[cohort].add(tweet_id)
            response = service.distribution(analysis, group)
            actual = {(r.get(group), r["label"]): r for r in response["rows"]}
            assert set(actual) == set(counts), "Etiket veya kitle kapsamı uyuşmuyor."
            for key, values in counts.items():
                assert actual[key]["total"] == len(values), "Etiket sayımı uyuşmuyor."
                assert actual[key]["share"] == round(100 * len(values) / len(totals[key[0]]), 2), "Payda uyuşmuyor."
            comparisons += len(counts)
    # Independent per-person denominator and outcome, not per-post counts.
    analysis = "emotion"
    if analysis in service.choices and {"female", "male"} <= set(service.groups("gender", analysis)):
        label = service.db.available_labels[analysis][0]
        n, positive = defaultdict(set), defaultdict(set)
        for tweet_id, kind, value in decoded:
            if kind != analysis:
                continue
            author = posts[tweet_id][0]
            person = audience.get(author, {})
            if person.get("is_org") != 0 or person.get("gender") not in {"female", "male"}:
                continue
            group = person["gender"]
            n[group].add(author)
            if value == label:
                positive[group].add(author)
        result = service.compare_people(analysis, label, "gender", "female", "male")
        assert (result["n_a"], result["n_b"]) == (len(n["female"]), len(n["male"])), "Kişi paydası uyuşmuyor."
        assert result["rate_a"] == len(positive["female"]) / len(n["female"]), "Kişi oranı uyuşmuyor."
        assert result["rate_b"] == len(positive["male"]) / len(n["male"]), "Kişi oranı uyuşmuyor."
    print(f"CSV karşılaştırması başarılı: {comparisons} etiket/kitle sayımı ve paydası eşleşti.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="Yerel Docker ClickHouse ve özel ayar dosyasını kullan.")
    parser.add_argument("--compare-csv-dir", type=Path, help="Orijinal iki CSV'nin bulunduğu klasör.")
    args = parser.parse_args()
    try:
        if args.local:
            from scripts.local_clickhouse import local_client, LOCAL
            db = ClickHouseDatabase(local_client(LOCAL, True), ("users", "tweet_predictions"))
        else:
            from agent import get_secret
            db = connect_clickhouse(get_secret)
        db = marketing_database(db)
        service = BusinessAnalysis(QueryAgent(db=db, catalog=db.catalog, dialect="clickhouse"))
        if not service.supported:
            raise ValueError("İş analizi şeması tanınamadı.")
        p = service.profile()
        print(json.dumps({"posts": p["posts"], "people": p["people"],
                          "label_counts": {k: len(v) for k, v in db.available_labels.items()}}, ensure_ascii=False))
        for analysis in service.choices:
            service.distribution(analysis)
        service.answer("Yaş gruplarının baskın duyguları neler?")
        service.answer("Kadınların şikayet oranı nedir?")
        if args.compare_csv_dir:
            compare_csv(service, args.compare_csv_dir)
        print("OK: İş analizi sorguları salt okunur çalıştı; kaynak veriler değiştirilmedi.")
        db.source.client.close()
        return 0
    except Exception as error:
        print(f"Kontrol tamamlanamadı ({type(error).__name__}). Bağlantı, tablo şeması ve CSV kapsamını kontrol edin.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
