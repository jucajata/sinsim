"""FR-039: se admite hasta el día siguiente (D+1); después, `INVALID_DATE`."""

from __future__ import annotations

from datetime import date

import pytest

from sinsim.domain.dates import ensure_allowed, latest_allowed_date, parse_allowed
from sinsim.domain.errors import DomainError

TODAY = date(2026, 10, 21)


def test_latest_allowed_is_tomorrow():
    assert latest_allowed_date(TODAY) == date(2026, 10, 22)
    assert latest_allowed_date() == date.today() + (date(2026, 1, 2) - date(2026, 1, 1))


def test_today_and_tomorrow_are_allowed_but_not_later():
    assert ensure_allowed(TODAY, TODAY) == TODAY
    assert ensure_allowed(date(2026, 10, 22), TODAY) == date(2026, 10, 22)
    assert parse_allowed("2026-10-22", TODAY) == date(2026, 10, 22)
    with pytest.raises(DomainError) as exc:
        ensure_allowed(date(2026, 10, 23), TODAY)
    assert exc.value.code == "INVALID_DATE" and "D+1" in exc.value.detail
    assert "mañana" in exc.value.user_message


def test_malformed_date_is_invalid():
    with pytest.raises(DomainError) as exc:
        parse_allowed("2026-13-01", TODAY)
    assert exc.value.code == "INVALID_DATE"


def test_suggested_date_is_tomorrow_once_the_dispatch_is_usually_published():
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    from sinsim.domain.dates import suggested_date

    bogota = ZoneInfo("America/Bogota")
    published = time(15, 0)
    assert suggested_date(datetime(2026, 11, 9, 14, 59, tzinfo=bogota), published, bogota) == date(
        2026, 11, 9
    )
    assert suggested_date(datetime(2026, 11, 9, 15, 0, tzinfo=bogota), published, bogota) == date(
        2026, 11, 10
    )
    # La hora que cuenta es la de Colombia, aunque el reloj del equipo esté en otra zona:
    # 21:30 UTC son las 16:30 en Bogotá, ya publicado; 19:30 UTC son las 14:30, todavía no.
    utc = ZoneInfo("UTC")
    assert suggested_date(datetime(2026, 11, 9, 21, 30, tzinfo=utc), published, bogota) == date(
        2026, 11, 10
    )
    assert suggested_date(datetime(2026, 11, 9, 19, 30, tzinfo=utc), published, bogota) == date(
        2026, 11, 9
    )
    # Pasada la medianoche en UTC sigue siendo el día anterior en Bogotá.
    assert suggested_date(datetime(2026, 11, 10, 2, 0, tzinfo=utc), published, bogota) == date(
        2026, 11, 10
    )
