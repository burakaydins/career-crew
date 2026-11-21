# SprintSquad: Çok Ajanlı Agile Yazılım Geliştirme Sistemi

> Çalışma adı. İstenirse değiştirilebilir.

## 1. Amaç

Kullanıcı tek cümlelik bir ürün fikri verir (örnek: *"basit bir todo CLI uygulaması"*). Bir yazılım şirketindeki rolleri üstlenen yapay zekâ ajanları, **hafifletilmiş bir Agile (Scrum) süreciyle** kendi aralarında konuşarak fikri çalışan ve test edilmiş bir yazılıma dönüştürür.

**Temel ilke:** Kullanıcı ajanların birbirleriyle yaptığı bütün konuşmaları **canlı olarak** görür. Kim kime ne söyledi, hangi kararı verdi, hangi dosyayı yazdı, hangi test geçti ya da kaldı, hepsi ekranda akar.

## 2. Kapsam

### Proje boyutu: küçük tutulur
Pro aboneliğinin kullanım limitlerine takılmamak için ajanların üreteceği projeler bilinçli olarak küçük tutulur:
- **En fazla 2 sprint**, her sprintte **en fazla 2 story** (toplamda en fazla 4 story)
- **Tek dil (Python)**, birkaç dosyalık projeler: CLI araçları, küçük kütüphaneler, basit oyunlar ve hesaplayıcılar
- **Toplam en fazla ~30 ajan turu**
- PO, backlog yazarken bu sınırları uygular. Fikir büyükse CTO kickoff'ta kapsamı daraltır ve geri kalanını "sonraki sürüm" olarak not eder.

### MVP'de olacaklar
- 7 rollü ajan ekibi (bkz. Bölüm 3)
- Agile-lite süreç: backlog, 1–2 sprint, review, test, demo ve kısa retro
- Ajanların ayrı bir `workspace/` klasörüne gerçek kod yazması
- QA ajanının `pytest` çalıştırması ve hataları Developer'a geri göndermesi
- Konuşmaları sohbet balonları hâlinde canlı gösteren web arayüzü
- Tüm konuşmanın ve çıktıların diske kaydedilmesi (`runs/<tarih>/`)

### Kullanım şekli
Kişisel bir araç. Kendi bilgisayarında `localhost` üzerinde çalışır ve tarayıcıdan açılır. App Store'a ya da internete yayınlanmayacak, bu yüzden kullanıcı girişi, çoklu kullanıcı ve sunucu kurulumu gerekmiyor.

### MVP'de olmayacaklar (sonraki sürümler)
- Kullanıcının süreç ortasında araya girip yorum yapması
- Birden fazla Developer ajanının paralel çalışması
- Python dışındaki dillerde proje üretimi
- Gerçek bir sunucuya deploy etme

## 3. Roller (Ajanlar)

| Ajan | Agile karşılığı | Sorumluluk | Çıktı |
|---|---|---|---|
| 👔 **CTO** | Yönetim | Fikri değerlendirir, kapsamı belirler, aşama onaylarını verir, anlaşmazlıkları çözer, son Go/No-Go kararını verir | Kickoff notu, onaylar, final rapor |
| 🧑‍💼 **Product Owner** | Scrum rolü | Product Backlog'u ve user story'leri yazar, kabul kriterlerini belirler, sprint sonunda işi kabul ya da reddeder | `docs/backlog.md` |
| 🧭 **Scrum Master** | Scrum rolü | Süreci yönetir: sıradaki konuşmacıyı seçer, sprintleri başlatıp bitirir, tur sınırlarını uygular. **LLM değildir, orchestrator kodudur.** Arayüzde ajan gibi görünür ama mesajları şablondan gelir, Pro limiti harcamaz | Sprint özetleri |
| 🏗️ **Tech Lead** | Ekip | Mimariyi, dosya yapısını ve teknik kararları belirler | `docs/design.md` |
| 👨‍💻 **Developer** | Development Team | Story'leri koda döker, review ve test geri bildirimlerini düzeltir | `src/` |
| 🔍 **Reviewer** | Development Team | Kodu okunabilirlik, hata ve tasarıma uygunluk açısından inceler | Review yorumları |
| 🧪 **QA** | Development Team | Kabul kriterlerine göre test yazar ve çalıştırır, hata raporlar | `tests/`, test raporu |

> DevOps rolü MVP'de yok. Paketleme (README ve çalıştırma talimatı) son sprintte Developer'a verilir.

## 4. Süreç Akışı

