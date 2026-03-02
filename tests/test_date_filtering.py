from datetime import datetime, timezone

from luxnews.config import RunConfig


def test_resolve_search_cutoff_tuesday_afternoon():
    config = RunConfig(
        keywords=["BNP"],
        medias=["rtl.lu"],
        business_days_before=1,
        cutoff_hour=11,
    )
    now = datetime(2026, 2, 24, 15, 0, tzinfo=timezone.utc)  # Tuesday
    cutoff = config.resolve_search_cutoff(now=now)
    assert cutoff.date().isoformat() == "2026-02-23"  # Monday
    assert cutoff.hour == 11
    assert cutoff.minute == 0


def test_resolve_search_cutoff_wednesday_morning():
    config = RunConfig(
        keywords=["BNP"],
        medias=["rtl.lu"],
        business_days_before=1,
        cutoff_hour=11,
    )
    now = datetime(2026, 2, 25, 6, 0, tzinfo=timezone.utc)  # Wednesday
    cutoff = config.resolve_search_cutoff(now=now)
    assert cutoff.date().isoformat() == "2026-02-24"  # Tuesday
    assert cutoff.hour == 11
    assert cutoff.minute == 0


def test_resolve_search_cutoff_monday_uses_friday():
    config = RunConfig(
        keywords=["BNP"],
        medias=["rtl.lu"],
        business_days_before=1,
        cutoff_hour=11,
    )
    now = datetime(2026, 2, 23, 9, 0, tzinfo=timezone.utc)  # Monday
    cutoff = config.resolve_search_cutoff(now=now)
    assert cutoff.date().isoformat() == "2026-02-20"  # Friday
    assert cutoff.hour == 11
    assert cutoff.minute == 0


def test_resolve_search_cutoff_two_business_days_back_on_monday():
    config = RunConfig(
        keywords=["BNP"],
        medias=["rtl.lu"],
        business_days_before=2,
        cutoff_hour=11,
    )
    now = datetime(2026, 2, 23, 9, 0, tzinfo=timezone.utc)  # Monday
    cutoff = config.resolve_search_cutoff(now=now)
    assert cutoff.date().isoformat() == "2026-02-19"  # Thursday
    assert cutoff.hour == 11
    assert cutoff.minute == 0
