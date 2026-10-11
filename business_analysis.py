"""Small, deterministic marketing analyses over the shared read-only views."""
from datetime import datetime, timezone
import json
import unicodedata
import re
import pandas as pd

from marketing_data import ANALYSES, display
from forecasting import regular_series, forecast_series
from statistical_analysis import fisher_test


class BusinessAnalysis:
    def __init__(self, agent):
        self.agent = agent
        self.db = agent.db
        self.supported = {"posts", "labels", "audience"} <= set(agent.catalog or {})

    @property
    def choices(self):
        return {k: name for k, name in ANALYSES.items() if k in self.db.available_labels} if self.supported else {}

    def filters(self, analysis=None, individuals=False):
        result = []
        if analysis:
            if analysis not in self.choices:
                raise ValueError("Bu analiz türü mevcut veride bulunmuyor.")
            result.append({"column": "analysis_type", "op": "EQ", "value": analysis})
        if individuals:
            result.append({"column": "is_org", "op": "EQ", "value": 0})
        return result

    def profile(self):
        plan = {"table": "posts", "aggregates": [
            {"op": "count_distinct", "column": "tweet_id", "as": "posts"},
            {"op": "count_distinct", "column": "author_id", "as": "people"},
            {"op": "min", "column": "published_at", "as": "start"},
            {"op": "max", "column": "published_at", "as": "end"}]}
        row = self.agent.execute_plan(plan)["result"][0]
        row["analyses"] = list(self.choices.values())
        return row

    def distribution(self, analysis, group=None, individuals=False, extra_filters=None):
        if group not in (None, "gender", "age_group"):
            raise ValueError("Desteklenmeyen karşılaştırma.")
        filters = self.filters(analysis, individuals) + list(extra_filters or [])
        if group:
            filters += [{"column": group, "op": "IS_NOT_NULL"}]
        groups = [group] if group else []
        base = {"table": "labels", "filters": filters,
                "aggregates": [{"op": "count_distinct", "column": "tweet_id", "as": "total"}]}
        totals = self.agent.execute_plan({**base, "group_by": groups})
        response = self.agent.execute_plan({**base, "group_by": groups + ["label"],
            "order_by": [{"column": "total", "dir": "desc"}], "limit": 1000})
        denominators = {r.get(group): r["total"] for r in totals["result"]}
        rows = [{**r, "share": round(100 * r["total"] / denominators.get(r.get(group), 1), 2)}
                for r in response["result"] if denominators.get(r.get(group), 0)]
        return {"analysis": analysis, "group": group, "rows": rows,
                "denominators": totals["result"], "sql": [totals["sql"], response["sql"]]}

    def answer(self, question, synthesis=None):
        """Use measured, unambiguous common questions; validate all other NL plans."""
        folded = "".join(c for c in unicodedata.normalize("NFKD", question.lower().replace("ı", "i"))
                         if not unicodedata.combining(c))
        gender = "female" if "kadin" in folded else "male" if "erkek" in folded else None
        analysis = "journey" if any(w in folded for w in ("sikayet", "tavsiye", "yolculuk")) else (
            "emotion" if any(w in folded for w in ("duygu", "ofke", "mutluluk")) else (
                "topic" if "konu" in folded else None))
        # Do not turn a specific product/date question into a broad preset silently.
        broad = not re.search(r"\d", folded) and not any(w in folded for w in (
            "urun", "gecen", "son ay", "bu ay", "karsilastir", "daha", "neden", "etkilesim", "satis"))
        broad = broad and not ("kadin" in folded and "erkek" in folded)
        # Specific emotion/brand/product requests go through the schema-aware planner.
        broad = broad and not any(w in folded for w in ("ofke", "mutluluk", "marka"))
        common_roots = ("yas", "grup", "baskin", "duyg", "dagil", "neler", "ne", "paylas", "oran",
                        "kadin", "erkek", "cinsiyet", "gore", "genel", "toplam", "sikayet", "baslik",
                        "muster", "aras", "ve", "bir", "hangi", "en", "sik", "konu", "yolcul", "tavsiye",
                        "goster", "analiz", "sorgula", "var", "mi", "nasil", "incel", "etiket", "mevcut",
                        "bana", "tuketic", "hakk", "icin", "ile", "kadar", "sayi", "olan")
        broad = broad and all(word.startswith(common_roots) for word in re.findall(r"\w+", folded))
        if broad and analysis in self.choices:
            extra = [{"column": "gender", "op": "EQ", "value": gender}] if gender else []
            group = "age_group" if "yas" in folded else "gender" if "cinsiyet" in folded else None
            distribution = self.distribution(analysis, group, bool(gender), extra)
            rows = distribution["rows"]
            if not rows:
                return {"summary": "Bu kapsamda etiketlenmiş paylaşım bulunamadı. Bu sonuç, "
                        "şikâyet veya ihtiyacın gerçekte hiç olmadığı anlamına gelmez.", "distribution": distribution}
            target = "Complaint" if "sikayet" in folded else "Recommendation" if "tavsiye" in folded else None
            if analysis == "journey" and target and group:
                matched = {r[group]: r for r in rows if r["label"] == target}
                rows = [{group: r[group], "label": target, "total": matched.get(r[group], {}).get("total", 0),
                         "share": matched.get(r[group], {}).get("share", 0)} for r in distribution["denominators"]]
                distribution["rows"] = rows
                summary = " ".join(f"{display(r[group])} grubunda {display(target)} etiketi {r['total']} "
                                   f"paylaşımda var; aynı türde etiketli paylaşımlardaki oran %{r['share']:.1f}." for r in rows)
                return {"summary": summary + " Bu oran kişiler veya satışlar için değil, paylaşımlar için hesaplanır.",
                        "distribution": distribution}
            if analysis == "journey" and target and group is None:
                complaint = next((r for r in rows if r["label"] == target), None)
                total = distribution["denominators"][0]["total"]
                count = complaint["total"] if complaint else 0
                prefix = "Kadınların" if gender == "female" else "Erkeklerin" if gender else "İncelenen"
                summary = (f"{prefix} tüketici yolculuğu etiketi bulunan {total} benzersiz paylaşımının "
                           f"{count} tanesinde {display(target)} etiketi var; paylaşım bazında oran %{100 * count / total:.1f}. "
                           "Bu oran müşterilerin değil, seçilen kapsamdaki paylaşımların oranıdır. "
                           "Bu başlığın yoğunlaştığı konuları inceleyerek iyileştirme önceliklerini belirleyebilirsiniz.")
                # Complaint topics are measured on the same posts, not inferred from the overall topic mix.
                if target == "Complaint" and "topic" in self.choices:
                    subset = {"table": "labels", "columns": ["tweet_id"],
                              "filters": self.filters("journey", bool(gender)) + extra + [
                                  {"column": "label", "op": "EQ", "value": "Complaint"}]}
                    topics = self.distribution("topic", individuals=bool(gender), extra_filters=extra + [
                        {"column": "tweet_id", "op": "IN", "value": subset}])
                    if topics["rows"]:
                        lead = topics["rows"][0]
                        summary += f" Konu etiketi de bulunan şikâyet paylaşımlarında en sık başlık {display(lead['label'])} ({lead['total']} paylaşım)."
                    distribution["sql"] += topics["sql"]
                return {"summary": summary, "distribution": distribution}
            if group:
                leaders = {}
                for row in rows:
                    leaders.setdefault(row[group], row)
                summary = " ".join(f"{display(k)} grubunda en sık başlık {display(r['label'])}: "
                                   f"{r['total']} paylaşım (%{r['share']:.1f})." for k, r in leaders.items())
            else:
                lead = rows[0]
                summary = (f"{self.choices[analysis]} analizinde en sık başlık {display(lead['label'])}: "
                           f"{lead['total']} paylaşım (%{lead['share']:.1f}).")
            summary += " Bu dağılım paylaşım sıklığını gösterir; satış veya etkileşim ölçümü değildir. "
            summary += "Öne çıkan başlıkları içerik ve hizmet iyileştirmelerinde önceliklendirip sonuçları aynı kapsamda izleyin."
            return {"summary": summary, "distribution": distribution}
        result = self.agent.execute_nl_query(question)
        rows = result["result"]
        summary = "Bu kapsamda kayıt bulunamadı; filtre ve tarih kapsamını gözden geçirin."
        if rows:
            evidence = {"question": question, "rows": rows[:20], "returned_rows": len(rows),
                        "note": "Gösterilen satırlar sorgu sınırına tabidir; sayım etkileşim/satış değildir."}
            summary = "Sorgu tamamlandı. Ölçülen sonucu aşağıdaki ayrıntılardan inceleyebilirsiniz."
            if len(rows) == 1:
                summary = "; ".join(f"{display(k)}: {v}" for k, v in rows[0].items()) + "."
            if synthesis is not None and synthesis.llm is not None:
                try:
                    summary = synthesis.synthesize_executive_summary(question, json.dumps(evidence, ensure_ascii=False, default=str))
                except Exception:
                    pass
        return {"summary": summary, "query": result}

    def overview(self):
        distributions = [self.distribution(k) for k in ("journey", "topic", "emotion") if k in self.choices]
        return {"profile": self.profile(), "distributions": distributions}

    def overview_text(self, evidence):
        profile = evidence["profile"]
        if not profile["posts"]:
            return "Analiz edilebilir geçmiş tarihli paylaşım bulunamadı. Veri kapsamını kontrol edin."
        facts = [f"İncelenen dönemde {profile['posts']:,} benzersiz paylaşım ve "
                 f"{profile['people']:,} paylaşım yapan kişi bulunuyor.".replace(",", ".")]
        for distribution in evidence["distributions"]:
            rows = distribution["rows"]
            if rows:
                lead = rows[0]
                facts.append(f"{ANALYSES[distribution['analysis']]} analizinde en sık görülen başlık "
                             f"{display(lead['label'])}: {lead['total']} paylaşım (%{lead['share']:.1f}).")
        topic = next((d for d in evidence["distributions"] if d["analysis"] == "topic" and d["rows"]), None)
        priority = display(topic["rows"][0]["label"]) if topic else "en sık dile getirilen ihtiyaçlar"
        facts.append(f"İlk öncelik olarak {priority} başlığındaki geri bildirimleri inceleyin; "
                     "sorumlu ekiple küçük bir iyileştirme çalışması başlatıp aynı kapsamdaki paylaşım "
                     "ve şikâyet oranlarını düzenli izleyin. Bu bir strateji önerisidir; paylaşım "
                     "sıklığı tek başına satış, etkileşim veya sorunun nedenini göstermiyor.")
        return " ".join(facts)

    def brief(self, question, evidence, synthesis=None):
        fallback = self.overview_text(evidence)
        if synthesis is None or synthesis.llm is None or not evidence["profile"]["posts"]:
            return fallback
        compact = {"profile": evidence["profile"], "analyses": [
            {"analysis": ANALYSES[d["analysis"]], "top": d["rows"][:5],
             "denominators": d["denominators"]} for d in evidence["distributions"]]}
        try:
            text = synthesis.synthesize_executive_summary(question, json.dumps(compact, ensure_ascii=False, default=str))
            return text or fallback
        except Exception:
            return fallback

    def compare_people(self, analysis, label, group, group_a, group_b):
        """One person per group, positive = at least one post with the chosen label."""
        if group not in {"gender", "age_group"} or group_a == group_b:
            raise ValueError("İki farklı kitle grubu seçin.")
        if label not in self.db.available_labels.get(analysis, []):
            raise ValueError("Seçilen başlık veride bulunmuyor.")
        filters = self.filters(analysis, True) + [
            {"column": group, "op": "IN", "value": [group_a, group_b]},
            {"column": "author_id", "op": "IS_NOT_NULL"}]
        base = {"table": "labels", "group_by": [group], "filters": filters,
                "aggregates": [{"op": "count_distinct", "column": "author_id", "as": "n"}]}
        total = self.agent.execute_plan(base)
        success = self.agent.execute_plan({**base, "filters": filters + [
            {"column": "label", "op": "EQ", "value": label}]})
        n = {r[group]: r["n"] for r in total["result"]}
        positive = {r[group]: r["n"] for r in success["result"]}
        result = fisher_test(positive.get(group_a, 0), n.get(group_a, 0),
                             positive.get(group_b, 0), n.get(group_b, 0),
                             display(group_a), display(group_b))
        result["sql"] = [total["sql"], success["sql"]]
        result["label"] = display(label)
        result["context"] = ("Her kişi bir kez sayılır. Oran, bu analiz türünde en az bir paylaşımı "
                            "etiketlenmiş kişiler içinde seçilen başlığa sahip en az bir paylaşımı olan kişilerin oranıdır. "
                            "Kurum hesapları ve çelişkili/bilinmeyen demografi dışlanır.")
        return result

    def groups(self, group, analysis=None):
        table = "labels" if analysis else "posts"
        response = self.agent.execute_plan({"table": table, "group_by": [group],
            "filters": self.filters(analysis, True) + [{"column": group, "op": "IS_NOT_NULL"}],
            "order_by": [{"column": group, "dir": "asc"}]})
        return [r[group] for r in response["result"]]

    def forecast(self, analysis=None, label=None, grain="month", horizon=6, allow_zero=False):
        if grain not in {"day", "week", "month"}:
            raise ValueError("Geçersiz dönem.")
        table = "labels" if analysis else "posts"
        filters = self.filters(analysis)
        if label:
            if label not in self.db.available_labels.get(analysis, []):
                raise ValueError("Seçilen başlık veride bulunmuyor.")
            filters += [{"column": "label", "op": "EQ", "value": label}]
        range_result = self.agent.execute_plan({"table": table, "filters": filters,
            "aggregates": [{"op": "min", "column": "published_at", "as": "start"},
                           {"op": "max", "column": "published_at", "as": "end"}]})
        row = range_result["result"][0]
        if row["start"] is None or row["end"] is None:
            raise ValueError("Seçilen başlıkta tarihli paylaşım bulunamadı.")
        frequency = {"day": "D", "week": "W-SUN", "month": "M"}[grain]
        start_date = pd.Timestamp(row["start"]).tz_localize(None)
        last = pd.Timestamp(row["end"]).tz_localize(None)
        start_period = start_date.to_period(frequency)
        start = start_period.start_time
        if start_date > start:
            start = (start_period + 1).start_time
        # Exclude partial last bucket and the still-open present bucket.
        end = min(last.to_period(frequency).start_time,
                  pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None).to_period(frequency).start_time)
        span = pd.date_range(start, end, freq={"day": "D", "week": "W-MON", "month": "MS"}[grain],
                             inclusive="left")
        if not 16 <= len(span) <= 1000:
            raise ValueError("Bu dönem seçimi için yeterli geçmiş yok. En az 16 tam dönem gerekiyor; "
                             "günlük/haftalık dönem veya daha geniş bir başlık deneyin.")
        response = self.agent.execute_plan({"table": table, "time_bucket": {
            "column": "published_at", "grain": grain, "as": "period"}, "group_by": ["period"],
            "aggregates": [{"op": "count_distinct", "column": "tweet_id", "as": "value"}],
            "filters": filters + [{"column": "published_at", "op": "GTE", "value": start.isoformat(sep=" ")},
                                  {"column": "published_at", "op": "LT", "value": end.isoformat(sep=" ")}],
            "order_by": [{"column": "period", "dir": "asc"}], "limit": 1000})
        gap_message = ("Geçmişte kayıt bulunmayan dönemler var. Veri toplamanın kesintisiz olduğunu "
                       "biliyorsanız boş dönemleri sıfır sayma seçeneğini işaretleyin.")
        try:
            series = regular_series(response["result"], grain, "zero" if allow_zero else "error").reindex(span)
        except ValueError as error:
            if "Eksik dönemler" in str(error):
                raise ValueError(gap_message) from None
            raise
        if series.isna().any():
            if not allow_zero:
                raise ValueError(gap_message)
            series = series.fillna(0)
        result = forecast_series(series, horizon, nonnegative=True)
        result["sql"] = [range_result["sql"], response["sql"]]
        result["context"] = f"{display(label) if label else self.choices.get(analysis, 'Tüm paylaşımlar')} · "
        result["context"] += f"{start.date()} – {end.date()} (bitiş hariç)"
        return result
