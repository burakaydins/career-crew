"""Scripted provider for demos, development and tests. No account needed.

The script is written for examples/cv.md and examples/ilan.md. Round 1 of the
CV loop contains deliberate fabrications so the checks and the verifier have
something to catch; round 2 fixes them.
"""

from __future__ import annotations

import time

from app.providers.base import AgentRequest, AgentResult

JOB = {
    "title": "Backend Developer (Python)",
    "company": "Hayali Teknoloji",
    "level": "mid",
    "location": "İstanbul, hibrit",
    "required_skills": ["Python", "Django", "PostgreSQL", "REST API", "Docker"],
    "preferred_skills": ["Kubernetes", "AWS", "Redis", "CI/CD"],
    "keywords": ["mikroservis", "test otomasyonu", "kod incelemesi", "SQL"],
    "summary": "Ödeme altyapısı için Python/Django backend geliştirici.",
}

_HEADER = """# Deniz Yılmaz

İstanbul · deniz.yilmaz@example.com · github.com/deniz-ornek
"""

CV_ROUND_1 = _HEADER + """
## Özet

5 yıllık deneyime sahip, Python, Django ve Docker ile ölçeklenebilir backend servisleri geliştiren yazılım geliştiriciyim.

## Deneyim

### Yazılım Geliştirici, Örnek Lojistik A.Ş. (2022 - Günümüz)

- Django ile şirket içi sipariş takip uygulamasını geliştirdim.
- PostgreSQL sorgu optimizasyonunu yönettim, sorgu sürelerini %40 azalttım.
- REST API uç noktaları yazdım ve belgelendirdim.
- Python scriptleri ile haftalık raporları otomatikleştirdim.

### Stajyer Geliştirici, Deneme Yazılım Ltd. (2021 - 2022)

- Birim testleri yazarak test kapsamını artırdım.
- Flask ile küçük bir envanter uygulamasının bakımına katkı verdim.

## Beceriler

Python, Django, PostgreSQL, REST API, Docker, pytest, Git, Linux, Flask

## Eğitim

Bilgisayar Mühendisliği, Örnek Üniversitesi (2017 - 2021)

## Projeler

- Kişisel bütçe takip uygulaması (Django, Chart.js). GitHub'da açık kaynak.
"""

CV_ROUND_2 = _HEADER + """
## Özet

3 yıllık deneyime sahip yazılım geliştiriciyim. Python ve Django ile web uygulamaları, REST API'ler ve PostgreSQL tabanlı backend işleri geliştiriyorum.

## Deneyim

### Yazılım Geliştirici, Örnek Lojistik A.Ş. (2022 - Günümüz)

- Django ile şirket içi sipariş takip uygulamasını geliştirdim.
- REST API uç noktaları yazdım ve belgelendirdim.
- PostgreSQL veritabanında SQL sorgu optimizasyonu çalışmalarında yer aldım.
- Python scriptleri ile haftalık raporları otomatikleştirdim.

### Stajyer Geliştirici, Deneme Yazılım Ltd. (2021 - 2022)

- Birim testleri (pytest) yazarak test kapsamını artırdım.
- Flask ile küçük bir envanter uygulamasının bakımına katkı verdim.

## Beceriler

Python, Django, PostgreSQL, REST API, pytest, Git, Linux, Flask

## Eğitim

Bilgisayar Mühendisliği, Örnek Üniversitesi (2017 - 2021)

## Projeler

- Kişisel bütçe takip uygulaması (Django, Chart.js). GitHub'da açık kaynak.
"""

_SHARED_CLAIMS = [
    {"claim": "Django ile şirket içi sipariş takip uygulamasını geliştirdim.",
     "evidence": "Django ile şirket içi sipariş takip uygulamasını geliştirdim."},
    {"claim": "REST API uç noktaları yazdım ve belgelendirdim.",
     "evidence": "REST API uç noktaları yazdım ve belgelendirdim."},
    {"claim": "Python scriptleri ile haftalık raporları otomatikleştirdim.",
     "evidence": "Python scriptleri ile haftalık raporları otomatikleştirdim."},
    {"claim": "Flask ile küçük bir envanter uygulamasının bakımına katkı verdim.",
     "evidence": "Flask ile küçük bir envanter uygulamasının bakımına katkı verdim."},
    {"claim": "Kişisel bütçe takip uygulaması (Django, Chart.js). GitHub'da açık kaynak.",
     "evidence": "Kişisel bütçe takip uygulaması (Django, Chart.js). GitHub'da açık kaynak."},
]

