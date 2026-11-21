"""Builds output/report.md from run state. Plain code, no LLM."""

from __future__ import annotations

from app.skills import RunState


def changes(original: str, new: str) -> tuple[list[str], list[str]]:
    a = [l.strip() for l in original.splitlines() if l.strip().startswith("- ")]
    b = [l.strip() for l in new.splitlines() if l.strip().startswith("- ")]
    # Set difference, not a line diff: a bullet that only moved is not a change.
    added = [x for x in b if x not in a]
    removed = [x for x in a if x not in b]
    return added, removed


def build(s: RunState) -> str:
    job, checks = s.job, s.checks
    best = s.best or {}
    lines = [f"# Başvuru Raporu: {job.get('title', '')}", ""]
    if job.get("company"):
        lines += [f"**Şirket:** {job['company']}", ""]
    if s.plateau:
        lines += ["> ⚠️ Puan hedefin (80) altında kaldı ve iki temiz turda artmadı, döngü erken durduruldu. "
                  "Kalan eksikler orijinal CV'de yok. Bu deneyimler gerçekten varsa orijinal CV'ye ekleyip yeniden çalıştırın.", ""]
    elif not s.converged:
        lines += ["> ⚠️ Döngü hedefe ulaşmadı (uydurma yok + puan ≥ 80). En iyi sürüm kullanıldı. "
                  "Göndermeden önce aşağıdaki sorunları kendiniz düzeltin.", ""]

    lines += ["## Skorlar", "",
              "| | Değer |", "|---|---|",
              f"| İşveren puanı | {best.get('score', 0)} / 100 |",
              f"| ATS (önce) | %{checks.ats_before if checks else 0} |",
              f"| ATS (sonra) | %{checks.ats_after if checks else 0} |",
              f"| Doğrulayıcı | {'Onay' if best.get('decision') == 'approve' else 'Ret'} |",
              f"| Tur sayısı | {len(s.rounds)} |", ""]

    lines += ["## Turlar", "", "| Tur | Kod hatası | Doğrulayıcı | Puan |", "|---|---|---|---|"]
    for r in s.rounds:
        lines.append(f"| {r['iteration']} | {r['errors']} | {r['decision']} | {r['score']} |")
    lines.append("")

    if checks:
        lines += ["## ATS Anahtar Kelimeleri", "",
                  f"**Geçenler:** {', '.join(checks.matched_keywords) or '-'}", "",
                  f"**Eksikler:** {', '.join(checks.missing_keywords) or '-'}", "",
                  "Eksik kelimeler CV'nize eklenmedi, çünkü orijinal CV'de karşılıkları yok.", ""]
        if checks.issues:
            lines += ["## Açık Sorunlar", ""]
            lines += [f"- **{i.check}** ({i.severity}): {i.message}" for i in checks.issues]
            lines.append("")

    if s.missing:
        lines += ["## İşe Alım Müdürünün Eksikleri", ""] + [f"- {m}" for m in s.missing] + [""]

    added, removed = changes(s.cv_text, s.cv)
    lines += ["## Değişiklikler", ""]
    lines += [f"- ➕ {x[2:]}" for x in added] + [f"- ➖ {x[2:]}" for x in removed]
    if not added and not removed:
        lines.append("- Maddelerde değişiklik yok, yalnızca sıralama ve bölümler.")
    lines += ["", "---", "", "Yapay zekâ çıktıları hatalı olabilir. Başvurmadan önce her şeyi kendiniz kontrol edin.", ""]
    return "\n".join(lines)
