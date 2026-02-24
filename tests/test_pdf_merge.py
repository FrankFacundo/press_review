from pathlib import Path

from pypdf import PdfReader

from luxnews.pdf_utils import build_run_summary_pdf, merge_pdfs, stamp_article_pdf_header


def test_merge_pdfs(tmp_path: Path):
    fixture_dir = Path(__file__).parent / "fixtures"
    pdf1 = fixture_dir / "fixture1.pdf"
    pdf2 = fixture_dir / "fixture2.pdf"
    output_pdf = tmp_path / "merged.pdf"

    merge_pdfs([pdf1, pdf2], output_pdf)
    assert output_pdf.exists()
    reader = PdfReader(str(output_pdf))
    assert len(reader.pages) == 2


def test_build_run_summary_pdf_with_long_article_row(tmp_path: Path):
    output_pdf = tmp_path / "summary.pdf"
    long_title = "Cap2020 fonds immobilier article headline " * 4
    long_url = "https://paperjam.lu/article/cap2020-fonds-immobilier-something-very-long-slug"
    long_keywords = "BNP PARIBAS, ARVAL, CARDIF, MICROLUX, BOB KIEFFER, FMI, CSSF"

    build_run_summary_pdf(
        output_path=output_pdf,
        run_id="run_test",
        run_timestamp="2026-02-17T00:00:00+00:00",
        last_days=2,
        medias=["paperjam.lu"],
        keywords=["BNP PARIBAS", "FMI"],
        media_statuses=[{"media": "paperjam.lu", "status": "ok", "errors": []}],
        article_rows=[
            [
                "paperjam.lu",
                "2026-02-16T00:00:00+00:00",
                long_title,
                long_url,
                long_keywords,
            ]
        ],
    )

    assert output_pdf.exists()
    reader = PdfReader(str(output_pdf))
    assert len(reader.pages) >= 1
    page_text = "\n".join((page.extract_text() or "") for page in reader.pages)
    assert "Matched Articles" in page_text
    assert "PDF" not in page_text

    page_has_link = False
    for page in reader.pages:
        annotations = page.get("/Annots") or []
        for annotation_ref in annotations:
            annotation = annotation_ref.get_object()
            action = annotation.get("/A")
            if not action:
                continue
            uri = action.get("/URI")
            if uri == long_url:
                page_has_link = True
                break
        if page_has_link:
            break

    assert page_has_link is True


def test_stamp_article_pdf_header(tmp_path: Path):
    from reportlab.pdfgen import canvas

    article_pdf = tmp_path / "article.pdf"
    base = canvas.Canvas(str(article_pdf))
    base.drawString(72, 720, "Article page one")
    base.showPage()
    base.drawString(72, 720, "Article page two")
    base.save()

    stamp_article_pdf_header(
        article_pdf,
        media="paperjam.lu",
        published_at="2026-02-16T00:00:00+00:00",
    )

    reader = PdfReader(str(article_pdf))
    assert len(reader.pages) == 2
    page1_text = reader.pages[0].extract_text() or ""
    page2_text = reader.pages[1].extract_text() or ""
    assert "paperjam.lu - 1/2 - 16.02.2026" in page1_text
    assert "paperjam.lu - 2/2 - 16.02.2026" in page2_text