```
Kullanıcı fikri
   │
   ▼
[1] KICKOFF        CTO fikri değerlendirir ve MVP kapsamını çizer
   │
   ▼
[2] BACKLOG        PO user story'leri ve kabul kriterlerini yazar ──► CTO onayı
   │
   ▼
[3] TASARIM        Tech Lead mimariyi belirler ──► CTO onayı
   │
   ▼
[4] SPRINT DÖNGÜSÜ (1–2 sprint, her biri en fazla 2 story)
   │   ├─ Sprint Planning   SM + PO: bu sprintte hangi story'ler var?
   │   ├─ Geliştirme        Developer kodu yazar
   │   ├─ Review + Test     Reviewer ve QA AYNI ANDA (paralel) çalışır
   │   ├─ Düzeltme          Developer ikisinin geri bildirimini tek turda düzeltir
   │   │                    (review en fazla 1, test en fazla 2 düzeltme turu)
   │   └─ Sprint Review     PO kabul kriterlerine bakar: kabul ya da ret
   │
   ▼
[5] RETRO          Ekip kısa bir değerlendirme yapar (ne iyi gitti, ne kötü)
   │
   ▼
[6] GO / NO-GO     CTO final kararı verir ve proje özetini yazar
   │
   ▼
✅ workspace/ içinde çalışan, test edilmiş proje
```

### Kurallar
- **Onay kapıları:** CTO reddederse iş gerekçesiyle bir önceki ajana döner (en fazla 1 kez).
- **Döngü sınırları:** Review ya da test döngüsü sınırı aşarsa Scrum Master konuyu CTO'ya taşır, son kararı CTO verir.
- **Daily standup yok.** Ajanlar ortak hafızayı zaten okuyor, standup yalnızca maliyet getirir. Onun yerine her sprint sonunda otomatik bir durum özeti yazılır.

## 4.1 Konuşma Tarzı: Kısa, Net, Laf Kalabalığı Yok

LLM'ler rol yaparken birbirini övmeye ve kurumsal dil kullanmaya meyillidir ("Harika bir vizyon, ekibimize güveniyorum!"). Bunu engellemek için **her ajanın sistem promptunda ortak bir "konuşma sözleşmesi"** bulunur:

```
KONUŞMA KURALLARI (herkes için geçerli)
- En fazla 3 cümle. Doküman ve kod bu sınıra dahil değil, onlar dosyaya yazılır.
- Selamlama, övgü, teşekkür, motivasyon cümlesi YOK.
  ("Harika iş!", "Ekibe güveniyorum", "Mükemmel bir soru" yasak.)
- Önce karar, sonra gerekçe. Gerekçe tek cümle.
- Söylenmiş bir şeyi tekrar etme. Dosyada yazanı mesajda özetleme, dosya adını ver.
- Sorun yoksa sadece "Onay." de, açıklama ekleme.
- Belirsizlik varsa tek bir net soru sor.
```

**Rol başına ek kurallar ve mesaj kalıpları**
| Ajan | Kural | Örnek mesaj |
|---|---|---|
| CTO | Sadece karar verir. "Onay" ya da "Ret: <tek cümle neden>" | `Ret: CSV dışa aktarma MVP'ye girmesin, sonraki sürüme.` |
| PO | Story'ler dosyaya yazılır, mesajda sadece sayı ve dosya adı verilir | `4 story yazdım → docs/backlog.md. S1 ve S2 ilk sprint için.` |
| Tech Lead | Mesajda en fazla 3 madde halinde kritik karar | `Tek modül: todo.py. Veri: JSON dosya. CLI: argparse.` |
| Developer | Ne yaptığını tek cümleyle söyler | `S1 bitti: todo.py'ye add/list eklendi.` |
| Reviewer | Sadece sorunları madde madde yazar, sorun yoksa "Onay." | `1) todo.py:24 boş başlık kabul ediliyor.` |
| QA | Sonuç + başarısız test adları | `5/6 geçti. Kalan: test_empty_title.` |

**Yapılandırılmış karar çıktısı:** CTO onayı, PO kabulü ve Reviewer kararı serbest metin değil, `--json-schema` ile **JSON** olarak alınır:
```json
{ "decision": "approve" | "reject", "reason": "tek cümle" }
```
Böylece hem cevaplar kısa olur hem de orchestrator kararı metinden tahmin etmek zorunda kalmaz.

## 4.2 Hız: Yavaş Olmaması İçin

Her `claude -p` çağrısının bir açılış süresi ve bir düşünme/yazma süresi vardır. İkisini birden kısaltırız:

