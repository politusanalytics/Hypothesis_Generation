"""Business questions first; statistical and SQL details are optional."""
import plotly.graph_objects as go
import streamlit as st
from business_analysis import BusinessAnalysis
from marketing_data import display
from statistical_analysis import hypothesis_report
from forecasting import forecast_report


def hypothesis_panel(query_agent):
    service = BusinessAnalysis(query_agent)
    st.subheader("🧪 İki kitleyi karşılaştır")
    st.write("Bir başlığın iki farklı kitlede ne kadar yaygın olduğunu karşılaştırın.")
    if not service.supported or not service.choices:
        st.info("Bu veri kaynağında karşılaştırılabilir kitle ve etiket alanları bulunamadı.")
        return
    analysis = st.selectbox("Ne hakkında karşılaştırma yapalım?", list(service.choices),
                            format_func=service.choices.get, key="hyp_analysis")
    label = st.selectbox("İncelenecek başlık", service.db.available_labels[analysis],
                        format_func=display, key=f"hyp_label_{analysis}")
    group = st.selectbox("Kitleyi nasıl ayıralım?", ["gender", "age_group"],
                         format_func=lambda x: {"gender": "Cinsiyete göre", "age_group": "Yaş grubuna göre"}[x],
                         key="hyp_group")
    try:
        groups = service.groups(group, analysis)
    except Exception:
        st.error("Kitle bilgileri okunamadı. Veri bağlantısını kontrol edin.")
        return
    if len(groups) < 2:
        st.info("Bu seçimde karşılaştırılabilir en az iki kitle grubu bulunmuyor.")
        return
    left, right = st.columns(2)
    a = left.selectbox("Birinci kitle", groups, format_func=display, key=f"hyp_a_{analysis}_{group}")
    b = right.selectbox("İkinci kitle", [g for g in groups if g != a], format_func=display,
                        key=f"hyp_b_{analysis}_{group}_{a}")
    st.caption("Her kişi bir kez sayılır. Seçilen başlığa sahip en az bir paylaşımı olan kişilerin oranı "
               "karşılaştırılır. Kurum hesapları ve çelişkili/bilinmeyen kitle bilgileri dışlanır.")
    independent = st.checkbox("İki kitlenin ayrı ve bağımsız kişileri temsil ettiğini onaylıyorum.",
                              key="hyp_independent")
    selection = (analysis, label, group, a, b)
    if st.button("Karşılaştır", key="hyp_run", type="primary"):
        st.session_state.pop("statistical_result", None)
        if not independent:
            st.warning("Karşılaştırmadan önce kitlelerin bağımsızlığını onaylayın.")
        else:
            try:
                with st.spinner("Kişi bazında oranlar karşılaştırılıyor..."):
                    result = service.compare_people(analysis, label, group, a, b)
                st.session_state.statistical_result = result
                st.session_state.statistical_selection = selection
            except ValueError as error:
                st.info(str(error))
            except Exception:
                st.error("Karşılaştırma tamamlanamadı. Veri bağlantısını kontrol edin.")
    result = st.session_state.get("statistical_result")
    if result and st.session_state.get("statistical_selection") == selection:
        c1, c2 = st.columns(2)
        c1.metric(result["group_a"], f"%{100 * result['rate_a']:.1f}", help=f"{result['n_a']} kişi")
        c2.metric(result["group_b"], f"%{100 * result['rate_b']:.1f}", help=f"{result['n_b']} kişi")
        conclusion = ("İstatistiksel test bu farkı anlamlı buluyor." if result["p_value"] < result["alpha"]
                      else "Bu veriler farkın anlamlı olduğunu göstermeye yetmiyor; eşitlik kanıtlanmış değil.")
        st.success(f"{result['label']} başlığında iki kitle arasında {abs(result['effect']) * 100:.1f} "
                   f"yüzde puan fark var. {conclusion} Sonuç farkın nedenini açıklamaz.")
        with st.expander("Hesaplama ayrıntıları"):
            st.caption(result["context"])
            st.markdown(hypothesis_report(result))
            for sql in result["sql"]:
                st.code(sql, language="sql")


