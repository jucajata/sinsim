"""Construcción del caso de estudio (FR-010 a FR-019; data-model.md §4–§5).

Orden:
1. Validar periodo y punto de operación.
2. Filtrar la red al alcance (≥ 57,5 kV), aplicar la regla de imputación y construir el mapa de
   frontera STR/SDL.
3. Conciliar recursos del despacho y nodos del pronóstico con las equivalencias; trasladar a la
   frontera lo que esté por debajo del alcance; registrar lo no ubicado.
4. Validación física; construcción del `pandapowerNet`; islas.
5. Reporte de calidad, supuestos, advertencias, hash y persistencia.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Any, cast

import pandapower as pp
import pandas as pd

from sinsim.adapters.sources_to_pandapower.buses import canonical_bus_id, level_for
from sinsim.adapters.sources_to_pandapower.lines import far_end_from_name
from sinsim.adapters.sources_to_pandapower.net_builder import ModelTables, build_net
from sinsim.config import LoadedConfig
from sinsim.domain import physical_checks
from sinsim.domain.balance import compute_balance
from sinsim.domain.case_hash import case_id_for
from sinsim.domain.constants import F_HZ, PERIODS_PER_DAY, S_BASE_MVA
from sinsim.domain.entities import (
    WARNING_PROGRAM_NOT_REAL_STATE,
    CaseInputs,
    ExcludedElement,
    ImputedValue,
    LoadedSnapshot,
    NotModeled,
    QualityReport,
    SnapshotTables,
    StudyCase,
    Transfer,
    UnlocatedDemand,
    UnlocatedResource,
)
from sinsim.domain.errors import DomainError
from sinsim.domain.ports import CaseRepository, EquivalenceRepository, SubstationCoord
from sinsim.services import islands as islands_service
from sinsim.services.snapshots import require_operating_point

IN_OPERATION = "Operación"
IMPUTATION_METHOD = "mediana de elementos del mismo tipo y nivel de tensión en el snapshot"


@dataclass
class _Report:
    unlocated_resources: list[UnlocatedResource] = field(default_factory=list)
    unlocated_demand: list[UnlocatedDemand] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    excluded: list[ExcludedElement] = field(default_factory=list)
    imputed: list[ImputedValue] = field(default_factory=list)
    not_modeled: list[NotModeled] = field(default_factory=list)


@dataclass(frozen=True)
class BuiltCase:
    """Resultado de `build_case`: el caso y su red."""

    case: StudyCase
    net: pp.pandapowerNet


# --- Utilidades ------------------------------------------------------------------


def _split_bus(bus_id: str) -> tuple[str, float]:
    sub, _, kv = bus_id.rpartition("|")
    return sub, float(kv)


def _complete(df: pd.DataFrame) -> pd.Series:
    return df.missing_params.map(len) == 0


def _impute(
    df: pd.DataFrame,
    kind: str,
    id_col: str,
    level_col: str,
    cfg: LoadedConfig,
    report: _Report,
) -> pd.DataFrame:
    """Aplica la regla de imputación (III.5): mediana por tipo y nivel, solo a `params`."""
    rule = cfg.config.imputation.rule
    params = set(cfg.config.imputation.params)
    if rule != "median" or not params or df.empty:
        return df
    out = df.copy()
    out["imputation_method"] = out["imputation_method"].astype(object)
    out["imputed"] = out["imputed"].astype(bool)
    levels = out[level_col].map(lambda kv: level_for(float(kv)) if pd.notna(kv) else None)
    new_missing: dict[Any, list[str]] = {}
    for param in params:
        if param not in out.columns:
            continue
        values = pd.to_numeric(out[param], errors="coerce")
        for level in levels.dropna().unique():
            mask_level = levels == level
            median = values[mask_level].median()
            if math.isnan(median):
                continue
            to_fill = mask_level & values.isna() & out.missing_params.map(lambda m, p=param: p in m)
            for idx in out.index[to_fill]:
                current = new_missing.get(idx, cast(list[str], out.at[idx, "missing_params"]))
                new_missing[idx] = [m for m in current if m != param]
                out.at[idx, param] = median
                out.at[idx, "imputed"] = True
                out.at[idx, "imputation_method"] = IMPUTATION_METHOD
                report.imputed.append(
                    ImputedValue(
                        element=str(out.at[idx, id_col]),
                        kind=kind,
                        param=param,
                        method=IMPUTATION_METHOD,
                        value=float(median),
                    )
                )
    if new_missing:
        out["missing_params"] = [
            new_missing.get(i, m) for i, m in zip(out.index, out["missing_params"], strict=True)
        ]
    return out


def _exclude_incomplete(df: pd.DataFrame, kind: str, id_col: str, report: _Report) -> pd.DataFrame:
    bad = df[~_complete(df)]
    for _, r in bad.iterrows():
        report.excluded.append(
            ExcludedElement(
                element=str(r[id_col]), kind=kind, missing_params=list(r.missing_params)
            )
        )
    return df[_complete(df)]


# --- Alias de subestaciones --------------------------------------------------------


_BUS_COLUMNS: dict[str, tuple[str, ...]] = {
    "buses": ("bus_id",),
    "lines": ("from_bus", "to_bus"),
    "trafos2w": ("hv_bus", "lv_bus"),
    "trafos3w": ("hv_bus", "mv_bus", "lv_bus"),
    "generators": ("bus",),
    "shunts": ("bus",),
    "svc_statcom": ("bus",),
}


def _apply_aliases(tables: SnapshotTables, aliases: dict[str, str]) -> tuple[SnapshotTables, int]:
    """Renombra las barras de subestaciones con alias y fusiona las duplicadas.

    Returns:
        Tablas renombradas y número de barras fusionadas.
    """
    if not aliases:
        return tables, 0

    def rename(bus: object) -> object:
        if not isinstance(bus, str) or "|" not in bus:
            return bus
        sub, _, kv = bus.rpartition("|")
        return f"{aliases.get(sub, sub)}|{kv}"

    renamed: dict[str, pd.DataFrame] = {}
    for name, cols in _BUS_COLUMNS.items():
        df = getattr(tables, name).copy()
        for col in cols:
            df[col] = df[col].map(rename)
        if "substation" in df.columns:
            df["substation"] = df["substation"].map(
                lambda s: aliases.get(s, s) if isinstance(s, str) else s
            )
        renamed[name] = df
    before = len(renamed["buses"])
    renamed["buses"] = (
        renamed["buses"].drop_duplicates("bus_id", keep="first").reset_index(drop=True)
    )
    merged = before - len(renamed["buses"])
    return SnapshotTables(dispatch=tables.dispatch, demand=tables.demand, **renamed), merged


def _apply_curated_coordinates(
    buses: pd.DataFrame, coords: Mapping[str, SubstationCoord]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Completa con la tabla curada las coordenadas que PARATEC no publica (FR-035).

    Solo llena barras sin latitud o sin longitud: una coordenada de PARATEC nunca se reemplaza.
    Cada coordenada aplicada se devuelve con su fuente para el registro de supuestos.

    Returns:
        Barras completadas y lista de coordenadas aplicadas, una por subestación.
    """
    if not coords:
        return buses, []
    out = buses.copy()
    if "lat" not in out.columns:
        out["lat"] = None
    if "lon" not in out.columns:
        out["lon"] = None
    missing = out.lat.isna() | out.lon.isna()
    applied: list[dict[str, Any]] = []
    for sub, row in sorted(coords.items()):
        mask = missing & (out.substation.astype(str) == sub)
        if not mask.any():
            continue
        out.loc[mask, "lat"] = float(row.lat)
        out.loc[mask, "lon"] = float(row.lon)
        applied.append(
            {
                "subestacion": sub,
                "lat": float(row.lat),
                "lon": float(row.lon),
                "barras": sorted(str(b) for b in out.bus_id[mask]),
                "fuente": row.note,
            }
        )
    return out, applied


