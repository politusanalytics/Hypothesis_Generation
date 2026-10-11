"""Simple business-facing UI, shared semantics across all five modes."""
import hashlib
import json
import pandas as pd
import plotly.express as px
import streamlit as st

from agent import get_hybrid_agent, get_secret, SynthesisEngine
from data_analysis import get_analysis_engine
from database import DatabaseInitializationError
from business_analysis import BusinessAnalysis
from marketing_data import ANALYSES, COLUMNS, display

st.set_page_config(page_title="Pazarlama İçgörüleri", page_icon="📊", layout="wide")
st.title("📊 Pazarlama İçgörüleri")
st.caption("Veriyi anlayın, önceliğinizi belirleyin ve sonuçları izleyin.")
st.sidebar.subheader("Ne yapmak istersiniz?")
MODES = ["🤖 Otonom İçgörü Modu", "👤 Manuel Soru Modu", "🧪 Hipotez Doğrulama Modu",
         "🔮 Tahminleme (Predictive) Modu", "📊 Veri Analiz Modu (ClickHouse)"]
mod = st.sidebar.radio("Çalışma modu", MODES)
with st.sidebar.expander("Gelişmiş ayarlar"):
    profile = st.selectbox("Yanıt profili", ["Dengeli", "Daha ayrıntılı", "Ekonomik"])
    selected_fast_model = "gpt-4o" if profile == "Daha ayrıntılı" else "gpt-4o-mini"
    selected_reasoning_model = "gpt-4o-mini" if profile == "Ekonomik" else "gpt-4o"
    st.caption("Model seçimi veri kapsamını veya hesaplama yöntemini değiştirmez.")


def connection_key():
    keys = ("DATABASE_BACKEND", "SQLITE_DB_PATH", "CLICKHOUSE_HOST", "CLICKHOUSE_PORT",
            "CLICKHOUSE_DB", "CLICKHOUSE_USERNAME", "CLICKHOUSE_PASSWORD", "CLICKHOUSE_TABLES",
            "CLICKHOUSE_SECURE", "CLICKHOUSE_VERIFY", "OPENAI_API_KEY")
    return hashlib.sha256(json.dumps([get_secret(k) for k in keys]).encode()).hexdigest()


@st.cache_resource(show_spinner=False, ttl=300)
def load_app_engine(f_model, r_model, fingerprint):
    return get_hybrid_agent(fast_model=f_model, reasoning_model=r_model)


@st.cache_resource(show_spinner=False, ttl=300)
def load_analysis_engine(model, fingerprint):
    return get_analysis_engine(model, get_secret)


fingerprint = connection_key()
session_key = ("friendly-v1", fingerprint)
if st.session_state.get("view_context") != session_key:
    for name in ("friendly_overview", "friendly_chat", "friendly_analysis", "explore_answer",
                 "statistical_result", "forecast_result"):
        st.session_state.pop(name, None)
    st.session_state.view_context = session_key
try:
    if mod == MODES[4]:
        engine = load_analysis_engine(selected_fast_model, fingerprint)
        query_agent = engine.planner
        synthesis_engine = SynthesisEngine(query_agent.llm) if get_secret("OPENAI_API_KEY") else None
        rewrite_agent = None
    else:
        db, llm, executor, query_agent, rewrite_agent, synthesis_engine = load_app_engine(
            selected_fast_model, selected_reasoning_model, fingerprint)
except DatabaseInitializationError as error:
    st.error(str(error))
    st.stop()
except Exception:
    st.error("ClickHouse bağlantısı veya uygulama başlatılamadı. Veri kaynağı ve bağlantı ayarlarını kontrol edin.")
    st.stop()

service = BusinessAnalysis(query_agent)
if not service.supported:
    st.info("Bu kaynağın alanları henüz iş analiziyle eşleştirilemedi. ClickHouse için users ve "
            "tweet_predictions tablolarının izinlerini ve sütunlarını kontrol edin.")
    st.stop()
try:
    available_choices = service.choices
except Exception:
    st.error("Analiz başlıkları okunamadı. ClickHouse bağlantısını ve tablo okuma izinlerini kontrol edin.")
    st.stop()
