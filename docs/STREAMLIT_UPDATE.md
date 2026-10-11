# Beş modlu sürümü yerelde deneme ve Streamlit'e yayınlama

Bu rehber mevcut `dev` dalındaki sadeleştirilmiş uygulama içindir. ClickHouse
tablolarını yeniden oluşturmanız veya CSV'leri yeniden yüklemeniz gerekmiyor.
Kod sorgu sırasında iş görünümleri hazırlar; mevcut SELECT hesabı yeterlidir.

## 1. Docker ve yerel veriyi kontrol edin

Docker Desktop'ı açın, motorun hazır olmasını bekleyin. PowerShell'de:

```powershell
cd C:\Users\Seker1\Desktop\Hypothesis_Generation
docker compose --env-file .local-clickhouse/docker.env -f compose.clickhouse.yaml up -d
.\.venv\Scripts\python.exe scripts\local_clickhouse.py check
.\.venv\Scripts\python.exe scripts\check_marketing_data.py --local
```

`docker` komutu bulunmuyorsa bu bilgisayardaki tam yolu kullanın:

```powershell
& "C:\Users\Seker1\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe" compose --env-file .local-clickhouse/docker.env -f compose.clickhouse.yaml up -d
```

İlk kontrolde `users: 5544`, `tweet_predictions: 50208` beklenir. İş analizi
kontrolünde 11 Ekim 2026 itibarıyla 3015 geçmiş tarihli benzersiz paylaşım,
2215 paylaşım yapan kişi, 16 duygu, 4 yolculuk, 10 konu, 3 konu başlığı ve 4 marka
etiketi doğrulandı. Tarih ilerledikçe kapsam değişebilir. Ham 50.208 kayıt,
50.208 ayrı paylaşım demek değildir; gelecekteki paylaşımlar da gösterilmez.

CSV'ler hâlâ Downloads klasöründeyse bağımsız karşılaştırma isteğe bağlıdır:

```powershell
.\.venv\Scripts\python.exe scripts\check_marketing_data.py --local --compare-csv-dir C:\Users\Seker1\Downloads
```

Bu veri setinde 222 etiket/kitle sayımı ve oran paydası CSV referansıyla eşleşir.

## 2. Yerel uygulamayı deneyin

Mevcut `.streamlit/secrets.toml` içinde yerel ClickHouse ayarları bulunmalı.
Yerel bağlantı için `.local-clickhouse/streamlit-local.toml` dosyasındaki
veritabanı alanlarını kullanın; mevcut `OPENAI_API_KEY` ve diğer ayarları koruyun.

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Testlerin sonunda `OK` görmelisiniz. Uygulama http://localhost:8501 adresinde
açılır. Bu çalışma sırasında 8502'de bir önizleme başlatılmış olabilir;
kendi başlattığınız terminalde yazan URL'yi kullanın. Durdurmak için Ctrl+C.

## 3. Değişiklikleri GitHub'a gönderin

Ayrı PowerShell açın:

```powershell
cd C:\Users\Seker1\Desktop\Hypothesis_Generation
git branch --show-current
git status --short
```

Bu çalışma `dev` dalında yapıldı; ilk komutta `dev` görmelisiniz. Ardından:

```powershell
git add app.py agent.py analytical_ui.py business_analysis.py marketing_data.py data_analysis.py database.py forecasting.py agents tests scripts/check_marketing_data.py README.md docs .streamlit/secrets.toml.example
git diff --cached --stat
git commit -m "Simplify five modes and correct ClickHouse analysis semantics"
git push origin dev
```

Listeye `.streamlit/secrets.toml`, `.local-clickhouse/`, CSV veya parola
eklemeyin. Bunlar zaten `.gitignore` kapsamındadır. `git diff --cached --stat`
ile yalnız kod, test, örnek ayar ve rehberlerin eklendiğini kontrol edin.

Push `rejected` / `fetch first` derse, **commit tamamlandıktan sonra**:

```powershell
git pull --rebase origin dev
git push origin dev
```