# --- Alcance y frontera -----------------------------------------------------------


def _frontier_map(
    buses: pd.DataFrame, t2: pd.DataFrame, t3: pd.DataFrame, min_kv: float
) -> dict[str, str]:
    """`bus SDL → bus del modelo` de la misma subestación, por el transformador que los une.

    Regla (FR-019): el nivel ≥ `min_kv` más bajo unido por un transformador al nivel original.
    """
    kv_of = buses.set_index("bus_id").vn_kv.to_dict()
    links: dict[str, set[str]] = {}

    def link(a: str | None, b: str | None) -> None:
        if not a or not b or a == b:
            return
        links.setdefault(a, set()).add(b)
        links.setdefault(b, set()).add(a)

    for _, t in t2.iterrows():
        link(t.hv_bus, t.lv_bus)
    for _, t in t3.iterrows():
        link(t.hv_bus, t.mv_bus)
        link(t.hv_bus, t.lv_bus)
        link(t.mv_bus, t.lv_bus)
    out: dict[str, str] = {}
    for sdl, neighbours in links.items():
        if kv_of.get(sdl, 0.0) >= min_kv:
            continue
        sub, _ = _split_bus(sdl)
        candidates = [
            n for n in neighbours if kv_of.get(n, 0.0) >= min_kv and _split_bus(n)[0] == sub
        ]
        if candidates:
            out[sdl] = min(candidates, key=lambda n: kv_of[n])
    return out


