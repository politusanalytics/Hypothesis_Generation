"""User-configured statistical and time-series analysis panels."""
from datetime import timedelta
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from statistical_analysis import test_database_groups, hypothesis_report
from forecasting import regular_series, forecast_series, forecast_report


def _filters(key):
    with st.expander("Ek filtreler"):
        text = st.text_area("JSON filtre listesi", "[]", key=key,
                            help='Örnek: [{"column":"brand","op":"EQ","value":"demo"}]')
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        st.error("Filtre listesi geçerli JSON olmalı.")
        return None
    if not isinstance(parsed, list):
        st.error("Filtreler bir JSON listesi olmalı.")
        return None
    return parsed


def _numeric(catalog, table):
    return [name for name, kind in catalog[table].items()
            if any(part in kind.lower() for part in ("int", "float", "decimal", "real", "double", "numeric"))]


def hypothesis_panel(query_agent):
    st.subheader("🧪 İstatistiksel Hipotez Testi")
    st.write("İki grubun ortalamasını veya bir sonucun oranını karşılaştırın. "
             "Test tüm seçili kayıtların toplamlarından hesaplanır.")
    st.caption("H0: Seçilen metrikte fark yok. H1: Fark var. İki yönlü test uygulanır; nedensel açıklamalar test edilmez.")
    catalog = query_agent.catalog
    tables = list(catalog)
    table = st.selectbox("Tablo", tables, index=tables.index("tweets") if "tweets" in tables else 0, key="hyp_table")
    columns = list(catalog[table])
    default_group = next((name for name in ("gender", "issue", "task_name", "sentiment", "brand") if name in columns), columns[0])
    group_col = st.selectbox("Grup sütunu", columns, index=columns.index(default_group),
                            key="hyp_group_col")
    try:
        groups_result = query_agent.execute_plan({"table": table, "group_by": [group_col],
                                                  "filters": [{"column": group_col, "op": "IS_NOT_NULL"}],
                                                  "limit": 1000})
        groups = [row[group_col] for row in groups_result["result"]]
    except Exception:
        st.error("Grup değerleri okunamadı; skaler bir grup sütunu seçin.")
        return
    if len(groups) < 2:
        st.info("Bu sütunda en az iki farklı, boş olmayan grup gerekli.")
        return
    group_a = st.selectbox("A grubu", groups, key="hyp_a")
    group_b = st.selectbox("B grubu", groups, index=1, key="hyp_b")
    method_label = st.selectbox("Test", ["Ortalama farkı — Welch", "Oran farkı — Fisher"], key="hyp_method")
    numeric = _numeric(catalog, table)
    if method_label.startswith("Ortalama") and not numeric:
        st.info("Bu tabloda sayısal bir metrik sütunu yok.")
        return
    metrics = numeric if method_label.startswith("Ortalama") else columns
    metric = st.selectbox("Metrik sütunu", metrics, key="hyp_metric")
    success_value = None
    if method_label.startswith("Oran"):
        raw_value = st.text_input("Başarı sayılacak değer", value="positive", key="hyp_success",
                                 help='Metin için positive; sayı için 1 yazın. Payda, metrik alanı boş olmayan kayıtlardır.')
        try:
            success_value = json.loads(raw_value)
        except json.JSONDecodeError:
            success_value = raw_value
    alpha = st.selectbox("Anlamlılık düzeyi (α)", [0.05, 0.01, 0.10], key="hyp_alpha")
    filters = _filters("hyp_filters")
    independent = st.checkbox("Gözlemler bağımsızdır; aynı kişi/olay tekrarı ve eşleştirilmiş veri yoktur.", key="hyp_independent")
    st.caption("Tekrarlanan kullanıcı tweetleri bağımsız olmayabilir. Böyle verilerde kişi düzeyinde "
               "toplulaştırılmış bir tablo veya uygun örneklem kullanın. Birden çok testte hata oranı artar.")
    if st.button("Hipotezi Test Et", key="hyp_run"):
        st.session_state.pop("statistical_result", None)
        if not independent or filters is None:
            st.warning("Bağımsızlık koşulunu ve filtre listesini doğrulayın.")
        else:
            try:
                result = test_database_groups(query_agent, table, group_col, group_a, group_b, metric,
                                              "welch" if method_label.startswith("Ortalama") else "fisher",
                                              success_value, filters, alpha)
                result["context"] = f"{table}.{metric}: A={group_a}, B={group_b}"
                st.session_state.statistical_result = result
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("Test sorgusu tamamlanamadı. Seçilen sütunların türlerini ve filtreleri kontrol edin.")
    result = st.session_state.get("statistical_result")
    if result:
        st.caption(result["context"])
        st.markdown(hypothesis_report(result))
        with st.expander("Testin SQL kanıtı"):
            for sql in result["sql"]:
                st.code(sql, language="sql")


