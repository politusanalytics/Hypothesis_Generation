# Pazarlama Veri Analizi ve İstatistik Motoru

Streamlit arayüzü, şemaya göre doğal dil sorgulama, istatistiksel hipotez testleri ve
zaman serisi tahmini sunar. ClickHouse ve salt okunur SQLite profilleri desteklenir.

## Modlar

- Otonom İçgörü: Gerçek şemadan araştırma soruları üretir ve sorgu bulgularını özetler.
- Manuel Soru: Konuşma bağlamını koruyarak doğal dil sorularını sorgular.
- Hipotez Doğrulama: Kullanıcının seçtiği iki grup için Welch ortalama farkı veya
  Fisher kesin oran farkı testi hesaplar; p-değeri, etki, güven aralığı ve H0 kararı gösterir.
- Tahminleme: Gün/hafta/ay bazında count/sum/avg toplaması, yerel doğrusal trend
  modeli, geçmiş dönem sınaması, MAE/RMSE, basit tahmin karşılaştırması ve %95 tahmin aralığı.
- Veri Analiz (ClickHouse): Yalnızca ClickHouse sorgularını SQL, tablo ve CSV olarak sunar.

Sorguların tamamı aynı doğrulayıcıdan geçer. Bilinmeyen tablo/sütun, ham JOIN koşulu,
geçersiz filtre, desteklenmeyen alan ve uygunsuz limit reddedilir. ClickHouse şeması
DESCRIBE TABLE ile okunur; örnek kayıtlar sorgu modeline gönderilmez. Eski sınırsız
SQL-agent ve kullanılmayan başlangıç RAG bağlantısı kaldırıldı. Veri kaynakları SQL'dir.
Doğal dil modlarında soru, şema ve (sentez için) sorgu sonuçları OpenAI'ye iletilir;
istatistik/tahmin modlarında veriler yerelde hesaplanır.

## Windows'ta adım adım yerel kurulum

CPython **3.12, 64 bit** kullanın. Projedeki requirements.txt bu sürümle Windows'ta
kurulup test edilmiş doğrudan ve geçişli bağımlılıkları sabitler. requirements.in
bilinçli paket güncellemeleri için doğrudan bağımlılık listesidir.

### 1. PowerShell'de proje klasörüne geçin

```powershell
cd C:\Users\Seker1\Desktop\Hypothesis_Generation
```

### 2. Sanal ortamı oluşturun ve paketleri yükleyin

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Bu çalışma sırasında `.venv` zaten oluşturuldu. Aynı bilgisayarda mevcut ortamı
kullanıyorsanız ilk komutu atlayabilirsiniz. `py -3.12` bulunamıyorsa standart
Python 3.12 kurulumunu tamamlayın veya kurulu Python 3.12 yürütülebilirinin tam yolunu
kullanın. MSYS Python 3.14 bu projenin doğrulanan ortamı değildir.
Aktivasyon şart değildir; komutlarda sanal ortamın Python'u doğrudan kullanılır.

### 3. Sentetik demo verisini oluşturun

```powershell
.\.venv\Scripts\python.exe scripts\create_demo.py
```

`data/demo_analytics.db` oluşur. Bu çalışma sırasında dosya zaten oluşturuldu.
Dosya varsa script üzerine yazmaz; mevcut dosyayı kullanın veya
`--output data/demo_2.db` ile yeni bir dosya üretin. Mevcut
`insight_generation_bot.db` değiştirilmez. Demo verileri sentetiktir.

### 4. Yerel ayar dosyasını hazırlayın

Mevcut `.streamlit/secrets.toml` dosyanız varsa üzerine kopyalamayın; ilgili alanları
o dosyada düzenleyin. Dosya yoksa:

```powershell
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Demo profili için:

```toml
DATABASE_BACKEND = "sqlite"
SQLITE_DB_PATH = "data/demo_analytics.db"
OPENAI_API_KEY = ""
CLICKHOUSE_HOST = ""
```

Hipotez ve tahmin modları API anahtarı olmadan çalışır. Otonom, manuel ve ClickHouse
veri analiz modları için `OPENAI_API_KEY` değerini doldurun. secrets.toml Git tarafından
yok sayılır. Ayarlar ortam değişkenleriyle de verilebilir; secrets.toml önceliklidir.

### 5. Bağlantıyı ve bütün testleri çalıştırın

```powershell
.\.venv\Scripts\python.exe scripts\check_connection.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Testler API anahtarı ve gerçek ClickHouse bağlantısı gerektirmez. SQL güvenliği,
şema doğrulaması, ClickHouse hata durumları, log gizliliği, istatistiksel sonuçlar,
zaman serisi ve Streamlit arayüz akışları denetlenir. Testlerde kişinin gerçek
bağlantı ayarları kullanılmaz. `ScriptRunContext` uyarıları Streamlit test ortamında
beklenir; başarı ölçütü testlerin sonunda `OK` yazmasıdır.