# Reutilizados por el cortocircuito (spec 004): mismas reglas de alias y de frontera (S2).
apply_aliases = _apply_aliases
frontier_map = _frontier_map


# --- Conciliación ---------------------------------------------------------------------


class _AliasedEquivalences:
    """Envuelve el repositorio para que los nodos y enlaces apunten a nombres canónicos."""

    def __init__(self, inner: EquivalenceRepository, aliases: dict[str, str]) -> None:
        self._inner = inner
        self._aliases = aliases

    @property
    def sha256(self) -> str:
        return self._inner.sha256

    def resolve_resource(self, resource: str, on: date) -> Any:
        eq = self._inner.resolve_resource(resource, on)
        if (
            eq is not None
            and eq.kind == "intl_link"
            and eq.connection_bus
            and "|" in eq.connection_bus
        ):
            sub, _, kv = eq.connection_bus.rpartition("|")
            if sub in self._aliases:
                return _ResourceAlias(eq, f"{self._aliases[sub]}|{kv}")
        return eq

    def resolve_node(self, node: str, vn_kv: float, on: date) -> Any:
        eq = self._inner.resolve_node(node, vn_kv, on)
        if eq is not None and eq.substation in self._aliases:
            return _NodeAlias(eq, self._aliases[eq.substation])
        return eq

    def substation_aliases(self, on: date) -> dict[str, str]:
        return self._inner.substation_aliases(on)

    def substation_coords(self, on: date) -> Mapping[str, SubstationCoord]:
        return self._inner.substation_coords(on)

    def step_up(self, unit_id: str, on: date) -> Any:
        return self._inner.step_up(unit_id, on)


@dataclass(frozen=True)
class _ResourceAlias:
    inner: Any
    connection_bus: str

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


