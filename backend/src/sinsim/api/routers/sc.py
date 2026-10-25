"""Cortocircuito IEC 60909 desde la interfaz (FR-069, FR-071; contracts/openapi-sc.yaml).

Síncrono (research R1): `POST` devuelve el resultado completo, reutilizando el `sc.json` vigente
del caso si lo hay; `GET` solo lee el guardado.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from sinsim.api.routers.snapshots import ctx_of
from sinsim.bootstrap import AppContext
from sinsim.domain.entities import LoadedSnapshot, Run, ShortCircuitAnalysis
from sinsim.services import sc
from sinsim.services import snapshots as snapshot_service

router = APIRouter(tags=["sc"])


class ScRequest(BaseModel):
    """Cuerpo opcional: limitar la respuesta a estas barras (`bus_id` o `SUBESTACION kV`)."""

    buses: list[str] = []


def _snapshot(ctx: AppContext, run: Run) -> LoadedSnapshot:
    return snapshot_service.load_verified(ctx.snapshots, run.trace.snapshot_date)


@router.post("/runs/{run_id}/sc", response_model=ShortCircuitAnalysis)
def calculate_sc(
    run_id: str, request: Request, body: ScRequest | None = None
) -> ShortCircuitAnalysis:
    """Calcula (o recupera) el cortocircuito del caso de la ejecución (FR-069, FR-071)."""
    ctx = ctx_of(request)
    run = ctx.cases.get_run(run_id)
    snapshot = _snapshot(ctx, run)
    net_json = ctx.cases.get_net_json(run.case_id)
    analysis = sc.get_or_calculate(
        case_id=run.case_id,
        run_id=run.run_id,
        trace=run.trace,
        net_json=net_json,
        snapshot=snapshot,
        cfg=ctx.cfg,
        equivalences=ctx.equivalences,
        cases=ctx.cases,
    )
    return sc.select_buses(analysis, body.buses if body else [])


@router.get("/runs/{run_id}/sc", response_model=ShortCircuitAnalysis)
def get_sc(run_id: str, request: Request) -> ShortCircuitAnalysis:
    """Resultado guardado vigente del caso, o `SC_NOT_FOUND`."""
    ctx = ctx_of(request)
    run = ctx.cases.get_run(run_id)
    return sc.current(run.case_id, _snapshot(ctx, run), ctx.cfg, ctx.equivalences, ctx.cases)
