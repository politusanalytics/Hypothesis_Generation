# 📊 AI-Powered Hybrid Marketing Insight Engine

Bu proje, yapılandırılmış (SQL) ve yapılandırılmamış (RAG/Vektör) verileri aynı anda analiz edebilen, LangChain ve GPT-4o tabanlı gelişmiş bir kurumsal veri analizi platformudur. Pazarlama yöneticileri için otonom içgörüler üretir, veri odaklı yarışan hipotezleri test eder ve geleceğe yönelik projeksiyonlar sunar.

---

## 🚀 Temel Yetenekler

Sistem 4 farklı operasyonel modda ve çok turlu konuşma bağlamında çalışmaktadır:

* **🤖 Otonom İçgörü Modu:** Veritabanını tarayarak en kritik vizyoner pazarlama sorusunu otomatik tespit eder ve yanıtlar.
* **👤 Manuel Soru & Takip Modu:** Kullanıcının sorularını, konuşma geçmişini koruyarak (`RewriteNLAgent`) ve muğlak niyetleri netleştirerek SQL ve RAG araçlarıyla çözer.
* **🧪 Yarışan Hipotezler Modu ($H_0, H_1, H_2$):** Kullanıcı gözlemlerini Ekonometrik karne formatında 3 rakip hipotezle sınar; verideki reel metriklerle KABUL / RED kararını gerekçelendirir.
* **🔮 Tahminleme (Predictive AI) Modu:** Geçmiş zaman serisi trendlerine dayanarak gelecek dönem risk ve fırsat projeksiyonları sunar.
* **📈 Generative UI:** Analiz sonuçlarını otomatik algılayarak Plotly ile dinamik ve interaktif grafiklere dönüştürür.
* **⚡ 2-Kademeli Hibrit Yönlendirme (Tiered Routing):** SQL/JSON sorgu planlama için hızlı `gpt-4o-mini`, stratejik CMO sentezi için derin `gpt-4o` kullanır (Arayüzden ayarlanabilir).

---

## 🛠️ Kullanılan Teknolojiler

* **Python & Streamlit:** Web arayüzü ve dinamik model seçim paneli.
* **LangChain:** Çoklu ajan (Agentic) orkestrasyonu ve SQL/RAG araç entegrasyonu.
* **OpenAI (GPT-4o & GPT-4o-mini):** 2-kademeli sorgu planlama ve stratejik yönetici sentezi.
* **ClickHouse & SQLite:** Çoklu SQL diyalekti desteği (ClickHouse dizi fonksiyonları, `ARRAY JOIN` ve otomatik SQLite yedekleme).
* **Deterministik SQL Derleyicisi:** Güvenli SPJQ JSON $\rightarrow$ SQL derleme katmanı (`agents/sql_compiler.py`).
* **İzole Sistem Promptları:** Modüler ve yönetilebilir prompt mimarisi (`agents/prompts/`).
* **Pinecone (RAG):** Yapılandırılmamış şirket dokümanları için vektör araması.
* **Plotly & Pandas:** Dinamik veri işleme ve görselleştirme.

---

## ⚙️ Kurulum ve Çalıştırma

### 1. Bağımlılıkları Yükleyin
```bash
pip install -r requirements.txt
```

### 2. Ortam Değişkenlerini / Secrets Yapılandırın
`.streamlit/secrets.toml.example` dosyasını `.streamlit/secrets.toml` olarak kopyalayın ve anahtarlarınızı girin:
```toml
OPENAI_API_KEY = "sk-..."
# İsteğe bağlı ClickHouse & Pinecone ayarları:
CLICKHOUSE_HOST = ""
PINECONE_API_KEY = ""
```

### 3. Uygulamayı Başlatın
```bash
streamlit run app.py
```

### 4. Testleri Çalıştırın
```bash
python -m unittest discover -s tests -v
```