### 6. Uygulamayı başlatın

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Tarayıcıda http://localhost:8501 adresini açın. Durdurmak için terminalde Ctrl+C.
Ayarları değiştirdiğinizde uygulamayı durdurup yeniden başlatın; bağlantılar önbelleğe alınır.

### 7. Demo hipotez testini deneyin

1. Sol menüden **Hipotez Doğrulama Modu** seçin.
2. Tablo: `tweets`; grup sütunu: `issue`.
3. A grubu: `delivery`; B grubu: `service`.
4. Test: **Ortalama farkı — Welch**; metrik: `engagement`; α: `0.05`.
5. Demo verisinde her kaydın ayrı kullanıcıya ait olduğunu bilerek bağımsızlık kutusunu işaretleyin.
6. **Hipotezi Test Et** düğmesine basın. p-değeri, ortalama farkı, güven aralığı ve SQL gösterilir.
7. Oran testi için **Oran farkı — Fisher**, metrik `sentiment`, başarı değeri `positive` seçin.

Bu testler iki seçili grup arasındaki ölçülebilir farkı sınar. Alternatif nedensel
H2 açıklamalarını veri olmadan doğrulamaz. p-değeri hipotezin doğru olma yüzdesi değildir;
H0'ın reddedilememesi eşitlik kanıtı değildir. Tekrarlanan kişi/olay gözlemleri veya
zamansal olarak bağımlı kayıtlar için bu bağımsız iki grup testleri uygun olmayabilir.
Birden çok test yürütüldüğünde çoklu karşılaştırma düzeltmesi bu sürümde otomatik yapılmaz.

### 8. Demo tahminini deneyin

1. **Tahminleme (Predictive) Modu** seçin.
2. Tablo `tweets`, tarih sütunu `created_at`, dönem `month`, metrik `count`.
3. Başlangıç `2024-01-01`, bitiş (hariç) `2026-07-01`; ufuk `6` dönem.
4. **Tahmin Üret** düğmesine basın.
5. MAE/RMSE, son-değer tahminiyle karşılaştırma, grafik ve %95 tahmin aralığını inceleyin.

En az 16 tam dönem gerekir. Başlangıç/bitişteki ve halen açık olan dönemler dışlanır.
Eksik dönemler varsayılan olarak hata verir. Yalnızca count/sum ve tam veri kapsamı
onayıyla sıfır doldurulabilir; ortalamada doldurulmaz. Son dönemler eğitim dışında
sınanır; final model tüm geçmişle yeniden eğitilir. Modelin mevsimsellik/dış etken
bileşeni yoktur. Tahmin aralıkları model varsayımlarına dayanır; negatif adet tahmini
veya basit modeli geçemeyen hata, modelin uygun olmadığını gösterebilir.

## Gerçek ClickHouse ile çalıştırma

secrets.toml içinde bağlantı ayarlarını doldurun:

```toml
DATABASE_BACKEND = "clickhouse"
OPENAI_API_KEY = "anahtarınız"
CLICKHOUSE_HOST = "sunucu-adresi"
CLICKHOUSE_PORT = "8123"
CLICKHOUSE_USERNAME = "okuma_kullanicisi"
CLICKHOUSE_PASSWORD = "parolanız"
CLICKHOUSE_DB = "veritabani"
CLICKHOUSE_SECURE = "false"
CLICKHOUSE_TABLES = "tweet_predictions,tweets,users,user_factors"
```

TLS için `CLICKHOUSE_SECURE = "true"` ve sunucunuzun TLS HTTP portunu (çoğunlukla
8443) kullanın. Port 443 kullanıldığında HTTPS otomatik etkinleştirilir.
`CLICKHOUSE_VERIFY` varsayılan olarak `"true"` değerindedir; mevcut bağlantı
ayarlarında açıkça verilen değer ortak bağlantı koduna iletilir.
HOST alanına `https://` eklemeyin. İzin listesinde yalnızca erişilebilir
tabloları/view'ları belirtin; varsayılan dört tablonun tamamının bulunması gerekir.

