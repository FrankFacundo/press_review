from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SearchHit:
    url: str
    title: Optional[str] = None
    published_at: Optional[datetime] = None
    snippet: Optional[str] = None
    media_id: Optional[str] = None


@dataclass
class ArticleRecord:
    run_id: str
    run_timestamp: str
    media: str
    url: str
    title: Optional[str]
    published_at: Optional[str]
    date_unknown: bool
    matched_keywords: list[str]
    snippets: list[str]
    per_article_pdf_path: Optional[str]
    status: str
    errors: list[str] = field(default_factory=list)


@dataclass
class MediaStatus:
    media: str
    status: str
    errors: list[str] = field(default_factory=list)


@dataclass
class DebugArtifacts:
    html_path: Optional[str] = None
    mhtml_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    console_log_path: Optional[str] = None
    performance_log_path: Optional[str] = None
    bundle_path: Optional[str] = None