@dataclass(frozen=True)
class _NodeAlias:
    inner: Any
    substation: str

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def _locate_generation(
    gens_src: pd.DataFrame,
    dispatch: pd.DataFrame,
    model_buses: set[str],
    frontier: dict[str, str],
    equivalences: EquivalenceRepository,
    on: date,
    cfg: LoadedConfig,
    report: _Report,
) -> tuple[pd.DataFrame, pd.DataFrame, float, float, list[dict[str, Any]]]:
    """Asigna la potencia programada a generadores del modelo.

    Returns:
        `(gens, sgens, p_scheduled_total, p_located, repartos)`.
    """
    by_plant: dict[str, pd.DataFrame] = {str(k): v for k, v in gens_src.groupby("plant")}
    by_unit = gens_src.set_index("unit")
    vm = cfg.config.generator.vm_pu_default
    gen_rows: list[dict[str, Any]] = []
    sgen_rows: list[dict[str, Any]] = []
    splits: list[dict[str, Any]] = []
    p_total = p_located = 0.0
    for _, d in dispatch.sort_values("resource").iterrows():
        resource, p_mw = str(d.resource), float(d.p_mw)
        if p_mw <= 0:
            continue  # fuera de servicio en el periodo (caso borde), no es error
        p_total += p_mw
        eq = equivalences.resolve_resource(resource, on)
        if eq is None:
            report.unlocated_resources.append(
                UnlocatedResource(resource=resource, p_mw=p_mw, reason="sin equivalencia")
            )
            continue
        if eq.kind == "intl_link":
            bus = eq.connection_bus or ""
            if "|" in bus:
                sub_name, link_kv = _split_bus(bus)
                bus = canonical_bus_id(sub_name, link_kv, {})
            if bus not in model_buses:
                report.unlocated_resources.append(
                    UnlocatedResource(
                        resource=resource, p_mw=p_mw, reason=f"barra {bus!r} no está en el modelo"
                    )
                )
                continue
            sgen_rows.append(
                {"sgen_id": f"link:{resource}", "resource": resource, "bus": bus, "p_mw": p_mw}
            )
            p_located += p_mw
            continue
        if eq.kind == "plant":
            frames = [by_plant[p] for p in eq.paratec_ids if p in by_plant]
        else:
            frames = [by_unit.loc[[u]].reset_index() for u in eq.paratec_ids if u in by_unit.index]
        units = pd.concat(frames) if frames else pd.DataFrame(columns=gens_src.columns)
        if units.empty:
            report.unlocated_resources.append(
                UnlocatedResource(
                    resource=resource, p_mw=p_mw, reason="equivalencia sin unidades en PARATEC"
                )
            )
            continue
        # Barra de destino por unidad: la propia si está en el modelo, la frontera si es SDL.
        targets: list[tuple[str, pd.Series]] = []
        for _, u in units.iterrows():
            unit_bus = u.bus if isinstance(u.bus, str) else ""
            if unit_bus in model_buses:
                targets.append((unit_bus, u))
            elif unit_bus in frontier:
                targets.append((frontier[unit_bus], u))
                report.transfers.append(
                    Transfer(
                        element=f"{resource} / {u.unit}",
                        kind="gen",
                        from_bus=unit_bus,
                        to_bus=frontier[unit_bus],
                        p_mw=0.0,  # se completa abajo con el reparto
                        q_mvar=0.0,
                    )
                )
        if not targets:
            report.unlocated_resources.append(
                UnlocatedResource(
                    resource=resource,
                    p_mw=p_mw,
                    reason="sin barra en el alcance ni frontera STR/SDL",
                )
            )
            continue
        pmax_total = sum(float(u.p_max_mw) for _, u in targets if pd.notna(u.p_max_mw)) or float(
            len(targets)
        )
        by_bus: dict[str, list[pd.Series]] = {}
        for bus, u in targets:
            by_bus.setdefault(bus, []).append(u)
        if len(by_bus) > 1:
            splits.append(
                {
                    "resource": resource,
                    "buses": sorted(by_bus),
                    "criterio": "proporcional a p_max_mw",
                }
            )
        for bus, us in by_bus.items():
            pmax_bus = sum(float(u.p_max_mw) if pd.notna(u.p_max_mw) else 1.0 for u in us)
            share = p_mw * pmax_bus / pmax_total
            q_abs = [float(u.q_absorb_mvar) for u in us if pd.notna(u.q_absorb_mvar)]
            q_gen = [float(u.q_gen_mvar) for u in us if pd.notna(u.q_gen_mvar)]
            complete_q = len(q_abs) == len(us) and len(q_gen) == len(us)
            gen_rows.append(
                {
                    "gen_id": f"{resource}@{bus}",
                    "resource": resource,
                    "bus": bus,
                    "p_mw": share,
                    "p_max_mw": pmax_bus,
                    "min_q_mvar": -sum(q_abs) if complete_q else math.nan,
                    "max_q_mvar": sum(q_gen) if complete_q else math.nan,
                    "q_source": (
                        "PARATEC (q_absorb_mvar, q_gen_mvar de las unidades)"
                        if complete_q
                        else "PARATEC no publica los límites de todas las unidades: sin límite de Q"
                    ),
                    "vm_pu": vm,
                    "slack_weight": share,
                    "is_angle_ref": False,
                    "units": [str(u.unit) for u in us],
                }
            )
        p_located += p_mw
    # Completar los MW de los traslados de generación con el reparto final por barra.
    gens_df = pd.DataFrame(gen_rows)
    fixed: list[Transfer] = []
    for t in report.transfers:
        if t.kind != "gen":
            fixed.append(t)
            continue
        resource = t.element.split(" / ")[0]
        row = (
            gens_df[(gens_df.resource == resource) & (gens_df.bus == t.to_bus)]
            if not gens_df.empty
            else gens_df
        )
        p = float(row.p_mw.sum()) if len(row) else 0.0
        n = len(row.units.iloc[0]) if len(row) else 1
        fixed.append(
            Transfer(
                element=t.element,
                kind="gen",
                from_bus=t.from_bus,
                to_bus=t.to_bus,
                p_mw=p / max(n, 1),
                q_mvar=0.0,
            )
        )
    report.transfers = fixed
    return gens_df, pd.DataFrame(sgen_rows), p_total, p_located, splits


def _locate_demand(
    demand: pd.DataFrame,
    model_buses: set[str],
    declared_buses: dict[str, float],
    frontier: dict[str, str],
    equivalences: EquivalenceRepository,
    on: date,
    report: _Report,
) -> tuple[pd.DataFrame, float, float]:
    """Asigna la demanda P (= act + pstr) y Q de cada nodo a una barra del modelo (FR-014)."""
    agg: dict[str, dict[str, float]] = {}
    p_located = p_unlocated = 0.0
    for _, n in demand.iterrows():
        node, kv = str(n.node), float(n.vn_kv)
        p = float(n.p_act_mw) + float(n.p_pstr_mw)
        q = float(n.q_mvar)
        eq = equivalences.resolve_node(node, kv, on)
        if eq is None:
            report.unlocated_demand.append(
                UnlocatedDemand(node=node, vn_kv=kv, p_mw=p, q_mvar=q, reason="sin equivalencia")
            )
            p_unlocated += p
            continue
        bus = canonical_bus_id(eq.substation, eq.paratec_vn_kv, {})
        if bus not in declared_buses:
            report.unlocated_demand.append(
                UnlocatedDemand(
                    node=node,
                    vn_kv=kv,
                    p_mw=p,
                    q_mvar=q,
                    reason=f"barra {bus!r} no existe en PARATEC",
                )
            )
            p_unlocated += p
            continue
        if bus not in model_buses:
            if bus in frontier:
                report.transfers.append(
                    Transfer(
                        element=node,
                        kind="demand",
                        from_bus=bus,
                        to_bus=frontier[bus],
                        p_mw=p,
                        q_mvar=q,
                    )
                )
                bus = frontier[bus]
            else:
                report.unlocated_demand.append(
                    UnlocatedDemand(
                        node=node,
                        vn_kv=kv,
                        p_mw=p,
                        q_mvar=q,
                        reason="sin barra en el alcance ni frontera STR/SDL",
                    )
                )
                p_unlocated += p
                continue
        entry = agg.setdefault(bus, {"p_mw": 0.0, "p_act_mw": 0.0, "p_pstr_mw": 0.0, "q_mvar": 0.0})
        # Se conservan por separado los dos componentes de la demanda activa (FR-014).
        entry["p_mw"] += p
        entry["p_act_mw"] += float(n.p_act_mw)
        entry["p_pstr_mw"] += float(n.p_pstr_mw)
        entry["q_mvar"] += q
        p_located += p
    rows = [{"load_id": f"load:{bus}", "bus": bus, **vals} for bus, vals in sorted(agg.items())]
    columns = ["load_id", "bus", "p_mw", "p_act_mw", "p_pstr_mw", "q_mvar"]
    return pd.DataFrame(rows, columns=columns), p_located, p_unlocated


