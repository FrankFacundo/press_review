from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RunConfig:
    keywords: list[str]
    medias: list[str]
    last_days: int = 2
    driver: str = "chrome"
    headless: bool = True
    output_dir: str = "outputs"
    max_pages: int = 1
    max_results: int = 200
    debug: bool = False
    pause: bool = False
    pause_on_error: bool = False
    open_devtools: bool = False
    rate_limit_seconds: float = 0.5
    request_timeout: float = 20.0
    page_timeout: float = 30.0
    wait_timeout: float = 20.0
    search_use_selenium: bool = False
    extra_user_agent: Optional[str] = None


@dataclass
class JobConfig:
    name: str
    keywords: list[str]
    medias: list[str]
    last_days: int = 2


def get_default_jobs() -> dict[str, JobConfig]:
    return {
        "daily_job_1": JobConfig(
            name="daily_job_1",
            keywords=["BGL", "BNP PARIBAS", "ARVAL", "CARDIF", "MICROLUX", "BOB KIEFFER"],
            medias=["rtl.lu", "delano.lu"],
            last_days=2,
        ),
        "daily_job_2": JobConfig(
            name="daily_job_2",
            keywords=["FMI", "PLACE FINANCIÈRE", "BCL", "CSSF"],
            medias=["rtl.lu", "virgule.lu"],
            last_days=2,
        ),
    }


def resolve_jobs(config_name: str) -> list[JobConfig]:
    defaults = get_default_jobs()
    if config_name == "daily":
        return [defaults["daily_job_1"], defaults["daily_job_2"]]
    if config_name in defaults:
        return [defaults[config_name]]
    raise KeyError(f"Unknown config: {config_name}")
