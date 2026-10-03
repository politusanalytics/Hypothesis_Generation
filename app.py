import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import re

# Dinamik motor fonksiyonu
from agent import get_hybrid_agent, get_secret
from data_analysis import get_analysis_engine

# --- 1. SAYFA YAPILANDIRMASI ---
st.set_page_config(
    page_title="Enlighty AI - Strategic Marketing Insight Engine",
    page_icon="📊",
    layout="wide"
)

st.title("📊 AI Destekli Pazarlama İçgörü Motoru")
st.caption("Stratejik Kök Neden Analizi, Demografik Sentez ve Hipotez Doğrulama Platformu")


# --- 2. SOL MENÜ: DİNAMİK MODEL SEÇİM PANELİ (TIERED ROUTING) ---
st.sidebar.subheader("⚙️ Model Yapılandırması")

profile_choice = st.sidebar.selectbox(
    "Çalışma Profili Seçin:",
    [
        "⚡ Hibrit Mod (Önerilen)",
        "🧠 Maksimum Hassasiyet",
        "💸 Maksimum Tasarruf & Hız",
        "🛠️ Özel Yapılandırma (Custom)"
    ],
    help="Sistemin sorgu planlama ve stratejik sentez adımlarında kullanacağı modelleri belirler."
)

if profile_choice == "⚡ Hibrit Mod (Önerilen)":
    selected_fast_model = "gpt-4o-mini"
    selected_reasoning_model = "gpt-4o"
    profile_badge = "⚡ Hibrit (Mini + GPT-4o)"
    profile_desc = "SQL/Sorgu motoru için hızlı `gpt-4o-mini`, stratejik yönetici sentezi için derin `gpt-4o` devrede."
elif profile_choice == "🧠 Maksimum Hassasiyet":
    selected_fast_model = "gpt-4o"
    selected_reasoning_model = "gpt-4o"
    profile_badge = "🧠 Full GPT-4o"
    profile_desc = "Sorgu planlama ve stratejik sentez aşamalarında gpt-4o kullanılır."
elif profile_choice == "💸 Maksimum Tasarruf & Hız":
    selected_fast_model = "gpt-4o-mini"
    selected_reasoning_model = "gpt-4o-mini"
    profile_badge = "💸 Full GPT-4o-mini"
    profile_desc = "Sorgu planlama ve stratejik sentez aşamalarında gpt-4o-mini kullanılır."
else:
    c1, c2 = st.sidebar.columns(2)
    with c1:
        selected_fast_model = st.selectbox("1. Kademe (SQL):", ["gpt-4o-mini", "gpt-4o"])
    with c2:
        selected_reasoning_model = st.selectbox("2. Kademe (Sentez):", ["gpt-4o", "gpt-4o-mini"])
    profile_badge = f"🛠️ Özel ({selected_fast_model} + {selected_reasoning_model})"
    profile_desc = "Kullanıcı tanımlı model eşleştirmesi."

st.sidebar.caption(profile_desc)

mod = st.sidebar.radio(
    "Çalışma Modunu Seçin:",
    ["🤖 Otonom İçgörü Modu", "👤 Manuel Soru Modu",
     "🧪 Hipotez Doğrulama Modu", "🔮 Tahminleme (Predictive) Modu",
     "📊 Veri Analiz Modu (ClickHouse)"]
)

@st.cache_resource(show_spinner=False)
def load_analysis_engine(model_name):
    return get_analysis_engine(model_name, get_secret)