CLAIMS_ROUND_1 = _SHARED_CLAIMS + [
    {"claim": "PostgreSQL sorgu optimizasyonunu yönettim, sorgu sürelerini %40 azalttım.",
     "evidence": "PostgreSQL sorgu optimizasyonunu yönettim."},
    {"claim": "Docker ile ölçeklenebilir backend servisleri geliştiriyorum.",
     "evidence": "Docker ile servisleri paketledim."},
    {"claim": "Birim testleri yazarak test kapsamını artırdım.",
     "evidence": "Birim testleri yazarak test kapsamını artırdım."},
]

CLAIMS_ROUND_2 = _SHARED_CLAIMS + [
    {"claim": "PostgreSQL veritabanında SQL sorgu optimizasyonu çalışmalarında yer aldım.",
     "evidence": "PostgreSQL veritabanında sorgu optimizasyonu çalışmalarında yer aldım."},
    {"claim": "Birim testleri (pytest) yazarak test kapsamını artırdım.",
     "evidence": "Birim testleri yazarak test kapsamını artırdım."},
    {"claim": "Python ve Django ile web uygulamaları geliştiriyorum.",
     "evidence": "Python ve Django ile web uygulamaları geliştiriyorum."},
]

LETTER = """Sayın Hayali Teknoloji İşe Alım Ekibi,

Backend Developer (Python) pozisyonu için başvuruyorum. Örnek Lojistik A.Ş.'de Django ile şirket içi sipariş takip uygulamasını geliştirdim ve bu uygulamanın REST API uç noktalarını yazıp belgelendirdim.

İlanda öne çıkan PostgreSQL ve sorgu optimizasyonu konusunda, veritabanındaki optimizasyon çalışmalarında yer aldım. Python scriptleri ile haftalık raporları otomatikleştirerek tekrar eden işleri azalttım. Stajım sırasında birim testleri yazarak test kapsamını artırdım; bu deneyim, ilandaki test otomasyonu sorumluluğuyla doğrudan ilgili.

Docker ve Kubernetes ile henüz profesyonel bir deneyimim yok. Ödeme altyapısı gibi güvenilirlik gerektiren bir alanda bu araçları ekibinizle birlikte öğrenmek istiyorum.

Görüşme fırsatı için teşekkür ederim.

Deniz Yılmaz
"""

INTERVIEW = """# Mülakat Hazırlığı: Backend Developer (Python)

## 1. Django'da N+1 sorgu sorununu nasıl çözersiniz?
- **Neden:** İlan PostgreSQL ve sorgu optimizasyonu istiyor.
- **İpucu:** Örnek Lojistik'teki sorgu optimizasyonu çalışmasını anlat. `select_related` ve `prefetch_related` örneği ver.

## 2. Yazdığınız REST API'leri nasıl belgelendirdiniz?
- **Neden:** CV'de "belgelendirdim" ifadesi var.
- **İpucu:** Kullandığın aracı ve belgelerin kimin işine yaradığını somut anlat.

## 3. Raporlama otomasyonu ne kadar zaman kazandırdı?
- **Neden:** Ölçülebilir sonuç merak edilecek.
- **İpucu:** CV'de rakam yok. Uydurma, gerçekten hatırladığın bir tahmini "yaklaşık" diye söyle.

## 4. Docker ile deneyiminiz var mı?
- **Neden:** İlanda zorunlu, CV'de yok.
- **Dürüst cevap:** Profesyonel deneyimin olmadığını söyle. Bütçe uygulamanı Docker ile paketleme planını anlat.

## 5. Mikroservis mimarisi hakkında ne biliyorsunuz?
- **Neden:** Sorumluluklarda geçiyor.
- **İpucu:** Monolit Django deneyiminden yola çıkarak servis sınırlarının nasıl çizileceğini anlat.

## 6. Test kapsamını nasıl artırdınız?
- **Neden:** İlanda test otomasyonu var.
- **İpucu:** Stajdaki pytest deneyimini, hangi modülleri test ettiğini anlat.

## 7. Bir kod incelemesinde neye dikkat edersiniz?
- **Neden:** Sorumluluklarda geçiyor.
- **İpucu:** Okunabilirlik, test ve güvenlik başlıklarıyla cevap ver.

## 8. Ödeme sistemlerinde veri tutarlılığını nasıl sağlarsınız?
- **Neden:** Şirketin alanı ödeme altyapısı.
- **İpucu:** Veritabanı transaction'ları ve idempotent API tasarımından bahset.
"""

