# Pazarlama İçgörüleri

Beş mod, aynı salt okunur veri katmanını kullanır. Ana ekranda iş soruları ve sade
Türkçe sonuçlar gösterilir; SQL, şema, ayrıntılı tablolar ve isteğe bağlı grafikler
açılır bölümlerdedir.

- **Otonom İçgörü:** Konu, duygu ve tüketici yolculuğundan ölçülmüş bulgulara dayanan
  tek paragraflık strateji özeti. Grafik varsayılan olarak kapalıdır.
- **Manuel Soru:** Doğal dilde soru ve sade yanıt. Sorular varsayılan olarak bağımsızdır;
  takip sorusunda “Önceki soruya devam et” seçilir. Ürün/marka varsayılmaz.
- **Hipotez Doğrulama:** Başlık ve iki kitle seçilir. Her kişi bir kez sayılarak
  Fisher kesin oran testi uygulanır. Teknik sonuçlar açılır bölümde bulunur.
- **Tahminleme:** Paylaşım tarihi otomatik seçilir; adet modeli, geçmiş dönem
  sınaması, basit tahmin karşılaştırması ve %95 tahmin aralığı hesaplanır.
- **Veri Analiz (ClickHouse):** Duygu, konu, yolculuk veya marka dağılımları;
  genel, cinsiyet veya yaş kırılımı. İsteğe bağlı doğal dil soruları.

## Mevcut Streamlit sitesini güncelleme

GitHub `dev` dalına push, Docker/ngrok, Cloud Secrets, beş modu deneme ve
hata giderme için [adım adım güncelleme rehberini](docs/STREAMLIT_UPDATE.md) izleyin.
İlk CSV aktarımı ve Docker kurulumu: [yerel ClickHouse rehberi](docs/LOCAL_CLICKHOUSE.md).

## Veri anlamı

Bu CSV'lerde kullanıcı verisi `users`, sınıflandırmalar `tweet_predictions`
tablosundadır. Kategori alanı liste kodlamalı bir metindir ve `task_name` ile
hangi analiz türüne ait olduğu anlaşılır. Yeni ortak katman:

- Metin/JSON/ClickHouse dizi etiketlerini ayrı değerlere açar; konu anahtar kelimelerini
  başlıktan ayırır. Sektör metadata'sını duygu/konu diye saymaz.
- Konuların aylık, çeyreklik, yarıyıllık ve yıllık kopyalarından tek aile seçer;
  mevcutsa aylık aileyi kullanır.
- Her paylaşımı benzersiz sayar. Kullanıcıları JOIN öncesi tekilleştirir;
  aynı kullanıcı için çelişkili demografiyi bilinmiyor kabul eder.
- Gelecek tarihli ve çelişkili tarihli paylaşımları kapsamdan çıkarır.
- Kaynak tabloları değiştirmez. İş görünümleri her SELECT içinde CTE olarak hazırlanır;
  yeni tablo oluşturma veya yönetici izni gerekmez.

Paylaşım bazındaki etiket oranının paydası, aynı analiz türünde ve kitlede en az bir
etiketi olan benzersiz paylaşımlardır. Bir paylaşımın birden fazla etiketi olabilir;
oranlar toplamı %100'ü aşabilir. Hipotez testinde payda aynı kapsamda etiketli
paylaşımı olan benzersiz **kişiler**, sonuç ise seçilen etiketi en az bir
paylaşımında taşıyan kişidir. Kurumlar ve bilinmeyen/çelişkili seçili demografi dışlanır.

Bu dosyalarda satış veya etkileşim ölçümü ve ürün alanı bulunmuyor.
Purchase, gerçekleşmiş satış adedi değil, paylaşımın sınıflandırma etiketidir.
Örnek marka/sektör adlarından gerçek ürün veya sektör çıkarılmaz. Eski sürümdeki
gibi hacimden satış, huni kaybı veya nedensellik iddiası üretilmez.

## Yerel kurulum ve test

CPython **3.12, 64 bit** kullanın. `requirements.txt` doğrudan ve geçişli
bağımlılıkları sabitler; mevcut sanal ortam varsa yeniden oluşturmayın.

```powershell
cd C:\Users\Seker1\Desktop\Hypothesis_Generation
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Yerel SQLite demosu için:

```powershell
.\.venv\Scripts\python.exe scripts\create_demo.py
```

Mevcut `.streamlit/secrets.toml` dosyasının üzerine yazmayın. Dosya yoksa
`.streamlit/secrets.toml.example` dosyasını kopyalayıp ayarları düzenleyin.
SQLite demosu: `DATABASE_BACKEND = "sqlite"`,
`SQLITE_DB_PATH = "data/demo_analytics.db"`. Bu demo tüketici yolculuğu etiketi
içermediğinden sadece mevcut analiz türleri sunulur.

ClickHouse için `DATABASE_BACKEND = "clickhouse"` seçin; mevcut bağlantı
ayarlarınızı ve `OPENAI_API_KEY` değerini koruyun. CSV veri setinde
`CLICKHOUSE_TABLES = "users,tweet_predictions"` kullanın. Cloud'da yerel
SQLite dosyanız bulunmaz; `localhost` ise Cloud sunucusunu ifade eder.

```powershell
.\.venv\Scripts\python.exe scripts\check_connection.py
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Tarayıcı: http://localhost:8501. Durdurma: Ctrl+C. Ayarları değiştirdikten sonra
yerel uygulamayı yeniden başlatın. Streamlit Secrets ortam değişkenlerinden önceliklidir.
Testler gerçek API/ClickHouse gerektirmez. Streamlit testindeki
`missing ScriptRunContext` uyarısı beklenir; sonda `OK` yazmalı.

