"""`GET /api/snapshots` (FR-002) y descarga de una fecha desde la interfaz (FR-038).

La descarga corre en el servidor local con la misma lógica que `sinsim scrape`; se acepta con
202 y se sigue por `GET /api/snapshots/descargas/{job_id}`. Nunca es automática (NG-09).
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, status

from sinsim.bootstrap import AppContext
from sinsim.domain.dates import ensure_allowed, suggested_date
from sinsim.domain.entities import ScrapeJob, SnapshotSummary, SuggestedDate
from sinsim.services import snapshots as snapshot_service
from sinsim.services.scrape import scrape_snapshot

router = APIRouter(tags=["snapshots"])


def ctx_of(request: Request) -> AppContext:
    """Contexto de la aplicación."""
    ctx: AppContext = request.app.state.ctx
    return ctx


@router.get("/snapshots", response_model=list[SnapshotSummary])
def list_snapshots(request: Request) -> list[SnapshotSummary]:
    """Lista las fechas disponibles y qué datos tiene cada una."""
    return snapshot_service.list_snapshots(ctx_of(request).snapshots)


@router.get("/snapshots/fecha-sugerida", response_model=SuggestedDate)
def get_suggested_date(request: Request) -> SuggestedDate:
    """Fecha por defecto: mañana desde la hora en que XM suele publicar el despacho, hoy antes."""
    cfg = ctx_of(request).cfg.config.scraper
    tz = ZoneInfo(cfg.timezone)
    published_at = time.fromisoformat(cfg.dispatch_published_at)
    return SuggestedDate(
        date=suggested_date(datetime.now(tz), published_at, tz),
        published_at=cfg.dispatch_published_at,
        timezone=cfg.timezone,
    )


@router.post(
    "/snapshots/{fecha}/descarga",
    response_model=ScrapeJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_scrape(fecha: date, request: Request) -> ScrapeJob:
    """Inicia la descarga de PARATEC, despacho y demanda de una fecha (FR-038, hasta D+1)."""
    ctx = ctx_of(request)
    day = ensure_allowed(fecha)
    snapshot_service.require_absent(ctx.snapshots, day)
    return ctx.scrape_runner.start(day, lambda on_step: scrape_snapshot(ctx, day, on_step=on_step))


@router.get("/snapshots/descargas/{job_id}", response_model=ScrapeJob)
def get_scrape(job_id: str, request: Request) -> ScrapeJob:
    """Estado de una descarga iniciada desde la interfaz (FR-038)."""
    return ctx_of(request).scrape_runner.get(job_id)
