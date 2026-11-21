from pathlib import Path

import pytest

from app.checks import dates, leakage
from app.cli import main
from app.inputs import InputError, normalize_bullets, promote_headings, read_document
from conftest import ROOT

FIX = ROOT / "tests" / "fixtures"


@pytest.mark.parametrize("name", ["cv.pdf", "cv.docx"])
def test_reads_pdf_and_docx_into_checkable_text(name, example_cv):
    text = read_document(FIX / name)
    bullets = [l for l in text.splitlines() if l.startswith("- ")]
    assert len(bullets) == 7
    assert "- Django ile şirket içi sipariş takip uygulamasını geliştirdim." in text
    assert {"## Deneyim", "## Beceriler"} <= {l.strip() for l in text.splitlines()}
    # The checks that depend on headings work on extracted text too.
    assert dates.experience_span(text) == dates.experience_span(example_cv)
    assert "pytest" in leakage.skills_items(text)


def test_reads_cp1254_text(tmp_path):
    f = tmp_path / "cv.txt"
    f.write_bytes(("Deneyim\n" + "Yazılım geliştirdim, İstanbul'da çalıştım. " * 5).encode("cp1254"))
    text = read_document(f)
    assert "İstanbul" in text and text.startswith("## Deneyim")


def test_rejects_unsupported_and_empty(tmp_path):
    with pytest.raises(InputError, match="Desteklenmeyen"):
        read_document(tmp_path / "cv.jpg")
    empty = tmp_path / "bos.txt"
    empty.write_text("kısa", encoding="utf-8")
    with pytest.raises(InputError, match="yeterli metin"):
        read_document(empty)
    broken = tmp_path / "bozuk.pdf"
    broken.write_bytes(b"not a pdf")
    with pytest.raises(InputError):
        read_document(broken)


def test_bullet_and_heading_normalization():
    assert normalize_bullets("• bir\n● iki\n- üç") == "- bir\n- iki\n- üç"
    assert promote_headings("DENEYİM\nmetin\nBeceriler:") == "## DENEYİM\nmetin\n## Beceriler"
    assert promote_headings("## Özet\nDeneyim") == "## Özet\nDeneyim"


@pytest.mark.parametrize("name", ["cv.pdf", "cv.docx"])
def test_cli_mock_with_pdf_and_docx(tmp_path, name):
    code = main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(FIX / name),
                 "--evet", "--hizli", "--runs", str(tmp_path)])
    assert code == 0
    (run,) = tmp_path.iterdir()
    assert (run / "inputs" / "cv_metin.md").exists()
    assert (run / "output" / "report.md").exists()