def forecast_panel(query_agent):
    service = BusinessAnalysis(query_agent)
    st.subheader("🔮 Önümüzdeki dönemleri tahmin et")
    st.write("Geçmiş paylaşım hacmine bakarak olası gelecek hacmini ve belirsizliğini görün.")
    if not service.supported:
        st.info("Bu veri kaynağında paylaşım tarihleri tanınamadı.")
        return
    choices = {"all": "Tüm paylaşımlar", **service.choices}
    selected = st.selectbox("Neyi tahmin edelim?", list(choices), format_func=choices.get, key="forecast_target")
    analysis = None if selected == "all" else selected
    label = None
    if analysis:
        label = st.selectbox("Hangi başlık?", [None] + service.db.available_labels[analysis],
                             format_func=lambda x: "Tüm başlıklar" if x is None else display(x),
                             key=f"forecast_label_{analysis}")
    grain = st.selectbox("Dönem", ["month", "week", "day"],
                         format_func=lambda x: {"month": "Aylık", "week": "Haftalık", "day": "Günlük"}[x],
                         key="forecast_grain")
    horizon = int(st.number_input("Kaç dönem ilerisi?", min_value=1, max_value=12, value=6, key="forecast_horizon"))
    with st.expander("Veri kapsamı seçenekleri"):
        zero = st.checkbox("Veri toplama kesintisizdi; kayıt olmayan dönemleri sıfır say.", key="forecast_zero")
        st.caption("Onay verilmezse eksik dönemlerde tahmin üretilmez. Gelecek tarihli kayıtlar ve "
                   "ilk/son kısmi dönemler kullanılmaz. Tarih alanı otomatik seçilir.")
    selection = (analysis, label, grain, horizon, zero)
    if st.button("Tahmini hazırla", key="forecast_run", type="primary"):
        st.session_state.pop("forecast_result", None)
        st.session_state.forecast_weak = False
        try:
            with st.spinner("Geçmiş dönemlerde sınanmış tahmin hazırlanıyor..."):
                result = service.forecast(analysis, label, grain, horizon, zero)
            st.session_state.forecast_result = result
            st.session_state.forecast_selection = selection
        except ValueError as error:
            st.info(str(error))
        except Exception:
            st.error("Tahmin tamamlanamadı. Veri bağlantısını kontrol edip yeniden deneyin.")
    result = st.session_state.get("forecast_result")
    if result and st.session_state.get("forecast_selection") == selection:
        if not result["beats_naive"]:
            st.warning("Model geçmiş dönem sınamasında basit son-değer tahminini geçemedi. "
                       "Bu veriyle güçlü bir trend öngörüsü sunulamıyor. Daha düzenli veya daha geniş "
                       "bir veri kapsamı deneyin.")
            with st.expander("Geçmiş dönem başarısını incele"):
                st.markdown(forecast_report(result))
            if not st.checkbox("Zayıf modelin tahminini yine de incele", key="forecast_weak"):
                return
        future, history = result["forecast"], result["history"]
        first = future.iloc[0]
        st.info(f"Bir sonraki dönem için yaklaşık {first['forecast']:.0f} paylaşım öngörülüyor. "
                   f"Modelin %95 tahmin aralığı {first['lower']:.0f}–{first['upper']:.0f} paylaşım. "
                   "Bu bir satış tahmini veya gerçekleşme garantisi değildir.")
        st.caption(result["context"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=history.index, y=history.values, name="Geçmiş paylaşımlar"))
        fig.add_trace(go.Scatter(x=future["period"], y=future["lower"], mode="lines", line={"width": 0}, showlegend=False))
        fig.add_trace(go.Scatter(x=future["period"], y=future["upper"], fill="tonexty", mode="lines",
                                line={"width": 0}, name="%95 tahmin aralığı"))
        fig.add_trace(go.Scatter(x=future["period"], y=future["forecast"], name="Tahmin"))
        fig.update_layout(yaxis_title="Benzersiz paylaşım sayısı", xaxis_title="Dönem", yaxis_rangemode="tozero")
        st.plotly_chart(fig, config={"displayModeBar": False})
        with st.expander("Tahmin tablosu ve model ayrıntıları"):
            frame = future.rename(columns={"period": "Dönem", "forecast": "Tahmin", "lower": "Alt sınır", "upper": "Üst sınır"})
            st.dataframe(frame, hide_index=True, width="stretch")
            st.markdown(forecast_report(result))
            st.dataframe(result["validation"].rename(columns={"period": "Dönem", "actual": "Gerçekleşen",
                         "prediction": "Model tahmini", "naive": "Basit tahmin"}), hide_index=True)
            for sql in result["sql"]:
                st.code(sql, language="sql")
            st.download_button("Tahmini indir", frame.to_csv(index=False).encode("utf-8-sig"), "tahmin.csv", "text/csv")
