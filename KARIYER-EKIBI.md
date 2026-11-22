# Kariyer Ekibi: Çok Ajanlı İş Başvurusu Asistanı

> Repo adı: **`career-crew`**.
> Bu doküman career-crew'un tasarım notlarıdır: kariyer ekibine odaklanan ve onaylanan kararlar.

---

## 1. Amaç

Kullanıcı bir **iş ilanı** ve kendi **CV'sini** verir. Altı uzman yapay zekâ ajanı kendi aralarında konuşarak şunları hazırlar:

- 📄 İlana göre uyarlanmış bir CV
- 💌 Ön yazı (cover letter)
- 🎤 İlana ve CV'ye özel mülakat hazırlığı
- 📊 Bir rapor: işveren puanı, ATS skoru (önce/sonra), yapılan değişiklikler

**Temel ilkeler:**
1. **Ajanların konuşması canlı izlenir.** Kullanıcı sadece sonucu değil, kim neyi neden değiştirdi, onu da görür.
2. **Uydurma yasak.** CV'de olmayan hiçbir deneyim, beceri, unvan ya da rakam eklenemez. Bu kural hem bir ajanla hem de kodla denetlenir.
3. **Kullanıcının verisi kullanıcıda kalır.** CV'ler ve ilanlar repoya hiç girmez.

**Kapsam dışı:** İş aramak, ilan çekmek (scraping), başvuruyu otomatik göndermek.

---

## 2. Kimler, Nasıl Kullanır?

İlk kullanıcı projenin sahibidir. Proje GitHub'da **MIT lisansıyla** paylaşılır, isteyen herkes kendi bilgisayarında kullanabilir.

| Mod | Kim için | Nasıl çalışır | Maliyet |
|---|---|---|---|
| `api` | **Başkaları için önerilen resmî yol** | Kendi Anthropic API anahtarıyla, Anthropic Python SDK üzerinden | Kullanan kişinin API kullanımı |
| `claude-code` | Kendi Claude Pro/Max aboneliğiyle **kişisel kullanım** | Makinede kurulu Claude Code'un headless modu (`claude -p`) | Ek ücret yok, abonelik limitine tabi |
| `mock` | Hesabı olmadan denemek isteyenler, demo, geliştirme | Önceden hazırlanmış örnek konuşmalar | Ücretsiz |

