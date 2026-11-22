# career-crew

İlana göre CV uyarlayan, ama CV'de olmayan hiçbir şeyi eklemeyen bir iş başvurusu asistanı.

[![tests](https://github.com/burakaydins/career-crew/actions/workflows/tests.yml/badge.svg)](https://github.com/burakaydins/career-crew/actions/workflows/tests.yml) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![Lisans](https://img.shields.io/badge/lisans-MIT-green)

![career-crew demo: ilk turda eklenen uydurmalar kod kontrolünde yakalanıyor, ikinci turda CV düzeltiliyor](docs/demo.gif)

Kendi iş başvurularım için yazdım. İlanı ve CV'yi veriyorsunuz, altı ajan sırayla çalışıp ilana göre düzenlenmiş bir CV, ön yazı, mülakat hazırlığı ve bir rapor çıkarıyor. Raporda işveren puanı, ATS skorunun önceki ve sonraki hâli, CV'de nelerin değiştiği ve kapanmayan eksikler var. Ajanların birbirine yazdıkları terminalde ya da yerel bir web sayfasında canlı akıyor, hangi maddenin neden değiştiğini oradan takip edebiliyorsunuz.

## İçindekiler

- [Neden farklı?](#neden-farklı)
- [Hızlı başlangıç](#hızlı-başlangıç)
- [Web arayüzü](#web-arayüzü)
- [Örnek çalıştırma](#örnek-çalıştırma)
- [Nasıl çalışır?](#nasıl-çalışır)
- [Mimari](#mimari)
- [Modlar](#modlar)
- [Diller](#diller)
- [Görsel ve taranmış PDF girdisi](#görsel-ve-taranmış-pdf-girdisi)
- [Gizlilik](#gizlilik)
- [Geliştirme](#geliştirme)
- [Yol haritası](#yol-haritası)

## Neden farklı?

Yapay zekâya CV uyarlattığınızda ilana uysun diye adayda olmayan beceri, rakam ya da kıdem ekleyebiliyor ([Grounded Optimization, arXiv 2607.01457](https://arxiv.org/abs/2607.01457) bu tür hataları sınıflandırıyor). Mülakatta sorulduğunda da ortaya çıkıyor.

Promptta "uydurma yapma" demek bunu engellemiyor. career-crew'da her CV maddesi orijinal CV'den birebir bir alıntıya bağlanıyor ve bu bağlantıyı model değil kod kontrol ediyor:

| | Yaygın yaklaşım | career-crew |
|---|---|---|
| Uydurmaya karşı | Prompta "uydurma yapma" yazılır, modele güvenilir | Her madde orijinal CV'den bir alıntıya bağlanır. Alıntıyı ve 8 ayrı kuralı kod kontrol eder |
| Son karar | Ajanlar birbirini onaylar | Kod hata bulduysa Doğrulayıcı onay veremez. Verirse kod kararı "ret" olarak değiştirir |
| Eksik beceriler | Eksik anahtar kelimeyi CV'ye eklemek önerilir | Eksik kelime eklenmez. Raporda gerçek eksik olarak yazılır, mülakat hazırlığında nasıl dürüstçe cevaplanacağı anlatılır |
| ATS skoru | Tek bir sayı | Önceki ve sonraki skor, eksik kelimeler ve neden eklenmedikleri |
| Şeffaflık | Sadece sonuç dosyası | Konuşma canlı akar, her turun CV'si `work/` klasöründe kalır, süreç `events.jsonl` dosyasına yazılır |
| Tur sayısı | Sabit sayıda yeniden yazma | Hedefe ulaşınca ya da puan artmayı bırakınca döngü durur |
| Veri | CV bir bulut hizmetine yüklenir | Program kendi bilgisayarınızda çalışır. Veri sadece seçtiğiniz model sağlayıcısına gider, analitik yok |
| Maliyet | Aylık ücretli hizmet | `mock` modu ücretsiz, `claude-code` modu mevcut Claude aboneliğinizle çalışır |

Gerçek bir çalıştırmada ilan Docker istiyordu ve CV'de Docker yoktu. CV Yazarı Docker'ı eklemedi, İşe Alım Müdürü de bu yüzden 62 puan verdi. Ön yazıda Docker deneyimi olmadığı açıkça yazıyordu, mülakat hazırlığında da "Docker kullandınız mı?" sorusu için dürüst bir cevap önerisi vardı.

## Hızlı başlangıç

Python 3.11 ya da üstü gerekiyor.

```bash
git clone https://github.com/burakaydins/career-crew.git
cd career-crew
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[api,dev]"
```

Hesap gerektirmeyen demo, sahte bir CV ve ilanla:

```bash
career-crew --ilan examples/ilan.md --cv examples/cv.md
```

Kendi dosyalarınızla:

```bash
career-crew --ilan ilan.pdf --cv cv.docx --mod api
```

CV ve ilan `.md`, `.txt`, `.pdf` ya da `.docx` olabilir. İlanın ekran görüntüsü (`.png`, `.jpg`) ve taranmış PDF de verilebilir, [aşağıda](#görsel-ve-taranmış-pdf-girdisi) anlattım. PDF, DOCX ve görsellerden çıkarılan metin, ajanların ve kontrollerin tam olarak neyi gördüğü bilinsin diye çalıştırma klasöründe `inputs/cv_metin.md` olarak saklanıyor.

Tarayıcıda kullanmak isterseniz:

```bash
career-crew web
```

| Seçenek | Açıklama |
|---|---|
| `--ilan` | İş ilanı (`.md`, `.txt`, `.pdf`, `.docx`, `.png`, `.jpg`) |
| `--cv` | CV (aynı türler) |
| `--mod` | `mock` (varsayılan), `claude-code` ya da `api` |
| `--dil` | Ajan promptlarının dili: `tr` (varsayılan) ya da `en` |
| `--runs` | Çalıştırma klasörlerinin yeri (varsayılan `runs/`) |
| `--evet` | İlan okuma onayını sorma |
| `--hizli` | `mock` modunda bekleme yapma |

## Web arayüzü

```bash
career-crew web
```

Komut `http://127.0.0.1:8765` adresinde bir sayfa açıyor ve tarayıcıyı da açıyor. Üç sütunu var. Solda süreç adımları ve durumları, ortada ajanların canlı konuşması, sağda skorlar, çıktı dosyaları ve orijinal CV ile uyarlanmış CV'nin karşılaştırması (eklenen satırlar yeşil, çıkarılanlar kırmızı, "Büyüt" ile iki CV yan yana açılıyor). İlan okuma onayı terminaldeki soru yerine konuşmanın içinde bir düğme olarak çıkıyor: onaylayabilir ya da ne düzeltileceğini yazabilirsiniz. Açık ve koyu tema var, telefon genişliğinde sütunlar alt alta diziliyor.

İlanı ve CV'yi sürükleyip bırakabilir ya da metin olarak yapıştırabilirsiniz. Dosya türü ve 10 MB sınırı hem tarayıcıda hem sunucuda denetleniyor. Sayfa adresindeki `#run=...` kısmı sayesinde sekmeyi yenileseniz de süreç baştan oynatılıyor.

| Seçenek | Açıklama |
|---|---|
| `--port` | Port (varsayılan `8765`) |
| `--mod` | Model sağlayıcısı. Web arayüzünde sunucuyu başlatırken seçiliyor |
| `--dil` | Varsayılan prompt dili, sayfadan değiştirilebiliyor |
| `--runs` | Çalıştırma klasörlerinin yeri |
| `--hizli` | `mock` modunda bekleme yapma |
| `--acma` | Tarayıcıyı kendiliğinden açma |

Sunucu yalnızca `127.0.0.1` adresini dinliyor, başka adres seçeneği yok. Bunun üstüne iki kontrol daha koydum. Host başlığı `127.0.0.1` ya da `localhost` değilse istek reddediliyor (DNS rebinding'e karşı). Yazma istekleri başka bir sitenin sayfasından gelmişse, yani Origin başlığı bu sunucunun adresi değilse, reddediliyor. Yine de bir ağ servisi olarak tasarlanmadı: kimlik doğrulaması yok, aynı anda tek süreç çalışıyor.

Arayüz düz HTML, CSS ve JavaScript. Derleme adımı ve CDN yok, `app/web/static/` altındaki üç dosyadan ibaret. Olaylar terminaldeki ile aynı Event Bus'tan geliyor, tarayıcıya SSE ile akıyor. Süreç arka plandaki bir iş parçacığında çalışıyor, orchestrator'ın mantığı web için kopyalanmadı.

## Örnek çalıştırma

`mock` modunda CV Yazarı ilk turda bilerek uydurma ekliyor, kontrollerin bunları nasıl yakaladığı görülsün diye:

```
───────────────────────────────── CV turu 1/3 ──────────────────────────────────
✍️ CV Yazarı: CV uyarlandı → output/cv.md. Backend becerileri özete ve beceri
listesinin başına alındı.
🧮 Kod kontrolü: 5 sorun: ATS %30.8 → %38.5
   ✗ Kanıt orijinal CV'de bulunamadı: 'PostgreSQL sorgu optimizasyonunu yönettim.'
   ✗ Kanıt orijinal CV'de bulunamadı: 'Docker ile servisleri paketledim.'
   ✗ 'Docker' ilanda var ama orijinal CV'de yok (sızıntı).
   ✗ '5 yıl' iddiası orijinal CV ile uyuşmuyor (en fazla 3 yıl).
   ✗ '40' rakamı orijinal CV'de yok.
🛡️ Doğrulayıcı: Ret: Docker, %40 ve 5 yıl uydurma. 'Yer aldım' ifadesi
'yönettim' yapılmış.
👔 İşe Alım Müdürü: Puan 72. Uydurmalar mülakatta ortaya çıkar, SQL görünmüyor,
test deneyimi zayıf anlatılmış.
───────────────────────────────── CV turu 2/3 ──────────────────────────────────
✍️ CV Yazarı: Düzeltildi. Docker, %40 ve 'yönettim' çıkarıldı, özet orijinal 3
yıla döndü. SQL, orijinal optimizasyon maddesinden öne çıkarıldı.
🧮 Kod kontrolü: Sorun yok. ATS %30.8 → %38.5
🛡️ Doğrulayıcı: Onay.
👔 İşe Alım Müdürü: Puan 84. Docker ve Kubernetes gerçek eksik, ölçülebilir
sonuç yok.
✓ CV 2. turda hedefe ulaştı.
```

Her çalıştırma `runs/` altında kendi klasörünü açıyor:

```
runs/2026-11-21_143000_ilan/
├── inputs/       ilan ve CV kopyası
├── work/         job.json, claims.json, her turun CV'si
├── output/       cv.md, cover_letter.md, interview.md, report.md
└── events.jsonl  tüm konuşma
```

## Nasıl çalışır?

### Ajanlar

| Ajan | Görev | Model |
|---|---|---|
| 🔎 İlan Analisti | İlandan beceri ve anahtar kelimeleri çıkarır | Sonnet |
| ✍️ CV Yazarı | CV'yi uyarlar, her maddeyi kanıta bağlar | Sonnet |
| 🛡️ Doğrulayıcı | Uydurma olup olmadığına karar verir | Sonnet |
| 👔 İşe Alım Müdürü | 0-100 puan verir, en kritik 3 eksiği söyler | Haiku |
| 💌 Mektup Yazarı | Ön yazı hazırlar | Sonnet |
| 🎤 Mülakatçı | Mülakat soruları ve cevap ipuçları hazırlar | Haiku |

Modeller `agents/*.json` dosyalarından, promptlar `prompts/tr/` ve `prompts/en/` altından değiştirilebiliyor. Ajanlara kısa konuşmaları söylendi: en fazla üç cümle, önce karar sonra gerekçe, selamlama ve övgü yok.

### Akış

```
İlan analizi → kullanıcı onayı → CV döngüsü (en fazla 3 tur) → ön yazı → mülakat → rapor
                                  │
                                  ├─ CV Yazarı
                                  ├─ kod kontrolleri
                                  └─ Doğrulayıcı + İşe Alım Müdürü (paralel)
```

Uydurma yoksa ve puan 80'e ulaştıysa döngü biter. Üst üste iki temiz turda puan yükselmediyse de durur, çünkü kalan eksikler orijinal CV'de yok ve yeni bir tur sadece token harcar. Üç tur dolarsa en iyi sürüm kullanılır, rapora da bir uyarı eklenir.

### Uydurma kontrolü

Kontrol üç aşamada yapılıyor. Önce CV Yazarı her maddeyi orijinal CV'den en az üç kelimelik birebir bir alıntıya bağlıyor. Kod, alıntının orijinal CV'de gerçekten geçtiğine ve CV'deki her maddenin bir alıntısı olduğuna bakıyor. Sonra aşağıdaki kurallar çalışıyor. Bunlar düz Python fonksiyonları, LLM kullanmıyorlar ve aynı girdiye hep aynı sonucu veriyorlar. En son Doğrulayıcı ajan, kodun yakalayamayacağı anlam kaymalarına bakıyor; "projede yer aldım" cümlesinin "projeyi yönettim" olması gibi. Kod hata bulduysa Doğrulayıcı onay veremiyor.

| Kontrol | Düzey | Ne yakalar |
|---|---|---|
| `coverage` | hata | Kanıta bağlanmamış CV maddesi |
| `evidence` | hata | Orijinal CV'de olmayan ya da 3 kelimeden kısa kanıt alıntısı |
| `leakage` | hata | İlanda olup orijinal CV'de olmayan beceri |
| `leakage` (yeni terim) | uyarı | İlanda da orijinal CV'de de olmayan teknoloji adı |
| `dates` | hata | Yeni yıllar, şişirilmiş "N yıl deneyim" |
| `numbers` | hata | Yeni rakam ve yüzdeler |
| `titles` | hata | Eklenen kıdem ya da unvan ifadesi |
| `structure` | uyarı | 2 sayfayı aşan uzunluk, kaybolan bölüm |
| `ats` | skor | İlan anahtar kelimelerinin CV'de geçme oranı |

## Mimari

```mermaid
flowchart TB
    CLI["CLI<br/>app/cli.py"]
    WEB["Web arayüzü<br/>app/web/"]
    BUS["Event Bus<br/>app/events.py"]
    LOG[("events.jsonl")]
    ORCH["Orchestrator<br/>app/orchestrator.py"]
    WF["Workflow<br/>Sequential · Parallel · Loop · UserGate<br/>app/workflow.py"]
    SKILLS["Skill'ler<br/>prompt + sonuç işleme<br/>app/skills.py"]
    REG["Registry<br/>agents/*.json · prompts/tr · prompts/en"]
    CHECKS["Kod kontrolleri<br/>app/checks/"]
    REPORT["Rapor<br/>app/report.py"]
    RUN[("runs/…/<br/>inputs · work · output")]

    subgraph PROV["Provider (tek arayüz)"]
        MOCK["MockProvider"]
        CC["ClaudeCodeProvider<br/>claude -p"]
        API["ApiProvider<br/>Anthropic SDK"]
    end

    CLI -->|ilan + CV| ORCH
    CLI -. kullanıcı onayı .-> ORCH
    WEB -->|ilan + CV| ORCH
    WEB -. onay düğmesi .-> ORCH
    ORCH --> WF
    WF -->|ajan adımı| SKILLS
    SKILLS --> REG
    SKILLS -->|prompt| PROV
    PROV -->|JSON zarfı| SKILLS
    WF -->|kod adımı| CHECKS
    WF -->|son adım| REPORT
    SKILLS -->|dosyalar| RUN
    REPORT --> RUN
    ORCH -->|olaylar| BUS
    BUS --> CLI
    BUS -->|SSE| WEB
    BUS --> LOG
```

Ajanlara hiç araç vermedim. İlan, CV ve önceki sürüm doğrudan prompta ekleniyor, her ajan da `{"message", "data", "files"}` biçiminde tek bir JSON döndürüyor. Dosyaları ajanlar değil orchestrator yazıyor ve her skill sadece kendi dosya adlarını yazabiliyor. Bu sayede üç mod aynı şekilde çalışıyor ve `claude-code` modunda bile ajanların dosya ya da shell erişimi olmuyor.

Workflow parçaları (`Sequential`, `Parallel`, `Loop`, `UserGate`) iş akışının ne olduğunu bilmiyor, sadece bir bağlam nesnesiyle konuşuyor. Kariyer akışı bu parçalarla [orchestrator.py](app/orchestrator.py) içinde kuruluyor. Terminal çıktısı, `events.jsonl` ve web arayüzü aynı Event Bus'tan besleniyor. Web tarafı olayları SSE ile alıyor.

Görev durumlarını A2A'dan aldım: `submitted → working → completed / rejected / failed / input-required`.

| Yol | Görev |
|---|---|
| `app/cli.py` | Argümanlar, renkli canlı akış, ilan okuma onayı, `web` komutu |
| `app/web/` | FastAPI sunucusu (`server.py`) ve tek sayfalık arayüz (`static/`) |
| `app/inputs.py` | `.md`, `.txt`, `.pdf`, `.docx` okuyucuları, boyut ve uzantı denetimi, görsel girdinin yönlendirilmesi |
| `app/orchestrator.py` | Kariyer akışını kurar, çalıştırma klasörünü açar, en iyi turu seçer |
| `app/workflow.py` | Akış yapı taşları: `Sequential`, `Parallel`, `Loop`, `CodeStep`, `UserGate` |
| `app/skills.py` | Skill başına prompt üretimi, yanıt doğrulama ve durum güncellemesi |
| `app/tasks.py` | `Task`, `Message`, `TextPart`, `FilePart`, `DataPart`, `Artifact` |
| `app/events.py` | Event Bus ve `events.jsonl` kaydı |
| `app/registry.py` | Agent Card'ları ve seçilen dildeki promptları yükler |
| `app/providers/` | `mock`, `claude_code`, `api` ve ortak JSON zarfı ayrıştırıcısı |
| `app/checks/` | `coverage`, `evidence`, `leakage`, `dates`, `numbers`, `titles`, `structure`, `ats` |
| `app/report.py` | `report.md`: skorlar, turlar, açık sorunlar, değişiklikler |
| `agents/` | 6 Agent Card: model, efor, renk, prompt dosyası |
| `prompts/tr/`, `prompts/en/` | Rol promptları ve ortak konuşma sözleşmesi, iki dilde |

## Modlar

| Mod | Kim için | Maliyet |
|---|---|---|
| `api` | Claude aboneliği olmayanlar için, kendi Anthropic API anahtarınızla | Kendi API kullanımınız |
| `claude-code` | Kendi Claude Pro/Max aboneliğinizle kişisel kullanım | Ek ücret yok, abonelik limitine tabi |
| `mock` | Demo ve geliştirme | Ücretsiz |

`api` modu için `ANTHROPIC_API_KEY` ortam değişkenini ayarlayın ya da `.env.example` dosyasını `.env` adıyla kopyalayıp anahtarı içine yazın. Anahtar koda ya da loglara yazılmıyor. Bu modu kendi işim için kullanmadığımdan gerçek API ile henüz çalıştırmadım. İstek biçimi ve hata yönetimi sahte bir istemciyle test ediliyor, ama bir sorun çıkarsa issue açarsanız sevinirim.

`claude-code` modu için Claude Code kurulu olmalı ve `claude auth login` ile giriş yapılmış olmalı. Ajanlar sizin global ayarlarınızı, eklentilerinizi, hook'larınızı ve MCP sunucularınızı yüklemeden çalışıyor, hiçbir araca da erişemiyor. Ortamda `ANTHROPIC_API_KEY` tanımlıysa bu mod onu kaldırıyor, böylece ücret API'ye değil aboneliğe yansıyor. Benim denememde bir çalıştırma iki dakika kadar sürdü.

> Kullanım şartları: `claude-code` modu herkesin kendi aboneliğiyle, kendi bilgisayarında kişisel kullanımı için var. Proje bir hizmet olarak sunulmuyor. Claude Code giriş bilgileri okunmuyor ya da başka bir yere taşınmıyor, sadece resmî `claude` komutu çağrılıyor. Bu modu kullananlar Anthropic kullanım şartlarına uymaktan kendileri sorumlu.

## Diller

`--dil tr|en` ya da web arayüzündeki dil seçimi, ajanların hangi dilde yazılmış prompt aldığını belirliyor. `registry.py` `prompts/tr/` ya da `prompts/en/` klasörünü seçiyor, kullanıcı prompt'undaki başlıklar da aynı dilde gidiyor. Kurallar iki dilde aynı: uydurma yasağı, kanıt alıntısı, JSON zarfı, 80 puan eşiği. Ajanların ürettiği CV, ön yazı ve mülakat notu promptun dilinden bağımsız olarak orijinal CV'nin dilinde yazılıyor, yani İngilizce promptla Türkçe bir CV'yi uyarlarsanız çıktı Türkçe kalıyor.

İki sınır var. `mock` sağlayıcısı hazır bir Türkçe senaryo oynattığı için `--dil en` ile de Türkçe konuşuyor. Kod kontrollerinin hata mesajları (örneğin "Kanıt orijinal CV'de bulunamadı") ve rapor da şimdilik Türkçe, İngilizce çalıştırmada bu mesajlar yazara Türkçe gidiyor.

## Görsel ve taranmış PDF girdisi

İlanın ekran görüntüsünü (`.png`, `.jpg`) ya da metin katmanı olmayan taranmış bir PDF'i verebilirsiniz. Metin çıkmadığında dosya modele gönderiliyor, model sadece içindeki yazıyı aynen yazıya döküyor (özetlemiyor, çevirmiyor), sonuç `inputs/*_metin.md` olarak saklanıyor ve sonrası normal akış. Ajanlar ve kontroller bu dökümü orijinal metin sayıyor, o yüzden okuma hatası olursa CV'deki "kanıt" da o hataya dayanır. Döküm dosyasına bakmanızı öneririm.

| Mod | Durum |
|---|---|
| `claude-code` | `claude -p` komutuna `--input-format stream-json` ile görsel ve PDF bloğu gönderiliyor. Bir ilan görüntüsüyle ve taranmış bir PDF ile elle denedim, çalıştı. Ajanlarda olduğu gibi araçsız ve ayarsız çalışıyor |
| `api` | Görsel için `image`, PDF için `document` bloğu gönderiliyor (görsel 5 MB ile sınırlı, API kuralı). Gerçek API ile denenmedi, anahtarım olmadığı için. İstek biçimi sahte istemciyle test ediliyor |
| `mock` | Görsel okuyamaz, bunu söyleyen bir hata veriyor |

## Gizlilik

`runs/`, `memory/` ve `.env` `.gitignore`'da. Repodaki örnek CV ve ilan sahte. Veriler seçilen model sağlayıcısı dışında bir yere gönderilmiyor, analitik ya da izleme yok. Web arayüzü yalnızca bu bilgisayardan erişilebiliyor. Yüklenen dosyalar geçici klasörde tutulup işlem bitince siliniyor, kopyaları `runs/` altında kalıyor.

## Geliştirme

```bash
pytest
```

Gerçek model çağıran testler için `claude-code` girişi gerekiyor:

```bash
CAREER_CREW_LIVE=1 pytest -m live
```

Bu testler ajan çağrısının kullanıcı eklentilerini ve MCP sunucularını yüklemediğine ve hiçbir araca erişmediğine bakıyor.

README'deki GIF `mock` çalıştırmasından üretiliyor (macOS, Pillow gerekir):

```bash
python scripts/make_demo_gif.py docs/demo.gif
```

Tasarım notları [KARIYER-EKIBI.md](KARIYER-EKIBI.md) dosyasında.

## Yol haritası

- [x] M1: çekirdek, terminal arayüzü, uydurma kontrolleri
- [x] PDF ve DOCX girdisi
- [x] M2: localhost web arayüzü, ilan görüntüsü ve taranmış PDF girdisi, İngilizce promptlar
- [ ] M3: hafıza, duraklatıp devam etme, PDF çıktı
- [ ] M4: replay modu

## Esinlenmeler

| Kaynak | Ne aldım |
|---|---|
| [DeepLearning.AI: Multi AI Agent Systems with crewAI](https://learn.deeplearning.ai/courses/multi-ai-agent-systems-with-crewai/lesson/a8ecj/build-a-crew-to-tailor-job-applications) | İş başvurusu ekibindeki roller |
| [Grounded Optimization, arXiv 2607.01457](https://arxiv.org/abs/2607.01457) (Indukuri ve Agrawal) | Katmanlı doğrulama fikri: tarih kontrolü, kodla sızıntı tespiti, yapı kontrolü ve değerlendirici ajan |
| [Hirepanel](https://github.com/punit2911/Hirepanel) | CV tarayan bu araçtaki "alıntı yoksa puan da yok" kuralı. Burada aynı kuralı CV'yi yazan tarafa uyguladım |
| Yusuf Baykaloğlu, *Çoklu-Ajan Sistemleri: A2A Protokolü ile AI Agent Orkestrasyonu* | Agent Card, görev durumları, Message/Part yapısı, workflow desenleri, Event Bus |

## Uyarı

Yapay zekâ çıktıları hatalı olabilir. Başvurmadan önce her şeyi kendiniz okuyun.

## Lisans

[MIT](LICENSE)
