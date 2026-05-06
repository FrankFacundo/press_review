from __future__ import annotations

MEDIA_ALIASES = {
    "lessentiel.lu/fr": "lessentiel.lu",
}


def canonical_media_id(media_id: str) -> str:
    normalized = (media_id or "").strip()
    return MEDIA_ALIASES.get(normalized, normalized)
