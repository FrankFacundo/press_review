from __future__ import annotations

from types import SimpleNamespace

import luxnews.core as core_module
from luxnews.config import RunConfig
from luxnews.core import LuxNewsRunner


def test_ensure_luxtimes_login_uses_wort_credentials(monkeypatch) -> None:
    calls: list[dict] = []
    runner = LuxNewsRunner(
        RunConfig(
            keywords=["k"],
            medias=["luxtimes.lu"],
            wort_username="user@example.com",
            wort_password="secret",
            wait_timeout=12.0,
        )
    )

    def _login_luxtimes(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(core_module, "login_luxtimes", _login_luxtimes)

    driver = SimpleNamespace()
    assert runner._ensure_luxtimes_login(driver) is True
    assert runner._ensure_luxtimes_login(driver) is True

    assert calls == [
        {
            "driver": driver,
            "username": "user@example.com",
            "password": "secret",
            "wait_timeout": 12.0,
        }
    ]


def test_ensure_luxtimes_login_requires_wort_credentials() -> None:
    runner = LuxNewsRunner(
        RunConfig(
            keywords=["k"],
            medias=["luxtimes.lu"],
            wort_username="",
            wort_password="",
        )
    )

    assert runner._ensure_luxtimes_login(SimpleNamespace()) is False