st.sidebar.caption("Veri kaynağı: " + ("ClickHouse" if query_agent.dialect == "clickhouse" else "Yerel demo"))
st.sidebar.caption("Gelecek tarihli kayıtlar hariç tutulur. Örnek marka adlarından sektör veya ürün varsayılmaz.")


def friendly_frame(rows):
    frame = pd.DataFrame(rows)
    for column in ("label", "gender", "age_group", "analysis_type"):
        if column in frame:
            frame[column] = frame[column].map(display)
    return frame.rename(columns=COLUMNS)


def distribution_details(result, key, expanded=False):
    with st.expander("Veriyi ve grafiği incele", expanded=expanded):
        frame = friendly_frame(result["rows"])
        st.caption("Adetler benzersiz paylaşımlardır. Oranların paydası, aynı analiz türünde ve kitlede "
                   "etiketlenmiş benzersiz paylaşımlardır. Bir paylaşım birden fazla başlığa sahip olabilir.")
        if frame.empty:
            st.info("Bu kapsamda etiketlenmiş paylaşım bulunamadı.")
        else:
            st.dataframe(frame, hide_index=True, width="stretch")
            if st.checkbox("Grafiği göster", key=key + "_chart"):
                plot = frame
                if result["group"]:
                    column = COLUMNS[result["group"]]
                    cohort = st.selectbox("Grafikteki kitle", list(frame[column].unique()), key=key + "_cohort")
                    plot = frame[frame[column] == cohort]
                plot = plot.nlargest(10, "Paylaşım sayısı").sort_values("Paylaşım sayısı")
                fig = px.bar(plot, x="Paylaşım sayısı", y="Başlık", orientation="h")
                fig.update_layout(yaxis_title="", height=max(300, len(plot) * 35), showlegend=False)
                st.plotly_chart(fig, config={"displayModeBar": False})
            st.download_button("Veriyi indir", frame.to_csv(index=False).encode("utf-8-sig"),
                               "analiz.csv", "text/csv", key=key + "_download")
    with st.expander("Sorgu ayrıntıları"):
        for sql in result["sql"]:
            st.code(sql, language="sql")


def answer_details(result, key):
    if "distribution" in result:
        distribution_details(result["distribution"], key)
    elif "query" in result:
        query = result["query"]
        with st.expander("Veriyi ve sorguyu incele"):
            st.dataframe(friendly_frame(query["result"]), hide_index=True, width="stretch")
            st.code(query["sql"], language="sql")
            st.caption("Sonuç en fazla 1000 satırdır. Sıfır veya boş sonuç gerçek hayatta hiç ihtiyaç olmadığı anlamına gelmez.")


if mod == MODES[0]:
    st.subheader("🤖 Strateji özeti")
    st.write("Mevcut veride öne çıkan konuları, duyguları ve tüketici yolculuğunu birlikte değerlendirin.")
    if st.button("Strateji özetini hazırla", key="overview_run", type="primary"):
        st.session_state.pop("friendly_overview", None)
        try:
            with st.spinner("Bulgular kontrol ediliyor ve özet hazırlanıyor..."):
                evidence = service.overview()
                summary = service.brief("Mevcut geri bildirimlere göre hangi konulara öncelik vermeliyiz?",
                                        evidence, synthesis_engine)
                st.session_state.friendly_overview = {"summary": summary, "evidence": evidence}
        except Exception:
            st.error("Özet hazırlanamadı. Veri bağlantısını kontrol edip tekrar deneyin.")
    result = st.session_state.get("friendly_overview")
    if result:
        st.success(result["summary"])
        p = result["evidence"]["profile"]
        start = pd.Timestamp(p["start"]).strftime("%d.%m.%Y") if p["start"] is not None else "Tarih yok"
        end = pd.Timestamp(p["end"]).strftime("%d.%m.%Y") if p["end"] is not None else "Tarih yok"
        st.caption(f"Kapsam: {start} – {end}. Paylaşım sıklığı ölçülür; gerçek satış veya etkileşim değil.")
        for i, distribution in enumerate(result["evidence"]["distributions"]):
            st.caption(ANALYSES[distribution["analysis"]])
            distribution_details(distribution, f"overview_{i}")

