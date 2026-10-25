"""Exportación del cortocircuito a CSV y `metadatos.json` (spec 004, contracts/export-sc.md).

Misma convención que `export_n1`: UTF-8 con encabezado, separador coma, punto decimal.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from sinsim.domain.entities import ShortCircuitAnalysis

BUSES_FILE = "cc_barras.csv"
SOURCES_FILE = "cc_fuentes.csv"
QUALITY_FILE = "cc_calidad.csv"
METADATA_FILE = "metadatos.json"
CSV_FILES = (BUSES_FILE, SOURCES_FILE, QUALITY_FILE)

BUS_COLUMNS = [
    "bus_id",
    "subestacion",
    "subarea",
    "kv_nominal",
    "kv_base",
    "ikss_ka",
    "skss_mva",
    "rk_ohm",
    "xk_ohm",
    "x_r",
    "sin_fuente",
]
SOURCE_COLUMNS = [
    "unit_id",
    "tipo",
    "bus_id",
    "trafo_elevador",
    "sn_mva",
    "vn_kv",
    "cos_phi",
    "xdss_pu",
    "rdss_ohm",
    "k",
    "origen_sn",
    "origen_vn",
    "origen_xdss",
    "origen_rdss",
]
QUALITY_COLUMNS = ["categoria", "unit_id", "detalle", "valor", "metodo"]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: _cell(row.get(c)) for c in columns})


def bus_rows(analysis: ShortCircuitAnalysis) -> list[dict[str, Any]]:
    """Filas de `cc_barras.csv` (FR-063), en el orden del análisis."""
    return [
        {
            "bus_id": b.bus_id,
            "subestacion": b.substation,
            "subarea": b.subarea,
            "kv_nominal": b.nominal_kv,
            "kv_base": b.base_kv,
            "ikss_ka": b.ikss_ka,
            "skss_mva": b.skss_mva,
            "rk_ohm": None if b.no_source else b.rk_ohm,
            "xk_ohm": None if b.no_source else b.xk_ohm,
            "x_r": None if b.no_source else b.x_r,
            "sin_fuente": b.no_source,
        }
        for b in analysis.buses
    ]


def source_rows(analysis: ShortCircuitAnalysis) -> list[dict[str, Any]]:
    """Filas de `cc_fuentes.csv`."""
    return [
        {
            "unit_id": s.unit_id,
            "tipo": s.kind,
            "bus_id": s.bus_id,
            "trafo_elevador": s.step_up_trafo_id,
            "sn_mva": s.sn_mva,
            "vn_kv": s.vn_kv,
            "cos_phi": s.cos_phi,
            "xdss_pu": s.xdss_pu,
            "rdss_ohm": s.rdss_ohm,
            "k": s.k,
            "origen_sn": s.origins.get("sn_mva"),
            "origen_vn": s.origins.get("vn_kv"),
            "origen_xdss": s.origins.get("xdss_pu"),
            "origen_rdss": s.origins.get("rdss_pu"),
        }
        for s in analysis.sources
    ]


def quality_rows(analysis: ShortCircuitAnalysis) -> list[dict[str, Any]]:
    """Filas de `cc_calidad.csv` (FR-073)."""
    q = analysis.quality
    rows: list[dict[str, Any]] = [
        {
            "categoria": "imputado",
            "unit_id": i.unit_id,
            "detalle": i.parameter,
            "valor": i.value,
            "metodo": i.method,
        }
        for i in q.imputed
    ]
    bus_of = {s.unit_id: s.bus_id for s in analysis.sources}
    rows += [
        {
            "categoria": "sin_elevador",
            "unit_id": u,
            "detalle": bus_of.get(u),
            "valor": None,
            "metodo": None,
        }
        for u in q.generators_without_step_up
    ]
    rows += [
        {
            "categoria": "sin_aporte",
            "unit_id": z.resource,
            "detalle": z.bus_id,
            "valor": None,
            "metodo": z.reason,
        }
        for z in q.sc_zero_sources
    ]
    rows += [
        {
            "categoria": "excluido",
            "unit_id": e.unit_id,
            "detalle": e.reason,
            "valor": None,
            "metodo": None,
        }
        for e in q.excluded
    ]
    return rows


def metadata(analysis: ShortCircuitAnalysis) -> dict[str, Any]:
    """Contenido de `metadatos.json` (FR-072)."""
    t = analysis.trace
    return {
        "tipo": "cortocircuito",
        "snapshot": t.snapshot_date.isoformat(),
        "despacho": t.dispatch_date.isoformat(),
        "periodo": t.period,
        "case_id": analysis.case_id,
        "run_id": analysis.run_id,
        "case_hash": analysis.case_hash,
        "sc_config_hash": analysis.sc_config_hash,
        "pandapower": t.pandapower_version,
        "sinsim": t.sinsim_version,
        "norma": analysis.norm.model_dump(),
        "config": analysis.config,
        "supuestos": [a.model_dump() for a in analysis.assumptions],
        "calculado_en": analysis.calculated_at.isoformat(),
        "resumen": analysis.summary.model_dump(),
        "equivalencias_elevadores": analysis.quality.step_up_equivalences.model_dump(),
        "atribucion": analysis.attribution,
    }


def write_export_sc(analysis: ShortCircuitAnalysis, out_dir: Path) -> list[Path]:
    """Escribe los tres CSV y `metadatos.json` en `out_dir`; devuelve las rutas."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, columns, rows in (
        (BUSES_FILE, BUS_COLUMNS, bus_rows(analysis)),
        (SOURCES_FILE, SOURCE_COLUMNS, source_rows(analysis)),
        (QUALITY_FILE, QUALITY_COLUMNS, quality_rows(analysis)),
    ):
        path = out_dir / name
        _write_csv(path, columns, rows)
        written.append(path)
    meta = out_dir / METADATA_FILE
    meta.write_text(
        json.dumps(metadata(analysis), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    written.append(meta)
    return written


__all__ = [
    "BUSES_FILE",
    "BUS_COLUMNS",
    "CSV_FILES",
    "METADATA_FILE",
    "QUALITY_COLUMNS",
    "QUALITY_FILE",
    "SOURCES_FILE",
    "SOURCE_COLUMNS",
    "bus_rows",
    "metadata",
    "quality_rows",
    "source_rows",
    "write_export_sc",
]