if mod == "📊 Veri Analiz Modu (ClickHouse)":
    st.subheader("📊 ClickHouse Veri Analizi")
    st.caption("Sorunuzu yazın; ClickHouse sonuçlarını SQL ve veri tablosuyla inceleyin.")
    st.sidebar.caption("Veri kaynağı: ClickHouse · En fazla 1000 satır · Sorgu süresi: 30 saniye")
    try:
        analysis_engine = load_analysis_engine(selected_fast_model)
    except Exception:
        st.error("ClickHouse bağlantısı veya şema okuma başarısız. Bağlantı ayarlarını, "
                 "okuma izinlerini ve izin verilen tabloların varlığını kontrol edin.")
        st.stop()
    with st.expander("Kullanılabilir Veri Şeması"):
        st.code(analysis_engine.planner.schema)
    with st.form("clickhouse_analysis"):
        question = st.text_area("Analiz sorusu", placeholder="Duygu etiketlerinin dağılımı nedir?")
        submitted = st.form_submit_button("Sorgula")
    if submitted and question.strip():
        st.session_state.pop("clickhouse_analysis_result", None)
        try:
            with st.spinner("ClickHouse sorgusu hazırlanıyor ve çalıştırılıyor..."):
                st.session_state.clickhouse_analysis_result = analysis_engine.execute(question.strip())
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("Sorgu tamamlanamadı. Şemayı, sorgu kapsamını ve ClickHouse erişimini kontrol edin.")
    result = st.session_state.get("clickhouse_analysis_result")
    if result:
        st.caption(result["question"])
        st.code(result["sql"], language="sql")
        df = pd.DataFrame(result["rows"], columns=result["columns"])
        if df.empty:
            st.info("Sorgu sonucu boş; bu filtrelerle eşleşen veri bulunamadı.")
        else:
            st.dataframe(df, width="stretch", hide_index=True)
            st.caption(f"{len(df)} satır gösteriliyor. Sonuç sorgunun LIMIT değeriyle sınırlıdır.")
            st.download_button("CSV İndir", df.to_csv(index=False).encode("utf-8-sig"),
                               "clickhouse_analysis.csv", "text/csv")
    st.stop()

# Seçilen modele göre motoru önbellekten yükleme
@st.cache_resource(show_spinner=False)
def load_app_engine(f_model: str, r_model: str):
    return get_hybrid_agent(fast_model=f_model, reasoning_model=r_model)

try:
    db, llm, agent_executor, query_agent, rewrite_agent, synthesis_engine = load_app_engine(
        selected_fast_model, selected_reasoning_model)
except Exception:
    st.error("Veritabanı başlatılamadı. Bağlantı ayarlarını ve tablo izinlerini kontrol edin.")
    st.stop()
st.sidebar.info(f"Aktif veri kaynağı: {query_agent.dialect}")
if not get_secret("OPENAI_API_KEY"):
    st.sidebar.caption("OpenAI anahtarı yok: hipotez ve tahmin modları yerelde çalışır; doğal dil modları anahtar gerektirir.")
    if mod in {"🤖 Otonom İçgörü Modu", "👤 Manuel Soru Modu"}:
        st.info("Bu mod için OPENAI_API_KEY tanımlayın veya yerel hipotez/tahmin modunu seçin.")
        st.stop()

st.sidebar.divider()
st.sidebar.markdown(
    f"""
    **Aktif Motor:** `{profile_badge}`
    - ⚡ *SQL / JSON:* `{selected_fast_model}`
    - 🧠 *Strateji / Sentez:* `{selected_reasoning_model}`
    
    ---
    **Sistem Yetenekleri:**
    - 🎯 *Kök Sebep Analizi (Topics & Products)*
    - 👥 *İlişkisel Demografi (SQL JOIN)*
    - 📉 *Huni Daralması (Funnel Narrowing)*
    - 🛡️ *Duygu Saplantısı Filtresi*
    """
)


# --- 3. MAKRO TEMA VE GRAFİK MOTORU ---
THEME_KEYWORDS = {
    "Satın Alma Sonrası & Teslimat/İade": ["satın alma", "iade", "teslimat", "kargo", "gecikme", "sipariş"],
    "Servis, Garanti & Onarım": ["servis", "garanti", "arıza", "tamir", "parça", "yedek", "onarım", "bakım"],
    "Ürün Kalitesi & Dayanıklılık": ["kalite", "performans", "dayanıklılık", "bozul", "fırın", "süpürge", "ocak", "alet", "küçük ev"],
    "Fiyat, Değer & Kampanya": ["fiyat", "kampanya", "indirim", "pahalı", "ücret", "değer"],
    "Müşteri Hizmetleri & Çağrı": ["müşteri hizmet", "çağrı", "destek", "iletişim", "ulaşım", "telefon"],
    "İnovasyon, Teknoloji & İmaj": ["inovasyon", "teknoloji", "liderlik", "güven", "tasarım", "robot"]
}

def map_micro_to_macro_theme(text: str) -> str:
    t_low = str(text).lower()
    for theme, kws in THEME_KEYWORDS.items():
        if any(kw in t_low for kw in kws):
            return theme
    return "Diğer Müşteri Geri Bildirimleri"