elif mod == MODES[1]:
    st.subheader("👤 Veriye bir soru sor")
    st.caption("Örnek: Kadınların paylaşımlarındaki şikâyet oranı nedir? · Yaş gruplarının baskın duyguları neler?")
    history = st.session_state.setdefault("friendly_chat", [])
    if st.sidebar.button("Yeni sohbet", key="chat_clear"):
        st.session_state.friendly_chat = []
        st.rerun()
    follow = st.checkbox("Önceki soruya devam et", key="chat_follow", disabled=not history,
                         help="Kapalıyken her soru bağımsızdır; önceki ürün ve filtreler taşınmaz.")
    for i, turn in enumerate(history):
        with st.chat_message("user"):
            st.write(turn["question"])
        with st.chat_message("assistant"):
            st.markdown(turn["result"]["summary"])
            answer_details(turn["result"], f"chat_{i}")
    question = st.chat_input("Sorunuzu yazın…")
    if question and question.strip():
        try:
            with st.spinner("Sorunuz mevcut veriye göre yanıtlanıyor..."):
                resolved = question.strip()
                if follow and history and rewrite_agent is not None:
                    resolved = rewrite_agent.contextualize_query(resolved, [
                        {"user": t["resolved"], "assistant_summary": ""} for t in history[-3:]])
                result = service.answer(resolved, synthesis_engine)
            history.append({"question": question.strip(), "resolved": resolved, "result": result})
            st.rerun()
        except ValueError as error:
            st.info(str(error))
        except Exception:
            st.error("Soru yanıtlanamadı. Bağlantıyı ve model anahtarını kontrol edip yeniden deneyin.")

elif mod == MODES[2]:
    from analytical_ui import hypothesis_panel
    hypothesis_panel(query_agent)

elif mod == MODES[3]:
    from analytical_ui import forecast_panel
    forecast_panel(query_agent)

else:
    st.subheader("📊 Veriyi keşfet")
    st.caption("Duygu, konu ve marka etiketlerini ayrı ayrı inceleyin. Bu mod yalnızca ClickHouse verisini kullanır.")
    if not available_choices:
        st.info("Bu kapsamda etiketlenmiş geçmiş tarihli paylaşım bulunamadı.")
        st.stop()
    analysis = st.selectbox("Neyi inceleyelim?", list(service.choices), format_func=service.choices.get, key="explore_analysis")
    group = st.selectbox("Nasıl karşılaştıralım?", [None, "gender", "age_group"],
                         format_func=lambda x: {None: "Genel dağılım", "gender": "Cinsiyete göre", "age_group": "Yaş grubuna göre"}[x],
                         key="explore_group")
    selection = (analysis, group)
    if st.button("Analizi göster", key="explore_run", type="primary"):
        st.session_state.pop("friendly_analysis", None)
        try:
            st.session_state.friendly_analysis = service.distribution(analysis, group)
            st.session_state.friendly_analysis_selection = selection
        except ValueError as error:
            st.info(str(error))
        except Exception:
            st.error("Analiz tamamlanamadı. ClickHouse bağlantısını kontrol edin.")
    result = st.session_state.get("friendly_analysis")
    if result and st.session_state.get("friendly_analysis_selection") == selection:
        distribution_details(result, "explore", expanded=True)
    with st.expander("Kendi analiz sorumu yazmak istiyorum"):
        with st.form("explore_question"):
            question = st.text_area("Sorunuz", placeholder="Yaş gruplarının baskın duyguları neler?")
            submitted = st.form_submit_button("Soruyu yanıtla")
        if submitted and question.strip():
            st.session_state.pop("explore_answer", None)
            try:
                st.session_state.explore_answer = service.answer(question.strip(), synthesis_engine)
            except ValueError as error:
                st.info(str(error))
            except Exception:
                st.error("Soru yanıtlanamadı. Model anahtarını ve veri bağlantısını kontrol edin.")
    answer = st.session_state.get("explore_answer")
    if answer:
        st.markdown(answer["summary"])
        answer_details(answer, "explore_answer")
    with st.expander("Teknik veri şeması"):
        st.code(query_agent.schema)
