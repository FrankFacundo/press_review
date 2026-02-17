from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter


def merge_pdfs(pdf_paths: Iterable[Path], output_path: Path) -> None:
    writer = PdfWriter()
    for path in pdf_paths:
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        writer.write(handle)


def build_run_summary_pdf(
    output_path: Path,
    run_id: str,
    run_timestamp: str,
    last_days: int,
    medias: list[str],
    keywords: list[str],
    media_statuses: list[dict],
    article_rows: list[list[str]],
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(output_path), pagesize=A4)
    content_width = float(doc.width)

    header_cell_style = ParagraphStyle(
        "SummaryTableHeader",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
    )
    body_cell_style = ParagraphStyle(
        "SummaryTableBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=11,
        wordWrap="CJK",
    )

    def _cell(value: object, *, header: bool = False) -> Paragraph:
        text = "" if value is None else str(value)
        style = header_cell_style if header else body_cell_style
        return Paragraph(escape(text), style)

    elements = []
    elements.append(Paragraph("LuxNews Run Summary", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Run ID: {run_id}", styles["Normal"]))
    elements.append(Paragraph(f"Timestamp: {run_timestamp}", styles["Normal"]))
    elements.append(Paragraph(f"Last Days: {last_days}", styles["Normal"]))
    elements.append(Paragraph(f"Medias: {', '.join(medias)}", styles["Normal"]))
    elements.append(Paragraph(f"Keywords: {', '.join(keywords)}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    status_rows = [[_cell("Media", header=True), _cell("Status", header=True), _cell("Errors", header=True)]]
    for status in media_statuses:
        status_rows.append(
            [
                _cell(status.get("media", "")),
                _cell(status.get("status", "")),
                _cell("; ".join(status.get("errors", []))),
            ]
        )

    status_table = Table(
        status_rows,
        colWidths=[
            content_width * 0.24,
            content_width * 0.14,
            content_width * 0.62,
        ],
        repeatRows=1,
    )
    status_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(Paragraph("Per-Media Status", styles["Heading2"]))
    elements.append(status_table)
    elements.append(Spacer(1, 16))

    if not article_rows:
        elements.append(Paragraph("No matched articles.", styles["Normal"]))
    else:
        table_rows = [
            [
                _cell("Media", header=True),
                _cell("Date", header=True),
                _cell("Title", header=True),
                _cell("URL", header=True),
                _cell("Keywords", header=True),
                _cell("PDF", header=True),
            ]
        ]
        for row in article_rows:
            table_rows.append([_cell(value) for value in row])

        article_table = Table(
            table_rows,
            colWidths=[
                content_width * 0.12,
                content_width * 0.15,
                content_width * 0.22,
                content_width * 0.26,
                content_width * 0.17,
                content_width * 0.08,
            ],
            repeatRows=1,
        )
        article_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(Paragraph("Matched Articles", styles["Heading2"]))
        elements.append(article_table)

    doc.build(elements)
