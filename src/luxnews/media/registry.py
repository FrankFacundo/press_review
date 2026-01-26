from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MediaDefinition:
    media_id: str
    search_url: str
    domain: str
    search_result_selectors: list[str] = field(default_factory=list)
    exclude_url_substrings: list[str] = field(default_factory=list)
    debug_selectors: dict[str, list[str]] = field(default_factory=dict)


DEFAULT_EXCLUDES = [
    "/search",
    "search?",
    "/recherche",
    "recherche?",
    "/suche",
    "suche?",
    "/pesquisa",
    "pesquisa?",
]

DEFAULT_DEBUG_SELECTORS = {
    "search": ["article", "a[href]", "time", "h2 a", "h3 a"],
    "article": ["article", "h1", "time", "meta[property='article:published_time']"],
}


def _debug_selectors() -> dict[str, list[str]]:
    return {key: list(value) for key, value in DEFAULT_DEBUG_SELECTORS.items()}


MEDIA_REGISTRY: dict[str, MediaDefinition] = {
    "rtl.lu": MediaDefinition(
        media_id="rtl.lu",
        search_url="https://rtl.lu/search?q={query}&p={page}",
        domain="rtl.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "today.rtl.lu": MediaDefinition(
        media_id="today.rtl.lu",
        search_url="https://today.rtl.lu/search?q={query}&p={page}",
        domain="today.rtl.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "infos.rtl.lu": MediaDefinition(
        media_id="infos.rtl.lu",
        search_url="https://infos.rtl.lu/search?q={query}&p={page}",
        domain="infos.rtl.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "lessentiel.lu": MediaDefinition(
        media_id="lessentiel.lu",
        search_url="https://lessentiel.lu/fr/search?q={query}",
        domain="lessentiel.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "lequotidien.lu": MediaDefinition(
        media_id="lequotidien.lu",
        search_url="https://lequotidien.lu/page/1/?s={query}",
        domain="lequotidien.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "tageblatt.lu": MediaDefinition(
        media_id="tageblatt.lu",
        search_url="https://tageblatt.lu/?s={query}",
        domain="tageblatt.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "virgule.lu": MediaDefinition(
        media_id="virgule.lu",
        search_url="https://virgule.lu/recherche/?q={query}",
        domain="virgule.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "wort.lu": MediaDefinition(
        media_id="wort.lu",
        search_url="https://wort.lu/suche/?q={query}",
        domain="wort.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "contacto.lu": MediaDefinition(
        media_id="contacto.lu",
        search_url="https://contacto.lu/pesquisa/?q={query}",
        domain="contacto.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "luxtimes.lu": MediaDefinition(
        media_id="luxtimes.lu",
        search_url="https://luxtimes.lu/search/?q={query}",
        domain="luxtimes.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "infogreen.lu": MediaDefinition(
        media_id="infogreen.lu",
        search_url="https://infogreen.lu/spip.php?page=recherche&lang=fr&recherche={query}",
        domain="infogreen.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "chronicle.lu": MediaDefinition(
        media_id="chronicle.lu",
        search_url="https://chronicle.lu/search/{query}",
        domain="chronicle.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "siliconluxembourg.lu": MediaDefinition(
        media_id="siliconluxembourg.lu",
        search_url="https://siliconluxembourg.lu/?s={query}",
        domain="siliconluxembourg.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "paperjam.lu": MediaDefinition(
        media_id="paperjam.lu",
        search_url=(
            "https://paperjam.lu/search?numericRefinementList%5BpublicationDate%5D=Tous&query={query}"
        ),
        domain="paperjam.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "delano.lu": MediaDefinition(
        media_id="delano.lu",
        search_url=(
            "https://delano.lu/search?numericRefinementList%5BpublicationDate%5D=All&query={query}"
        ),
        domain="delano.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "gemengen.lu": MediaDefinition(
        media_id="gemengen.lu",
        search_url="https://gemengen.lu/web/?s={query}",
        domain="gemengen.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
    "reporter.lu": MediaDefinition(
        media_id="reporter.lu",
        search_url="https://reporter.lu/fr/?s={query}",
        domain="reporter.lu",
        exclude_url_substrings=DEFAULT_EXCLUDES,
        debug_selectors=_debug_selectors(),
    ),
}
