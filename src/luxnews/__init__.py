"""LuxNews media monitoring package."""

from __future__ import annotations

from typing import Any

__all__ = ["LuxNewsRunner", "RunConfig", "get_default_jobs"]


def __getattr__(name: str) -> Any:
    if name == "LuxNewsRunner":
        from luxnews.core import LuxNewsRunner

        return LuxNewsRunner
    if name == "RunConfig":
        from luxnews.config import RunConfig

        return RunConfig
    if name == "get_default_jobs":
        from luxnews.config import get_default_jobs

        return get_default_jobs
    raise AttributeError(name)
