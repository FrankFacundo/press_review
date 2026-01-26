from pathlib import Path

from pypdf import PdfReader

from luxnews.pdf_utils import merge_pdfs


def test_merge_pdfs(tmp_path: Path):
    fixture_dir = Path(__file__).parent / "fixtures"
    pdf1 = fixture_dir / "fixture1.pdf"
    pdf2 = fixture_dir / "fixture2.pdf"
    output_pdf = tmp_path / "merged.pdf"

    merge_pdfs([pdf1, pdf2], output_pdf)
    assert output_pdf.exists()
    reader = PdfReader(str(output_pdf))
    assert len(reader.pages) == 2
