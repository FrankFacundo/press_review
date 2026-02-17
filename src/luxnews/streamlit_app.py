from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import streamlit as st

from luxnews.config import RunConfig, get_default_jobs
from luxnews.core import LuxNewsRunner
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.selector_playground import run_selector_playground


st.set_page_config(page_title="LuxNews", layout="wide")


def _parse_keywords(raw: str) -> list[str]:
    if not raw:
        return []
    parts = []
    for line in raw.replace(",", "\n").splitlines():
        cleaned = line.strip()
        if cleaned:
            parts.append(cleaned)
    return parts


def _render_results(result: dict) -> None:
    st.success(f"Run {result['run_id']} complete")
    st.write(f"Merged PDF: {result['merged_pdf']}")
    st.write(f"Matches JSON: {result['matches_json']}")

    merged_path = Path(result["merged_pdf"])
    if merged_path.exists():
        st.download_button(
            "Download merged PDF",
            merged_path.read_bytes(),
            file_name=merged_path.name,
        )

    json_path = Path(result["matches_json"])
    if json_path.exists():
        st.download_button(
            "Download matches.json",
            json_path.read_bytes(),
            file_name=json_path.name,
        )

    records = result.get("records", [])
    if records:
        st.dataframe(
            [
                {
                    "media": record.media,
                    "title": record.title,
                    "url": record.url,
                    "status": record.status,
                    "matched_keywords": ", ".join(record.matched_keywords),
                }
                for record in records
            ]
        )


def _run_with_progress(config: RunConfig, job_name: Optional[str] = None) -> dict:
    total = len(config.medias)
    progress = st.progress(0.0)
    status_box = st.empty()
    status_rows = []

    def callback(payload: dict) -> None:
        event = payload.get("event")
        if event == "media_start":
            status_box.info(f"Starting {payload.get('media')}")
        if event == "media_done":
            status_rows.append(
                {
                    "media": payload.get("media"),
                    "status": payload.get("status"),
                    "errors": "; ".join(payload.get("errors") or []),
                }
            )
            status_box.table(status_rows)
        index = payload.get("index")
        if index:
            progress.progress(min(index / max(total, 1), 1.0))

    runner = LuxNewsRunner(config, progress_callback=callback)
    return runner.run_job(job_name=job_name)


st.title("LuxNews")

run_tab, selector_tab = st.tabs(["Runs", "Selector Playground"])

with run_tab:
    st.subheader("Daily Jobs")
    if st.button("Generate today's 2 default PDFs"):
        defaults = get_default_jobs()
        for job in defaults.values():
            st.write(f"Running {job.name}...")
            cfg = RunConfig(
                keywords=job.keywords,
                medias=job.medias,
                last_days=job.last_days,
                headless=True,
            )
            result = _run_with_progress(cfg, job_name=job.name)
            _render_results(result)

    st.subheader("Advanced Mode")
    media_options = list(MEDIA_REGISTRY.keys())
    defaults = get_default_jobs()
    preset_options = [*defaults.keys(), "custom"]

    def _load_advanced_preset(preset_name: str) -> None:
        if preset_name not in defaults:
            return
        preset = defaults[preset_name]
        st.session_state["advanced_keywords_raw"] = "\n".join(preset.keywords)
        st.session_state["advanced_medias"] = preset.medias
        st.session_state["advanced_last_days"] = preset.last_days

    if "advanced_preset" not in st.session_state:
        st.session_state["advanced_preset"] = "daily_job_1" if "daily_job_1" in defaults else next(iter(defaults), "custom")
    if (
        "advanced_keywords_raw" not in st.session_state
        or "advanced_medias" not in st.session_state
        or "advanced_last_days" not in st.session_state
    ):
        _load_advanced_preset(st.session_state["advanced_preset"])

    def _on_advanced_preset_change() -> None:
        _load_advanced_preset(st.session_state["advanced_preset"])

    st.selectbox(
        "Preset setup",
        preset_options,
        key="advanced_preset",
        format_func=lambda name: "Custom" if name == "custom" else name,
        on_change=_on_advanced_preset_change,
    )

    keywords_raw = st.text_area("Keywords (comma or newline separated)", key="advanced_keywords_raw")
    selected_medias = st.multiselect("Medias", media_options, key="advanced_medias")
    last_days = st.number_input("Last days", min_value=1, max_value=30, key="advanced_last_days")
    driver = st.selectbox("Driver", ["chrome", "edge"])
    headless = st.checkbox("Headless", value=False)
    output_dir = st.text_input("Output directory", value="outputs")

    st.markdown("**Debug options**")
    debug = st.checkbox("Enable debug artifacts", value=False)
    open_devtools = st.checkbox("Open DevTools (best-effort)", value=False)
    search_use_selenium = st.checkbox("Use Selenium for search pages", value=True)

    if st.button("Run custom job"):
        keywords = _parse_keywords(keywords_raw)
        if not keywords or not selected_medias:
            st.error("Provide at least one keyword and one media.")
        else:
            cfg = RunConfig(
                keywords=keywords,
                medias=selected_medias,
                last_days=int(last_days),
                driver=driver,
                headless=headless,
                output_dir=output_dir,
                debug=debug,
                open_devtools=open_devtools,
                search_use_selenium=search_use_selenium,
            )
            result = _run_with_progress(cfg)
            _render_results(result)

with selector_tab:
    st.subheader("Selector Playground")
    html_path = st.text_input("HTML file path (optional)")
    url = st.text_input("Live URL (optional)")
    css = st.text_input("CSS selector")
    xpath = st.text_input("XPath selector")
    limit = st.number_input("Limit", min_value=1, max_value=20, value=5)
    driver = st.selectbox("Driver", ["chrome", "edge"], key="selector_driver")
    headless = st.checkbox("Headless", value=False, key="selector_headless")

    if st.button("Run selectors"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            screenshot_path = Path(tmp_dir) / "page.png"
            result = run_selector_playground(
                html_path=Path(html_path) if html_path else None,
                url=url or None,
                css=css or None,
                xpath=xpath or None,
                limit=int(limit),
                screenshot_path=screenshot_path if url else None,
                driver_name=driver,
                headless=headless,
            )
            if result.screenshot_path:
                st.image(result.screenshot_path, caption="Live page screenshot")
            if result.css:
                st.write(f"CSS matches: {result.css.count}")
                st.json(
                    [
                        {"text": match.text, "href": match.href}
                        for match in result.css.matches
                    ]
                )
            if result.xpath:
                st.write(f"XPath matches: {result.xpath.count}")
                st.json(
                    [
                        {"text": match.text, "href": match.href}
                        for match in result.xpath.matches
                    ]
                )
