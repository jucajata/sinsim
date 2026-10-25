"""Entidades de dominio (data-model.md).

Modelos Pydantic v2 inmutables. Este módulo no importa pandapower, httpx ni FastAPI
(constitución IV). Las tablas normalizadas viajan como DataFrames de pandas en
`SnapshotTables`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

FlowType = Literal["ac", "dc"]
RunStatus = Literal["convergio", "no_convergio"]
VoltageLevel = Literal["STN", "STR", "SDL"]


class Frozen(BaseModel):
    """Base inmutable para todas las entidades."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Snapshot y manifiesto -----------------------------------------------------

ScrapeStatus = Literal["en_cola", "descargando", "listo", "error"]
ScrapeStep = Literal["en_cola", "paratec", "despacho_y_demanda", "normalizacion", "listo", "error"]


class ProblemInfo(Frozen):
    """Problem Details (RFC 9457) extendido, tal como lo devuelve la API (constitución V)."""

    type: str
    title: str
    status: int
    detail: str
    code: str
    user_message: str
    trace_id: str


class ScrapeJob(Frozen):
    """Descarga de una fecha pedida desde la interfaz (data-model.md §1.2, FR-038).

    Vive en memoria mientras la API está encendida; no se persiste.
    """

    job_id: str
    date: date
    status: ScrapeStatus
    step: ScrapeStep
    started_at: datetime
    finished_at: datetime | None = None
    snapshot: SnapshotSummary | None = None
    error: ProblemInfo | None = None
    notice: str


class SourceFile(Frozen):
    """Origen de una entidad del snapshot."""

    entity: str
    url: str
    source_modified_at: datetime | None = None
    standard_version: str | None = None


class FileEntry(Frozen):
    """Archivo del snapshot con su checksum."""

    path: str
    sha256: str
    bytes: int


class DispatchVersion(Frozen):
    """Versión del despacho usada cuando XM publica varias el mismo día (D-3)."""

    used: str
    available: list[str]


class Manifest(Frozen):
    """`manifest.json` de un snapshot (contracts/snapshot-format.md)."""

    schema_version: int = 1
    snapshot_date: date
    extracted_at: datetime
    scraper_version: str
    attribution: str
    sources: list[SourceFile]
    dispatch_version: DispatchVersion | None = None
    record_counts: dict[str, int]
    files: list[FileEntry]


class SnapshotSummary(Frozen):
    """Fila de `sinsim snapshots list` y de `GET /api/snapshots` (FR-002)."""

    date: date
    has_paratec: bool
    has_dispatch: bool
    has_demand: bool
    intact: bool


@dataclass(frozen=True)
class SnapshotTables:
    """Tablas normalizadas de un snapshot (data-model.md §2)."""

    buses: pd.DataFrame
    lines: pd.DataFrame
    trafos2w: pd.DataFrame
    trafos3w: pd.DataFrame
    generators: pd.DataFrame
    shunts: pd.DataFrame
    svc_statcom: pd.DataFrame
    dispatch: pd.DataFrame
    demand: pd.DataFrame


@dataclass(frozen=True)
class LoadedSnapshot:
    """Snapshot verificado y cargado en memoria."""

    date: date
    manifest: Manifest
    manifest_sha256: str
    tables: SnapshotTables


# --- Caso de estudio -------------------------------------------------------------


class CaseInputs(Frozen):
    """Entradas que definen un caso; su JSON canónico se hashea en `case_id`."""

    snapshot_date: date
    dispatch_date: date
    period: int = Field(ge=1, le=24)
    snapshot_manifest_sha256: str
    equivalences_sha256: str
    config_sha256: str
    sinsim_version: str


class UnlocatedResource(Frozen):
    """Recurso del despacho con P > 0 sin equivalencia o sin barra (FR-012)."""

    resource: str
    p_mw: float
    reason: str


class UnlocatedDemand(Frozen):
    """Nodo del pronóstico sin barra asociable (FR-014a)."""

    node: str
    vn_kv: float
    p_mw: float
    q_mvar: float
    reason: str


class Transfer(Frozen):
    """Traslado de un generador o una carga a la barra de la frontera STR/SDL (FR-019)."""

    element: str
    kind: Literal["gen", "demand"]
    from_bus: str
    to_bus: str
    p_mw: float
    q_mvar: float


