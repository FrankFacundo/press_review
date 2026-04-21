from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape, quoteattr

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


def stamp_article_pdf_header(pdf_path: Path, media: str, published_at: str | None) -> None:
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    if not pdf_path.exists():
        return

    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    if total_pages == 0:
        return

    writer = PdfWriter()
    header_date = _format_header_date(published_at)

    for index, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        packet = io.BytesIO()
        overlay = canvas.Canvas(packet, pagesize=(width, height))

        header_text = f"{media} - {index}/{total_pages} - {header_date}"
        top_margin = 22.0
        side_margin = 20.0
        band_height = 26.0
        text_y = height - 14.0
        line_y = height - top_margin

        overlay.setFillColor(colors.white)
        overlay.rect(0, height - band_height, width, band_height, fill=1, stroke=0)
        overlay.setFont("Helvetica", 9)
        overlay.setFillColor(colors.black)
        overlay.drawString(side_margin, text_y, header_text)
        overlay.setStrokeColor(colors.black)
        overlay.setLineWidth(0.7)
        overlay.line(side_margin, line_y, width - side_margin, line_y)
        overlay.save()

        packet.seek(0)
        header_page = PdfReader(packet).pages[0]
        writer.add_page(page)
        writer.pages[-1].merge_page(header_page)

    output_tmp = pdf_path.with_suffix(".tmp.pdf")
    with output_tmp.open("wb") as handle:
        writer.write(handle)
    output_tmp.replace(pdf_path)


def _format_header_date(published_at: str | None) -> str:
    if not published_at:
        return "unknown"
    value = published_at.strip()
    if not value:
        return "unknown"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return dt.strftime("%d.%m.%Y")


def build_run_summary_pdf(
    output_path: Path,
    run_id: str,
    run_timestamp: str,
    search_cutoff: datetime,
    business_days_before: int,
    cutoff_hour: int,
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
    text_scale = 0.65

    title_style = ParagraphStyle(
        "SummaryTitle",
        parent=styles["Title"],
        fontSize=styles["Title"].fontSize * text_scale,
        leading=styles["Title"].leading * text_scale,
    )
    normal_style = ParagraphStyle(
        "SummaryNormal",
        parent=styles["Normal"],
        fontSize=styles["Normal"].fontSize * text_scale,
        leading=styles["Normal"].leading * text_scale,
    )
    heading_style = ParagraphStyle(
        "SummaryHeading2",
        parent=styles["Heading2"],
        fontSize=styles["Heading2"].fontSize * text_scale,
        leading=styles["Heading2"].leading * text_scale,
    )

    header_cell_style = ParagraphStyle(
        "SummaryTableHeader",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=10 * text_scale,
        leading=12 * text_scale,
    )
    body_cell_style = ParagraphStyle(
        "SummaryTableBody",
        parent=styles["BodyText"],
        fontSize=9 * text_scale,
        leading=11 * text_scale,
        wordWrap="CJK",
    )

    def _cell(value: object, *, header: bool = False) -> Paragraph:
        text = "" if value is None else str(value)
        style = header_cell_style if header else body_cell_style
        return Paragraph(escape(text), style)

    def _link_cell(url: object) -> Paragraph:
        text = "" if url is None else str(url).strip()
        if not text:
            return _cell("")
        escaped_text = escape(text)
        href = quoteattr(text)
        return Paragraph(
            f'<link href={href}><u><font color="blue">{escaped_text}</font></u></link>',
            body_cell_style,
        )

    elements = []
    elements.append(Paragraph("LuxNews Run Summary", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Run ID: {run_id}", normal_style))
    elements.append(Paragraph(f"Timestamp: {run_timestamp}", normal_style))
    elements.append(
        Paragraph(
            f"Search cutoff: {search_cutoff.astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
            normal_style,
        )
    )
    elements.append(Paragraph(f"Business days before: {business_days_before}", normal_style))
    elements.append(Paragraph(f"Cutoff hour: {cutoff_hour:02d}:00", normal_style))
    elements.append(Paragraph(f"Medias: {', '.join(medias)}", normal_style))
    elements.append(Paragraph(f"Keywords: {', '.join(keywords)}", normal_style))
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
    elements.append(Paragraph("Per-Media Status", heading_style))
    elements.append(status_table)
    elements.append(Spacer(1, 16))

    if not article_rows:
        elements.append(Paragraph("No matched articles.", normal_style))
    else:
        table_rows = [
            [
                _cell("Media", header=True),
                _cell("Date", header=True),
                _cell("Title", header=True),
                _cell("URL", header=True),
                _cell("Keywords", header=True),
            ]
        ]
        for row in article_rows:
            rendered_row = []
            for index, value in enumerate(row):
                if index == 3:
                    rendered_row.append(_link_cell(value))
                else:
                    rendered_row.append(_cell(value))
            table_rows.append(rendered_row)

        article_table = Table(
            table_rows,
            colWidths=[
                content_width * 0.12,
                content_width * 0.15,
                content_width * 0.26,
                content_width * 0.28,
                content_width * 0.19,
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
        elements.append(Paragraph("Matched Articles", heading_style))
        elements.append(article_table)

    doc.build(elements)
