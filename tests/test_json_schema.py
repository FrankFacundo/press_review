import json
from pathlib import Path

from jsonschema import validate


def test_matches_schema():
    schema_path = Path(__file__).parent / "fixtures" / "matches_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    sample = [
        {
            "run_id": "run_20240101",
            "run_timestamp": "2024-01-01T00:00:00Z",
            "media": "rtl.lu",
            "url": "https://rtl.lu/news/article",
            "title": "Sample",
            "published_at": "2024-01-01T00:00:00Z",
            "date_unknown": False,
            "matched_keywords": ["BNP"],
            "snippets": ["Snippet"],
            "per_article_pdf_path": "outputs/run_20240101/pdfs/article.pdf",
            "status": "ok",
            "errors": [],
        }
    ]
    validate(sample, schema)
