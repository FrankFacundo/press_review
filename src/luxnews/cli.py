from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from luxnews.config import RunConfig, resolve_jobs
from luxnews.core import LuxNewsRunner
from luxnews.debug import DebugManager, DebugOptions
from luxnews.media.base import BaseMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.selenium_utils import (
    create_driver,
    extract_title,
    print_to_pdf,
    try_accept_cookies,
    wait_for_ready,
)
from luxnews.selector_playground import run_selector_playground
from luxnews.utils import ensure_dir

app = typer.Typer(add_completion=False)
logging.basicConfig(level=logging.INFO)


@app.command("run")
def run(
    config: Optional[str] = typer.Option(None, help="Named config: daily, daily_job_1, daily_job_2"),
    keywords: list[str] = typer.Option([], help="Keywords to search"),
    medias: list[str] = typer.Option([], help="Media IDs to search"),
    last_days: int = typer.Option(2, help="Look back window in days"),
    driver: str = typer.Option("chrome", help="Browser driver: chrome or edge"),
    headed: bool = typer.Option(False, help="Run in headed mode"),
    output_dir: str = typer.Option("outputs", help="Output directory"),
    debug: bool = typer.Option(False, help="Enable debug artifacts"),
    pause: bool = typer.Option(False, help="Pause at key steps for DevTools"),
    pause_on_error: bool = typer.Option(False, help="Pause when errors occur"),
    open_devtools: bool = typer.Option(False, help="Attempt to open DevTools automatically"),
    search_use_selenium: bool = typer.Option(False, help="Use Selenium for search pages"),
):
    if config:
        jobs = resolve_jobs(config)
        for job in jobs:
            cfg = RunConfig(
                keywords=job.keywords,
                medias=job.medias,
                last_days=job.last_days,
                driver=driver,
                headless=not headed,
                output_dir=output_dir,
                debug=debug,
                pause=pause,
                pause_on_error=pause_on_error,
                open_devtools=open_devtools,
                search_use_selenium=search_use_selenium,
            )
            result = LuxNewsRunner(cfg).run_job(job_name=job.name)
            typer.echo(f"Run {result['run_id']} completed: {result['merged_pdf']}")
    else:
        if not keywords or not medias:
            raise typer.BadParameter("Provide --keywords and --medias or use --config")
        cfg = RunConfig(
            keywords=keywords,
            medias=medias,
            last_days=last_days,
            driver=driver,
            headless=not headed,
            output_dir=output_dir,
            debug=debug,
            pause=pause,
            pause_on_error=pause_on_error,
            open_devtools=open_devtools,
            search_use_selenium=search_use_selenium,
        )
        result = LuxNewsRunner(cfg).run_job()
        typer.echo(f"Run {result['run_id']} completed: {result['merged_pdf']}")


@app.command("debug-search")
def debug_search(
    media: str = typer.Option(..., help="Media ID"),
    keyword: str = typer.Option(..., help="Keyword to search"),
    last_days: int = typer.Option(2, help="Look back window in days"),
    driver: str = typer.Option("chrome", help="Browser driver"),
    headed: bool = typer.Option(False, help="Run in headed mode"),
    debug: bool = typer.Option(True, help="Enable debug artifacts"),
    pause: bool = typer.Option(False, help="Pause at key steps"),
    open_devtools: bool = typer.Option(False, help="Attempt to open DevTools"),
):
    if media not in MEDIA_REGISTRY:
        raise typer.BadParameter(f"Unknown media: {media}")

    cfg = RunConfig(
        keywords=[keyword],
        medias=[media],
        last_days=last_days,
        driver=driver,
        headless=not headed,
        debug=debug,
        pause=pause,
        open_devtools=open_devtools,
        search_use_selenium=True,
    )
    runner = LuxNewsRunner(cfg)
    scraper = BaseMediaScraper(MEDIA_REGISTRY[media], cfg)

    driver_instance = create_driver(driver, not headed, open_devtools, enable_logging=debug, page_timeout=30.0)
    debug_manager = DebugManager(
        DebugOptions(enabled=debug, output_dir=Path(cfg.output_dir), run_id="debug_search")
    )

    try:
        hits = runner._search_with_selenium(scraper, driver_instance, debug_manager, keyword, last_days)
        typer.echo(f"Found {len(hits)} hits for {keyword} on {media}")
        for hit in hits[:20]:
            typer.echo(f"- {hit.url} | {hit.title or ''}")
    finally:
        driver_instance.quit()