Çakışma bildirirse işaretleri rastgele silmeyin ve `--force` kullanmayın.
`git rebase --abort` sizi rebase öncesindeki yerel commit'e geri döndürür;
çakışmayı çözmeden yeniden push yapmayın. GitHub giriş ekranı açılırsa kendi
hesabınızla giriş yapın. `nothing to commit` değişikliklerin zaten commit
edildiği anlamına gelebilir; `git log -1 --oneline` ve push sonucunu kontrol edin.

## 4. Streamlit'in doğru dalı izlediğinden emin olun

[share.streamlit.io](https://share.streamlit.io) hesabınızdan beş modlu uygulamayı
açın. Repo `politusanalytics/Hypothesis_Generation`, dal `dev`, giriş dosyası
`app.py` olmalıdır. `main` izleyen dört modlu siteye `dev` push'u uygulanmaz.

Yanlış site `main` izliyorsa `dev` izleyen mevcut uygulamayı açın. Böyle bir
uygulama yoksa **Create app / Deploy app** üzerinden aynı repo için `dev` ve
`app.py` seçerek ayrı uygulama yayınlayın; Secrets ayarlarını yeni uygulamaya da
girin. Önce `dev` sürümünü doğrulayın; `main` ile birleştirmek ayrı adımdır.

Doğru dal izleniyorsa Python değişiklikleri push sonrasında otomatik alınır.
Python ortamı yeni oluşturulacaksa bağımlılıkların doğrulandığı **Python 3.12**
sürümünü seçin. Bu değişiklikte yeni paket gerekmez.

## 5. ngrok'u açık tutun

Mevcut çalışan tüneliniz varsa ikinci kez başlatmayın. Yoksa ayrı terminalde:

```powershell
cd C:\Users\Seker1\Desktop\Hypothesis_Generation
.\.local-clickhouse\tools\ngrok\ngrok.exe http 8123 --inspect=false --config .local-clickhouse/ngrok.yml
```

Token daha önce kaydedildi; yeniden girmeniz gerekmez. Terminali açık bırakın.
Forwarding satırındaki **güncel** HTTPS adresini alın. Bilgisayar uyumamalı;
Docker, internet ve ngrok çalışmaya devam etmelidir.

Adres değiştiyse başka terminalde, örnek adresi kendi adresinizle değiştirerek:

```powershell
.\.venv\Scripts\python.exe scripts\local_clickhouse.py cloud-config --url "https://SIZIN-GUNCEL-ADRESINIZ.ngrok-free.dev"
```

Bu komut `.local-clickhouse/streamlit-cloud.toml` dosyasını oluşturur; parola
sohbete veya terminal çıktısına yazılmaz. Bu dosyayı GitHub'a yüklemeyin.

## 6. Cloud Secrets ve yeniden başlatma

Streamlit çalışma alanında uygulamanın yanındaki **⋮ → Settings → Secrets**
bölümünü açın. `.local-clickhouse/streamlit-cloud.toml` içindeki veritabanı
alanlarını buradaki aynı anahtarlarla değiştirin; mevcut `OPENAI_API_KEY` ve
diğer ilgisiz ayarları koruyun. Aynı anahtarı iki kez tanımlamayın.

Beklenen önemli değerler:

```toml
DATABASE_BACKEND = "clickhouse"
CLICKHOUSE_HOST = "SIZIN-GUNCEL-NGROK-ALAN-ADINIZ"
CLICKHOUSE_PORT = "443"
CLICKHOUSE_SECURE = "true"
CLICKHOUSE_VERIFY = "true"
CLICKHOUSE_DB = "brand_analytics"
CLICKHOUSE_TABLES = "users,tweet_predictions"
CLICKHOUSE_USERNAME = "dataset_analyst"
```

`CLICKHOUSE_PASSWORD` üretilen dosyadaki **analiz hesabının** parolası olmalı;
yönetici/aktarım hesabını kullanmayın. HOST içinde `https://` veya yol bulunmaz.
Cloud için `127.0.0.1:8123` değerini kullanmayın.

**Save** deyin. Ardından çalışma alanındaki **⋮ → Reboot → Reboot** veya
uygulamadaki **Manage app → ⋮ → Reboot app** ile yeniden başlatın. Başlangıç
tamamlanınca sayfayı yenileyin; eski sohbet/önbellek taşınmasın.

## 7. Beş modu kısa bir turla doğrulayın

1. **Otonom:** “Strateji özetini hazırla”. Yeşil alanda sade bir strateji paragrafı
   görünmeli; grafik kendiliğinden açılmamalı. Ürün/etkileşim/satış uydurulmamalı.
2. **Manuel:** “Yaş gruplarının baskın duyguları neler?” ardından bağımsız olarak
   “Kadınların paylaşımlarındaki şikayet oranı nedir?”. Kahve makinesi gibi
   kullanıcı tarafından belirtilmeyen ürün filtresi eklenmemeli. 11 Ekim 2026
   kapsamındaki ikinci sonuç 362/563 ≈ %64,3 paylaşım oranıdır; müşteri oranı değildir.
   Takip sorusu için “Önceki soruya devam et”i bilinçli olarak açın.
3. **Hipotez:** “Duygular” → bir duygu → “Cinsiyete göre” → iki kitle. Bağımsızlık
   onayını verip “Karşılaştır”a basın. Yüzdeler ve sade sonuç görünmeli. Test kişi
   bazındadır; manuel moddaki paylaşım oranıyla aynı paydada değildir.
4. **Tahmin:** “Tüm paylaşımlar” → “Aylık” → 6 dönem → “Tahmini hazırla”. Eksik
   dönem varsa açık bir bilgi mesajı beklenir; uygulama çökmemeli. Kesintisiz veri
   toplandığını gerçekten biliyorsanız kapsam seçeneklerindeki sıfır doldurmayı
   onaylayıp tekrar deneyin. Model basit tahmini geçemezse zayıf sonuçların grafiği
   kapalı kalır; kullanıcı isterse “Zayıf modelin tahminini yine de incele” ile açabilir.
5. **Veri Analiz:** “Duygular” → “Yaş grubuna göre” → “Analizi göster”. Türkçe
   başlıklarla duygu sonuçları görünmeli; duygu listesinde `demo_sector` veya konu
   başlıkları olmamalı. Grafik açarsanız tek kitle seçilerek en fazla 10 başlık çizilir.

Otonom model sentezi ve özel doğal dil soruları için geçerli `OPENAI_API_KEY`
gerekir. Anahtar yoksa hazır analizler, hesaplanmış özetler, açık örnek sorular,
istatistik ve tahmin çalışır. Bu çalışma gerçek OpenAI anahtarıyla uçtan uca
model çıktısını doğrulamaz; bağlantı ve sorgular gerçek yerel ClickHouse'ta sınanır.

## Sorun sürerse

- Hâlâ dört mod veya eski ekran varsa uygulama yanlış dalı izliyor ya da push
  gerçekleşmedi. GitHub'da `dev` dalındaki `app.py` ve yeni iki Python dosyasını kontrol edin.
- Bağlantı hatası varsa önce Docker ve ngrok, ardından güncel Cloud host/parola
  ayarlarını kontrol edin. Yerel testin geçmesi Cloud erişiminin geçtiğini kanıtlamaz.
- Sıfır sonuç, gerçek hayatta hiç şikâyet olmadığı anlamına gelmez. Filtre/kitle,
  tarih ve etiket kapsamını inceleyin. Artık veride olmayan ürün alanı uydurulmaz.
- Kaynaklar anonimleştirilmiş örnekler ve gelecekteki kayıtlar içeriyor. Bu nedenle
  eski sürümün satış/huni kaybı gibi kesin iddialarını yeni sürüm üretmez.

Kaynaklar: [Otomatik GitHub güncellemeleri](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/edit-your-app),
[Secrets ayarları](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings),
[Reboot](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/reboot-your-app).