SCRIPT: dict[str, list[dict]] = {
    "analyze_job": [{
        "message": "İlan okundu → work/job.json. Zorunlu 5 beceri, tercih edilen 4 beceri çıkarıldı.",
        "data": JOB,
    }],
    "tailor_cv": [
        {"message": "CV uyarlandı → output/cv.md. Backend becerileri özete ve beceri listesinin başına alındı.",
         "data": {"claims": CLAIMS_ROUND_1}, "files": {"cv.md": CV_ROUND_1}},
        {"message": "Düzeltildi. Docker, %40 ve 'yönettim' çıkarıldı, özet orijinal 3 yıla döndü. SQL, orijinal optimizasyon maddesinden öne çıkarıldı.",
         "data": {"claims": CLAIMS_ROUND_2}, "files": {"cv.md": CV_ROUND_2}},
    ],
    "verify": [
        {"message": "Ret: Docker, %40 ve 5 yıl uydurma. 'Yer aldım' ifadesi 'yönettim' yapılmış.",
         "data": {"decision": "reject", "reason": "Kod kontrollerinde açık uydurma var.",
                  "issues": ["Docker orijinal CV'de yok, çıkarılsın.",
                             "%40 rakamı orijinal CV'de yok, çıkarılsın.",
                             "Özetteki 5 yıl, orijinaldeki 3 yıla dönsün.",
                             "'Optimizasyonunu yönettim' → 'çalışmalarında yer aldım' olsun."]}},
        {"message": "Onay.", "data": {"decision": "approve", "reason": "Tüm maddeler kanıta dayanıyor.", "issues": []}},
    ],
    "score": [
        {"message": "Puan 72. Uydurmalar mülakatta ortaya çıkar, SQL görünmüyor, test deneyimi zayıf anlatılmış.",
         "data": {"score": 72, "missing": ["SQL deneyimi görünmüyor", "Test deneyimi zayıf anlatılmış", "Docker gerçek eksik"]}},
        {"message": "Puan 84. Docker ve Kubernetes gerçek eksik, ölçülebilir sonuç yok.",
         "data": {"score": 84, "missing": ["Docker yok (gerçek eksik)", "Ölçülebilir sonuç yok", "Mikroservis deneyimi görünmüyor"]}},
    ],
    "write_letter": [{
        "message": "Ön yazı hazır → output/cover_letter.md. Docker eksiği açıkça yazıldı.",
        "files": {"cover_letter.md": LETTER},
    }],
    "prepare_interview": [{
        "message": "8 soru hazır → output/interview.md. Docker için dürüst cevap önerildi.",
        "files": {"interview.md": INTERVIEW},
    }],
}


class MockProvider:
    name = "mock"

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay

    def run(self, request: AgentRequest) -> AgentResult:
        if self.delay:
            time.sleep(self.delay)
        turns = SCRIPT[request.skill]
        turn = turns[min(request.iteration, len(turns)) - 1]
        return AgentResult(
            message=turn["message"],
            data=turn.get("data", {}),
            files=turn.get("files", {}),
            usage={"mock": True},
        )