@app.command("debug-article")
def debug_article(
    url: str = typer.Option(..., help="Article URL"),
    driver: str = typer.Option("chrome", help="Browser driver"),
    headed: bool = typer.Option(False, help="Run in headed mode"),
    open_devtools: bool = typer.Option(False, help="Attempt to open DevTools"),
    pause: bool = typer.Option(False, help="Pause after load"),
):
    driver_instance = create_driver(driver, not headed, open_devtools, enable_logging=True, page_timeout=30.0)
    output_root = ensure_dir(Path("outputs"))
    run_id = f"debug_article_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    debug_manager = DebugManager(
        DebugOptions(enabled=True, output_dir=output_root, run_id=run_id)
    )
    output_dir = ensure_dir(output_root / run_id)
    pdf_path = output_dir / "article.pdf"

    try:
        driver_instance.get(url)
        wait_for_ready(driver_instance, 20.0)
        try_accept_cookies(driver_instance)
        debug_manager.dump_page(driver_instance, media="manual", kind="article", url=url)
        if pause:
            input("Article loaded. Press Enter to continue...")
        title = extract_title(driver_instance)
        print_to_pdf(driver_instance, pdf_path)
        typer.echo(f"Title: {title}")
        typer.echo(f"PDF saved: {pdf_path}")
    finally:
        driver_instance.quit()


@app.command("selector-playground")
def selector_playground(
    html: Optional[Path] = typer.Option(None, help="HTML file path"),
    url: Optional[str] = typer.Option(None, help="Live URL"),
    css: Optional[str] = typer.Option(None, help="CSS selector"),
    xpath: Optional[str] = typer.Option(None, help="XPath selector"),
    limit: int = typer.Option(5, help="Number of matches to show"),
    report: Optional[Path] = typer.Option(None, help="Write selector_report.json"),
    driver: str = typer.Option("chrome", help="Browser driver for live URL"),
    headed: bool = typer.Option(False, help="Run in headed mode"),
):
    result = run_selector_playground(
        html_path=html,
        url=url,
        css=css,
        xpath=xpath,
        limit=limit,
        report_path=report,
        driver_name=driver,
        headless=not headed,
    )
    if result.css:
        typer.echo(f"CSS matches: {result.css.count}")
        for match in result.css.matches:
            typer.echo(f"- {match.text} | {match.href or ''}")
    if result.xpath:
        typer.echo(f"XPath matches: {result.xpath.count}")
        for match in result.xpath.matches:
            typer.echo(f"- {match.text} | {match.href or ''}")


@app.command("debug-selectors")
def debug_selectors(
    selectors_file: Path = typer.Option(..., help="JSON file with css/xpath selectors"),
    html: Optional[Path] = typer.Option(None, help="HTML file path"),
    url: Optional[str] = typer.Option(None, help="Live URL"),
    report: Optional[Path] = typer.Option(None, help="Write selector_report.json"),
    driver: str = typer.Option("chrome", help="Browser driver for live URL"),
    headed: bool = typer.Option(False, help="Run in headed mode"),
):
    payload = json.loads(selectors_file.read_text(encoding="utf-8"))
    css = payload.get("css")
    xpath = payload.get("xpath")
    result = run_selector_playground(
        html_path=html,
        url=url,
        css=css,
        xpath=xpath,
        report_path=report,
        driver_name=driver,
        headless=not headed,
    )
    if result.css:
        typer.echo(f"CSS matches: {result.css.count}")
        for match in result.css.matches:
            typer.echo(f"- {match.text} | {match.href or ''}")
    if result.xpath:
        typer.echo(f"XPath matches: {result.xpath.count}")
        for match in result.xpath.matches:
            typer.echo(f"- {match.text} | {match.href or ''}")