```powershell
.\.venv\Scripts\python.exe scripts\check_connection.py --clickhouse
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

**Veri Analiz Modu (ClickHouse)** seçip “tweets tablosunda kaç kayıt var?” gibi
bir sorgu deneyin. Mod, `DATABASE_BACKEND=sqlite` olsa bile ClickHouse ister;
bağlantı hatasında SQLite'a geçmez. Diğer modlar da ClickHouse profili seçildiğinde
bağlantı hatasında durur. Hipotez için grup ve metrik aynı tabloda bulunmalıdır;
gerekirse sunucuda bağımsız gözlem düzeyinde bir analiz view'ı hazırlayıp izin listesine ekleyin.

ClickHouse kullanıcısına sunucuda yalnızca SELECT/şema okuma yetkisi verin ve profil
üzerinden süre/bellek limitlerini tanımlayın. Uygulama sorguya `readonly=1`,
`max_execution_time=30`, 1000 sonuç satırı ve 10 MB sonuç sınırı gönderir; sürücü
sunucuda değiştirilemeyen ayarları atlayabilir. Canlı bağlantının doğrulanması için
`check_connection.py --clickhouse` çıktısı gerekir; çevrimdışı testler bu doğrulamayı yapmaz.

## Log gizliliği

Yeni loglar yalnızca olay, rastgele sorgu kimliği, süre, durum ve sonuç satır sayısını
tutar. Kullanıcı sorusu, SQL, JSON filtreleri, kayıt örnekleri ve hata mesajı/traceback
kaydedilmez. Ek hassas alanlar maskelenir; e-posta, telefon, anahtar ve URI parolası
kalıpları mesajlarda filtrelenir. Aynı filtre yerel dosya, konsol ve Graylog'a uygulanır.
Önceden oluşmuş uygulama loglarını yerinde maskelemek için uygulamayı durdurup:

```powershell
.\.venv\Scripts\python.exe scripts\mask_logs.py
```

Bu işlem `logs/app.log*` dosyalarında eski mesaj ve hassas alanları geri alınamayacak
şekilde maskeler. Eski Graylog kayıtları sunucuda ayrıca yönetilmelidir.

## Streamlit Cloud'da import sırasında IndentationError

`app.py` içindeki `from agent import ...` satırında gösterilen hata, `agent.py`
dosyasındaki çözümlenmemiş Git birleştirme işaretlerinden kaynaklanabilir.
Çakışma işaretlerini silmekle birlikte iki kod sürümünden tutarlı bir akış seçilmelidir;
yalnızca işaretleri silip iki bağlantı akışını birlikte bırakmayın.
Uygulama ortak `database.connect_clickhouse` bağlantısını kullanır.

GitHub'a yüklemeden önce:

```powershell
.\.venv\Scripts\python.exe -m py_compile agent.py database.py app.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`test_repository_integrity.py` tüm Python kaynaklarının sözdizimini ve örnek
secrets dosyasının TOML biçimini denetler. Düzeltmeyi Streamlit'in izlediği GitHub
dalına gönderin; gerekirse uygulamayı [Reboot](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/reboot-your-app)
ile yeniden başlatın. Cloud'daki mevcut kullanıcı adı, parola ve veritabanı ayarlarını
koruyun; örnek secrets dosyasındaki boş değerlerle değiştirmeyin.

## Cloud'da veritabanı başlatma hatası

Cloud Secrets içinde ClickHouse için `DATABASE_BACKEND = "clickhouse"` seçin.
Örnek secrets yerel SQLite demosunu seçer; `data/demo_analytics.db` Git'e dahil
edilmediğinden bu dosya Cloud'da kendiliğinden bulunmaz. Mevcut bağlantı parolanızı
ve anahtarınızı koruyun. `CLICKHOUSE_DB` gerçek veritabanınız; `CLICKHOUSE_TABLES`
bu veritabanında bulunan ve kullanıcıya okuma izni verilen tablo adları olmalıdır.
Varsayılan dört tablodan biri bile bulunamazsa şema yüklenmesi durur.

Başlangıç mesajları bağlantı ile şema okuma hatalarını ayırır. ClickHouse kod 60
tablonun, 81 veritabanının bulunamadığını; 516 kimlik doğrulamasının başarısız
olduğunu belirtir. Ham sürücü hataları, URL, parola, SQL veya veri örneği gösterilmez.
Diğer bağlantı hatalarında host/HTTP(S) port/TLS ve ağ erişimini kontrol edin;
Cloud'daki `localhost` kendi bilgisayarınıza bağlanmaz.

OpenAI çağrısı yapmadan bağlantıyı ve tüm yapılandırılmış tabloları kontrol etmek için:

```powershell
.\.venv\Scripts\python.exe scripts\check_connection.py --clickhouse
```

Yerelde çalışan bağlantı Cloud ağından erişimin de çalıştığını kanıtlamaz.
GitHub'a düzeltmeyi gönderdikten sonra Cloud Secrets ayarlarını kaydedin ve uygulamayı
yeniden başlatın; ekranda görünen güvenli teşhis mesajına göre ayarları düzeltin.

## Kullanılan hesaplama yöntemleri

- [SciPy Welch testi](https://docs.scipy.org/doc/scipy-1.16.2/reference/generated/scipy.stats.ttest_ind_from_stats.html)
- [SciPy Fisher kesin testi](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.fisher_exact.html)
- [Newcombe oran farkı güven aralığı](https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.confint_proportions_2indep.html)
- [Durum uzayı zaman serisi modeli](https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.structural.UnobservedComponents.html)
