"""CLI `sinsim` (contracts/cli.md). Mensajes en español; códigos de salida 0–4 (constitución V)."""

from __future__ import annotations

import csv
import json
import logging
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import pandapower as pp
import typer

from sinsim.adapters.sources_to_pandapower.buses import class_kv
from sinsim.adapters.storage.export import write_export
from sinsim.adapters.storage.export_n1 import write_export_n1
from sinsim.adapters.storage.export_sc import write_export_sc
from sinsim.bootstrap import AppContext, build_context
from sinsim.domain.dates import parse_allowed
from sinsim.domain.entities import N1Analysis, Run, ShortCircuitAnalysis, StudyCase, Trace
from sinsim.domain.errors import DomainError, ExitCode
from sinsim.domain.shortcircuit import propose_step_ups
from sinsim.observability import log_event, new_trace_id
from sinsim.services import n1 as n1_service
from sinsim.services import sc as sc_service
from sinsim.services import snapshots as snapshot_service
from sinsim.services.build_case import apply_aliases, build_case
from sinsim.services.run_flow import run_flow, solver_settings
from sinsim.services.scrape import PARATEC_NOTICE, scrape_snapshot

log = logging.getLogger("sinsim.cli")
app = typer.Typer(
    help="Flujo de potencia del SIN sobre el despacho programado de XM.",
    no_args_is_help=True,
    rich_markup_mode=None,
)
snapshots_app = typer.Typer(help="Snapshots de datos disponibles.")
app.add_typer(snapshots_app, name="snapshots")
equivalencias_app = typer.Typer(help="Mantenimiento de las tablas de equivalencias.")
app.add_typer(equivalencias_app, name="equivalencias")


# --- utilidades --------------------------------------------------------------------


def _fail(exc: DomainError) -> None:
    typer.echo(f"Error ({exc.code}): {exc.user_message}", err=True)
    if exc.detail:
        typer.echo(f"  detalle: {exc.detail}", err=True)
    raise typer.Exit(code=int(exc.exit_code))


def parse_date(text: str) -> date:
    """Convierte `YYYY-MM-DD`; rechaza formatos inválidos y fechas posteriores a D+1 (FR-039)."""
    return parse_allowed(text)


def _context() -> AppContext:
    new_trace_id()
    return build_context()


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


# --- snapshots list ------------------------------------------------------------------


@snapshots_app.command("list")
def snapshots_list(
    json_output: Annotated[bool, typer.Option("--json", help="Salida en JSON.")] = False,
) -> None:
    """Lista las fechas disponibles y qué datos tiene cada una (FR-002)."""
    try:
        ctx = _context()
        rows = snapshot_service.list_snapshots(ctx.snapshots)
    except DomainError as exc:
        _fail(exc)
        return
    if json_output:
        typer.echo(_dump([r.model_dump(mode="json") for r in rows]))
        return
    if not rows:
        typer.echo("No hay snapshots en data/paratec/. Ejecuta `sinsim scrape --fecha YYYY-MM-DD`.")
        return
    typer.echo(f"{'fecha':<12}| {'paratec':<8}| {'despacho':<9}| {'demanda':<8}| íntegro")
    for r in rows:
        typer.echo(
            f"{r.date.isoformat():<12}| {_si(r.has_paratec):<8}| {_si(r.has_dispatch):<9}| "
            f"{_si(r.has_demand):<8}| {_si(r.intact)}"
        )


def _si(value: bool) -> str:
    return "sí" if value else "no"


# --- run ------------------------------------------------------------------------------


def _print_case(case: StudyCase) -> None:
    q, b = case.quality, case.quality.balance
    typer.echo("── Reporte de calidad del caso ──")
    typer.echo(
        f"Generación programada: {b.p_scheduled_total_mw:,.1f} MW | ubicada: "
        f"{b.p_located_mw:,.1f} MW ({b.coverage_pct:.1f} %) | no ubicada: "
        f"{b.p_unlocated_mw:,.1f} MW"
    )
    typer.echo(
        f"Demanda asignada: {b.p_demand_mw:,.1f} MW | no ubicada: {b.p_demand_unlocated_mw:,.1f} MW"
        f" | diferencia generación − demanda: {b.difference_mw:,.1f} MW"
    )
    typer.echo(
        f"Recursos no ubicados: {len(q.unlocated_resources)} | nodos de demanda no ubicados: "
        f"{len(q.unlocated_demand)} | traslados a frontera: {len(q.transfers)} | excluidos: "
        f"{len(q.excluded)} | imputados: {len(q.imputed)} | no modelados: {len(q.not_modeled)}"
    )
    lost = sum(i.p_gen_lost_mw for i in q.islands[1:])
    typer.echo(
        f"Islas: {len(q.islands)} (energizada: {q.islands[0].n_buses if q.islands else 0} barras; "
        f"{lost:,.1f} MW de generación fuera)"
    )
    for issue in q.physical_issues[:5]:
        typer.echo(f"  validación física: {issue}")
    for w in case.warnings:
        typer.echo(f"  ⚠ {w}")


