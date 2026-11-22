"""PDF output: Turkish letters survive embedding, layout fits, files appear in the run."""

from pypdf import PdfReader

from app import cli, pdf
from app.providers.mock import CV_ROUND_2, LETTER
from conftest import ROOT

TURKISH = "ığşüöçİĞŞÜÖÇ"


def text_of(path):
    return "\n".join(p.extract_text() for p in PdfReader(path).pages)


def test_turkish_characters_are_readable_from_the_text_layer(tmp_path):
    out = tmp_path / "cv.pdf"
    pdf.render(f"# İlker Şahin\n\nİstanbul · mail\n\n## Özet\n\n**Kalın** ve *eğik* {TURKISH}.\n\n- Madde: {TURKISH}\n", out)
    text = text_of(out)
    assert TURKISH in text and "İlker Şahin" in text and "Madde" in text
    assert "•" in text and "**" not in text and "##" not in text


def test_fonts_are_embedded(tmp_path):
    out = tmp_path / "cv.pdf"
    pdf.render(CV_ROUND_2, out)
    fonts = {f.get("/BaseFont", "") for p in PdfReader(out).pages for f in
             (r.get_object() for r in p["/Resources"]["/Font"].values())}
    assert any("DejaVu" in str(f) for f in fonts)
    assert (pdf.FONTS / "LICENSE_DEJAVU.txt").is_file()


def test_cv_fits_two_pages_by_shrinking_type(tmp_path):
    long_cv = "# Ad Soyad\n\niletişim\n\n## Deneyim\n\n" + "\n".join(
        f"- Satır {i}: çok uzun bir madde metni, " + "kelime " * 14 for i in range(56))
    pages = pdf.render(long_cv, tmp_path / "x.pdf")
    assert pages <= 2
    assert pdf._build(long_cv, "cv", pdf.SIZES["cv"][0]).page_no() > 2  # it only fits because the type shrank


def test_letter_is_one_page(tmp_path):
    assert pdf.render(LETTER, tmp_path / "l.pdf", "letter") == 1
    assert "Sayın Hayali Teknoloji" in text_of(tmp_path / "l.pdf")


def test_unsupported_glyphs_are_dropped_not_boxed(tmp_path):
    pdf.render("# A\n\nMerhaba \U0001F9FF​ dünya\n", tmp_path / "e.pdf")
    assert "Merhaba" in text_of(tmp_path / "e.pdf")


def test_cli_pdf_flag_writes_both_files(tmp_path):
    code = cli.main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(ROOT / "examples/cv.md"), "--evet", "--hizli",
                     "--pdf", "--runs", str(tmp_path / "runs"), "--hafiza", str(tmp_path / "mem")])
    assert code == 0
    (run,) = (tmp_path / "runs").iterdir()
    assert "Yılmaz" in text_of(run / "output" / "cv.pdf")
    assert "Sayın" in text_of(run / "output" / "cover_letter.pdf")


def test_no_pdf_without_the_flag(tmp_path):
    cli.main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(ROOT / "examples/cv.md"), "--evet", "--hizli",
              "--runs", str(tmp_path / "runs"), "--hafiza", str(tmp_path / "mem")])
    (run,) = (tmp_path / "runs").iterdir()
    assert not list((run / "output").glob("*.pdf"))


def test_pdf_failure_does_not_fail_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf, "render_outputs", lambda out: (_ for _ in ()).throw(RuntimeError("yazı tipi yok")))
    code = cli.main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(ROOT / "examples/cv.md"), "--evet", "--hizli",
                     "--pdf", "--runs", str(tmp_path / "runs"), "--hafiza", str(tmp_path / "mem")])
    assert code == 0
