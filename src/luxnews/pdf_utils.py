from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

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
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(output_path), pagesize=A4)

    elements = []
    elements.append(Paragraph("LuxNews Run Summary", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Run ID: {run_id}", styles["Normal"]))
    elements.append(Paragraph(f"Timestamp: {run_timestamp}", styles["Normal"]))
    elements.append(Paragraph(f"Last Days: {last_days}", styles["Normal"]))
    elements.append(Paragraph(f"Medias: {', '.join(medias)}", styles["Normal"]))
    elements.append(Paragraph(f"Keywords: {', '.join(keywords)}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    status_rows = [["Media", "Status", "Errors"]]
    for status in media_statuses:
        status_rows.append(
            [
                status.get("media", ""),
                status.get("status", ""),
                "; ".join(status.get("errors", [])),
            ]
        )

    status_table = Table(status_rows, colWidths=[120, 80, 300])
    status_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elements.append(Paragraph("Per-Media Status", styles["Heading2"]))
    elements.append(status_table)
    elements.append(Spacer(1, 16))

    if not article_rows:
        elements.append(Paragraph("No matched articles.", styles["Normal"]))
    else:
        table_rows = [["Media", "Date", "Title", "URL", "Keywords", "PDF"]] + article_rows
        article_table = Table(table_rows, colWidths=[70, 60, 140, 140, 90, 60])
        article_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements.append(Paragraph("Matched Articles", styles["Heading2"]))
        elements.append(article_table)

    doc.build(elements)
