from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin

from dateutil import parser as date_parser

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def parse_date(text: str) -> Optional[datetime]:
    try:
        dt = date_parser.parse(text, fuzzy=True)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_within_last_days(dt: datetime, last_days: int, now: Optional[datetime] = None) -> bool:
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=last_days)
    return dt >= cutoff


def safe_filename(text: str, max_len: int = 120) -> str:
    normalized = normalize_text(text)
    normalized = re.sub(r"[^a-z0-9\-_. ]", "", normalized)
    normalized = normalized.replace(" ", "-").strip("-")
    if not normalized:
        normalized = "item"
    return normalized[:max_len]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def to_absolute_url(base_url: str, href: str) -> str:
    return urljoin(base_url, href)


def dump_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
