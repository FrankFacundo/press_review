from datetime import datetime, timedelta, timezone

from luxnews.utils import is_within_last_days


def test_is_within_last_days():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    old = now - timedelta(days=10)
    assert is_within_last_days(recent, 2, now=now) is True
    assert is_within_last_days(old, 2, now=now) is False