def _repair_self_loops(
    lines: pd.DataFrame, known_substations: set[str], declared_buses: dict[str, float]
) -> pd.DataFrame:
    """Reasigna el extremo lejano de las líneas lazo cuando el nombre lo da (ver `lines.py`)."""
    if lines.empty:
        return lines
    out = lines.copy()
    for idx, r in out[out.from_bus == out.to_bus].iterrows():
        sub, _, kv_text = str(r.from_bus).rpartition("|")
        name = str(r.line_id).removeprefix("line:")
        far = far_end_from_name(name, sub, known_substations)
        if far is None:
            continue
        candidate = f"{far}|{kv_text}"
        if candidate in declared_buses:
            out.at[idx, "to_bus"] = candidate
    return out


def _missing_coordinates(buses: pd.DataFrame) -> pd.Series:
    """Máscara de barras sin coordenadas de PARATEC (FR-035); sin columnas, todas faltan."""
    if not {"lat", "lon"} <= set(buses.columns):
        return pd.Series(True, index=buses.index)
    return buses.lat.isna() | buses.lon.isna()


def _missing_subarea(buses: pd.DataFrame) -> pd.Series:
    """Máscara de barras sin subárea de PARATEC (FR-034); sin columna, todas faltan."""
    if "subarea" not in buses.columns:
        return pd.Series(True, index=buses.index)
    return ~buses.subarea.map(lambda v: isinstance(v, str) and bool(v.strip()))


# --- Barra de ángulo ------------------------------------------------------------------


def choose_angle_ref(gens: pd.DataFrame, buses: pd.DataFrame, configured: str) -> tuple[str, str]:
    """Elige la barra de referencia de ángulo.

    Usa la configurada si tiene generación despachada en el periodo; si no, la barra STN del
    generador con mayor P programada, y lo reporta como supuesto.
    """
    if gens.empty:
        raise DomainError(
            "PHYSICAL_CHECK_FAILED", "ningún recurso del despacho quedó ubicado en el modelo"
        )
    if configured and (gens.bus == configured).any():
        return configured, "configurada (config/defaults.toml)"
    stn = gens.merge(buses[["bus_id", "vn_kv"]], left_on="bus", right_on="bus_id")
    pool = stn[stn.vn_kv >= 220] if (stn.vn_kv >= 220).any() else stn
    top = pool.groupby("bus").p_mw.sum().idxmax()
    reason = "barra con mayor P programada en el periodo (la configurada no tiene generación)"
    return str(top), reason


# --- Servicio principal ---------------------------------------------------------------


def make_inputs(
    snapshot: LoadedSnapshot,
    dispatch_snapshot: LoadedSnapshot,
    period: int,
    equivalences: EquivalenceRepository,
    cfg: LoadedConfig,
    sinsim_version: str,
) -> CaseInputs:
    """Entradas que identifican un caso; su hash es el `case_id` (data-model.md §4)."""
    return CaseInputs(
        snapshot_date=snapshot.date,
        dispatch_date=dispatch_snapshot.date,
        period=period,
        snapshot_manifest_sha256=snapshot.manifest_sha256,
        equivalences_sha256=equivalences.sha256,
        config_sha256=cfg.sha256,
        sinsim_version=sinsim_version,
    )