def forecast_panel(query_agent):
    st.subheader("🔮 Zaman Serisi Tahmini")
    st.write("Dönemlik bir metriği yerel doğrusal trend modeliyle tahmin edin; "
             "son dönemlerde ölçülen hata ve tahmin aralığını inceleyin.")
    catalog = query_agent.catalog
    tables = list(catalog)
    table = st.selectbox("Tablo", tables, index=tables.index("tweets") if "tweets" in tables else 0, key="forecast_table")
    dates = [name for name, kind in catalog[table].items()
             if "date" in kind.lower() or "time" in kind.lower() or any(
                 hint in name.lower() for hint in ("date", "timestamp", "created_at", "event_time"))]
    if not dates:
        st.info("Bu tabloda tanınan bir tarih sütunu yok; tarih içeren bir tablo seçin.")
        return
    date_col = st.selectbox("Tarih sütunu", dates, key="forecast_date")
    grain = st.selectbox("Dönem", ["month", "week", "day"], key="forecast_grain")
    op = st.selectbox("Metrik", ["count", "sum", "avg"], key="forecast_op")
    metric = None
    if op != "count":
        numeric = _numeric(catalog, table)
        if not numeric:
            st.info("Toplam/ortalama için sayısal sütun gerekli.")
            return
        metric = st.selectbox("Metrik sütunu", numeric, key="forecast_metric")
    try:
        range_result = query_agent.execute_plan({"table": table, "aggregates": [
            {"op": "min", "column": date_col, "as": "earliest"},
            {"op": "max", "column": date_col, "as": "latest"}]})["result"][0]
        start = pd.Timestamp(range_result["earliest"]).date()
        end = pd.Timestamp(range_result["latest"]).date() + timedelta(days=1)
    except Exception:
        st.info("Tarih kapsamı okunamadı; tarih sütununu ve veri varlığını kontrol edin.")
        return
    start = st.date_input("Başlangıç (dahil)", start, key="forecast_start")
    end = st.date_input("Bitiş (hariç)", end, key="forecast_end")
    horizon = int(st.number_input("Tahmin ufku (dönem)", 1, 60, 6, key="forecast_horizon"))
    filters = _filters("forecast_filters")
    zero = st.checkbox("Kayıt bulunmayan dönemleri sıfır say (tam veri kapsamını doğruladım).",
                       disabled=op == "avg", key="forecast_zero")
    st.caption("En az 16 tam dönem gerekli. Başlangıç ve bitişteki kısmi dönemler dışlanır. "
               "Ortalama metriklerinde eksik dönemler sıfırla doldurulmaz.")
    if st.button("Tahmin Üret", key="forecast_run"):
        st.session_state.pop("forecast_result", None)
        try:
            if filters is None or end <= start:
                raise ValueError("Tarih aralığı veya filtreler geçersiz.")
            frequency = {"day": "D", "week": "W-SUN", "month": "M"}[grain]
            start_period = pd.Timestamp(start).to_period(frequency)
            query_start = start_period.start_time
            if query_start.date() < start:
                query_start = (start_period + 1).start_time
            query_end = pd.Timestamp(end).to_period(frequency).start_time
            # Exclude the still-open current bucket, even if a future end is selected.
            today_bucket = pd.Timestamp.now(tz="Europe/Istanbul").tz_localize(None).to_period(frequency).start_time
            query_end = min(query_end, today_bucket)
            span = pd.date_range(query_start, query_end, freq={"day": "D", "week": "W-MON", "month": "MS"}[grain],
                                 inclusive="left")
            if not 16 <= len(span) <= 1000:
                raise ValueError("Seçilen kapsam 16–1000 tam dönem içermeli.")
            aggregate = {"op": op, "as": "value"}
            if metric:
                aggregate["column"] = metric
            plan = {"table": table, "time_bucket": {"column": date_col, "grain": grain, "as": "period"},
                    "group_by": ["period"], "aggregates": [aggregate],
                    "filters": filters + [{"column": date_col, "op": "GTE", "value": query_start.isoformat(sep=" ")},
                                           {"column": date_col, "op": "LT", "value": query_end.isoformat(sep=" ")}],
                    "order_by": [{"column": "period", "dir": "asc"}], "limit": 1000}
            response = query_agent.execute_plan(plan)
            series = regular_series(response["result"], grain, "zero" if zero and op != "avg" else "error")
            # Include empty edge buckets too: coverage is the selected range, not only returned rows.
            series = series.reindex(span)
            if series.isna().any():
                if zero and op != "avg":
                    series = series.fillna(0)
                else:
                    raise ValueError("Seçilen kapsamda eksik dönemler var.")
            result = forecast_series(series, horizon)
            result["sql"] = response["sql"]
            result["context"] = f"{table} · {op}({metric or '*'}) · {grain} · {query_start.date()}–{query_end.date()}"
            st.session_state.forecast_result = result
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("Tahmin sorgusu/modeli tamamlanamadı. Tarih sütunu, metrik ve filtreleri kontrol edin.")
    result = st.session_state.get("forecast_result")
    if result:
        st.caption(result["context"])
        st.markdown(forecast_report(result))
        fig = go.Figure()
        history, future = result["history"], result["forecast"]
        fig.add_trace(go.Scatter(x=history.index, y=history.values, name="Geçmiş"))
        fig.add_trace(go.Scatter(x=future["period"], y=future["lower"], mode="lines", line={"width": 0}, showlegend=False))
        fig.add_trace(go.Scatter(x=future["period"], y=future["upper"], fill="tonexty", mode="lines",
                                 line={"width": 0}, name="%95 tahmin aralığı"))
        fig.add_trace(go.Scatter(x=future["period"], y=future["forecast"], name="Tahmin"))
        st.plotly_chart(fig)
        st.dataframe(future, hide_index=True, width="stretch")
        with st.expander("Geçmiş dönem sınaması"):
            st.dataframe(result["validation"], hide_index=True)
        st.code(result["sql"], language="sql")
        st.download_button("Tahmini CSV İndir", future.to_csv(index=False).encode("utf-8-sig"),
                           "forecast.csv", "text/csv")