class ExcludedElement(Frozen):
    """Elemento excluido por parámetros faltantes (FR-013)."""

    element: str
    kind: str
    missing_params: list[str]


class ImputedValue(Frozen):
    """Parámetro imputado de forma explícita (FR-013, constitución III.5)."""

    element: str
    kind: str
    param: str
    method: str
    value: float


class NotModeled(Frozen):
    """Elemento conocido que no entra al modelo."""

    element: str
    kind: str
    reason: str


class Island(Frozen):
    """Componente conexa del modelo (FR-016, D-5)."""

    island_id: int
    n_buses: int
    buses: list[str]
    p_gen_lost_mw: float
    p_demand_lost_mw: float
    energized: bool


class Balance(Frozen):
    """Balance del caso (data-model.md §5)."""

    p_scheduled_total_mw: float
    p_located_mw: float
    p_unlocated_mw: float
    coverage_pct: float
    p_demand_mw: float
    p_demand_unlocated_mw: float
    difference_mw: float


class QualityReport(Frozen):
    """Reporte de calidad del caso (HU-2)."""

    unlocated_resources: list[UnlocatedResource]
    unlocated_demand: list[UnlocatedDemand]
    transfers: list[Transfer]
    excluded: list[ExcludedElement]
    imputed: list[ImputedValue]
    not_modeled: list[NotModeled]
    islands: list[Island]
    physical_issues: list[str] = []
    buses_without_coordinates: list[str] = []
    """Barras del modelo cuya subestación no tiene coordenadas en PARATEC (FR-035)."""
    buses_without_subarea: list[str] = []
    """Barras del modelo cuya subestación no tiene subárea en PARATEC (FR-034)."""
    balance: Balance


class StudyCase(Frozen):
    """Caso construido para una fecha y un periodo (data-model.md §4)."""

    case_id: str
    inputs: CaseInputs
    quality: QualityReport
    assumptions: dict[str, Any]
    warnings: list[str]
    created_at: datetime


# --- Ejecución y resultado -------------------------------------------------------


class SolverSettings(Frozen):
    """Parámetros del solver registrados en la trazabilidad (FR-023)."""

    algorithm: str
    tolerance_mva: float
    max_iteration: int
    init: str
    enforce_q_lims: bool
    distributed_slack: bool


class Trace(Frozen):
    """Trazabilidad obligatoria de cada resultado (FR-023, constitución III.7)."""

    snapshot_date: date
    dispatch_date: date
    period: int
    flow_type: FlowType
    pandapower_version: str
    sinsim_version: str
    solver: SolverSettings
    case_id: str


class BusMismatch(Frozen):
    """Barra con desbalance en una no convergencia."""

    bus: str
    mismatch_mva: float


class Diagnostics(Frozen):
    """Diagnóstico de una no convergencia (FR-022, constitución III.8)."""

    iterations: int
    max_mismatch_mva: float
    worst_buses: list[BusMismatch]
    basis: str = "última iteración"
    """Tensión usada para el desbalance: última iteración, última finita o arranque plano."""


class BusResult(Frozen):
    """Resultado por barra (FR-030)."""

    bus_id: str
    vn_kv: float
    vm_pu: float
    vm_kv: float
    va_degree: float
    violation: Literal["low", "high"] | None = None
    subarea: str | None = None


class BranchResult(Frozen):
    """Resultado por línea o transformador (FR-030)."""

    element_id: str
    kind: Literal["line", "trafo2w", "trafo3w"]
    from_bus: str
    to_bus: str
    p_from_mw: float
    q_from_mvar: float
    p_to_mw: float
    q_to_mvar: float
    i_ka: float
    loading_percent: float
    pl_mw: float
    ql_mvar: float
    overload: bool
    subarea_from: str | None = None
    subarea_to: str | None = None


class GeneratorResult(Frozen):
    """Resultado por generador (FR-030, FR-024)."""

    gen_id: str
    resource: str
    bus: str
    p_scheduled_mw: float
    p_mw: float
    q_mvar: float
    slack_adjust_mw: float


class LimitInfo(Frozen):
    """Límite aplicado y su fuente (constitución III.9)."""

    name: str
    value: str
    source: str


class Violation(Frozen):
    """Una violación de límite en el resultado (FR-037)."""

    kind: Literal["tension_baja", "tension_alta", "sobrecarga"]
    element: str
    subarea: str | None
    value: float
    limit: float
    deviation: float
    unit: Literal["pu", "%"]
    source: str


