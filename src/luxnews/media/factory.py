from __future__ import annotations

from luxnews.config import RunConfig
from luxnews.media.base import BaseMediaScraper
from luxnews.media.contacto import ContactoMediaScraper
from luxnews.media.delano import DelanoMediaScraper
from luxnews.media.infogreen import InfogreenMediaScraper
from luxnews.media.lequotidien import LeQuotidienMediaScraper
from luxnews.media.lessentiel import LessentielMediaScraper
from luxnews.media.luxtimes import LuxTimesMediaScraper
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MediaDefinition
from luxnews.media.rtl import RTLMediaScraper
from luxnews.media.tageblatt import TageblattMediaScraper
from luxnews.media.virgule import VirguleMediaScraper
from luxnews.media.wort import WortMediaScraper

RTL_MEDIA_IDS = {
    "rtl.lu",
    "today.rtl.lu",
    "infos.rtl.lu",
}

PAPERJAM_MEDIA_IDS = {
    "paperjam.lu",
}

WORT_MEDIA_IDS = {
    "wort.lu",
}

VIRGULE_MEDIA_IDS = {
    "virgule.lu",
}

LUXTIMES_MEDIA_IDS = {
    "luxtimes.lu",
    "luxtimes.lu/en",
}

DELANO_MEDIA_IDS = {
    "delano.lu",
}

LEQUOTIDIEN_MEDIA_IDS = {
    "lequotidien.lu",
}

LESSENTIEL_MEDIA_IDS = {
    "lessentiel.lu",
    "lessentiel.lu/fr",
}

TAGEBLATT_MEDIA_IDS = {
    "tageblatt.lu",
}

CONTACTO_MEDIA_IDS = {
    "contacto.lu",
}

INFOGREEN_MEDIA_IDS = {
    "infogreen.lu",
}


def build_media_scraper(definition: MediaDefinition, config: RunConfig) -> BaseMediaScraper:
    if definition.media_id in RTL_MEDIA_IDS:
        return RTLMediaScraper(definition, config)
    if definition.media_id in PAPERJAM_MEDIA_IDS:
        return PaperjamMediaScraper(definition, config)
    if definition.media_id in WORT_MEDIA_IDS:
        return WortMediaScraper(definition, config)
    if definition.media_id in VIRGULE_MEDIA_IDS:
        return VirguleMediaScraper(definition, config)
    if definition.media_id in LUXTIMES_MEDIA_IDS:
        return LuxTimesMediaScraper(definition, config)
    if definition.media_id in DELANO_MEDIA_IDS:
        return DelanoMediaScraper(definition, config)
    if definition.media_id in LEQUOTIDIEN_MEDIA_IDS:
        return LeQuotidienMediaScraper(definition, config)
    if definition.media_id in LESSENTIEL_MEDIA_IDS:
        return LessentielMediaScraper(definition, config)
    if definition.media_id in TAGEBLATT_MEDIA_IDS:
        return TageblattMediaScraper(definition, config)
    if definition.media_id in CONTACTO_MEDIA_IDS:
        return ContactoMediaScraper(definition, config)
    if definition.media_id in INFOGREEN_MEDIA_IDS:
        return InfogreenMediaScraper(definition, config)
    return BaseMediaScraper(definition, config)