def build_case(
    *,
    snapshot: LoadedSnapshot,
    dispatch_snapshot: LoadedSnapshot,
    period: int,
    equivalences: EquivalenceRepository,
    cfg: LoadedConfig,
    sinsim_version: str,
    cases: CaseRepository | None = None,
) -> BuiltCase:
    """Construye el caso para una fecha y un periodo.

    Args:
        snapshot: Snapshot de PARATEC (red).
        dispatch_snapshot: Snapshot del que se toman despacho y demanda (puede ser el mismo).
        period: Periodo horario 1..24.
        equivalences: Tablas de equivalencias.
        cfg: Configuración cargada.
        sinsim_version: Versión de `sinsim`.
        cases: Repositorio donde persistir el caso (opcional).

    Returns:
        `BuiltCase` con el `StudyCase` y la red.

    Raises:
        DomainError: `PERIOD_OUT_OF_RANGE`, `OPERATING_POINT_MISSING`, `PHYSICAL_CHECK_FAILED`.
    """
    if not 1 <= period <= PERIODS_PER_DAY:
        raise DomainError("PERIOD_OUT_OF_RANGE", f"periodo {period}")
    require_operating_point(dispatch_snapshot)
    report = _Report()
    c = cfg.config
    min_kv = c.network.min_vn_kv
    aliases = equivalences.substation_aliases(dispatch_snapshot.date)
    t, merged_buses = _apply_aliases(snapshot.tables, aliases)
    # Coordenadas que PARATEC no publica (Pimampiro, en Ecuador), desde la tabla curada.
    curated_buses, curated_coords = _apply_curated_coordinates(
        t.buses, equivalences.substation_coords(dispatch_snapshot.date)
    )
    t = replace(t, buses=curated_buses)

    # 1. Alcance y elementos de red.
    buses = t.buses
    declared_buses: dict[str, float] = {
        str(k): float(v) for k, v in buses.set_index("bus_id").vn_kv.items()
    }
    model_buses = set(buses[buses.vn_kv >= min_kv].bus_id)

    def in_scope(*cols: pd.Series) -> pd.Series:
        m = pd.Series(True, index=cols[0].index)
        for col in cols:
            m &= col.isin(model_buses)
        return m

    lines = t.lines[t.lines.state == IN_OPERATION]
    for _, r in t.lines[t.lines.state != IN_OPERATION].iterrows():
        report.not_modeled.append(
            NotModeled(element=r.line_id, kind="línea", reason=f"estado {r.state}")
        )
    lines = _exclude_incomplete(lines, "línea", "line_id", report)
    # PARATEC publica `sub1 = sub2` cuando el otro extremo está fuera de su listado. Si el
    # nombre de la línea nombra una subestación declarada (PIMAMPIRO), se usa ese extremo; se
    # aplica aquí para que valga también en snapshots normalizados antes de esta regla.
    lines = _repair_self_loops(lines, set(buses.substation.astype(str)), declared_buses)
    # Lo que sigue siendo un lazo no transporta nada: es un hallazgo de datos, no se modela.
    self_loop = lines.from_bus == lines.to_bus
    for _, r in lines[self_loop].iterrows():
        report.not_modeled.append(
            NotModeled(
                element=r.line_id,
                kind="línea",
                reason=f"los dos extremos resuelven a la misma barra ({r.from_bus})",
            )
        )
    lines = lines[~self_loop]
    scope = in_scope(lines.from_bus, lines.to_bus)
    for _, r in lines[~scope].iterrows():
        report.not_modeled.append(
            NotModeled(
                element=r.line_id, kind="línea", reason=f"fuera del alcance (< {min_kv:g} kV)"
            )
        )
    lines = lines[scope]

    t2_all = t.trafos2w[t.trafos2w.state == IN_OPERATION]
    t3_all = t.trafos3w[t.trafos3w.state == IN_OPERATION]
    frontier = _frontier_map(buses, t2_all, t3_all, min_kv)

    t2 = _impute(t2_all, "transformador", "trafo_id", "vn_hv_kv", cfg, report)
    t2 = t2[in_scope(t2.hv_bus, t2.lv_bus)]
    t2 = _exclude_incomplete(t2, "transformador", "trafo_id", report)

    t3 = _impute(t3_all, "transformador 3w", "trafo_id", "vn_hv_kv", cfg, report)
    full3 = t3[in_scope(t3.hv_bus, t3.mv_bus, t3.lv_bus)]
    full3 = _exclude_incomplete(full3, "transformador 3w", "trafo_id", report)
    # 3 devanados con terciario SDL → 2 devanados HV–MV con la impedancia HM (frontera por el LV).
    partial3 = t3[in_scope(t3.hv_bus, t3.mv_bus) & ~t3.lv_bus.isin(model_buses)]
    partial3 = partial3[
        partial3.missing_params.map(
            lambda m: not {"vk_hv_percent", "vkr_hv_percent", "pfe_kw"} & set(m)
        )
    ]
    as2w = pd.DataFrame(
        {
            "trafo_id": partial3.trafo_id,
            "hv_bus": partial3.hv_bus,
            "lv_bus": partial3.mv_bus,
            "sn_mva": partial3[["sn_hv_mva", "sn_mv_mva"]].min(axis=1),
            "vn_hv_kv": partial3.vn_hv_kv,
            "vn_lv_kv": partial3.vn_mv_kv,
            "vk_percent": partial3.vk_hv_percent,
            "vkr_percent": partial3.vkr_hv_percent,
            "pfe_kw": partial3.pfe_kw,
            "i0_percent": partial3.i0_percent,
            "tap_side": partial3.tap_side.where(partial3.tap_side != "lv", "hv"),
            "tap_min": partial3.tap_min,
            "tap_max": partial3.tap_max,
            "tap_neutral": partial3.tap_neutral,
            "tap_pos": partial3.tap_pos,
            "tap_step_percent": partial3.tap_step_percent,
        }
    )
    t2 = pd.concat([t2, as2w], ignore_index=True) if not as2w.empty else t2

    shunts = t.shunts[
        (t.shunts.state == IN_OPERATION) & t.shunts.modeled & t.shunts.bus.isin(model_buses)
    ]
    for _, r in t.shunts[~t.shunts.modeled].iterrows():
        report.not_modeled.append(
            NotModeled(element=r.shunt_id, kind=r.kind, reason=r.reason or "parámetros faltantes")
        )
    svc = t.svc_statcom[t.svc_statcom.modeled & t.svc_statcom.bus.isin(model_buses)]
    for _, r in t.svc_statcom[~t.svc_statcom.modeled].iterrows():
        report.not_modeled.append(
            NotModeled(element=r.id, kind=r.kind, reason=r.reason or "parámetros faltantes")
        )

    # 2. Punto de operación.
    on = dispatch_snapshot.date
    dt = dispatch_snapshot.tables
    equivalences_with_alias = _AliasedEquivalences(equivalences, aliases)
    dispatch = dt.dispatch[dt.dispatch.period == period]
    demand = dt.demand[dt.demand.period == period]
    gens, sgens, p_total, p_located, splits = _locate_generation(
        t.generators, dispatch, model_buses, frontier, equivalences_with_alias, on, cfg, report
    )
    loads, p_demand, p_demand_unlocated = _locate_demand(
        demand, model_buses, declared_buses, frontier, equivalences_with_alias, on, report
    )
    ref_bus, ref_reason = choose_angle_ref(gens, buses, c.network.angle_ref_bus)
    gens["is_angle_ref"] = gens.bus == ref_bus
    gens.loc[gens.is_angle_ref, "is_angle_ref"] = [True] + [False] * (
        int(gens.is_angle_ref.sum()) - 1
    )
    compensators = pd.DataFrame(
        {
            "gen_id": svc.id,
            "bus": svc.bus,
            "min_q_mvar": -svc.ind_mvar.astype(float),
            "max_q_mvar": svc.cap_mvar.astype(float),
            "vm_pu": c.generator.vm_pu_default,
        }
    )

    # 3. Validación física (constitución V).
    used = set(lines.from_bus) | set(lines.to_bus) | set(t2.hv_bus) | set(t2.lv_bus)
    used |= (
        set(full3.hv_bus) | set(full3.mv_bus) | set(full3.lv_bus) | set(gens.bus) | set(loads.bus)
    )
    used |= set(shunts.bus) | set(compensators.bus)
    if not sgens.empty:
        used |= set(sgens.bus)
    model_bus_df = buses[buses.bus_id.isin(used | {ref_bus})]
    issues = physical_checks.check_model(model_bus_df, lines, t2, full3, gens, loads)
    blocking = physical_checks.blocking_issues(issues)
    if blocking:
        raise DomainError(
            "PHYSICAL_CHECK_FAILED",
            "; ".join(i.describe() for i in blocking[:10]),
        )

    # 4. Red e islas.
    model = ModelTables(
        buses=model_bus_df,
        lines=lines,
        trafos2w=t2,
        trafos3w=full3,
        gens=gens,
        compensators=compensators,
        sgens=sgens,
        shunts=shunts,
        loads=loads,
    )
    net = build_net(model, F_HZ, S_BASE_MVA)
    islands = islands_service.detect_and_isolate(net, ref_bus)

    # 5. Reporte, supuestos, advertencias e identidad.
    balance = compute_balance(
        p_scheduled_total_mw=p_total,
        p_located_mw=p_located,
        p_demand_mw=p_demand,
        p_demand_unlocated_mw=p_demand_unlocated,
    )
    quality = QualityReport(
        unlocated_resources=report.unlocated_resources,
        unlocated_demand=report.unlocated_demand,
        transfers=report.transfers,
        excluded=report.excluded,
        imputed=report.imputed,
        not_modeled=report.not_modeled,
        islands=islands,
        physical_issues=[i.describe() for i in issues],
        buses_without_coordinates=sorted(
            str(b) for b in model_bus_df.bus_id[_missing_coordinates(model_bus_df)]
        ),
        buses_without_subarea=sorted(
            str(b) for b in model_bus_df.bus_id[_missing_subarea(model_bus_df)]
        ),
        balance=balance,
    )
    inputs = make_inputs(snapshot, dispatch_snapshot, period, equivalences, cfg, sinsim_version)
    weights = gens.set_index("gen_id").slack_weight
    assumptions: dict[str, Any] = {
        "consigna_tension_pu": {
            "valor": c.generator.vm_pu_default,
            "fuente": c.generator.vm_pu_source,
        },
        "barra_referencia_angulo": {
            "barra": ref_bus,
            "criterio": ref_reason,
            "fuente": c.network.angle_ref_source,
        },
        "referencia_distribuida": {
            "criterio": "proporcional a la potencia programada (FR-015)",
            "factores": {k: float(v / weights.sum()) for k, v in weights.items()}
            if weights.sum()
            else {},
        },
        "repartos_entre_barras": splits,
        # FR-018: consigna y límites de reactiva asignados a cada generador, con su fuente.
        "generadores": [
            {
                "gen_id": str(g.gen_id),
                "barra": str(g.bus),
                "vm_pu": float(g.vm_pu),
                "fuente_vm": c.generator.vm_pu_source,
                "q_min_mvar": None if pd.isna(g.min_q_mvar) else float(g.min_q_mvar),
                "q_max_mvar": None if pd.isna(g.max_q_mvar) else float(g.max_q_mvar),
                "fuente_q": str(g.q_source),
            }
            for _, g in gens.iterrows()
        ]
        + [
            {
                "gen_id": str(k.gen_id),
                "barra": str(k.bus),
                "vm_pu": float(k.vm_pu),
                "fuente_vm": c.generator.vm_pu_source,
                "q_min_mvar": float(k.min_q_mvar),
                "q_max_mvar": float(k.max_q_mvar),
                "fuente_q": "PARATEC (SVC/STATCOM: inductivo y capacitivo nominales, D-6)",
            }
            for _, k in compensators.iterrows()
        ],
        # FR-014: la demanda activa de cada barra conserva sus dos componentes.
        "demanda_por_barra": {
            "criterio": "P = Ener.Act. + Perd.PSTR; Q = Ener.Reac (FR-014)",
            "barras": [
                {
                    "barra": str(ld.bus),
                    "p_act_mw": float(ld.p_act_mw),
                    "p_pstr_mw": float(ld.p_pstr_mw),
                    "q_mvar": float(ld.q_mvar),
                }
                for _, ld in loads.iterrows()
            ],
        },
        "traslados_frontera": len(report.transfers),
        "taps": {"politica": c.trafo.tap_policy, "fuente": c.trafo.tap_source},
        "i0_percent": {"valor": c.trafo.i0_percent, "fuente": c.trafo.i0_source},
        "svc_statcom": "modelados como fuentes de reactiva con consigna de tensión (D-6)",
        "imputacion": {
            "regla": c.imputation.rule,
            "parametros": c.imputation.params,
            "metodo": IMPUTATION_METHOD,
        },
        "alcance_kv_min": min_kv,
        "alias_subestaciones": {"aplicados": aliases, "barras_fusionadas": merged_buses},
        "coordenadas_curadas": curated_coords,
        "version_despacho": dispatch_snapshot.manifest.dispatch_version.model_dump()
        if dispatch_snapshot.manifest.dispatch_version
        else None,
    }
    warnings = [WARNING_PROGRAM_NOT_REAL_STATE]
    if snapshot.date != dispatch_snapshot.date:
        warnings.append(
            f"DATES_DIFFER: los parámetros son del {snapshot.date} "
            f"y el despacho del {dispatch_snapshot.date}."
        )
    dv = dispatch_snapshot.manifest.dispatch_version
    if dv and dv.used != "V0":
        warnings.append(
            f"DISPATCH_REVISED: se usó la versión {dv.used} del despacho "
            f"(disponibles: {', '.join(dv.available)})."
        )
    case = StudyCase(
        case_id=case_id_for(inputs),
        inputs=inputs,
        quality=quality,
        assumptions=assumptions,
        warnings=warnings,
        created_at=datetime.now(UTC),
    )
    if cases is not None:
        cases.save_case(case, pp.to_json(net))
    return BuiltCase(case=case, net=net)