def _print_run(run: Run) -> None:
    t = run.trace
    typer.echo(f"── {run.label} ──")
    typer.echo(
        f"Snapshot PARATEC: {t.snapshot_date} | despacho: {t.dispatch_date} periodo {t.period} | "
        f"flujo: {t.flow_type} | pandapower {t.pandapower_version} | sinsim {t.sinsim_version}"
    )
    typer.echo(f"Solver: {t.solver.model_dump()} | caso: {t.case_id}")
    typer.echo(f"Estado: {run.status}")
    if run.result is None:
        d = run.diagnostics
        if d is not None:
            typer.echo(
                f"Diagnóstico: {d.iterations} iteraciones, desbalance máximo "
                f"{d.max_mismatch_mva:,.2f} MVA ({d.basis})"
            )
            for w in d.worst_buses:
                typer.echo(f"  {w.bus}: {w.mismatch_mva:,.2f} MVA")
        return
    s = run.result.summary
    typer.echo(
        f"Generación {s.p_gen_mw:,.1f} MW | carga {s.p_load_mw:,.1f} MW | pérdidas "
        f"{s.p_losses_mw:,.1f} MW | ajuste de la referencia {s.slack_adjust_total_mw:,.1f} MW"
    )
    typer.echo(f"Violaciones de tensión: {s.n_voltage_violations} | sobrecargas: {s.n_overloads}")
    worst_v = sorted(run.result.buses, key=lambda b: abs(b.vm_pu - 1.0), reverse=True)[:10]
    typer.echo("Peores tensiones (pu / kV):")
    for b in worst_v:
        flag = f" [{b.violation}]" if b.violation else ""
        typer.echo(f"  {b.bus_id}: {b.vm_pu:.3f} pu / {b.vm_kv:.1f} kV{flag}")
    branches = sorted(
        run.result.lines + run.result.trafos, key=lambda x: x.loading_percent, reverse=True
    )[:10]
    typer.echo("Mayores cargabilidades (%):")
    for br in branches:
        flag = " [sobrecarga]" if br.overload else ""
        typer.echo(f"  {br.element_id}: {br.loading_percent:.1f} %{flag}")


