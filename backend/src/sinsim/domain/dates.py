"""Regla de fechas admitidas (FR-039).

XM publica el despacho programado la víspera, así que la última fecha admitida es el día
siguiente al actual (D+1). Cualquier fecha posterior es `INVALID_DATE`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo

from sinsim.domain.errors import DomainError

DAYS_AHEAD = 1
"""Días hacia adelante admitidos: el despacho de mañana ya está publicado hoy."""


def latest_allowed_date(today: date | None = None) -> date:
    """Última fecha admitida: hoy + `DAYS_AHEAD`."""
    return (today or date.today()) + timedelta(days=DAYS_AHEAD)


def ensure_allowed(value: date, today: date | None = None) -> date:
    """Devuelve `value` si no pasa de D+1; si no, lanza `INVALID_DATE`."""
    limit = latest_allowed_date(today)
    if value > limit:
        raise DomainError("INVALID_DATE", f"fecha {value} posterior a {limit} (D+1)")
    return value


def parse_allowed(text: str, today: date | None = None) -> date:
    """Convierte `YYYY-MM-DD` y aplica `ensure_allowed`."""
    try:
        value = date.fromisoformat(text)
    except ValueError as exc:
        raise DomainError("INVALID_DATE", f"fecha {text!r}") from exc
    return ensure_allowed(value, today)


def suggested_date(now: datetime, published_at: time, tz: tzinfo) -> date:
    """Fecha que se propone por defecto.

    Mañana si en `tz` ya pasó la hora a la que XM suele publicar el despacho programado de mañana
    (`published_at`); hoy si todavía no.
    """
    local = now.astimezone(tz)
    return local.date() + timedelta(days=1) if local.time() >= published_at else local.date()
