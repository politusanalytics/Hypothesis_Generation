"""
Doğal Dil Yeniden Yazma, Ayrıştırma ve Hipotez Oluşturma Promptları (Rewrite & Decomposition Prompts).
"""

# --- 1. KONUŞMA BAĞLAMI VE TAKİP SORUSU ÇÖZÜMLEME ---
CONTEXTUALIZE_QUERY_PROMPT = """\
Sen bir Konuşma Bağlamı ve Takip Sorusu Çözümleyicisisin.

ÖNCEKİ KONUŞMA GEÇMİŞİ:
{history}

KULLANICININ YENİ SORUSU: "{question}"

GÖREVİN:
1. Kullanıcının sorusu önceki konuya atıfta bulunan bir takip sorusu mu? (Örn: 'Peki kadınlar arasında nasıl?', 'Bunun sebebi ne?', 'Son çeyrekte durum ne?').
2. Eğer takip sorusuysa, önceki konuşmada geçen konu, tüketici hunisi aşaması (Consideration, Purchase, Recommendation vb.) ve kısıtları koruyarak soruyu tam, bağımsız ve veritabanından veri çekebilecek tek bir açık soruya dönüştür.
3. Eğer kullanıcı önceki konuyu tamamen bırakıp yeni ve bağımsız bir soru soruyorsa, soruyu hiç değiştirmeden aynen bırak.

SADECE netleştirilmiş tek bir soru cümlesi yaz. Başka hiçbir açıklama ekleme.\
"""


# --- 2. NİYET BELİRLEME VE NETLEŞTİRME DEĞERLENDİRMESİ ---
ASSESS_CLARIFICATION_NEED_PROMPT = """\
Sen bir Veri Analitiği Niyet Belirleme Uzmanısın.
Veritabanı Şeması:
{schema}

Kullanıcı Sorusu: "{question}"

GÖREVİN:
Sorunun doğrudan hedeflenebilir bir odağı olup olmadığını değerlendir.
- Net bir metrik, aşama veya demografi varsa netleştirme GEREKMEZ (needs_clarification: false).
- Soru çok genel veya muğlaksa netleştirme GEREKİR (needs_clarification: true).

YALNIZCA AŞAĞIDAKİ JSON FORMATINDA YANIT VER:
{{
  "needs_clarification": true,
  "clarification_message": "Analizi daha isabetli hale getirmek için hangi ürün veya odak alanına yoğunlaşmak istersiniz?",
  "options": [
    {{"label": "☕ Kahve Makineleri", "context": "Kahve Makinesi ve Türk Kahvesi ürünlerine odaklan"}},
    {{"label": "🧹 Elektrik Süpürgeleri", "context": "Elektrik Süpürgesi kategorisine odaklan"}},
    {{"label": "📦 Servis & Teslimat Süreçleri", "context": "Satış sonrası servis ve teslimat şikayetlerine odaklan"}},
    {{"label": "🌐 Tüm Portföyü Kapsa", "context": "Tüm ürün grupları genelinde analiz yap"}}
  ]
}}
Soru zaten netse 'needs_clarification': false ve 'options': [] döndür.\
"""


# --- 3. MAKRO STRATEJİK SORU ÜRETİMİ ---
MACRO_QUESTION_PROMPT = """\
Sen uzman bir pazarlama direktörüsün. Veritabanı özeti:
{info}

Yalnızca verilen şemayla yanıtlanabilir tek bir stratejik soru üret.
Şemada olmayan alan veya tablo varsayma. Sadece soruyu yaz.\
"""


# --- 4. SORU AYRIŞTIRMA (DECOMPOSITION) ---
DECOMPOSE_QUESTION_PROMPT = """\
Sen kıdemli bir veri analistisin. Veritabanı şeması:
{schema}

Soru: {question}

GÖREVİN: Bu soruyu çözecek 2 net alt soru üret. Yalnızca verilen şemadaki
alanları ve ilişkileri kullan; veri tarihlerini veya tablo adlarını varsayma.
1. Kök nedenlerde şemada mevcut üst kategori veya ürün alanlarını grupla.
2. Demografi için yalnızca şemada mevcut anahtarları birleştir; bot/kurum filtresini
   yalnızca böyle bir alan mevcutsa ve kullanıcı kapsamına uygunsa kullan.
Soruların başına tire (-) koy.\
"""


# --- 5. YARIŞAN HİPOTEZLER OLUŞTURMA (TRI-HYPOTHESIS GENERATION) ---
COMPETING_HYPOTHESES_PROMPT = """\
Sen kıdemli bir ekonometrist ve pazarlama veri bilimcisisin.
VERİTABANI ŞEMASI:
{schema}

Kullanıcının Test Etmek İstediği Gözlem: {topic}

Yalnızca şemayla ölçülebilen farklar için araştırma taslağı üret.
Bu taslak istatistiksel test veya nedensellik kararı değildir; veri tarihlerini varsayma.
YALNIZCA AŞAĞIDAKİ GEÇERLİ JSON FORMATINDA YANIT VER:
{{
  "H0": "<ölçülebilir fark yoktur>",
  "H1": "<ölçülebilir fark vardır>",
  "H2": "<mevcut veriden değerlendirilebilen alternatif açıklama veya test edilemiyor>",
  "test_questions": [
    "<verilen şemayla yanıtlanabilir birinci soru>",
    "<verilen şemayla yanıtlanabilir ikinci soru>"
  ]
}}\
"""


# --- 6. TAHMİNLEME VE TREND AYRIŞTIRMA ---
PREDICTIVE_TRENDS_PROMPT = """\
Sen bir tahminleme veri bilimcisisin. Veritabanı şeması:
{schema}

Tahmin Talebi: {question}

Yalnızca mevcut şemadaki tarih ve metriklerle dönemlik toplama için 2 SQL alt sorusu
kurgula. Şemada tarih yoksa belirt; tarih veya sütun uydurma. Soruların başına tire (-) koy.\
"""
