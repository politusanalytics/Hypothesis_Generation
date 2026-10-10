# CSV verisiyle yerel ClickHouse ve Streamlit Cloud bağlantısı

Bu akış iki CSV'den `brand_analytics.users` ve
`brand_analytics.tweet_predictions` tablolarını oluşturur. `tweets` veya
`user_factors` verisi uydurulmaz. Uygulamanın `CLICKHOUSE_TABLES` ayarı sadece
bu iki tabloyu içerir. Docker kurulumu, Windows yönetici onayı/yeniden başlatması
ve ngrok hesabına giriş kullanıcı tarafından tamamlanmalıdır.

## 1. Windows çalışma ortamı

Bilgisayarda Docker Desktop ve WSL yoksa **yönetici olarak** PowerShell açın:

```powershell
wsl --install --no-distribution
```

Windows isterse bilgisayarı yeniden başlatın. Ardından
[Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
kurun, WSL 2 altyapısını ve Linux containers seçeneğini kullanın. Docker Desktop'ı
açın; motor çalışır duruma gelmeli. [WSL kurulum rehberi](https://learn.microsoft.com/en-us/windows/wsl/install).

## 2. Proje ve hazırlanan veri

Normal PowerShell'de:

```powershell
cd C:\Users\Seker1\Desktop\Hypothesis_Generation
docker version
.\.venv\Scripts\python.exe scripts\local_clickhouse.py prepare
```

Son komut Downloads klasöründeki iki CSV'yi okur. Başka konum için `--users`
ve `--predictions` parametrelerine tam dosya yollarını verin.
Kaynak CSV'ler değiştirilmez. Hazırlama sırasında sütun sayısı, tarih, boolean ve
sayısal türler tüm satırlarda doğrulanır. Kaynak/hash, NULL sayıları ve tekrarlar
`.local-clickhouse/manifest.json` içinde tutulur. CSV içindeki boş değer,
`\N` ve `NULL`, nullable sütunlarda gerçek NULL olur. Kimlikler String olarak
saklanır; büyük sayılar yuvarlanmaz. Kategori alanlarının metin/dizi kodlaması
aynen korunur. Kaynakta saat dilimi yoksa UTC varsayılır; bu varsayım manifestte
belirtilir. `tweet_date` ve `prediction_month` kodları dönüştürülmeden saklanır;
zaman serileri için gerçek `tweet_created_at` tarihini kullanın.

Kaynakta tekrar eden kullanıcı id'leri varsa hepsi korunur ve sayıları raporlanır.
`users` tablosunda bir id'nin birden fazla satırı bulunabileceğinden demografi
JOIN'i satır çoğaltabilir. Kullanıcı sayısı için `count_distinct(id)` kullanın.
Tahmin tablosunda bir tweet farklı task/scope kayıtları içerebilir; tweet hacmi
için `count_distinct(tweet_id)` ve uygun task filtresini kullanın. Demografik
ortalama/istatistiksel testlerde tekilleştirme kuralı belirlenmeden JOIN sonuçlarını
bağımsız gözlem gibi kullanmayın. Tekrarlar otomatik silinmez.

## 3. ClickHouse'u başlatın

```powershell
docker compose --env-file .local-clickhouse/docker.env -f compose.clickhouse.yaml up -d
docker compose --env-file .local-clickhouse/docker.env -f compose.clickhouse.yaml ps
```

İlk çalıştırma Docker imajını indirir. HTTP arayüzü sadece bilgisayarınızdaki
`127.0.0.1:8123` adresine bağlanır. Veriler kalıcı Docker volume içinde tutulur.
Compose dosyası 25.8 sürüm dalını kullanır; o dalın güncel yama imajı indirilir.
İmajın sürüm/digest bilgisini `docker image inspect` ile sabitleyebilirsiniz.

## 4. Veriyi yükleyin ve uygulama hesabıyla doğrulayın

```powershell
.\.venv\Scripts\python.exe scripts\local_clickhouse.py load
.\.venv\Scripts\python.exe scripts\local_clickhouse.py check
```

Sunucu henüz hazır değilse kısa süre sonra tekrar deneyin. Aktarım geçici tabloları
doldurup satır sayılarını doğrular; ardından gerçek tablo adlarını yayınlar.
`load` mevcut hedef tablo varsa durur; ikinci kez veri eklemez, eski veriyi silmez.
`check`, Streamlit'in kullanacağı yalnızca SELECT izni verilen hesapla hem şemayı
hem kayıt sayılarını kontrol eder. Bu komut başarılı olmadan Cloud'a geçmeyin.

Yerel Streamlit testi için `.local-clickhouse/streamlit-local.toml` içindeki
veritabanı ayarlarını `.streamlit/secrets.toml` dosyasına aktarın. Mevcut
`OPENAI_API_KEY` ve ilgisiz ayarları koruyun. Sonra:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## 5. ngrok ile HTTPS tüneli

[Windows ngrok kurulum sayfasından](https://ngrok.com/download/windows) kurun.
Hesabınızın dashboard'undaki authtoken komutunu **kendi terminalinizde** çalıştırın:

```powershell
ngrok config add-authtoken "KENDI_NGROK_AUTHTOKENINIZ"
ngrok http 8123 --inspect=false
```

`Forwarding` satırındaki `https://...` adresini alın. Tünel terminali açık kalmalı.
`--inspect=false` HTTP isteklerinin ngrok yerel denetleyicisinde tutulmasını kapatır.
ClickHouse bağlantısı kullanıcı/parola ile korunur. Cloud için SELECT hesabını
kullanın; aktarım hesabı parolasını Cloud'a koymayın.

ngrok bu projede `.local-clickhouse/tools/ngrok/ngrok.exe` konumuna indirilmişse,
token'ı komut geçmişine veya sohbete yazmadan kendi terminalinizde tanımlayabilirsiniz:

```powershell
.\.venv\Scripts\python.exe scripts\configure_ngrok.py
```

Token gizli giriş alanında istenir; `.local-clickhouse/ngrok.yml` dosyasında saklanır.
Bu yapılandırmayla tüneli başlatmak için:

```powershell
.\.local-clickhouse\tools\ngrok\ngrok.exe http 8123 --inspect=false --config .local-clickhouse/ngrok.yml
```

## 6. Cloud Secrets dosyasını oluşturun

Başka bir PowerShell terminalinde, adresi kendi tünel adresinizle değiştirin:

```powershell
.\.venv\Scripts\python.exe scripts\local_clickhouse.py cloud-config --url "https://SIZIN-TUNEL-ADRESINIZ.ngrok-free.app"
```

`.local-clickhouse/streamlit-cloud.toml` dosyasını açın. Streamlit Cloud'da
Manage app → Settings → Secrets bölümündeki veritabanı ayarlarını bu dosyadaki
değerlerle değiştirin. `OPENAI_API_KEY` ve ilgisiz ayarları koruyun. Cloud'daki host,
`https://` içermeyen ngrok alan adıdır; port 443, secure true ve verify true olmalıdır.
Dosyadaki `CLICKHOUSE_TABLES = "users,tweet_predictions"` ayarı önemlidir.

Kaydedin, uygulamayı yeniden başlatın ve Veri Analiz Modu'nda şu soruları deneyin:

- Tahmin kayıtlarının task_name alanına göre dağılımı nedir?
- Kaç benzersiz kullanıcı id'si var?
- Aylara göre benzersiz tweet sayısı nedir?

## Çalışma koşulları ve dosyalar

Bilgisayar, Docker ve ngrok açık kaldığı sürece Cloud yerel ClickHouse'a erişir.
Uyku/kapanma/tünel kesintisi bağlantıyı durdurur. Tünel adresi değişirse Cloud Secrets
ayarını güncelleyin. Kalıcı yayın için erişilebilir bir sunucu gerekir.

`.local-clickhouse/` Git tarafından yok sayılır: dönüştürülmüş veri, parolalar,
Docker env ve Cloud secrets **GitHub'a gönderilmez**. Compose dosyası, aktarım
betiği ve bu rehber Git'e eklenebilir. `.local-clickhouse/settings.json` içindeki
parolalar her hazırlamada değiştirilmez; yeniden hazırlama mevcut sunucu hesabını
bozmaz. Klasörü silmek, mevcut Docker volume hesabının parolasını otomatik değiştirmez.

ClickHouse loglarında sorgu metadata'sı bulunabilir; Docker/ngrok loglarını herkese
açık paylaşmayın. Uygulamanın mevcut log maskelemesi ClickHouse sunucu loglarını
otomatik maskelemez.

Kaynaklar: [ClickHouse Docker imajı](https://hub.docker.com/r/clickhouse/clickhouse-server/),
[Python sürücüsü](https://clickhouse.com/integrations/python),
[ngrok CLI](https://ngrok.com/docs/gateway/agent/cli),
[Streamlit Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).
