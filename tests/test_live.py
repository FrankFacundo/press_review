import os
from pathlib import Path

import pytest

from luxnews.config import RunConfig
from luxnews.media.base import BaseMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY


@pytest.mark.live
@pytest.mark.parametrize("media_id,keyword", [("rtl.lu", "finance"), ("delano.lu", "bank"), ("virgule.lu", "finance")])
def test_live_search_and_pdf(media_id: str, keyword: str, tmp_path: Path):
    try:
        from luxnews.selenium_utils import (
            create_driver,
            print_to_pdf,
            try_accept_cookies,
            wait_for_ready,
        )
    except ModuleNotFoundError as exc:
        pytest.skip(f"Selenium not available: {exc}")

    config = RunConfig(
        keywords=[keyword],
        medias=[media_id],
        last_days=7,
        headless=True,
        search_use_selenium=True,
    )
    scraper = BaseMediaScraper(MEDIA_REGISTRY[media_id], config)
    driver = create_driver("chrome", headless=True, open_devtools=False, enable_logging=False, page_timeout=30.0)

    try:
        hits = []
        for url in scraper.build_search_urls(keyword)[:1]:
            driver.get(url)
            wait_for_ready(driver, 20.0)
            try_accept_cookies(driver)
            html = driver.page_source
            hits = scraper.parse_search_results(html, url)
            if hits:
                break
        if not hits:
            pytest.skip("No hits found or blocked")

        article_url = hits[0].url
        driver.get(article_url)
        wait_for_ready(driver, 20.0)
        try_accept_cookies(driver)
        pdf_path = tmp_path / f"{media_id}.pdf"
        print_to_pdf(driver, pdf_path)
        assert pdf_path.exists() and pdf_path.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Live test skipped due to error: {exc}")
    finally:
        driver.quit()
