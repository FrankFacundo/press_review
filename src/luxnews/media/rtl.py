from __future__ import annotations

from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from luxnews.media.base import BaseMediaScraper


class RTLMediaScraper(BaseMediaScraper):
    DATE_FMT_SEARCH = "%d.%m.%Y"

    def extract_date(self, html: str) -> datetime | None:  # noqa: D401
        soup = BeautifulSoup(html, "lxml")
        time_tag = soup.find("time")
        if time_tag and time_tag.has_attr("datetime"):
            try:
                value = time_tag["datetime"].replace("Z", "+00:00")
                return datetime.fromisoformat(value)
            except ValueError:  # malformed datetime
                pass

        date_tag = soup.select_one("a.rtl-search-res_date")
        if date_tag:
            try:
                return datetime.strptime(date_tag.get_text(strip=True), self.DATE_FMT_SEARCH)
            except ValueError:
                pass
        return None

    def _extract_date_text(self, element) -> Optional[str]:
        extracted = self.extract_date(str(element))
        if extracted:
            return extracted.isoformat()

        if hasattr(element, "parents"):
            for parent in element.parents:
                extracted = self.extract_date(str(parent))
                if extracted:
                    return extracted.isoformat()

        return super()._extract_date_text(element)
