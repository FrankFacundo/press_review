from luxnews.media.base import BaseMediaScraper
from luxnews.media.delano import DelanoMediaScraper
from luxnews.media.factory import build_media_scraper
from luxnews.media.lequotidien import LeQuotidienMediaScraper
from luxnews.media.lessentiel import LessentielMediaScraper
from luxnews.media.luxtimes import LuxTimesMediaScraper
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY, MediaDefinition
from luxnews.media.rtl import RTLMediaScraper
from luxnews.media.tageblatt import TageblattMediaScraper
from luxnews.media.virgule import VirguleMediaScraper
from luxnews.media.wort import WortMediaScraper

__all__ = [
    "BaseMediaScraper",
    "DelanoMediaScraper",
    "build_media_scraper",
    "LeQuotidienMediaScraper",
    "LessentielMediaScraper",
    "LuxTimesMediaScraper",
    "PaperjamMediaScraper",
    "MEDIA_REGISTRY",
    "MediaDefinition",
    "RTLMediaScraper",
    "TageblattMediaScraper",
    "VirguleMediaScraper",
    "WortMediaScraper",
]
