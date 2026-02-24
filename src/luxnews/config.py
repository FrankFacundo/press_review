from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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
    wort_username: Optional[str] = field(default_factory=lambda: os.getenv("WORT_USERNAME"))
    wort_password: Optional[str] = field(
        default_factory=lambda: os.getenv("WORT_PASSWORD"),
        repr=False,
    )


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
                "luxtimes.lu/en",
                "infogreen.lu",
                "chronicle.lu",
                "siliconluxembourg.lu",
                "agefi.lu",
                "paperjam.lu",
                "gemengen.lu",
                "reporter.lu",
            ],
            last_days=2,
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
                "bitcoin"
            ],
            medias=[
                "rtl.lu",
                "today.rtl.lu",
                "infos.rtl.lu",
                "reporter.lu",
                "wort.lu",
                "paperjam.lu"
            ],
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
