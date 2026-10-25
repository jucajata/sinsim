"""Formato de exportación del cortocircuito (contracts/export-sc.md)."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from sinsim.adapters.storage.export_sc import (
    BUS_COLUMNS,
    BUSES_FILE,
    METADATA_FILE,
    QUALITY_COLUMNS,
    QUALITY_FILE,
    SOURCE_COLUMNS,
    SOURCES_FILE,
    write_export_sc,
)
from sinsim.domain.entities import (
    ScAssumption,
    ScBusResult,
    ScExcluded,
    ScImputed,
    ScNorm,
    ScQuality,
    ScSource,
    ScSummary,
    ScZeroSource,
    ShortCircuitAnalysis,
    SolverSettings,
    StepUpStats,
    Trace,
)


def analysis() -> ShortCircuitAnalysis:
    trace = Trace(
        snapshot_date="2026-10-20",
        dispatch_date="2026-10-20",
        period=19,
        flow_type="ac",
        pandapower_version="3.5.6",
        sinsim_version="0.7.0",
        solver=SolverSettings(
            algorithm="nr",
            tolerance_mva=1e-6,
            max_iteration=30,
            init="dc",
            enforce_q_lims=True,
            distributed_slack=True,
        ),
        case_id="c" * 64,
    )
    buses = [
        ScBusResult(
            bus_id="A|230",
            substation="A",
            subarea="Caribe",
            nominal_kv=220,
            base_kv=230,
            ikss_ka=40.0,
            skss_mva=15242.0,
            rk_ohm=0.3,
            xk_ohm=3.0,
            x_r=10.0,
        ),
        ScBusResult(
            bus_id="B|115",
            substation="B",
            nominal_kv=115,
            base_kv=115,
            ikss_ka=0.0,
            skss_mva=0.0,
            no_source=True,
        ),
    ]
    sources = [
        ScSource(
            unit_id="hidráulica:U 1",
            kind="sincrona",
            bus_id="A|230",
            step_up_trafo_id="trafo:T",
            sn_mva=100,
            vn_kv=13.8,
            cos_phi=0.85,
            xdss_pu=0.2,
            rdss_ohm=0.01,
            origins={
                "sn_mva": "publicado",
                "vn_kv": "tension_elevador",
                "xdss_pu": "mediana",
                "rdss_pu": "relacion_iec",
                "cos_phi": "publicado",
            },
        ),
        ScSource(
            unit_id="solar:S",
            kind="convertidor",
            bus_id="B|115",
            sn_mva=20,
            vn_kv=115,
            k=1.0,
            origins={"sn_mva": "publicado"},
        ),
    ]
    quality = ScQuality(
        imputed=[
            ScImputed(unit_id="hidráulica:U 1", parameter="xdss_pu", value=0.2, method="mediana")
        ],
        generators_without_step_up=["hidráulica:U 2"],
        sc_zero_sources=[
            ScZeroSource(resource="ECUADOR230_1", bus_id="JAMONDINO|230", reason="S29")
        ],
        excluded=[ScExcluded(unit_id="svc:CHINU", reason="compensador")],
        step_up_equivalences=StepUpStats(
            matched=1, by_method={"nombre": 1}, curated=0, uncurated=1
        ),
    )
    return ShortCircuitAnalysis(
        case_id="c" * 64,
        run_id="r",
        case_hash="c" * 64,
        sc_config_hash="h" * 64,
        trace=trace,
        norm=ScNorm(c_max=1.1),
        config={"converter_k": 1.0},
        assumptions=[ScAssumption(id="S26", text="t", source="s")],
        calculated_at=datetime(2026, 10, 25, 20, 0, tzinfo=UTC),
        summary=ScSummary(
            n_buses=2,
            n_sources_sync=1,
            n_sources_converter=1,
            n_imputed_units=1,
            n_without_step_up=1,
            n_no_source=1,
            duration_s=0.5,
        ),
        buses=buses,
        sources=sources,
        quality=quality,
        attribution="Información proporcionada por XM S.A. E.S.P.",
    )


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_csv_columns_and_empty_cells_for_buses_without_source(tmp_path: Path):
    written = write_export_sc(analysis(), tmp_path)
    assert [p.name for p in written] == [BUSES_FILE, SOURCES_FILE, QUALITY_FILE, METADATA_FILE]
    buses = read(tmp_path / BUSES_FILE)
    assert list(buses[0]) == BUS_COLUMNS
    assert (
        buses[0]["bus_id"] == "A|230"
        and buses[0]["x_r"] == "10"
        and buses[0]["sin_fuente"] == "false"
    )
    assert buses[1]["sin_fuente"] == "true" and buses[1]["rk_ohm"] == buses[1]["x_r"] == ""
    sources = read(tmp_path / SOURCES_FILE)
    assert list(sources[0]) == SOURCE_COLUMNS
    assert sources[0]["origen_xdss"] == "mediana" and sources[1]["k"] == "1"
    quality = read(tmp_path / QUALITY_FILE)
    assert list(quality[0]) == QUALITY_COLUMNS
    assert [q["categoria"] for q in quality] == [
        "imputado",
        "sin_elevador",
        "sin_aporte",
        "excluido",
    ]
    assert quality[1]["detalle"] == ""  # la unidad sin elevador no es fuente en este ejemplo
    assert quality[2]["unit_id"] == "ECUADOR230_1" and quality[2]["detalle"] == "JAMONDINO|230"


def test_metadata_keys(tmp_path: Path):
    write_export_sc(analysis(), tmp_path)
    meta = json.loads((tmp_path / METADATA_FILE).read_text(encoding="utf-8"))
    assert set(meta) == {
        "tipo",
        "snapshot",
        "despacho",
        "periodo",
        "case_id",
        "run_id",
        "case_hash",
        "sc_config_hash",
        "pandapower",
        "sinsim",
        "norma",
        "config",
        "supuestos",
        "calculado_en",
        "resumen",
        "equivalencias_elevadores",
        "atribucion",
    }
    assert meta["tipo"] == "cortocircuito" and meta["norma"]["c_max"] == 1.1
    assert meta["resumen"]["n_buses"] == 2 and meta["equivalencias_elevadores"]["matched"] == 1
