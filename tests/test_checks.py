import datetime as dt

from app.checks import ats, dates, evidence, leakage, numbers, run_all, structure, titles
from app.checks.text import contains_term, normalize
from app.providers import mock

JOB = mock.JOB


def test_normalize_folds_turkish_and_case():
    assert normalize("İSTANBUL Işık ÇAĞ") == "istanbul isik cag"
    assert normalize("CI/CD, C++ ve C#") == "ci cd c++ ve c#"


def test_contains_term_is_whole_word():
    assert contains_term("PostgreSQL, Git", "git")
    assert not contains_term("PostgreSQL", "SQL")
    assert contains_term("REST API'ler yazdım", "REST API")


def test_evidence_exact_and_fuzzy(example_cv):
    claims = [
        {"claim": "x", "evidence": "Python scriptleri ile haftalık raporları otomatikleştirdim"},
        {"claim": "x", "evidence": "python scriptleri ile haftalik raporlari otomatiklestirdim."},
        {"claim": "x", "evidence": "Python scriptleri ile haftalık raporu otomatikleştirdim"},
    ]
    assert evidence.check(example_cv, claims) == []


def test_evidence_catches_invented_quote_and_empty(example_cv):
    claims = [{"claim": "a", "evidence": "Kubernetes kümelerini yönettim"}, {"claim": "b", "evidence": ""}]
    issues = evidence.check(example_cv, claims)
    assert len(issues) == 2 and all(i.severity == "error" for i in issues)
    assert evidence.check(example_cv, [])[0].severity == "error"


def test_leakage(example_cv):
    new = example_cv + "\nDocker, Kubernetes"
    leaked = {i.message.split("'")[1] for i in leakage.check(example_cv, new, JOB)}
    assert leaked == {"Docker", "Kubernetes"}


def test_leakage_allows_implied_terms(example_cv):
    # "SQL" is implied by "PostgreSQL" in the original CV.
    assert leakage.check(example_cv, example_cv + "\nSQL", JOB) == []


def test_dates_new_year_and_inflated_experience(example_cv):
    new = example_cv.replace("3 yıllık", "5 yıllık").replace("2017", "2015")
    msgs = [i.message for i in dates.check(example_cv, new)]
    assert any("2015" in m for m in msgs)
    assert any("5 yıl" in m for m in msgs)


def test_dates_uses_experience_span_when_no_explicit_claim():
    original = "## Deneyim\n### Dev (2020 - Günümüz)\n## Eğitim\nOkul (2010 - 2014)\n"
    today = dt.date(2026, 1, 1)
    assert dates.experience_span(original, today) == 6
    assert dates.check(original, original + "\n6 yıl deneyim", today) == []
    assert len(dates.check(original, original + "\n8 yıl deneyim", today)) == 1


def test_numbers_flags_new_figures_only(example_cv):
    assert numbers.check(example_cv, example_cv) == []
    msgs = [i.message for i in numbers.check(example_cv, example_cv + "\nSüreleri %40 azalttım, 12 servis")]
    assert msgs == ["'12' rakamı orijinal CV'de yok.", "'40' rakamı orijinal CV'de yok."]


def test_titles():
    assert titles.check("Junior Developer", "Senior Developer")[0].check == "titles"
    assert titles.check("Kıdemli Geliştirici", "Kıdemli Geliştirici") == []


def test_ats_score(example_cv):
    score, matched, missing = ats.score(example_cv, JOB)
    assert set(matched) == {"Python", "Django", "PostgreSQL", "REST API"}
    assert "Docker" in missing
    assert score == round(100 * 4 / 13, 1)


def test_structure_missing_section(example_cv):
    new = example_cv.replace("## Projeler", "")
    assert any("projeler" in i.message for i in structure.check(example_cv, new))


def test_mock_rounds(example_cv):
    r1 = run_all(example_cv, mock.CV_ROUND_1, mock.CLAIMS_ROUND_1, JOB)
    assert {i.check for i in r1.errors} == {"evidence", "leakage", "dates", "numbers"}
    r2 = run_all(example_cv, mock.CV_ROUND_2, mock.CLAIMS_ROUND_2, JOB)
    assert r2.issues == []
    assert r2.ats_after > r2.ats_before


# ---- regression tests for the review findings ----------------------------------

from app.checks import coverage


def test_bullet_without_claim_is_an_error(example_cv):
    new = mock.CV_ROUND_2.replace("## Beceriler", "- Kafka ile gerçek zamanlı olay akışı kurdum.\n\n## Beceriler")
    issues = coverage.check(new, mock.CLAIMS_ROUND_2)
    assert len(issues) == 1 and "Kafka" in issues[0].message and issues[0].severity == "error"
    assert coverage.check(mock.CV_ROUND_2, mock.CLAIMS_ROUND_2) == []


def test_short_or_partial_evidence_is_rejected(example_cv):
    for quote in ("test", "Python", "Django ile"):
        assert evidence.check(example_cv, [{"claim": "Kubernetes yönettim", "evidence": quote}])[0].severity == "error"
    # Whole words only: "gelistir" is part of "geliştirdim", not a word of the CV.
    assert evidence.best_match_ratio("gelistir", example_cv) < 1.0


def test_new_technology_not_in_job_is_a_warning(example_cv):
    new = example_cv.replace("pytest", "pytest, Kafka") + "\n- gRPC ve FastAPI ile servis yazdım.\n"
    issues = leakage.check_new_terms(example_cv, new, {"required_skills": ["Python"]})
    assert {i.message.split("'")[1] for i in issues} == {"Kafka", "gRPC", "FastAPI"}
    assert all(i.severity == "warning" for i in issues)
    assert leakage.check_new_terms(example_cv, mock.CV_ROUND_2, JOB) == []


def test_decimal_years():
    assert dates.years_claims("3.5 yıllık") == [3.5]
    assert dates.years_claims("3,5 yıllık") == [3.5]
    assert len(dates.check("3.5 yıllık", "5 yıllık")) == 1
    assert dates.check("3,5 yıllık", "3,5 yıllık") == []