Yerel Docker verisinin iş anlamı ve orijinal CSV ile bağımsız sayım karşılaştırması:

```powershell
.\.venv\Scripts\python.exe scripts\check_marketing_data.py --local --compare-csv-dir C:\Users\Seker1\Downloads
```

`--local` olmadan bu betik uygulamanın Secrets ayarındaki ClickHouse'a bağlanır.
Sadece okur; kayıt örneği veya parola yazdırmaz. CSV yolu isteğe bağlıdır.

## Model ve veri kapsamı

Hazır dağılımlar, hesaplanmış strateji özeti, sık kullanılan açık sorular,
hipotez testi ve tahmin API anahtarı olmadan çalışır. Özel doğal dil sorguları ve
model tarafından yazılan strateji için `OPENAI_API_KEY` gerekir.
Otonom özette model hatası olursa hesaplanmış özet gösterilir.

Hipotez kararı Python'da Fisher testiyle hesaplanır. p-değeri hipotezin doğru olma
yüzdesi değildir; H0'ın reddedilememesi eşitlik kanıtı değildir. Nedensellik
test edilmez. Bağımsız kişileri temsil etmeyen örneklerde bu test uygun değildir.
Çoklu karşılaştırma düzeltmesi otomatik uygulanmaz. Welch ve genel istatistik
yardımcıları kodda korunur; sade ekranda bu CSV'ye uygun kişi bazlı oran testi sunulur.

Tahmin için en az 16 tam dönem gerekir. İlk/son kısmi ve halen açık dönemler dışlanır.
Eksik dönemler varsayılan olarak tahmini durdurur; yalnızca kesintisiz toplama
onayıyla sıfır doldurulur. Adetler log(1+adet) ölçeğinde yerel doğrusal trend
modeliyle hesaplanır; geri dönüştürülmüş merkezi tahmin ve aralıklar negatif olamaz.
Son dönemler eğitime alınmadan sınanır; final model tüm geçmişle eğitilir.
L-BFGS yakınsamazsa en fazla bir Powell denemesi yapılır, başarısız model sunulmaz.
Mevsimsellik veya dış etken yoktur. Model basit son-değer tahminini geçemezse uyarı
gösterilir; zayıf modelin sayı/grafiği varsayılan olarak kapalı tutulur ve yalnızca
kullanıcı isterse açılır. Tahmin aralığı garanti değildir. Sıfır doldurulmuş kesintili bu örnek
veriden güçlü ticari tahmin beklentisi çıkarılmamalıdır.

## Sorgu güvenliği ve gizlilik

Bütün sorgular ortak şema/plan doğrulamasından geçer. Bilinmeyen tablo/sütun,
ham JOIN koşulu, geçersiz filtre ve uygunsuz limit reddedilir. Etiket sorgularında
her etiket tablosuna ayrı analiz türü filtresi ve benzersiz sayım zorunludur.
OpenAI'ye ham SQL çalıştırma yetkisi verilmez. Sonuçlar en fazla 1000 satır,
ClickHouse sorguları en fazla 30 saniyedir. Kaynak hesap yalnız SELECT yetkilidir.

Model kullanılan akışlarda soru, şema ve etiket envanteri OpenAI'ye iletilir;
özet için toplulaştırılmış bulgular, özel sorguların özetinde dönen sonuçlar
gönderilebilir. Uygulama logları soru, SQL, filtre değeri, kayıt örneği ve ham hata
kaydetmez; yalnız sorgu kimliği, süre, durum ve güvenli metadata kaydeder.
Bu maskeleme ClickHouse veya ngrok sunucu loglarını ayrıca yönetmez.
`.streamlit/secrets.toml`, `.local-clickhouse/`, yerel veriler ve loglar Git'e eklenmez.

Eski uygulama loglarını maskelemek için uygulamayı durdurup
`.\.venv\Scripts\python.exe scripts\mask_logs.py` çalıştırabilirsiniz.
Bu işlem mevcut log içeriğini geri alınamayacak şekilde maskeler.

## Kaynaklar

- [Streamlit uygulama güncelleme](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/edit-your-app)
- [Streamlit Secrets ayarları](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings)
- [Fisher kesin testi](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.fisher_exact.html)
- [Durum uzayı zaman serisi modeli](https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.structural.UnobservedComponents.html)