def render_generative_ui(result_data, query_json: dict, title_context: str = ""):
    if not result_data:
        st.info("Bu adım için görselleştirilecek veri dönmedi.")
        return

    df = None
    try:
        if isinstance(result_data, str) and result_data.startswith("[("):
            import ast
            raw_tuples = ast.literal_eval(result_data)
            cols = []
            if query_json.get("group_by"):
                cols.extend(query_json["group_by"])
            if query_json.get("aggregates"):
                cols.extend([agg.get("as", "Adet") for agg in query_json["aggregates"]])
            if not cols and raw_tuples:
                cols = [f"Alan_{i+1}" for i in range(len(raw_tuples[0]))]
            df = pd.DataFrame(raw_tuples, columns=cols[:len(raw_tuples[0])] if raw_tuples else None)
        elif isinstance(result_data, list) and len(result_data) > 0 and isinstance(result_data[0], dict):
            df = pd.DataFrame(result_data)
        elif isinstance(result_data, pd.DataFrame):
            df = result_data.copy()
    except Exception:
        df = None

    if df is None or df.empty:
        st.write("**Ham Veri:**", result_data)
        return

    df.columns = [str(c).replace('"', '').replace("'", "").split(".")[-1] for c in df.columns]

    for c in df.columns:
        converted = pd.to_numeric(df[c], errors='coerce')
        if not converted.isna().all() and converted.notna().sum() > len(df) * 0.5:
            df[c] = converted

    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    categorical_cols = df.select_dtypes(exclude=['number']).columns.tolist()

    if not numeric_cols and categorical_cols:
        cat_c = categorical_cols[0]
        freq = df[cat_c].value_counts().reset_index()
        freq.columns = [cat_c, "Bahsedilme Sayısı"]
        df = freq
        numeric_cols = ["Bahsedilme Sayısı"]
        categorical_cols = [cat_c]

    val_col = numeric_cols[0] if numeric_cols else df.columns[-1]

    # Senaryo 1: Demografi (Yaş & Cinsiyet)
    has_age = any("age" in c.lower() for c in df.columns)
    has_gen = any("gender" in c.lower() for c in df.columns)
    if has_age and has_gen:
        age_col = [c for c in df.columns if "age" in c.lower()][0]
        gen_col = [c for c in df.columns if "gender" in c.lower()][0]
        fig = px.bar(
            df,
            x=age_col,
            y=val_col,
            color=gen_col,
            barmode="group",
            title=f"{title_context} (Yaş ve Cinsiyet Dağılımı)",
            text=val_col,
            color_discrete_sequence=["#1f77b4", "#ff7f0e"]
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(height=380, margin=dict(l=20, r=20, t=40, b=40), yaxis_title="Bahsedilme Hacmi")
        st.plotly_chart(fig)

    # Senaryo 2: Kök Neden ve Konu Dağılımı
    elif categorical_cols:
        cat_col = categorical_cols[0]
        if df[val_col].max() <= 3 and len(df) >= 3:
            df_plot = df.copy()
            df_plot["Makro Tema"] = df_plot[cat_col].apply(map_micro_to_macro_theme)
            df_plot = df_plot.groupby("Makro Tema")[val_col].sum().reset_index()
            df_plot = df_plot.sort_values(by=val_col, ascending=True)
            plot_cat = "Makro Tema"
            st.caption("ℹ️ *Tekil mikro başlıklar karar verilebilir netlik için makro iş temalarına konsolide edilmiştir.*")
        else:
            df[cat_col] = df[cat_col].astype(str).apply(lambda x: (x[:40] + "...") if len(x) > 40 else x)
            df_plot = df.sort_values(by=val_col, ascending=True).tail(8)
            plot_cat = cat_col

        fig = px.bar(
            df_plot,
            x=val_col,
            y=plot_cat,
            orientation="h",
            title=f"{title_context} (Hacim Dağılımı)",
            text=val_col,
            color_discrete_sequence=["#2b5c8f"]
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            height=340,
            xaxis_title="Bahsedilme Sayısı",
            yaxis_title="",
            margin=dict(l=10, r=30, t=40, b=30),
            yaxis=dict(tickfont=dict(size=12))
        )
        st.plotly_chart(fig)
    else:
        st.dataframe(df, width="stretch")

    with st.expander("📋 Detaylı Veri Tablosunu İncele", expanded=False):
        st.dataframe(df, width="stretch", hide_index=True)


# --- 4. ÇALIŞMA MODLARI ---

# MOD 1: OTONOM İÇGÖRÜ MODU
if mod == "🤖 Otonom İçgörü Modu":
    st.subheader("🤖 Otonom Stratejik İçgörü Keşfi")
    st.write("Ajan, veritabanındaki anomalileri ve operasyonel tıkanıklıkları otonom olarak araştırır.")

    if st.button("🚀 Otonom Taramayı Başlat"):
        with st.spinner("Veritabanı şeması taranıyor ve makro iş problemi belirleniyor..."):
            schema = query_agent.schema
            macro_q = rewrite_agent.generate_macro_question(schema)
            st.info(f"**Belirlenen Stratejik Araştırma Sorusu:** {macro_q}")
            _, sub_qs = rewrite_agent.decompose_question(macro_q, schema)
            
        evidence_list = []
        all_query_results = []
        for i, sq in enumerate(sub_qs[:2], 1):
            with st.status(f"Adım {i}: {sq}", expanded=False):
                try:
                    q_res = query_agent.execute_nl_query(sq)
                    evidence_list.append(f"Soru: {sq}\nBulgu: {q_res['result']}\nSQL: {q_res['sql']}")
                    all_query_results.append((sq, q_res))
                    st.code(q_res['sql'], language="sql")
                except Exception as e:
                    evidence_list.append(f"Soru: {sq}\nHata: {e}")

        with st.spinner("Yönetici özeti hazırlanıyor..."):
            combined_evidence = "\n\n".join(evidence_list)
            insight = synthesis_engine.synthesize_executive_summary(macro_q, combined_evidence)
            
            st.markdown("### 📌 Yönetici Özeti (Final Insight)")
            st.success(insight)

            if all_query_results:
                tab_titles = [f"📊 Görsel Analiz (Adım {idx+1})" for idx in range(len(all_query_results))]
                tabs = st.tabs(tab_titles)
                for idx, tab in enumerate(tabs):
                    with tab:
                        sq_text, res_obj = all_query_results[idx]
                        st.caption(f"**Soru:** {sq_text}")
                        render_generative_ui(res_obj["result"], res_obj["json_query"], f"Adım {idx+1}")

# ==============================================================================
# MOD 2: ÇOK TURLU SOHBET VE KONU TAKİBİ MODU (ROADMAP 3A - CHAT THREADING)
# ==============================================================================
elif mod == "👤 Manuel Soru Modu":
    st.subheader("👤 Yönetici Soru ve Takip Modu (Chat Threading)")
    st.caption("Önceki sorularınızı ve filtrelerinizi unutmayan çok turlu konuşma motoru.")

    # Oturum durumlarını (Session State) başlat
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "pending_clarification" not in st.session_state:
        st.session_state.pending_clarification = None
    if "active_final_query" not in st.session_state:
        st.session_state.active_final_query = None

    # Sol tarafa sohbeti temizleme butonu ekle
    with st.sidebar:
        if st.button("🗑️ Konuyu Sıfırla (Yeni Oturum)"):
            st.session_state.chat_history = []
            st.session_state.pending_clarification = None
            st.session_state.active_final_query = None
            st.rerun()

    # 1. Önceki konuşma geçmişini ekrana bas
    for idx, turn in enumerate(st.session_state.chat_history):
        with st.chat_message("user"):
            st.markdown(f"**{turn['user_query']}**")
            if turn.get("resolved_query") and turn["resolved_query"] != turn["user_query"]:
                st.caption(f"*(Bağlamdan türetilen analiz sorusu: {turn['resolved_query']})*")

        with st.chat_message("assistant"):
            st.markdown(turn["insight"])
            if turn.get("all_query_results"):
                tab_titles = [f"📊 Grafik {t_idx+1}" for t_idx in range(len(turn["all_query_results"]))]
                tabs = st.tabs(tab_titles)
                for t_idx, tab in enumerate(tabs):
                    with tab:
                        sq_text, res_obj = turn["all_query_results"][t_idx]
                        st.caption(f"**Soru:** {sq_text}")
                        render_generative_ui(res_obj["result"], res_obj["json_query"], f"T{idx+1}-Adım{t_idx+1}")

    # 2. Netleştirme bekleyen butonlar varsa göster
    if st.session_state.pending_clarification:
        clar_data = st.session_state.pending_clarification
        st.warning(f"🤔 **Hedef Belirleme:** {clar_data['message']}")
        opt_cols = st.columns(len(clar_data["options"]))
        for idx, opt in enumerate(clar_data["options"]):
            with opt_cols[idx]:
                if st.button(opt["label"], key=f"clar_btn_chat_{idx}"):
                    st.session_state.active_final_query = f"{clar_data['base_query']} ({opt['context']})"
                    st.session_state.pending_clarification = None
                    st.rerun()

    # 3. Yeni soru girişi (Chat Input)
    user_input = st.chat_input("Pazarlama stratejisi veya takip sorunuzu yazın (Örn: Peki bunun kadınlar arasındaki oranı ne?)...")

    if user_input:
        schema = query_agent.schema

        # Konuşma hafızasından takip sorusunu çözümle
        with st.spinner("Önceki bağlam taranıyor ve soru netleştiriliyor..."):
            resolved_query = rewrite_agent.contextualize_query(
                user_input, 
                [{"user": t["user_query"], "assistant_summary": t["insight"]} for t in st.session_state.chat_history]
            )

        # Netleştirme gerekiyor mu denetle
        clarification_eval = rewrite_agent.assess_clarification_need(resolved_query, schema)

        if clarification_eval.get("needs_clarification", False) and clarification_eval.get("options"):
            st.session_state.pending_clarification = {
                "base_query": resolved_query,
                "message": clarification_eval.get("clarification_message", "Hangi alana odaklanalım?"),
                "options": clarification_eval.get("options", [])
            }
            st.rerun()
        else:
            st.session_state.pending_clarification = None
            st.session_state.active_final_query = resolved_query
            st.session_state.last_user_raw_input = user_input

    # 4. Soruyu Çalıştır ve Yanıtı Kaydet
    if st.session_state.active_final_query:
        query_to_run = st.session_state.active_final_query
        raw_input = getattr(st.session_state, "last_user_raw_input", query_to_run)
        st.session_state.active_final_query = None

        with st.chat_message("user"):
            st.markdown(f"**{raw_input}**")
            if query_to_run != raw_input:
                st.caption(f"*(Bağlamdan türetilen analiz: {query_to_run})*")

        with st.chat_message("assistant"):
            with st.spinner("Soru alt analiz adımlarına ayrıştırılıyor..."):
                schema = query_agent.schema
                _, sub_qs = rewrite_agent.decompose_question(query_to_run, schema)

            evidence_list = []
            all_query_results = []
            for i, sq in enumerate(sub_qs[:2], 1):
                with st.status(f"Analiz Adımı {i}: {sq}", expanded=False):
                    try:
                        q_res = query_agent.execute_nl_query(sq)
                        evidence_list.append(f"Bulgu: {q_res['result']}")
                        all_query_results.append((sq, q_res))
                        st.code(q_res['sql'], language="sql")
                    except Exception as e:
                        evidence_list.append(f"Hata: {e}")

            with st.spinner("Yönetici özeti sentezleniyor..."):
                combined_evidence = "\n\n".join(evidence_list)
                insight = synthesis_engine.synthesize_executive_summary(query_to_run, combined_evidence)

                st.markdown(insight)

                if all_query_results:
                    tab_titles = [f"📊 Analiz {idx+1}" for idx in range(len(all_query_results))]
                    tabs = st.tabs(tab_titles)
                    for idx, tab in enumerate(tabs):
                        with tab:
                            sq_text, res_obj = all_query_results[idx]
                            st.caption(f"**Araştırılan Soru:** {sq_text}")
                            render_generative_ui(res_obj["result"], res_obj["json_query"], f"Bulgu {idx+1}")

            # Konuşma hafızasına kaydet
            st.session_state.chat_history.append({
                "user_query": raw_input,
                "resolved_query": query_to_run,
                "insight": insight,
                "all_query_results": all_query_results
            })
            st.rerun()


# ==============================================================================
# MOD 3: ÇOKLU VE RAKİP HİPOTEZ DOĞRULAMA MODU (ROADMAP 3E)
# ==============================================================================
elif mod == "🧪 Hipotez Doğrulama Modu":
    from analytical_ui import hypothesis_panel
    hypothesis_panel(query_agent)

elif mod == "🔮 Tahminleme (Predictive) Modu":
    from analytical_ui import forecast_panel
    forecast_panel(query_agent)