| # | Önlem | Etkisi |
|---|---|---|
| 1 | **Scrum Master LLM değil, kod** | Her aşama geçişinde 1 LLM turu tasarrufu |
| 2 | **Kısa mesaj kuralı (4.1)** | Daha az çıktı token'ı, daha hızlı cevap |
| 3 | **Hafif roller için hızlı model:** CTO ve PO `haiku` ile çalışır (karar verme ve liste yazma için yeterli) | Bu rollerin turları birkaç saniyeye iner |
| 4 | **Düşük efor:** Konuşan rollerde `--effort low`, kod yazan rollerde `medium` | Gereksiz uzun düşünme yok |
| 5 | **Reviewer ve QA paralel çalışır**, Developer tek turda ikisini düzeltir | Sprint başına 1–2 tur ve bekleme süresi tasarrufu |
| 6 | **Hafif başlatma:** `--strict-mcp-config` (MCP sunucuları yüklenmez), `--setting-sources ""` (kullanıcı ayarları ve hook'lar yüklenmez), `--tools` ile sadece gereken araçlar | Her çağrının açılış süresi kısalır |
| 7 | **Kısa sistem promptu:** `--system-prompt` ile Claude Code'un uzun varsayılan promptu yerine rolün kendi kısa promptu verilir | Daha az girdi, daha hızlı ilk cevap |
| 8 | **Bağlam kırpma:** Ajana tüm konuşma geçmişi değil, sadece ilgili son mesajlar ve dosya adları verilir. Dosya içeriğini gerekirse kendisi okur | Girdi küçük kalır |
| 9 | **(M3) Kalıcı ajan süreçleri:** Her ajan için bir `claude -p --input-format stream-json` süreci açık tutulur, her tur için yeniden başlatılmaz | Tur başına açılış süresi tamamen ortadan kalkar |

**Hedef süre:** Küçük bir proje için **toplam 5–10 dakika**. Arayüzde her ajanın çalıştığı süre ve toplam süre gösterilir, böylece yavaşlayan yer hemen görülür.

> Not: `--bare` modu en hızlı başlatmayı sağlar ama sadece API anahtarıyla çalışır, Pro girişini okumaz. Bu yüzden `claude-code` modunda değil, yalnızca `api` modunda kullanılır.

## 5. Mimari

```
┌──────────────────────────── Tarayıcı ────────────────────────────┐
│  Fikir giriş kutusu  │  Canlı sohbet akışı  │  Dosyalar / Durum  │
└──────────────▲───────────────────────────────────────────────────┘
               │ Server-Sent Events (canlı akış)
┌──────────────┴────────────── Backend (FastAPI) ──────────────────┐
│  Orchestrator (Scrum Master mantığı: aşamalar, turlar, kapılar)  │
│        │                                                         │
│        ▼                                                         │
│  Ajanlar ── ortak "toplantı odası" (mesaj geçmişi) ──► Event Bus  │
│        │                                                         │
│        ▼                                                         │
│  Claude Code headless:  claude -p  (her ajan turu bir çağrı)     │
│        │   Read / Write / Edit / Bash(pytest) araçları hazır      │
│        ▼                                                         │
│  workspace/  (ajanların ürettiği proje, sandbox klasör)          │
└──────────────────────────────────────────────────────────────────┘
               │
               ▼
        Kullanıcının Claude Pro aboneliği (ekstra ücret yok)
```

### Bileşenler
- **Agent:** Rol adı, sistem promptu, modeli ve izin verilen araçlarından oluşur. Her konuşma sırası, `workspace/` klasöründe çalıştırılan bir `claude -p` çağrısıdır.
- **Toplantı odası (shared transcript):** Tüm ajanların mesajlarının tutulduğu ortak geçmiş. Orchestrator, ajanı çağırırken ilgili kısmı prompta ekler.
- **Orchestrator:** Süreç akışını (Bölüm 4) kodla yönetir. Kimin konuşacağına kod karar verir, böylece süreç öngörülebilir ve sınırlı olur.
- **Event Bus:** `claude -p --output-format stream-json` çıktısı satır satır okunur. Her mesaj, araç çağrısı ve test sonucu bir olay olarak arayüze anlık gönderilir.

### LLM bağlantısı: Claude Code headless modu
API anahtarı ve ücretli kredi yerine, makinede kurulu **Claude Code CLI'ın headless modu** kullanılır. Böylece kullanıcının mevcut **Claude Pro aboneliği** ile çalışır, ekstra ücret yoktur.

Kullanılan bayraklar:
| Bayrak | Amaç |
|---|---|
| `-p` | Etkileşimsiz (headless) çalıştırma |
| `--append-system-prompt` | Ajanın rolünü ve kurallarını vermek |
| `--output-format stream-json --verbose` | Çıktıyı canlı olarak arayüze akıtmak |
| `--model` | Rol başına model seçimi (`sonnet` / `opus`) |
| `--allowedTools` | Rol başına araç izinleri |
| `--resume <session-id>` | Ajanın kendi önceki turlarını hatırlaması |

**Rol başına izinler**
| Ajan | İzinli araçlar | Model | Efor |
|---|---|---|---|
| CTO | Sadece okuma (`Read`) | Haiku | low |
| PO | Okuma + `docs/backlog.md` yazma | Haiku | low |
| Scrum Master | — (LLM değil, kod) | — | — |
| Tech Lead | Okuma + `docs/` altına yazma | Sonnet | low |
| Developer | Okuma + `Write`, `Edit` | Sonnet | medium |
| Reviewer | Sadece okuma | Sonnet | low |
| QA | Okuma + `Write`, `Edit` (`tests/` için) + `Bash(pytest:*)` | Sonnet | medium |

> Hız ve Pro limitleri için hafif roller **Haiku**, kod ve teknik değerlendirme yapan roller **Sonnet** kullanır. Ayarlardan istenen rol Opus'a çevrilebilir.

**Kullanım limiti yönetimi:** `claude -p` limit hatası döndürürse orchestrator süreci **duraklatır**, durumu `runs/<tarih>/state.json` dosyasına kaydeder ve arayüzde "Limit doldu, şu saatte devam edilebilir" mesajı gösterir. Kullanıcı daha sonra kaldığı yerden devam ettirebilir.

**Kullanım şartları:** Bu mod, kullanıcının kendi bilgisayarında kişisel kullanım içindir. Uygulama bir hizmet olarak başkalarına sunulmayacak. Kaynak kod GitHub'da paylaşılabilir, bkz. aşağıdaki bölüm. Claude Code'un giriş bilgileri asla doğrudan okunmaz ya da API'ye taşınmaz, yalnızca resmî `claude` komutu kullanılır.

**İleride:** Ayarlara "Anthropic API anahtarı kullan" seçeneği eklenecek (bkz. GitHub'da paylaşım).

### GitHub'da paylaşım (portfolyo)
Proje, "böyle bir sistem yaptım" amacıyla GitHub'da **açık kaynak kod olarak** paylaşılacak. Bunun için:
- **Paylaşılan şey kaynak kod:** Kimse senin aboneliğini kullanmaz. Kodu indiren kişi kendi bilgisayarında kendi Claude Code kurulumuyla ya da kendi API anahtarıyla çalıştırır.
- **İki çalışma modu olacak:**
  1. `claude-code`: Kişisel kullanım, kişinin kendi Claude Code girişiyle.
  2. `api`: Anthropic API anahtarı ile. Uygulamaların resmî yolu bu, README'de başkaları için önerilen mod olarak anlatılır.
  3. `mock`: Hiçbir hesap gerektirmeden demo.
- **README'de açık not:** Bu projenin kişisel/eğitim amaçlı olduğu ve Claude Code modunu kullananların Anthropic kullanım şartlarına kendilerinin uyması gerektiği belirtilir.
- **Gizli bilgi sızmaması:** `.env`, `runs/` ve `workspace/` klasörleri `.gitignore`'a eklenir. Repoya hiçbir hesap bilgisi girmez.
- **Vitrin:** README'ye arayüzün ekran görüntüsü ve bir GIF eklenir, ajanların canlı konuştuğu görülür. Örnek bir çalıştırmanın çıktısı `examples/` klasöründe paylaşılır.

## 5.1 A2A'dan Uyarlananlar (Ek Maliyet Yok)

Google'ın **A2A (Agent-to-Agent)** protokolünün kavramları sisteme uyarlanır. Kaynak: Yusuf Baykaloğlu, *"Çoklu-Ajan Sistemleri: A2A Protokolü ile AI Agent Orkestrasyonu"* (Medium, Ocak 2026).

**Kural:** Uyarlanan hiçbir şey **ekstra LLM çağrısı yapmaz**. Hepsi Python kodu, veri yapısı ya da arayüz özelliğidir, Pro limitinden harcamaz.

### 1. Agent Card: her ajanın kimlik kartı
Her rol `agents/<rol>.json` dosyasında A2A Agent Card formatına yakın bir kartla tanımlanır. Promptlar, model, efor ve izinler koda gömülmez, buradan okunur.
```json
{
  "name": "developer",
  "displayName": "👨‍💻 Developer",
  "description": "Story'leri koda döker, geri bildirimleri düzeltir",
  "skills": ["implement_story", "fix_feedback"],
  "model": "sonnet",
  "effort": "medium",
  "allowedTools": ["Read", "Write", "Edit"],
  "color": "#4F8EF7"
}
```
- Yeni bir rol eklemek = yeni bir JSON dosyası eklemek. Orchestrator kartları başlangıçta okuyup bir **registry** oluşturur.
- Arayüzde ajanın ikonuna tıklayınca kartı görünür: kim olduğu, ne yapabildiği, hangi modeli kullandığı.

### 2. Task yaşam döngüsü: her işin durumu
Ajanlara verilen her iş bir **Task** nesnesidir ve A2A durumlarından geçer:
```
submitted → working → completed
                   ↘ input-required   (ajan bir soru sordu, M4'te kullanıcıya da sorulabilir)
                   ↘ rejected         (CTO/PO/Reviewer reddetti)
                   ↘ failed           (hata, zaman aşımı ya da Pro limiti doldu)
```
- Arayüzde her ajanın yanında canlı bir **durum rozeti** olur: 🟡 working, 🟢 completed, 🔴 rejected...
- `failed` durumundaki bir task, Pro limiti açıldığında **kaldığı yerden yeniden denenebilir**.
- Task'lar `runs/<tarih>/tasks.json` dosyasına yazılır. Süreç durup tekrar başlatılabilir.

### 3. Message ve Part: standart mesaj formatı
Ajanlar arası her mesaj A2A'daki gibi **parçalardan (Part)** oluşur:
| Part | Ne taşır | Örnek |
|---|---|---|
| `TextPart` | Kısa konuşma metni | "S1 bitti: todo.py'ye add/list eklendi." |
| `FilePart` | Yazılan ya da değiştirilen dosyaya referans | `src/todo.py` |
| `DataPart` | Yapılandırılmış JSON | `{"decision": "reject", "reason": "..."}` |

Arayüz her parçayı farklı çizer: metin balon olarak, dosya tıklanabilir bir rozet olarak, karar renkli bir etiket olarak.

### 4. Artifact: işin somut çıktıları
Her task'ın ürettiği dosyalar ve kararlar **Artifact** olarak kaydedilir (backlog.md, design.md, todo.py, test raporu...). Sağ paneldeki "Dosyalar" bölümü bu artifact listesinden beslenir: hangi dosyayı hangi ajanın, hangi sprintte ürettiği görünür.

### 5. Workflow desenleri: orchestrator'ın dili
Orchestrator, makaledeki dört desenin küçük ve deterministik Python karşılıklarıyla yazılır:
| Desen | Bizde kullanıldığı yer |
|---|---|
| `Sequential` | Kickoff → Backlog → Tasarım |
| `Parallel` | Reviewer ∥ QA |
| `Loop(max_iterations)` | Developer ⇄ QA düzeltme döngüsü |
| `Gate` (onay kapısı) | CTO / PO onayları, `rejected` olursa geri döner |

Böylece süreç kod okunurken bile anlaşılır olur:
```python
sprint = Sequential(
    Step("developer", "implement_story"),
    Parallel(Step("reviewer", "review"), Step("qa", "test")),
    Loop(Step("developer", "fix_feedback"), Parallel(...), max_iterations=2),
    Gate("po", "accept_sprint"),
)
```

### 6. Event Bus + geçmiş: tekrar oynatma (replay)
Makaledeki gibi her olay (task durumu, mesaj, araç çağrısı) Event Bus'a yayınlanır ve **olay geçmişi** `runs/<tarih>/events.jsonl` dosyasına yazılır.
- **Replay modu:** Eski bir çalıştırmanın konuşması, hiç LLM çağırmadan arayüzde baştan oynatılır.
- **GitHub demosu:** `examples/` klasöründeki örnek olay dosyası, projeyi indiren biri tarafından hesap gerektirmeden canlıymış gibi izlenebilir.
- Mock mod da bu altyapıyı kullanır.

### Alınmayanlar ve nedenleri
| A2A özelliği | Neden şimdilik yok |
|---|---|
| Her ajanın ayrı HTTP sunucusu (port 9001, 9002...) | Tek makinede, tek süreçte çalışıyoruz. Gereksiz karmaşıklık ve yavaşlık getirir |
| JSON-RPC, webhook, kimlik doğrulama şemaları | Ajanlar aynı süreçte. Bunlar ağ üzerinden konuşan servisler için |
| LLM tabanlı Coordinator (dinamik yönlendirme) | Her yönlendirme kararı bir LLM turu harcar. Bizde akışı kod belirliyor |

**M4 (opsiyonel):** Resmî `a2a-sdk` Python paketiyle her ajanın Agent Card'ını gerçek bir A2A endpoint'i olarak yayınlamak. Para gerektirmez, yalnızca ek geliştirme süresi gerektirir. GitHub'da "A2A uyumlu" rozeti için iyi bir ekstra.

## 5.2 Takım Şablonları

Sistem yazılıma özel değildir. Bir **takım şablonu**, bir dizi Agent Card ve bir workflow'dan oluşur. Arayüzde "Hangi ekip çalışsın?" seçimi yapılır.
```
templates/
├── software-team/    ← yazılım ekibi (Bölüm 3–4)
└── career-team/      ← kariyer ekibi (aşağıda)
```
> Öncelik sırası henüz belirlenmedi. MVP'de tek şablon yapılır, ama kod baştan şablon mantığıyla yazılır.

### Kariyer Ekibi: İş Başvurusu Hazırlama

**Amaç:** Kullanıcının CV'sini belirli bir iş ilanına göre uyarlamak, ön yazı hazırlamak ve mülakata hazırlamak. İş **aramaz**, başvuruya **hazırlar**.

#### Girdiler
| Girdi | Nasıl verilir |
|---|---|
| **İş ilanı** | (a) Metin olarak kopyala-yapıştır, ya da (b) **fotoğraf / ekran görüntüsü** (PNG, JPG). Uzun ilanlar için birden fazla görsel yüklenebilir. Ayrıca PDF de kabul edilir |
| **CV** | PDF, DOCX, Markdown ya da düz metin |

**Arayüz:** Sürükle-bırak alanı, panodan doğrudan yapıştırma (Ctrl/Cmd+V ile ekran görüntüsü) ve metin kutusu.

**Görsellerin okunması (ek maliyet yok):** Ayrı bir OCR kütüphanesi kullanılmaz. Görsel, çalıştırmanın `inputs/` klasörüne kaydedilir. İlan Analisti, Claude Code'un `Read` aracıyla görseli doğrudan okur, çünkü Claude görselleri anlayabiliyor. Ekran görüntüsündeki tablo ve madde düzenini klasik OCR'dan daha iyi korur.

**Okuma onayı (`input-required`):** Görselden çıkarılan ilan metni ve yapılandırılmış özet (pozisyon, şirket, zorunlu ve tercih edilen beceriler, seviye) önce **kullanıcıya gösterilir**. Kullanıcı "Doğru" der ya da düzeltir. Yanlış okunan bir ilan bütün süreci boşa çıkaracağı için süreç bu onaydan sonra devam eder.

#### Roller
| Ajan | Görev | Model |
|---|---|---|
| 🔎 **İlan Analisti** | Metni ya da görseli okur. Zorunlu ve tercih edilen becerileri, anahtar kelimeleri ve seviyeyi çıkarır → `docs/job.json` | Sonnet |
| ✍️ **CV Yazarı** | CV'yi ilana göre uyarlar: sıralama, vurgu, anahtar kelimeler → `output/cv.md` | Sonnet |
| 🛡️ **Doğrulayıcı** | Yeni CV'deki her iddianın orijinal CV'de karşılığı var mı diye bakar. Kaynaksız her şeyi işaretler | Sonnet |
| 👔 **İşe Alım Müdürü** | İşveren gözüyle 0–100 puan verir, en kritik 3 eksiği söyler | Haiku |
| 💌 **Mektup Yazarı** | Ön yazı hazırlar → `output/cover_letter.md` | Sonnet |
| 🎤 **Mülakatçı** | İlana ve CV'ye özel mülakat soruları ve cevap ipuçları hazırlar → `output/interview.md` | Haiku |

#### Akış
```
İlan (metin/görsel) + CV
   → İlan Analizi → [Kullanıcı onayı: ilan doğru okundu mu?]
   → CV Uyarlama ⇄ [Doğrulayıcı ∥ İşe Alım Müdürü]   (skor ≥ 80 ve uydurma yok; en fazla 3 tur)
   → Ön Yazı → Mülakat Hazırlığı
   → 📦 Başvuru paketi: cv.md · cover_letter.md · interview.md · rapor
```

#### Kurallar
- **Uydurma yasak:** Orijinal CV'de olmayan hiçbir deneyim, beceri, unvan ya da rakam eklenemez. Doğrulayıcı onaylamadan CV kabul edilmez.
- **Kodla ölçülen, bedava kontroller** (LLM kullanılmaz):
  - **ATS anahtar kelime skoru:** İlandaki anahtar kelimelerin CV'de geçme oranı, önce ve sonra
  - Uzunluk (1–2 sayfa) ve zorunlu bölümlerin varlığı
- **Otomatik ilan çekme yok:** LinkedIn ya da başka sitelerden scraping yapılmaz, bu kullanım şartlarına aykırıdır. İlanı kullanıcı verir.

#### Gizlilik
- `inputs/` (CV, ilan görselleri) ve `output/` klasörleri `.gitignore`'dadır. GitHub'a asla gitmez.
- GitHub'daki demo **sahte bir CV ve sahte bir ilan** ile hazırlanır.
- Not: Claude Code kullanıldığı için CV ve ilan içeriği, Claude'u normal kullanırken olduğu gibi Anthropic'e gönderilir.

#### Sonraki adım (M4)
🎤 **Canlı deneme mülakatı:** Mülakatçı soruları tek tek sorar, kullanıcı arayüzden cevaplar (`input-required`), sonunda geri bildirim verilir.

## 5.3 Hafıza ve Sürekli İyileştirme ("Hatırla → Geliştir")

> Esin kaynağı: [ECC](https://github.com/affaan-m/ECC) (MIT). ECC'nin `planla → test → uygula → incele → doğrula → hatırla → geliştir` döngüsündeki son iki adım sisteme uyarlanır. ECC'nin kendisi kurulmaz, sadece fikir alınır.

**Amaç:** Ekip her çalıştırmada aynı hataları tekrarlamasın. Retro'da çıkan dersler bir sonraki çalıştırmaya aktarılsın.

### Nasıl çalışır?
```
Çalıştırma → Retro → Ders adayları → [Kullanıcı onayı] → Hafıza
                                                          │
Sonraki çalıştırma ← ilgili rolün promptuna en fazla 5 ders eklenir
```

**1. Ders çıkarma (Retro adımında, ekstra LLM turu yok).** Retro zaten süreçte var. Retro çıktısı serbest metin yerine yapılandırılmış ders adaylarıyla genişletilir:
```json
{
  "role": "developer",
  "lesson": "CLI argümanlarında boş girdi kontrolü baştan yazılsın",
  "evidence": "Sprint 1'de QA 2 testi bu yüzden kaldı"
}
```
En fazla 3 ders adayı üretilir. Kanıtı olmayan ders kabul edilmez.

**2. Kullanıcı onayı (`input-required`).** Ders adayları arayüzde gösterilir. Kullanıcı her biri için **Kaydet / Düzenle / At** seçer. Hafızaya çöp birikmemesi için onaysız hiçbir ders kaydedilmez.

**3. Hafıza dosyası.** Dersler takım şablonu ve rol bazında saklanır:
```
memory/
├── software-team/lessons.jsonl
└── career-team/lessons.jsonl
```
Her dersin `created`, `used` (kaç kez prompta eklendi) ve `helped` (o çalıştırmada ilgili sorun tekrar etmediyse +1) sayaçları vardır.

**4. Derslerin kullanımı.** Bir ajan çağrılırken orchestrator, o role ait en faydalı **en fazla 5 dersi** (toplam ~200 token) sistem promptuna ekler:
```
GEÇMİŞ ÇALIŞTIRMALARDAN DERSLER
- CLI argümanlarında boş girdi kontrolü baştan yazılsın.
- ...
```
Arayüzde "Bu çalıştırmada kullanılan dersler" paneli gösterilir.

**5. Ders → içgüdü (instinct).** Aynı ders 3 farklı çalıştırmada faydalı olduysa, kalıcı bir kural olarak rolün Agent Card'ına taşınması **önerilir**. Kullanıcı onaylarsa kart güncellenir, ders hafızadan çıkar.

**6. Budama.** Rol başına en fazla 20 ders tutulur. 5 kez kullanılıp hiç işe yaramamış dersler otomatik olarak "pasif" işaretlenir. Kullanıcı hafızayı arayüzden görüp düzenleyebilir ya da tamamen silebilir.

### Örnekler
| Takım | Rol | Ders |
|---|---|---|
| Yazılım | Developer | "Dosya yollarını `pathlib` ile yaz, QA testleri Windows yolu yüzünden kaldı." |
| Yazılım | PO | "Kabul kriterlerine boş girdi senaryosunu her zaman ekle." |
| Kariyer | CV Yazarı | "Kullanıcı yazılım ilanlarına başvuruyor: GitHub linki iletişim bilgilerinin hemen altında olsun." |
| Kariyer | İşe Alım Müdürü | "Kullanıcının sektörü fintech, bu alandaki deneyimleri öne çıkmalı." |

### Maliyet
Ek LLM çağrısı yok. Retro zaten çalışıyor, sadece çıktısı yapılandırılıyor. Promptlara eklenen dersler ~200 token ile sınırlı.

### ECC'den alınan diğer fikirler
- **Temiz bağlamla inceleme:** Reviewer, Developer'ın oturumunu devam ettirmez (`--resume` kullanılmaz). Her incelemeye yeni bir oturumla başlar, kodu ilk kez görüyormuş gibi okur.
- **Doğrula adımı:** Sprint, PO kabulünden önce QA testlerinin son hâliyle bir kez daha çalıştırılmasıyla kapanır ("bende çalışıyordu" durumu olmasın).

## 6. Teknoloji Seçimleri

| Konu | Seçim |
|---|---|
| Platform | Web, yalnızca kişisel kullanım: `localhost` üzerinde çalışır, giriş/üyelik yok, yayına alma yok |
| Dil | Python 3.12+ |
| LLM | Claude Code CLI headless modu (`claude -p`), kullanıcının Pro aboneliğiyle |
| Varsayılan model | Sonnet (rol başına Opus seçilebilir) |
| Backend | FastAPI + Uvicorn |
| Canlı akış | Server-Sent Events (SSE) |
| Arayüz | Tek bir HTML/CSS/JS sayfası, build adımı yok |
| Test | `pytest` (hem üretilen proje hem sistemin kendisi için) |

## 7. Arayüz Taslağı

```
┌─────────────────────────────────────────────────────────────────┐
│ SprintSquad          [ Fikrini yaz...                ] [Başlat] │
├───────────────┬─────────────────────────────────┬───────────────┤
│ SÜREÇ         │ 👔 CTO → Ekip                    │ DOSYALAR      │
│ ✅ Kickoff     │ "MVP'de sadece ekleme ve        │ 📄 backlog.md │
│ ✅ Backlog     │  listeleme olsun."              │ 📄 design.md  │
│ ✅ Tasarım     │                                 │ 📁 src/       │
│ 🔄 Sprint 1    │ 👨‍💻 Developer → Reviewer         │   todo.py     │
│ ⏳ Sprint 2    │ "todo.py hazır, inceler misin?" │ 📁 tests/     │
│ ⏳ Retro       │   🛠 write_file(src/todo.py)    │               │
│ ⏳ Go/No-Go    │                                 │ TESTLER       │
│               │ 🔍 Reviewer → Developer          │ ✅ 4 geçti    │
│ Tur: 12       │ "Boş girdi kontrolü eksik."     │ ❌ 1 kaldı    │
└───────────────┴─────────────────────────────────┴───────────────┘
```
- Her ajanın kendi rengi ve ikonu olur.
- Mesajlar "kimden → kime" başlığıyla gösterilir.
- Araç çağrıları (dosya yazma, test çalıştırma) mesajın altında küçük satırlar olarak görünür.

## 8. Klasör Yapısı

```
sprintsquad/
├── PROJECT.md            ← bu doküman
├── README.md             ← kurulum ve çalıştırma
├── requirements.txt
├── agents/               ← her rolün Agent Card'ı (cto.json, developer.json...)
├── memory/               ← onaylanmış dersler (takım ve rol bazında), .gitignore'da
├── examples/             ← örnek çalıştırma (events.jsonl), replay demosu için
├── app/
│   ├── main.py           ← FastAPI + SSE endpoint'leri
│   ├── orchestrator.py   ← süreç akışı, onay kapıları, tur sınırları
│   ├── workflow.py       ← Sequential, Parallel, Loop, Gate desenleri
│   ├── tasks.py          ← Task, Message, Part, Artifact modelleri ve durumları
│   ├── registry.py       ← Agent Card'ları okuyan registry
│   ├── agents.py         ← Agent sınıfı ve `claude -p` çağrısı
│   ├── roles.py          ← 7 rolün sistem promptları, modelleri, izinleri
│   ├── mock.py           ← Pro limitini harcamadan test için sahte ajanlar
│   └── events.py         ← Event Bus
├── static/
│   └── index.html        ← canlı konuşma arayüzü
├── runs/                 ← her çalıştırmanın kaydı ve üretilen proje
└── tests/                ← sistemin kendi testleri
```

## 9. Güvenlik ve Maliyet

- **Ekstra maliyet yok:** Kullanıcının mevcut Pro aboneliği kullanılır.
- Her `claude -p` çağrısı o çalıştırmanın `workspace/` klasöründe başlatılır. Ajanlara yalnızca rolünün gerektirdiği araçlara izin verilir.
- Shell erişimi yalnızca QA'da ve yalnızca `pytest` ile sınırlıdır. Keyfî komut çalıştırılmaz. Her çağrının zaman aşımı vardır.
- Toplam tur sayısında üst sınır olur (~30 ajan turu).
- **Global eklenti izolasyonu:** Kullanıcının Claude Code'a global olarak kurduğu plugin, hook ve skill'ler (ör. ECC) ajan çağrılarına yüklenmez (`--setting-sources ""`, `--strict-mcp-config`). Bu izolasyon M1'de test edilir. Aksi hâlde ajanlar yavaşlar, bağlam şişer ve Pro limiti hızlı tükenir.
- **Mock mod:** Arayüz ve süreç geliştirilirken gerçek ajan yerine sahte ajanlar çalışır. Pro limitinden hiç harcanmaz.

## 10. Yol Haritası

| Aşama | İçerik | Bitti sayılması için |
|---|---|---|
| **M1: Çekirdek** | Agent sınıfı (`claude -p`), roller, mock mod, terminalde çalışan orchestrator | Mock modda süreç uçtan uca akıyor. Gerçek modda `python -m app.cli "fikir"` workspace'e çalışan kod üretiyor |
| **M2: Canlı arayüz** | FastAPI, SSE, sohbet arayüzü | Tarayıcıda konuşmalar canlı akıyor |
| **M3: Agile detayları** | Onay kapıları, sprintler, retro, dosya paneli, limit dolunca duraklat/devam et, **hafıza ve ders sistemi (5.3)** | Tam süreç uçtan uca, sınırlar içinde tamamlanıyor. İkinci çalıştırmada önceki dersler kullanılıyor |
| **M4: İyileştirmeler** | Kullanıcının araya girmesi (`input-required`), replay ile geçmiş çalıştırmaları izleme, "Takım vs Tek Ajan" karşılaştırması, opsiyonel A2A endpoint'leri | Kullanıcı süreç ortasında yorum ekleyebiliyor, eski çalıştırmalar oynatılabiliyor |

## 11. Açık Sorular

1. Projenin adı "SprintSquad" mı olsun, başka bir isim mi?
2. Ajanlar birbirleriyle **Türkçe** mi konuşsun, İngilizce mi? (Kod ve yorumlar İngilizce kalabilir.)
3. Kullanıcı süreç ortasında araya girebilsin mi, yoksa bu M4'e mi kalsın?
4. ~~Claude API erişimi~~ → **Karar verildi:** API yerine Claude Code headless modu ve Pro aboneliği kullanılacak.
5. ~~Proje boyutu~~ → **Karar verildi:** Küçük projeler (en fazla 2 sprint, 4 story, ~30 tur).