> **Kullanım şartları notu (README'de yer alacak):** `claude-code` modu, herkesin **kendi** aboneliğiyle **kendi** bilgisayarında kişisel kullanımı içindir. Proje bir hizmet olarak sunulmaz. Claude Code giriş bilgileri asla okunmaz ya da başka bir yere taşınmaz, yalnızca resmî `claude` komutu kullanılır. Bu modu kullananlar Anthropic kullanım şartlarına kendileri uymakla yükümlüdür.

---

## 3. Ajan Ekibi

| Ajan | Görev | Çıktı | Model* | Araçlar (`claude-code` modu) |
|---|---|---|---|---|
| 🔎 **İlan Analisti** | İlandan pozisyon, şirket, zorunlu ve tercih edilen becerileri, anahtar kelimeleri ve seviyeyi çıkarır | `work/job.json` | Sonnet | `Read` |
| ✍️ **CV Yazarı** | CV'yi ilana göre uyarlar: sıralama, vurgu, anahtar kelimeler. Her maddeyi orijinal CV'den bir **kanıt alıntısına** bağlar | `output/cv.md` + `work/claims.json` | Sonnet | `Read`, `Write` |
| 🛡️ **Doğrulayıcı** | Kodla yapılan kontrollerin sonuçlarını yorumlar. Anlam değiştiren abartıları yakalar | `{decision, reason, issues[]}` | Sonnet | `Read` |
| 👔 **İşe Alım Müdürü** | İşveren gözüyle 0–100 puan verir, en kritik 3 eksiği söyler | `{score, missing[3]}` | Haiku | `Read` |
| 💌 **Mektup Yazarı** | Uyarlanmış CV ve ilana göre ön yazı hazırlar | `output/cover_letter.md` | Sonnet | `Read`, `Write` |
| 🎤 **Mülakatçı** | İlana ve CV'ye özel mülakat soruları ve cevap ipuçları hazırlar | `output/interview.md` | Haiku | `Read`, `Write` |

\* Varsayılanlar. Her rolün modeli, kendi Agent Card dosyasından değiştirilebilir.

> **Uygulama notu (M1):** Araçlar sütunu uygulanmadı. Girdiler (ilan, CV, önceki sürüm) prompta doğrudan eklenir. Ajanlar `{"message", "data", "files"}` biçiminde tek bir JSON döndürür. Dosyaları orchestrator yazar. Bu yüzden `claude-code` modunda ajanlara hiç araç verilmez (`--tools ""`), `allowedTools` boş listedir. Üç mod aynı biçimi kullanır.

### Agent Card örneği (`app/agents/cv_writer.json`)
```json
{
  "name": "cv_writer",
  "displayName": "✍️ CV Yazarı",
  "description": "CV'yi ilana göre uyarlar, her maddeyi kanıta bağlar",
  "skills": ["tailor_cv", "fix_feedback"],
  "model": "sonnet",
  "effort": "medium",
  "allowedTools": ["Read", "Write"],
  "color": "#4F8EF7",
  "promptFile": "prompts/tr/cv_writer.md"
}
```

---

## 4. Akış

```
İlan + CV
   │
   ▼
[1] İLAN ANALİZİ        🔎 İlan Analisti → job.json
   │
   ▼
[2] OKUMA ONAYI         🙋 Kullanıcı: "İlan doğru okundu mu?"   (input-required)
   │
   ▼
[3] CV UYARLAMA DÖNGÜSÜ (en fazla 3 tur)
   │   ├─ ✍️ CV Yazarı              → cv.md + claims.json
   │   ├─ 🧮 Kod kontrolleri         (Bölüm 6, LLM'siz)
   │   ├─ PARALEL:
   │   │     🛡️ Doğrulayıcı         → onay / ret
   │   │     👔 İşe Alım Müdürü      → puan + eksikler
   │   └─ Çıkış koşulu: uydurma yok VE puan ≥ 80
   │      (3 turda sağlanamazsa en iyi sürüm + uyarı ile devam)
   │      Erken çıkış: üst üste iki temiz turda puan artmazsa durulur
   │      (kalan eksikler gerçek, yeni tur sadece token harcar)
   │
   ▼
[4] ÖN YAZI             💌 Mektup Yazarı
   │
   ▼
[5] MÜLAKAT HAZIRLIĞI   🎤 Mülakatçı
   │
   ▼
[6] RAPOR               🧾 (kod) özet, skorlar, değişiklik listesi
   │
   ▼
📦 output/: cv.md · cover_letter.md · interview.md · report.md
```

**Workflow kodu (taslak):**
```python
career_flow = Sequential(
    Step("job_analyst", "analyze_job"),
    UserGate("confirm_job"),
    Loop(
        Step("cv_writer", "tailor_cv"),
        CodeChecks("evidence", "dates", "leakage", "ats"),
        Parallel(Step("verifier", "verify"), Step("recruiter", "score")),
        until=lambda s: s.no_fabrication and s.score >= 80,
        max_iterations=3,
    ),
    Step("letter_writer", "write_letter"),
    Step("interviewer", "prepare_interview"),
    Report(),
)
```

---

## 5. Konuşma Sözleşmesi

Her ajanın sistem promptunda bulunur:

```
KONUŞMA KURALLARI
- En fazla 3 cümle. CV, mektup ve listeler mesaja değil dosyaya yazılır.
- Selamlama, övgü, teşekkür, motivasyon cümlesi YOK.
- Önce karar, sonra tek cümlelik gerekçe.
- Dosyada yazanı tekrar etme, dosya adını ver.
- Sorun yoksa sadece "Onay." de.
```

**Örnek konuşma:**
> ✍️ **CV Yazarı:** "CV uyarlandı → output/cv.md. 'Deneyim' bölümünde Python projeleri öne alındı."
> 🧮 **Kod kontrolü:** "2 sorun: 'Kubernetes' ilanda var ama orijinal CV'de yok (sızıntı). 3. madde için kanıt alıntısı bulunamadı."
> 🛡️ **Doğrulayıcı:** "Ret: 2 uydurma. Kubernetes çıkarılsın, 3. madde orijinal ifadeye dönsün."
> 👔 **İşe Alım Müdürü:** "Puan 72. Eksikler: ölçülebilir sonuç yok, SQL görünmüyor, özet çok genel."
> ✍️ **CV Yazarı:** "Düzeltildi. SQL, orijinal CV'deki 'veri raporlama' maddesinden öne çıkarıldı."

---

## 6. Doğrulama: Uydurmaya Karşı Katmanlar

Araştırmalar, önlem alınmadığında yapay zekânın CV yeniden yazarken uydurma eklediğini ve bunun en çok **deneyim** bölümünde olduğunu gösteriyor (bkz. Kaynaklar). Bu yüzden doğrulama üç katmanlıdır:

### Katman 1: Kanıt alıntısı (kod)
CV Yazarı her madde için `claims.json` üretir:
```json
{ "claim": "Python ile veri raporlama otomasyonu geliştirdim",
  "evidence": "Python scriptleri ile haftalık raporları otomatikleştirdim" }
```
Kod, `evidence` metninin orijinal CV'de **gerçekten geçip geçmediğini** kontrol eder (normalize edilmiş, bulanık eşleşme). Kanıtı bulunamayan madde işaretlenir.

### Katman 2: Deterministik kontroller (kod)
| Kontrol | Ne yakalar |
|---|---|
| **İlan kelimesi sızıntısı** | İlanda geçen ama orijinal CV'de hiç geçmeyen teknoloji ve becerilerin yeni CV'ye girmesi |
| **Tarih tutarlılığı** | "5 yıl deneyim" gibi iddiaların CV'deki tarihlerle uyuşmaması, değişen tarihler |
| **Rakam kontrolü** | Orijinal CV'de olmayan yeni sayılar ve yüzdeler ("%40 artış") |
| **Unvan kontrolü** | Unvanların değiştirilmesi ("Junior Developer" → "Senior Developer") |
| **ATS skoru** | İlandaki anahtar kelimelerin CV'de geçme oranı, önce ve sonra |
| **Yapı** | Uzunluk (1–2 sayfa), zorunlu bölümlerin varlığı |

### Katman 3: Doğrulayıcı ajan (LLM)
Kod kontrollerinin sonuçlarını alır, kodun yakalayamayacağı **anlam değiştiren abartıları** değerlendirir ("projede yer aldım" → "projeyi yönettim").

**Kural:** Katman 1 ya da 2'de açık bir sorun varken Doğrulayıcı onay veremez.

---

## 7. Girdiler ve Çıktılar

| | M1 | Sonra |
|---|---|---|
| **İlan** | Metin dosyası (`.txt`, `.md`) ya da yapıştırma | M2: PDF, fotoğraf/ekran görüntüsü (Claude görseli kendisi okur) |
| **CV** | Markdown ya da düz metin | M2: PDF, DOCX |
| **Çıktı** | Markdown dosyaları | M3: PDF dışa aktarma |

**Çalıştırma klasörü:**
```
runs/2026-11-21_1430_backend-developer/
├── inputs/      ← ilan ve CV kopyası
├── work/        ← job.json, claims.json, ara sürümler
├── output/      ← cv.md, cover_letter.md, interview.md, report.md
└── events.jsonl ← tüm konuşma (replay için)
```

---

## 8. Mimari

```
CLI (M1)  /  Web arayüzü (M2)
        │  Event Bus (canlı olaylar)
        ▼
Orchestrator ── workflow: Sequential · Parallel · Loop · Gate · UserGate
        │
        ├── Registry ← app/agents/*.json (Agent Card'lar)
        ├── Kod kontrolleri (checks/)
        └── Provider
              ├── MockProvider        (örnek konuşmalar)
              ├── ClaudeCodeProvider  (claude -p, stream-json)
              └── ApiProvider         (Anthropic Python SDK)
```

**A2A'dan uyarlanan kavramlar:** Agent Card, Task durumları (`submitted → working → completed / rejected / failed / input-required`), Message ve Part (`TextPart`, `FilePart`, `DataPart`), Artifact.

### Klasör yapısı
```
career-crew/
├── README.md
├── LICENSE                 ← MIT
├── pyproject.toml
├── .gitignore              ← runs/, memory/, .env, kişisel dosyalar
├── app/agents/                 ← 6 Agent Card
├── app/prompts/tr/            ← Türkçe rol promptları (M2: prompts/en/)
├── app/
│   ├── cli.py              ← terminal arayüzü
│   ├── orchestrator.py
│   ├── workflow.py         ← Sequential, Parallel, Loop, Gate, UserGate
│   ├── tasks.py            ← Task, Message, Part, Artifact
│   ├── events.py           ← Event Bus
│   ├── registry.py
│   ├── providers/
│   │   ├── mock.py
│   │   ├── claude_code.py
│   │   └── api.py
│   └── checks/
│       ├── evidence.py     ← kanıt alıntısı
│       ├── leakage.py      ← ilan kelimesi sızıntısı
│       ├── dates.py
│       ├── numbers.py
│       └── ats.py
├── examples/               ← SAHTE CV ve ilan, örnek events.jsonl
└── tests/
```

---

## 9. Arayüz

**M1: Terminal**
```bash
career-crew --ilan examples/ilan.md --cv examples/cv.md --mod mock
```
Ajanların mesajları renkli ve canlı akar. Her ajanın kendi rengi ve ikonu vardır. İlan okuma onayı terminalden sorulur.

**M2: Web (localhost)**
Solda süreç adımları ve durum rozetleri, ortada canlı konuşma, sağda dosyalar, skorlar ve "önce/sonra" karşılaştırması. Sürükle-bırak ile ilan (metin/PDF/fotoğraf) ve CV yükleme.

---

## 10. Hafıza (M3)

Her çalıştırmanın sonunda en fazla 3 ders adayı çıkarılır, kullanıcı onaylarsa kaydedilir ve sonraki çalıştırmada ilgili ajanın promptuna eklenir. Örnek:
> **CV Yazarı:** "Kullanıcı yazılım ilanlarına başvuruyor: GitHub linki iletişim bilgilerinin hemen altında olsun."


---

## 11. Gizlilik ve Güvenlik

- `runs/`, `memory/`, `.env` ve kullanıcı dosyaları `.gitignore`'dadır. Repoda yalnızca **sahte** örnek CV ve ilan bulunur.
- Hiçbir veri, seçilen LLM sağlayıcısı dışında bir yere gönderilmez. Analitik ya da izleme yok.
- `claude-code` modunda ajanlar yalnızca o çalıştırmanın klasöründe çalışır ve sadece rolünün gerektirdiği araçlara erişir. Shell erişimi yoktur.
- Kullanıcının global Claude Code eklentileri ve hook'ları (ör. ECC) ajan çağrılarına yüklenmez (`--setting-sources ""`, `--strict-mcp-config`). Bu izolasyon M1'de test edilir.
- `api` modunda API anahtarı ortam değişkeninden ya da `.env` dosyasından okunur, koda ya da loglara yazılmaz.
- README'de: "Yapay zekâ çıktıları hatalı olabilir. Başvurmadan önce her şeyi kendiniz kontrol edin."

---

## 12. Token ve Limit Stratejisi

- Bir çalıştırma tahminen **8–12 ajan turu** ve **~80–150 bin token**. Yazılım ekibinden 5–10 kat daha hafif.
- Hafif roller (İşe Alım Müdürü, Mülakatçı) Haiku ile çalışır, efor düşüktür.
- Kısa sistem promptu (`--system-prompt`) ve sadece gereken araçlar.
- CV döngüsü en fazla 3 tur.
- Limit dolarsa süreç durur, durumu kaydeder ve kaldığı yerden devam edebilir (M3).

---

## 13. Yol Haritası

### M1: Çekirdek + terminal ✅ *onaylandı*
1. Kalıcı klasör, `git init`, `.gitignore`, MIT lisansı
2. Python proje iskeleti (`pyproject.toml`, `app/`)
3. 6 Agent Card + Türkçe promptlar + konuşma sözleşmesi
4. Çekirdek: Task, Message, Part, Event Bus, workflow yapıları
5. Provider'lar: `mock` → `claude-code` → `api`
6. Kod kontrolleri: kanıt alıntısı, sızıntı, tarih, rakam, unvan, ATS
7. Terminal arayüzü (`career-crew` komutu), canlı renkli akış
8. Testler (pytest) + sahte örnek CV ve ilan
9. README ilk sürüm

**Bitti sayılması için:** `mock` modunda süreç uçtan uca çalışıyor, `claude-code` modunda sahte CV ile gerçek bir başvuru paketi üretiliyor, testler geçiyor.

### M2: Web arayüzü ✅
FastAPI + SSE, canlı konuşma ekranı, dosya yükleme (PDF/fotoğraf), önce/sonra karşılaştırması, İngilizce prompt seçeneği.

### M3: Hafıza ve dayanıklılık ✅
Ders sistemi, limit dolunca duraklat/devam et, PDF çıktı.

### M4: Vitrin ✅
Replay modu (`career-crew replay`, web geçmiş listesi), canlı deneme mülakatı (`career-crew mulakat`, web sohbet sayfası, `ask_question` ve `evaluate_answer` skill'leri), web arayüzü GIF'i (başsız Chrome ile), yayın öncesi kontroller (agents/prompts paketin içine alındı).

### GitHub'a yükleme
M1 bittikten sonra, **kullanıcının onayıyla**.

---

## 14. Esinlenmeler ve Kaynaklar

| Kaynak | Ne alındı |
|---|---|
| [DeepLearning.AI – Multi AI Agent Systems with crewAI](https://learn.deeplearning.ai/courses/multi-ai-agent-systems-with-crewai/lesson/a8ecj/build-a-crew-to-tailor-job-applications) | İş başvurusu ekibi rolleri (araştırmacı, profil, CV stratejisti, mülakat) |
| [Grounded Optimization, arXiv 2607.01457](https://arxiv.org/abs/2607.01457) | Uydurmanın deneyim bölümünde yoğunlaşması, tarih kontrolü, deterministik sızıntı tespiti |
| [Hirepanel](https://github.com/punit2911/Hirepanel) | "Her iddia doğrulanmış bir alıntıya dayanmalı" ilkesi |
| Yusuf Baykaloğlu, *Çoklu-Ajan Sistemleri: A2A Protokolü ile AI Agent Orkestrasyonu* (Medium, Ocak 2026) | Agent Card, Task durumları, Message/Part, workflow desenleri, Event Bus + SSE |
| [ECC](https://github.com/affaan-m/ECC) | Hatırla → geliştir döngüsü, temiz bağlamla inceleme |

---

## 15. Açık Kararlar

1. ~~Repo ve klasör adı~~ → **`career-crew`**
2. ~~Kalıcı klasör konumu~~ → repo kökü
3. ~~Ajanların dili~~ → Varsayılan **Türkçe**, İngilizce seçeneği M2'de.
