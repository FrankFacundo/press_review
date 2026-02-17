from __future__ import annotations

from luxnews.config import RunConfig
from luxnews.media.base import BaseMediaScraper
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MediaDefinition
from luxnews.media.rtl import RTLMediaScraper

RTL_MEDIA_IDS = {
    "rtl.lu",
    "today.rtl.lu",
    "infos.rtl.lu",
}

PAPERJAM_MEDIA_IDS = {
    "paperjam.lu",
}


def build_media_scraper(definition: MediaDefinition, config: RunConfig) -> BaseMediaScraper:
    if definition.media_id in RTL_MEDIA_IDS:
        return RTLMediaScraper(definition, config)
    if definition.media_id in PAPERJAM_MEDIA_IDS:
        return PaperjamMediaScraper(definition, config)
    return BaseMediaScraper(definition, config)
