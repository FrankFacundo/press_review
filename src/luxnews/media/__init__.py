from luxnews.media.base import BaseMediaScraper
from luxnews.media.factory import build_media_scraper
from luxnews.media.luxtimes import LuxTimesMediaScraper
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY, MediaDefinition
from luxnews.media.rtl import RTLMediaScraper
from luxnews.media.virgule import VirguleMediaScraper
from luxnews.media.wort import WortMediaScraper

__all__ = [
    "BaseMediaScraper",
    "build_media_scraper",
    "LuxTimesMediaScraper",
    "PaperjamMediaScraper",
    "MEDIA_REGISTRY",
    "MediaDefinition",
    "RTLMediaScraper",
    "VirguleMediaScraper",
    "WortMediaScraper",
]