@app.command()
def run(
    fecha: Annotated[
        str, typer.Option("--fecha", help="Fecha del snapshot de PARATEC (YYYY-MM-DD).")
    ],
    periodo: Annotated[int, typer.Option("--periodo", help="Periodo horario 1–24.")],
    fecha_despacho: Annotated[
        str | None, typer.Option("--fecha-despacho", help="Snapshot del despacho y la demanda.")
    ] = None,
    tipo: Annotated[str, typer.Option("--tipo", help="ac o dc.")] = "ac",
    exportar: Annotated[
        Path | None, typer.Option("--exportar", help="Directorio donde escribir la exportación.")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Salida en JSON.")] = False,
) -> None:
    """Construye el caso, imprime el reporte de calidad y corre el flujo (HU-1, HU-2, HU-4)."""
    try:
        if tipo not in ("ac", "dc"):
            raise DomainError(
                "INVALID_DATE", f"tipo {tipo!r}", user_message="El tipo debe ser ac o dc."
            )
        if not 1 <= periodo <= 24:
            raise DomainError("PERIOD_OUT_OF_RANGE", f"periodo {periodo}")
        snapshot_date = parse_date(fecha)
        dispatch_date = parse_date(fecha_despacho) if fecha_despacho else snapshot_date
        ctx = _context()
        snapshot = snapshot_service.load_verified(ctx.snapshots, snapshot_date)
        dispatch_snapshot = (
            snapshot
            if dispatch_date == snapshot_date
            else snapshot_service.load_verified(ctx.snapshots, dispatch_date)
        )
        built = build_case(
            snapshot=snapshot,
            dispatch_snapshot=dispatch_snapshot,
            period=periodo,
            equivalences=ctx.equivalences,
            cfg=ctx.cfg,
            sinsim_version=ctx.version,
            cases=ctx.cases,
        )
        result = run_flow(built.case, built.net, tipo, ctx.cfg, ctx.version)  # type: ignore[arg-type]
        ctx.cases.save_run(result)
        if exportar is not None:
            written = write_export(built.case, result, ctx.cfg.config.attribution.text, exportar)
            typer.echo(f"Exportación escrita en {exportar} ({len(written)} archivos)", err=True)
        log_event(
            log,
            "run terminado",
            case_id=built.case.case_id,
            run_id=result.run_id,
            status=result.status,
        )
    except DomainError as exc:
        _fail(exc)
        return
    if json_output:
        typer.echo(
            _dump(
                {"case": built.case.model_dump(mode="json"), "run": result.model_dump(mode="json")}
            )
        )
    else:
        _print_case(built.case)
        _print_run(result)
    raise typer.Exit(code=int(ExitCode.OK))


def _print_n1(analysis: N1Analysis) -> None:
    s = analysis.summary
    typer.echo("── Análisis de contingencias N-1 ──")
    typer.echo(
        f"Contingencias analizadas: {s.n_total} | cargabilidad: {s.n_loading} | tensiones: "
        f"{s.n_voltage} | aíslan demanda: {s.n_isolation} | sin solución: {s.n_unsolved} | "
        f"sin impacto: {s.n_no_impact} | {s.duration_s:,.1f} s con {analysis.workers} proceso(s)"
    )
    for lim in analysis.limits:
        typer.echo(f"  límite {lim.name}: {lim.value} ({lim.source})")
    typer.echo("Cargabilidad (10 primeras):")
    for r in analysis.loading[:10]:
        typer.echo(f"  {r.rank}. {r.outage.element_id} → {r.element_id}: {r.loading_percent:.1f} %")
    typer.echo("Tensiones (10 primeras):")
    for v in analysis.voltage[:10]:
        typer.echo(
            f"  {v.rank}. {v.outage.element_id} → {v.bus_id}: {v.vm_pu:.3f} pu "
            f"({v.deviation_pu:+.3f} pu fuera de banda)"
        )
    typer.echo("Aíslan demanda (10 primeras):")
    for i in analysis.isolation[:10]:
        typer.echo(
            f"  {i.rank}. {i.outage.element_id}: {i.n_buses} barras, "
            f"{i.p_demand_lost_mw:,.1f} MW sin servicio"
        )
    typer.echo("Sin solución:")
    for u in analysis.unsolved[:10]:
        typer.echo(
            f"  {u.outage.element_id}: {u.diagnostics.iterations} iteraciones, desbalance "
            f"{u.diagnostics.max_mismatch_mva:,.2f} MVA"
        )


@app.command()
def n1(
    fecha: Annotated[
        str, typer.Option("--fecha", help="Fecha del snapshot de PARATEC (YYYY-MM-DD).")
    ],
    periodo: Annotated[int, typer.Option("--periodo", help="Periodo horario 1–24.")],
    fecha_despacho: Annotated[
        str | None, typer.Option("--fecha-despacho", help="Snapshot del despacho y la demanda.")
    ] = None,
    salida: Annotated[
        Path | None,
        typer.Option("--salida", help="Carpeta de los CSV; por defecto ./n1-<fecha>-p<NN>/."),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Salida en JSON.")] = False,
) -> None:
    """Corre el flujo AC base y el análisis de contingencias N-1; escribe los listados (HU-8)."""
    try:
        if not 1 <= periodo <= 24:
            raise DomainError("PERIOD_OUT_OF_RANGE", f"periodo {periodo}")
        snapshot_date = parse_date(fecha)
        dispatch_date = parse_date(fecha_despacho) if fecha_despacho else snapshot_date
        ctx = _context()
        snapshot = snapshot_service.load_verified(ctx.snapshots, snapshot_date)
        dispatch_snapshot = (
            snapshot
            if dispatch_date == snapshot_date
            else snapshot_service.load_verified(ctx.snapshots, dispatch_date)
        )
        built = build_case(
            snapshot=snapshot,
            dispatch_snapshot=dispatch_snapshot,
            period=periodo,
            equivalences=ctx.equivalences,
            cfg=ctx.cfg,
            sinsim_version=ctx.version,
            cases=ctx.cases,
        )
        run = run_flow(built.case, built.net, "ac", ctx.cfg, ctx.version)
        ctx.cases.save_run(run)
        if run.status != "convergio":
            _print_run(run)
            raise DomainError(
                "N1_BASE_INVALID",
                f"el flujo base de {snapshot_date} periodo {periodo} no convergió",
            )
        net_json = ctx.cases.get_net_json(built.case.case_id)

        def progress(done: int, total: int) -> None:
            typer.echo(f"\rN-1: {done}/{total} contingencias", nl=False, err=True)

        analysis = n1_service.analyze(run, net_json, ctx.cfg, progress=progress)
        typer.echo("", err=True)
        out_dir = salida if salida is not None else Path(f"n1-{snapshot_date}-p{periodo:02d}")
        written = write_export_n1(analysis, ctx.cfg.config.attribution.text, out_dir)
        typer.echo(f"Análisis N-1 escrito en {out_dir} ({len(written)} archivos)", err=True)
        log_event(
            log,
            "n1 terminado",
            case_id=built.case.case_id,
            run_id=run.run_id,
            n_total=analysis.summary.n_total,
        )
    except DomainError as exc:
        _fail(exc)
        return
    if json_output:
        typer.echo(_dump(analysis.model_dump(mode="json")))
    else:
        _print_n1(analysis)
    raise typer.Exit(code=int(ExitCode.OK))


# --- sc (cortocircuito) ----------------------------------------------------------------


def _print_sc(analysis: ShortCircuitAnalysis) -> None:
    s, q = analysis.summary, analysis.quality
    typer.echo("── Cortocircuito trifásico máximo (IEC 60909) ──")
    t = analysis.trace
    typer.echo(
        f"Snapshot PARATEC: {t.snapshot_date} | periodo {t.period} | pandapower "
        f"{t.pandapower_version} | sinsim {t.sinsim_version} | caso: {analysis.case_id[:12]}…"
    )
    typer.echo(
        f"Barras: {s.n_buses} | fuentes síncronas: {s.n_sources_sync} | convertidores: "
        f"{s.n_sources_converter} | unidades con imputaciones: {s.n_imputed_units} | sin elevador: "
        f"{s.n_without_step_up} | sin fuente: {s.n_no_source} | {s.duration_s:.1f} s"
    )
    if s.max_ikss:
        typer.echo(f"Mayor Ikss: {s.max_ikss.bus_id} ({s.max_ikss.value:,.2f} kA)")
    if s.min_skss:
        typer.echo(f"Menor Sk: {s.min_skss.bus_id} ({s.min_skss.value:,.0f} MVA)")
    typer.echo(
        f"Elevadores casados: {q.step_up_equivalences.matched} "
        f"({q.step_up_equivalences.uncurated} sin curar) | enlaces sin aporte: "
        f"{len(q.sc_zero_sources)} | excluidos: {len(q.excluded)}"
    )
    typer.echo("Barras con mayor Ikss (kA / MVA / X/R):")
    for b in sorted(analysis.buses, key=lambda x: x.ikss_ka, reverse=True)[:10]:
        xr = f"{b.x_r:.2f}" if b.x_r is not None else "-"
        typer.echo(f"  {b.bus_id}: {b.ikss_ka:,.2f} kA / {b.skss_mva:,.0f} MVA / {xr}")
    for a in analysis.assumptions:
        typer.echo(f"  supuesto {a.id}: {a.text}")


@app.command()
def sc(
    fecha: Annotated[
        str, typer.Option("--fecha", help="Fecha del snapshot de PARATEC (YYYY-MM-DD).")
    ],
    periodo: Annotated[int, typer.Option("--periodo", help="Periodo horario 1–24.")],
    fecha_despacho: Annotated[
        str | None, typer.Option("--fecha-despacho", help="Snapshot del despacho y la demanda.")
    ] = None,
    barra: Annotated[
        list[str] | None,
        typer.Option("--barra", help="Barra del caso (`SUB|kV` o `SUB kV`); repetible."),
    ] = None,
    salida: Annotated[
        Path | None,
        typer.Option("--salida", help="Carpeta de los CSV; por defecto ./cc-<fecha>-p<NN>/."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Imprime solo el resultado en JSON; no escribe archivos.")
    ] = False,
) -> None:
    """Cortocircuito trifásico máximo IEC 60909 por barra; escribe CSV o JSON (HU-10)."""
    try:
        if not 1 <= periodo <= 24:
            raise DomainError("PERIOD_OUT_OF_RANGE", f"periodo {periodo}")
        snapshot_date = parse_date(fecha)
        dispatch_date = parse_date(fecha_despacho) if fecha_despacho else snapshot_date
        ctx = _context()
        snapshot = snapshot_service.load_verified(ctx.snapshots, snapshot_date)
        dispatch_snapshot = (
            snapshot
            if dispatch_date == snapshot_date
            else snapshot_service.load_verified(ctx.snapshots, dispatch_date)
        )
        built = build_case(
            snapshot=snapshot,
            dispatch_snapshot=dispatch_snapshot,
            period=periodo,
            equivalences=ctx.equivalences,
            cfg=ctx.cfg,
            sinsim_version=ctx.version,
            cases=ctx.cases,
        )
        trace = Trace(
            snapshot_date=snapshot_date,
            dispatch_date=dispatch_date,
            period=periodo,
            flow_type="ac",
            pandapower_version=pp.__version__,
            sinsim_version=ctx.version,
            solver=solver_settings(ctx.cfg),
            case_id=built.case.case_id,
        )
        analysis = sc_service.get_or_calculate(
            case_id=built.case.case_id,
            run_id=str(uuid.uuid4()),
            trace=trace,
            net_json=ctx.cases.get_net_json(built.case.case_id),
            snapshot=snapshot,
            cfg=ctx.cfg,
            equivalences=ctx.equivalences,
            cases=ctx.cases,
        )
        analysis = sc_service.select_buses(analysis, list(barra or []))
        if not json_output:
            out_dir = salida if salida is not None else Path(f"cc-{snapshot_date}-p{periodo:02d}")
            written = write_export_sc(analysis, out_dir)
            typer.echo(f"Cortocircuito escrito en {out_dir} ({len(written)} archivos)", err=True)
        log_event(
            log,
            "sc terminado",
            case_id=built.case.case_id,
            n_buses=len(analysis.buses),
            n_sources=len(analysis.sources),
        )
    except DomainError as exc:
        _fail(exc)
        return
    if json_output:
        typer.echo(_dump(analysis.model_dump(mode="json")))
    else:
        _print_sc(analysis)
    raise typer.Exit(code=int(ExitCode.OK))


@equivalencias_app.command("elevadores")
def equivalencias_elevadores(
    fecha: Annotated[
        str, typer.Option("--fecha", help="Fecha del snapshot de PARATEC (YYYY-MM-DD).")
    ],
    salida: Annotated[
        Path | None,
        typer.Option(
            "--salida", help="CSV a escribir; por defecto data/equivalencias/elevadores.csv."
        ),
    ] = None,
    vigente_desde: Annotated[
        str,
        typer.Option(
            "--vigente-desde",
            help="valid_from de las filas, como en las demás tablas (los elevadores existen antes "
            "del snapshot que los revela).",
        ),
    ] = "2020-01-01",
) -> None:
    """Propone `elevadores.csv` (unidad ↔ transformador elevador) para curarlo a mano (FR-065)."""
    try:
        snapshot_date = parse_date(fecha)
        valid_from = date.fromisoformat(vigente_desde)
        ctx = _context()
        snapshot = snapshot_service.load_verified(ctx.snapshots, snapshot_date)
        tables, _ = apply_aliases(
            snapshot.tables, ctx.equivalences.substation_aliases(snapshot_date)
        )
        units = tables.generators[tables.generators["state"] == "Operación"]
        rows = propose_step_ups(
            units,
            tables.trafos2w,
            tables.trafos3w,
            aliases={},
            class_of=class_kv,
            valid_from=valid_from,
        )
        out = salida if salida is not None else ctx.paths.equivalences / "elevadores.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(
                ["unit_id", "trafo_id", "method", "curated", "valid_from", "valid_to", "note"]
            )
            for r in rows:
                writer.writerow(
                    [r.unit_id, r.trafo_id, r.method, "false", r.valid_from.isoformat(), "", r.note]
                )
        by_method: dict[str, int] = {}
        for r in rows:
            by_method[r.method] = by_method.get(r.method, 0) + 1
        n_sync = int(units["tech"].isin(["hidráulica", "térmica"]).sum())
        typer.echo(
            f"{len(rows)} de {n_sync} unidades síncronas con elevador propuesto "
            f"({', '.join(f'{k}: {v}' for k, v in sorted(by_method.items()))}) → {out}"
        )
        typer.echo("Revisa y marca curated=true fila por fila antes de confiar en la propuesta.")
    except DomainError as exc:
        _fail(exc)
        return
    raise typer.Exit(code=int(ExitCode.OK))


# --- scrape -------------------------------------------------------------------------


@app.command()
def scrape(
    fecha: Annotated[str, typer.Option("--fecha", help="Fecha de operación (YYYY-MM-DD).")],
    out: Annotated[Path | None, typer.Option("--out", help="Directorio de snapshots.")] = None,
) -> None:
    """Descarga PARATEC, el despacho programado y el pronóstico de demanda (HU-3)."""
    steps = {
        "paratec": "Descargando PARATEC…",
        "despacho_y_demanda": f"Descargando despacho y pronóstico de demanda del {fecha}…",
        "normalizacion": "Normalizando y escribiendo el snapshot…",
    }
    try:
        day = parse_date(fecha)
        ctx = _context()
        outcome = scrape_snapshot(
            ctx,
            day,
            out_dir=out,
            on_step=lambda step: typer.echo(steps[step], err=True) if step in steps else None,
        )
    except DomainError as exc:
        _fail(exc)
        return
    manifest = outcome.manifest
    counts = manifest["record_counts"]
    typer.echo(f"Snapshot creado en {outcome.path}")
    typer.echo(f"Aviso: {PARATEC_NOTICE}", err=True)
    typer.echo(
        f"Entidades PARATEC: {sum(1 for k in counts if k.startswith('paratec.'))} | líneas "
        f"{counts.get('paratec.lines')} | transformadores {counts.get('paratec.transformers')} | "
        f"recursos del despacho {counts.get('xm.dispatch.resources')} | nodos de demanda "
        f"{counts.get('xm.demand.nodes')}"
    )
    dv = manifest.get("dispatch_version") or {}
    available = ", ".join(dv.get("available", []))
    typer.echo(
        f"Versión del despacho usada: {dv.get('used')} (disponibles: {available}) "
        f"| estándar: XM-CND-2014-045 ed. 2025"
    )
    raise typer.Exit(code=int(ExitCode.OK))


# --- serve -------------------------------------------------------------------------

HOST = "127.0.0.1"  # Solo local, sin autenticación (NG-08).


def _open_when_ready(url: str, timeout_s: float = 15.0) -> None:
    """Abre el navegador cuando la API responde, sin bloquear el servidor."""

    def wait_and_open() -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{url}/api/snapshots", timeout=1):
                    webbrowser.open(url)
                    return
            except OSError:
                time.sleep(0.3)

    threading.Thread(target=wait_and_open, daemon=True).start()


@app.command()
def serve(
    puerto: Annotated[
        int, typer.Option("--puerto", min=1, max=65535, help="Puerto local (127.0.0.1).")
    ] = 8000,
    abrir: Annotated[
        bool, typer.Option("--abrir/--no-abrir", help="Abrir la interfaz en el navegador.")
    ] = True,
) -> None:
    """Levanta la API y la interfaz en 127.0.0.1 (FR-044)."""
    import uvicorn

    from sinsim.api.app import create_app

    ctx = _context()
    url = f"http://{HOST}:{puerto}"
    typer.echo(f"Datos: {ctx.paths.root} (modo {ctx.paths.mode})")
    if ctx.paths.web is None:
        typer.echo(
            f"La interfaz no está incluida: solo se sirve la API en {url}/api. "
            "Instala sinsim desde un release, o en el repositorio ejecuta `pnpm --dir frontend "
            "build`.",
            err=True,
        )
    else:
        typer.echo(f"sinsim en {url} (Ctrl+C para salir)")
        if abrir:
            _open_when_ready(url)
    uvicorn.run(create_app(ctx), host=HOST, port=puerto, log_level="warning")


def main() -> None:
    """Punto de entrada con manejo de errores no previstos (constitución V)."""
    try:
        app(standalone_mode=True)
    except DomainError as exc:  # pragma: no cover - los comandos ya los convierten
        _fail(exc)
    except typer.Exit:
        raise
    except Exception as exc:  # último recurso: nunca un stack trace al usuario
        trace_id = new_trace_id()
        log.exception("error no previsto", extra={"extra_fields": {"trace_id": trace_id}})
        typer.echo(f"Error no previsto (trace_id {trace_id}): {type(exc).__name__}", err=True)
        sys.exit(int(ExitCode.GENERAL))


_ = (pp, Path)  # pandapower se usa en services; Path queda para --exportar (historia 4)
