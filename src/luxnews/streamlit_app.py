from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import streamlit as st

from luxnews.config import (
    RunConfig,
    get_default_jobs,
    get_default_output_dir,
    get_playwright_cache_dir,
    is_valid_env_key,
    normalize_media_ids,
    read_env_file,
    write_env_file,
)
from luxnews.core import LuxNewsRunner
from luxnews.media.registry import selectable_media_ids
from luxnews.browser_utils import close_active_driver
from luxnews.selector_playground import run_selector_playground


st.set_page_config(page_title="LuxNews", layout="wide")

SENSITIVE_ENV_KEY_MARKERS = (
    "PASSWORD",
    "SECRET",
    "TOKEN",
    "API_KEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
)


def _get_saved_run_results() -> list[dict]:
    return st.session_state.setdefault("run_results", [])


def _set_saved_run_results(results: list[dict]) -> None:
    st.session_state["run_results"] = results


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


def _render_stop_button() -> None:
    if st.button("Stop crawler browser", type="secondary", key="stop_browser"):
        if close_active_driver():
            st.info("Crawler browser closed.")
        else:
            st.info("No crawler browser is currently running.")


def _is_sensitive_env_key(key: str) -> bool:
    upper_key = key.upper()
    return any(marker in upper_key for marker in SENSITIVE_ENV_KEY_MARKERS)


def _render_env_settings() -> None:
    env_path = Path(".env")
    env_values = read_env_file(env_path)
    generation = st.session_state.setdefault("env_editor_generation", 0)

    st.subheader(".env Variables")
    st.caption(f"Loaded from: {env_path.resolve()}")

    saved_message = st.session_state.pop("env_save_message", None)
    if saved_message:
        st.success(saved_message)

    if not env_path.exists():
        st.info("No .env file exists yet. Add a variable below to create one.")
    elif not env_values:
        st.info("The .env file exists but does not contain any variable assignments.")

    show_sensitive = st.checkbox(
        "Show sensitive values",
        value=False,
        key="env_show_sensitive",
    )

    with st.form(f"env_editor_{generation}"):
        updated_values: dict[str, str] = {}
        for key, value in env_values.items():
            input_type = (
                "password" if _is_sensitive_env_key(key) and not show_sensitive else "default"
            )
            updated_values[key] = st.text_input(key, value=value, type=input_type)

        st.markdown("**Add variable**")
        new_key = st.text_input("Variable name")
        new_value = st.text_input("Variable value")
        submitted = st.form_submit_button("Save .env")

    if not submitted:
        return

    normalized_new_key = new_key.strip()
    if normalized_new_key:
        if not is_valid_env_key(normalized_new_key):
            st.error(
                "Variable names must start with a letter or underscore and use only "
                "letters, numbers, and underscores."
            )
            return
        if normalized_new_key in updated_values:
            st.error(f"{normalized_new_key} already exists.")
            return
        updated_values[normalized_new_key] = new_value

    try:
        write_env_file(updated_values, env_path)
    except (OSError, ValueError) as exc:
        st.error(f"Could not save .env: {exc}")
        return

    st.session_state["env_editor_generation"] = generation + 1
    st.session_state["env_save_message"] = ".env saved. New values will be used by subsequent runs."
    st.rerun()


st.title("LuxNews")
_render_stop_button()

run_tab, selector_tab, settings_tab = st.tabs(["Runs", "Selector Playground", "Settings"])

with run_tab:
    st.subheader("Daily Jobs")
    if st.button("Generate today's 2 default PDFs"):
        defaults = get_default_jobs()
        batch_results = []
        for job in defaults.values():
            st.write(f"Running {job.name}...")
            cfg = RunConfig(
                keywords=job.keywords,
                medias=job.medias,
                business_days_before=job.business_days_before,
                cutoff_hour=job.cutoff_hour,
                headless=True,
            )
            result = _run_with_progress(cfg, job_name=job.name)
            batch_results.append(result)
        _set_saved_run_results(batch_results)

    st.subheader("Advanced Mode")
    media_options = selectable_media_ids()
    media_option_set = set(media_options)
    defaults = get_default_jobs()
    preset_options = [*defaults.keys(), "custom"]

    def _selectable_media_ids(media_ids: list[str]) -> list[str]:
        return [
            media_id
            for media_id in normalize_media_ids(media_ids)
            if media_id in media_option_set
        ]

    def _load_advanced_preset(preset_name: str) -> None:
        if preset_name not in defaults:
            return
        preset = defaults[preset_name]
        st.session_state["advanced_keywords_raw"] = "\n".join(preset.keywords)
        st.session_state["advanced_medias"] = _selectable_media_ids(preset.medias)
        st.session_state["advanced_business_days_before"] = preset.business_days_before
        st.session_state["advanced_cutoff_hour"] = preset.cutoff_hour

    if "advanced_preset" not in st.session_state:
        st.session_state["advanced_preset"] = "daily_job_1" if "daily_job_1" in defaults else next(iter(defaults), "custom")
    if (
        "advanced_keywords_raw" not in st.session_state
        or "advanced_medias" not in st.session_state
        or "advanced_business_days_before" not in st.session_state
        or "advanced_cutoff_hour" not in st.session_state
    ):
        _load_advanced_preset(st.session_state["advanced_preset"])
    else:
        st.session_state["advanced_medias"] = _selectable_media_ids(
            st.session_state["advanced_medias"]
        )

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
    business_days_before = st.number_input(
        "Business days before",
        min_value=0,
        max_value=30,
        key="advanced_business_days_before",
    )
    cutoff_hour = st.number_input(
        "Cutoff hour",
        min_value=0,
        max_value=23,
        key="advanced_cutoff_hour",
    )
    driver = "playwright"
    st.caption(f"Playwright browser cache: {get_playwright_cache_dir()}")
    headless = st.checkbox("Headless", value=False)
    output_dir = st.text_input("Output directory", value=str(get_default_output_dir()))
    st.markdown("**Debug options**")
    debug = st.checkbox("Enable debug artifacts", value=False)
    open_devtools = st.checkbox("Open DevTools (best-effort)", value=False)
    search_use_browser = st.checkbox("Use browser automation for search pages", value=True)

    if st.button("Run custom job"):
        keywords = _parse_keywords(keywords_raw)
        if not keywords or not selected_medias:
            st.error("Provide at least one keyword and one media.")
        else:
            cfg = RunConfig(
                keywords=keywords,
                medias=selected_medias,
                business_days_before=int(business_days_before),
                cutoff_hour=int(cutoff_hour),
                driver=driver,
                headless=headless,
                output_dir=output_dir,
                debug=debug,
                open_devtools=open_devtools,
                search_use_browser=search_use_browser,
            )
            result = _run_with_progress(cfg)

            _set_saved_run_results([result])

    for saved_result in _get_saved_run_results():
        _render_results(saved_result)

with selector_tab:
    st.subheader("Selector Playground")
    html_path = st.text_input("HTML file path (optional)")
    url = st.text_input("Live URL (optional)")
    css = st.text_input("CSS selector")
    xpath = st.text_input("XPath selector")
    limit = st.number_input("Limit", min_value=1, max_value=20, value=5)
    driver = "playwright"
    headless = st.checkbox("Headless", value=False, key="selector_headless")
    st.caption(f"Playwright browser cache: {get_playwright_cache_dir()}")

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

with settings_tab:
    _render_env_settings()
