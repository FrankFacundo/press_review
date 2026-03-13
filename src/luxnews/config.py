from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Optional

APP_NAME = "LuxNews"


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env_file()


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_app_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("win"):
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    xdg_data_home = os.getenv("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def get_default_output_dir() -> Path:
    if is_packaged_app():
        return get_app_data_dir() / "outputs"
    return Path("outputs")


def resolve_output_dir(path: str | Path) -> Path:
    output_path = Path(path).expanduser()
    if output_path.is_absolute():
        return output_path
    if is_packaged_app():
        return get_app_data_dir() / output_path
    return output_path


@dataclass
class RunConfig:
    keywords: list[str]
    medias: list[str]
    business_days_before: int = 1
    cutoff_hour: int = 11
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
    wort_username: Optional[str] = field(default_factory=lambda: os.getenv("WORT_USERNAME"))
    wort_password: Optional[str] = field(
        default_factory=lambda: os.getenv("WORT_PASSWORD"),
        repr=False,
    )
    lessentiel_email: Optional[str] = field(
        default_factory=lambda: os.getenv("LESSENTIEL_EMAIL")
        or os.getenv("LESSENTIEL_USERNAME")
    )
    lessentiel_password: Optional[str] = field(
        default_factory=lambda: os.getenv("LESSENTIEL_PASSWORD"),
        repr=False,
    )
    contacto_email: Optional[str] = field(
        default_factory=lambda: os.getenv("CONTACTO_EMAIL")
    )
    contacto_password: Optional[str] = field(
        default_factory=lambda: os.getenv("CONTACTO_PASSWORD"),
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.business_days_before < 0:
            raise ValueError("business_days_before must be >= 0")
        if not 0 <= self.cutoff_hour <= 23:
            raise ValueError("cutoff_hour must be between 0 and 23")
        self.output_dir = str(resolve_output_dir(self.output_dir))

    def resolve_search_cutoff(self, now: Optional[datetime] = None) -> datetime:
        current = now.astimezone() if now else datetime.now().astimezone()
        target_date = current.date()
        remaining = self.business_days_before

        while remaining > 0:
            target_date -= timedelta(days=1)
            if target_date.weekday() < 5:  # Monday=0 ... Friday=4
                remaining -= 1

        return datetime.combine(
            target_date,
            dt_time(hour=self.cutoff_hour, minute=0),
            tzinfo=current.tzinfo,
        )


@dataclass
class JobConfig:
    name: str
    keywords: list[str]
    medias: list[str]
    business_days_before: int = 1
    cutoff_hour: int = 11


def get_default_jobs() -> dict[str, JobConfig]:
    return {
        "daily_job_1": JobConfig(
            name="daily_job_1",
            keywords=["BGL", "BNP PARIBAS", "ARVAL", "CARDIF", "MICROLUX", "BOB KIEFFER"],
            medias=[
                "rtl.lu",
                "delano.lu",
                "today.rtl.lu",
                "5minutes.rtl.lu",
                "lessentiel.lu/fr",
                "lequotidien.lu",
                "tageblatt.lu",
                "virgule.lu",
                "wort.lu",
                "contacto.lu",
                "luxtimes.lu",
                "infogreen.lu",
                "chronicle.lu",
                "siliconluxembourg.lu",
                "agefi.lu",
                "paperjam.lu",
                "gemengen.lu",
                "reporter.lu",
            ],
            business_days_before=1,
            cutoff_hour=11,
        ),
        "daily_job_2": JobConfig(
            name="daily_job_2",
            keywords=[
                "FMI",
                "Place financière",
                "Finanzplatz",
                "Financial centre",
                "Banque Centrale Luxembourg",
                "BCL",
                "Gilles Roth",
                "ABBL",
                "CSSF",
                "LFF",
                "Luxembourg for Finance",
                "BCEE",
                "Spuerkeess",
                "Banque de Luxembourg",
                "BIL",
                "ING",
                "Bancomat",
                "Geldautomat",
                "ATM",
                "Payconiq",
                "Phishing",
                "Blanchiment",
                "Geldwäsche",
                "Money laundering",
                "RSE",
                "ESG",
            ],
            medias=[
                "rtl.lu",
                "today.rtl.lu",
                "infos.rtl.lu",
                "reporter.lu",
                "wort.lu",
                "paperjam.lu",
                "lequotidien.lu",
                "infogreen.lu",
                "chronicle.lu",
                "siliconluxembourg.lu",
                "gemengen.lu",
            ],
            business_days_before=1,
            cutoff_hour=11,
        ),
    }


def resolve_jobs(config_name: str) -> list[JobConfig]:
    defaults = get_default_jobs()
    if config_name == "daily":
        return [defaults["daily_job_1"], defaults["daily_job_2"]]
    if config_name in defaults:
        return [defaults[config_name]]
    raise KeyError(f"Unknown config: {config_name}")
