"""SC-003, SC-004 y meta de rendimiento sobre el snapshot real incluido en el repositorio.

Requiere `data/paratec/2026-10-20/` y las equivalencias de `data/equivalencias/`.
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pytest

from sinsim.bootstrap import build_context
from sinsim.services import snapshots as snapshot_service
from sinsim.services.build_case import build_case
from sinsim.services.run_flow import run_flow

INCLUDED = date(2026, 10, 20)
ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.included_snapshot


@pytest.fixture(scope="module")
def ctx(tmp_path_factory: pytest.TempPathFactory):
    if not (ROOT / "data" / "paratec" / INCLUDED.isoformat()).exists():
        pytest.skip("el snapshot incluido no está en data/paratec/")
    return build_context(ROOT, cases_dir=tmp_path_factory.mktemp("cases"))


@pytest.fixture(scope="module")
def snapshot(ctx):
    return snapshot_service.load_verified(ctx.snapshots, INCLUDED)


# Con la demanda completa ubicada (nodos_demanda.csv curada, 0.7.1) el pico del periodo 21 colapsa
# en Mompox–Magangué: con las mismas cargas que el modelo de XM, el soporte de reactiva del modelo
# (taps en neutro, sin elevadores en el flujo, condensadores fijos) no alcanza. Antes pasaba solo
# porque faltaban 1,4 GW de demanda. Se corrige con el modelo de tensión, no con las equivalencias.
_PICO_SIN_SOPORTE = pytest.mark.xfail(
    strict=True,
    reason="colapso de tensión en el pico: falta modelo de reactiva (ver CHANGELOG 0.7.1)",
)


@pytest.mark.parametrize(
    "period", [pytest.param(p, marks=_PICO_SIN_SOPORTE) if p == 21 else p for p in range(1, 25)]
)
def test_every_period_converges_with_coverage_and_time(ctx, snapshot, period: int):
    t0 = time.perf_counter()
    built = build_case(
        snapshot=snapshot,
        dispatch_snapshot=snapshot,
        period=period,
        equivalences=ctx.equivalences,
        cfg=ctx.cfg,
        sinsim_version=ctx.version,
    )
    run = run_flow(built.case, built.net, "ac", ctx.cfg, ctx.version)
    elapsed = time.perf_counter() - t0
    assert run.status == "convergio", run.diagnostics
    assert built.case.quality.balance.coverage_pct >= 95.0, built.case.quality.balance
    assert elapsed < 30.0, f"periodo {period}: {elapsed:.1f} s"
    assert run.result is not None and run.result.summary.p_losses_mw > 0