class ResultSummary(Frozen):
    """Resumen de una ejecución convergida."""

    p_gen_mw: float
    p_load_mw: float
    p_losses_mw: float
    slack_adjust_total_mw: float
    n_voltage_violations: int
    n_overloads: int
    limits: list[LimitInfo]
    warnings: list[str]
    violations: list[Violation] = []
    """Reporte de violaciones (FR-037); vacío en ejecuciones anteriores a la regla."""


class RunResult(Frozen):
    """Valores por elemento de una ejecución convergida (data-model.md §7)."""

    buses: list[BusResult]
    lines: list[BranchResult]
    trafos: list[BranchResult]
    generators: list[GeneratorResult]
    summary: ResultSummary


class Run(Frozen):
    """Ejecución de un flujo sobre un caso (data-model.md §6)."""

    run_id: str
    case_id: str
    flow_type: FlowType
    status: RunStatus
    label: str
    solver: SolverSettings
    trace: Trace
    diagnostics: Diagnostics | None = None
    result: RunResult | None = None
    created_at: datetime


LABEL_AC = "Flujo sobre despacho programado"
LABEL_DC = "Aproximación DC sobre despacho programado"
WARNING_PROGRAM_NOT_REAL_STATE = (
    "PROGRAM_NOT_REAL_STATE: el resultado describe el despacho programado por XM, "
    "no el estado real del SIN."
)


# --- Contingencias N-1 (specs/003-contingencias-n1/data-model.md) ---------------------

OutageKind = Literal["line", "trafo2w", "gen", "compensador"]
N1Status = Literal["en_cola", "calculando", "listo", "error"]


class Outage(Frozen):
    """El activo que sale de servicio en una contingencia (FR-049)."""

    element_id: str
    kind: OutageKind
    subarea: str | None = None
    angle_ref_moved_to: str | None = None
    """Barra que toma la referencia de ángulo si sale el generador de referencia (FR-051)."""


class Isolation(Frozen):
    """Barras que una contingencia deja sin la componente de referencia (FR-055)."""

    n_buses: int = Field(gt=0)
    p_demand_lost_mw: float = Field(ge=0)


class LoadingRow(Frozen):
    """Fila del listado de cargabilidad (FR-053)."""

    rank: int = Field(ge=1)
    outage: Outage
    element_id: str
    loading_base_percent: float
    loading_percent: float
    n_elements: int = Field(ge=1)
    isolation: Isolation | None = None


class VoltageRow(Frozen):
    """Fila del listado de tensiones (FR-054)."""

    rank: int = Field(ge=1)
    outage: Outage
    bus_id: str
    vm_base_pu: float
    vm_pu: float
    deviation_pu: float
    """Distancia a la banda con signo: negativa en subtensión, positiva en sobretensión."""
    n_buses: int = Field(ge=1)
    isolation: Isolation | None = None


class IsolationRow(Frozen):
    """Fila del bloque «Aíslan demanda» (FR-055)."""

    rank: int = Field(ge=1)
    outage: Outage
    n_buses: int = Field(ge=1)
    p_demand_lost_mw: float = Field(gt=0)


class UnsolvedRow(Frozen):
    """Fila del bloque «Sin solución» (FR-056)."""

    outage: Outage
    diagnostics: Diagnostics


class N1Summary(Frozen):
    """Resumen del análisis (FR-057; invariante SC-017)."""

    n_total: int
    n_loading: int
    n_voltage: int
    n_isolation: int
    n_unsolved: int
    n_no_impact: int
    duration_s: float


class N1Analysis(Frozen):
    """Resultado completo de un análisis N-1 con su trazabilidad (FR-060)."""

    run_id: str
    trace: Trace
    limits: list[LimitInfo]
    analyzed_at: datetime
    workers: int = Field(ge=1)
    summary: N1Summary
    loading: list[LoadingRow]
    voltage: list[VoltageRow]
    isolation: list[IsolationRow]
    unsolved: list[UnsolvedRow]


class N1Job(Frozen):
    """Análisis N-1 en segundo plano (FR-058); vive en memoria mientras la API está encendida."""

    job_id: str
    run_id: str
    status: N1Status
    done: int = Field(ge=0)
    total: int = Field(ge=0)
    started_at: datetime
    finished_at: datetime | None = None
    result: N1Analysis | None = None
    error: ProblemInfo | None = None


# --- Cortocircuito IEC 60909 (spec 004, data-model.md) ---------------------------------------

ScSourceKind = Literal["sincrona", "convertidor"]
ScMethod = Literal[
    "publicado", "mediana", "relacion_iec", "derivado_p_cosphi", "tension_elevador", "tension_barra"
]
StepUpMethod = Literal["nombre+tension", "nombre", "tension", "manual"]


class StepUpEquivalence(Frozen):
    """Fila de `data/equivalencias/elevadores.csv`: unidad ↔ transformador elevador (FR-065)."""

    unit_id: str
    trafo_id: str
    method: StepUpMethod
    curated: bool
    valid_from: date
    note: str = ""


class ScSource(Frozen):
    """Fuente de cortocircuito usada en el cálculo, con el origen de cada parámetro (FR-064)."""

    unit_id: str
    kind: ScSourceKind
    bus_id: str
    step_up_trafo_id: str | None = None
    sn_mva: float = Field(gt=0)
    vn_kv: float = Field(gt=0)
    cos_phi: float | None = None
    xdss_pu: float | None = None
    rdss_ohm: float | None = None
    k: float | None = None
    origins: dict[str, ScMethod]


class ScBusResult(Frozen):
    """Resultado por barra referido a la tensión nominal de PARATEC (FR-063, S26)."""

    bus_id: str
    substation: str | None = None
    subarea: str | None = None
    nominal_kv: float = Field(gt=0)
    base_kv: float = Field(gt=0)
    ikss_ka: float = Field(ge=0)
    skss_mva: float = Field(ge=0)
    rk_ohm: float | None = None
    xk_ohm: float | None = None
    x_r: float | None = None
    no_source: bool = False


class ScImputed(Frozen):
    """Parámetro imputado a una unidad (FR-073)."""

    unit_id: str
    parameter: str
    value: float
    method: ScMethod


class ScZeroSource(Frozen):
    """Fuente que no aporta corriente (enlaces internacionales, S29)."""

    resource: str
    bus_id: str
    reason: str


class ScExcluded(Frozen):
    """Unidad o elemento fuera del cálculo, con su causa."""

    unit_id: str
    reason: str


class StepUpStats(Frozen):
    """Cuántas unidades casaron con su elevador y por qué método."""

    matched: int = Field(ge=0)
    by_method: dict[str, int]
    curated: int = Field(ge=0)
    uncurated: int = Field(ge=0)


class ScQuality(Frozen):
    """Reporte de calidad del cortocircuito (FR-073)."""

    imputed: list[ScImputed]
    generators_without_step_up: list[str]
    sc_zero_sources: list[ScZeroSource]
    excluded: list[ScExcluded]
    step_up_equivalences: StepUpStats


class ScExtreme(Frozen):
    """Barra extrema del resumen."""

    bus_id: str
    value: float


class ScSummary(Frozen):
    """Resumen del cálculo (data-model §7)."""

    n_buses: int = Field(ge=0)
    max_ikss: ScExtreme | None = None
    min_skss: ScExtreme | None = None
    n_sources_sync: int = Field(ge=0)
    n_sources_converter: int = Field(ge=0)
    n_imputed_units: int = Field(ge=0)
    n_without_step_up: int = Field(ge=0)
    n_no_source: int = Field(ge=0)
    duration_s: float = Field(ge=0)


class ScAssumption(Frozen):
    """Supuesto aplicado (S26 a S31) con su fuente."""

    id: str
    text: str
    source: str


class ScNorm(Frozen):
    """Norma y variante calculadas."""

    standard: str = "IEC 60909-0:2016"
    fault: Literal["3ph"] = "3ph"
    case: Literal["max"] = "max"
    c_max: float


class ShortCircuitAnalysis(Frozen):
    """Resultado completo del cortocircuito de un caso (FR-071, FR-072)."""

    case_id: str
    run_id: str
    case_hash: str
    sc_config_hash: str
    trace: Trace
    norm: ScNorm
    config: dict[str, Any]
    assumptions: list[ScAssumption]
    calculated_at: datetime
    summary: ScSummary
    buses: list[ScBusResult]
    sources: list[ScSource]
    quality: ScQuality
    attribution: str
