"""Cortocircuito trifásico máximo IEC 60909 (spec 004: FR-062 a FR-073).

Deriva de la red del caso una red de cortocircuito (research R3): quita las plantas del despacho
y los compensadores, crea una fuente por cada unidad síncrona en operación (con su transformador
elevador cuando `elevadores.csv` lo casa) y una fuente de corriente limitada por cada planta
solar o eólica, y corre `calc_sc` de pandapower. Las reglas puras viven en
`domain/shortcircuit.py`; las conversiones de unidades, en `adapters/sources_to_pandapower/`.
"""

from __future__ import annotations

import logging
import math
import time
import warnings
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import pandapower as pp
import pandapower.shortcircuit as ppsc
import pandas as pd

from sinsim.adapters.sources_to_pandapower.buses import class_kv
from sinsim.adapters.sources_to_pandapower.generators import rdss_ohm
from sinsim.config import LoadedConfig
from sinsim.domain import shortcircuit as rules
from sinsim.domain.entities import (
    LoadedSnapshot,
    ScBusResult,
    ScExcluded,
    ScNorm,
    ScQuality,
    ScSource,
    ScZeroSource,
    ShortCircuitAnalysis,
    StepUpStats,
    Trace,
)
from sinsim.domain.errors import DomainError
from sinsim.domain.ports import CaseRepository, EquivalenceRepository
from sinsim.observability import log_event
from sinsim.services.build_case import apply_aliases, frontier_map

log = logging.getLogger("sinsim.sc")

IN_OPERATION = "Operación"
COMPENSATOR_PREFIXES = ("svc:", "statcom:")
LINK_PREFIX = "link:"


@dataclass
class _Built:
    """Red de cortocircuito derivada y todo lo que la acompaña."""

    net: pp.pandapowerNet
    n_case_buses: int
    sources: list[ScSource] = field(default_factory=list)
    imputed: list[Any] = field(default_factory=list)
    without_step_up: list[str] = field(default_factory=list)
    zero_sources: list[ScZeroSource] = field(default_factory=list)
    excluded: list[ScExcluded] = field(default_factory=list)
    by_method: dict[str, int] = field(default_factory=dict)
    curated: int = 0


def _bus_index(net: pp.pandapowerNet) -> dict[str, int]:
    return {str(name): int(idx) for idx, name in net.bus["name"].items()}


def _step_up_row(trafo_id: str, t2: pd.DataFrame, t3: pd.DataFrame) -> tuple[pd.Series, str] | None:
    hit = t2[t2["trafo_id"] == trafo_id]
    if not hit.empty:
        return hit.iloc[0], "2w"
    hit = t3[t3["trafo_id"] == trafo_id]
    if not hit.empty:
        return hit.iloc[0], "3w"
    return None


def _positive_or_zero(value: object) -> float:
    """Pérdidas de cobre faltantes (NaN/None) valen 0 en la red de cortocircuito."""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return v if v == v and v > 0 else 0.0


def _lv_side(row: pd.Series, kind: str, rated_u: float | None) -> tuple[float, float, float, float]:
    """`(vn_lv_kv, sn_mva, vk_percent, vkr_percent)` del par alta–baja del elevador.

    En un tridevanado se usa el devanado por debajo de 57,5 kV más cercano a `ratedU` (o el más
    bajo) y la impedancia del par alta–ese devanado según la convención de pandapower.
    """
    if kind == "2w":
        return (
            float(row["vn_lv_kv"]),
            float(row["sn_mva"]),
            float(row["vk_percent"]),
            _positive_or_zero(row.get("vkr_percent")),
        )
    options: list[tuple[float, str]] = []
    for side in ("mv", "lv"):
        v = float(row[f"vn_{side}_kv"])
        if v < rules.SDL_MAX_KV:
            options.append((v, side))
    if not options:
        options = [(float(row["vn_lv_kv"]), "lv")]
    if rated_u is not None:
        v, side = min(options, key=lambda o: abs(o[0] - rated_u))
    else:
        v, side = min(options)
    # Convención de pandapower para 3 devanados: vk_hv = HV–MV, vk_mv = MV–LV, vk_lv = HV–LV.
    pair = "hv" if side == "mv" else "lv"
    sn = float(min(row["sn_hv_mva"], row[f"sn_{side}_mva"]))
    vkr = _positive_or_zero(row.get(f"vkr_{pair}_percent"))
    return v, sn, float(row[f"vk_{pair}_percent"]), vkr


def build_sc_net(
    net_json: str,
    snapshot: LoadedSnapshot,
    equivalences: EquivalenceRepository,
    cfg: LoadedConfig,
    *,
    on: date,
) -> _Built:
    """Red de cortocircuito derivada del caso (research R3; FR-064 a FR-068)."""
    sc_cfg = cfg.config.shortcircuit
    net = pp.from_json_string(net_json)
    n_case_buses = len(net.bus)
    tables, _ = apply_aliases(snapshot.tables, equivalences.substation_aliases(on))
    frontier = frontier_map(
        tables.buses, tables.trafos2w, tables.trafos3w, cfg.config.network.min_vn_kv
    )
    units = tables.generators
    units = units[units["state"] == IN_OPERATION]
    built = _Built(net=net, n_case_buses=n_case_buses)
    by_name = _bus_index(net)

    # Plantas del despacho y compensadores fuera: las fuentes vienen de las unidades (R3).
    for name in net.gen["name"].astype(str):
        if name.startswith(COMPENSATOR_PREFIXES):
            built.excluded.append(ScExcluded(unit_id=name, reason="compensador"))
    net.gen.drop(net.gen.index, inplace=True)
    for _, s in net.sgen.iterrows():
        name = str(s["name"])
        if name.startswith(LINK_PREFIX) and not sc_cfg.international_links_contribute:
            built.zero_sources.append(
                ScZeroSource(
                    resource=name.removeprefix(LINK_PREFIX),
                    bus_id=str(net.bus.at[int(s["bus"]), "name"]),
                    reason="enlace internacional sin fuente pública de potencia de cortocircuito "
                    "(S29)",
                )
            )
    net.sgen.drop(net.sgen.index, inplace=True)

    medians = rules.medians_by_tech(units[units["tech"].isin(rules.SYNC_TECHS)])
    rg = rules.RgRatios(sc_cfg.rg_ratio_large, sc_cfg.rg_ratio_small, sc_cfg.rg_ratio_lv)
    gen_bus_by_trafo: dict[str, tuple[int, int]] = {}

    def resolve_bus(unit: pd.Series) -> int | None:
        bus = unit.get("bus")
        if not isinstance(bus, str):
            return None
        if bus in by_name:
            return by_name[bus]
        moved = frontier.get(bus)
        return by_name.get(moved) if moved else None

    for _, u in units.iterrows():
        unit_id = str(u["unit_id"])
        tech = str(u["tech"])
        bus_idx = resolve_bus(u)
        if bus_idx is None:
            built.excluded.append(ScExcluded(unit_id=unit_id, reason="sin_barra"))
            continue
        bus_id = str(net.bus.at[bus_idx, "name"])
        bus_kv = float(net.bus.at[bus_idx, "vn_kv"])
        if tech in rules.CONVERTER_TECHS:
            sn = rules._positive(u.get("sn_mva")) or rules._positive(u.get("p_max_mw"))
            if sn is None:
                built.excluded.append(ScExcluded(unit_id=unit_id, reason="sin_parametros"))
                continue
            pp.create_sgen(
                net,
                bus=bus_idx,
                p_mw=0.0,
                sn_mva=sn,
                name=unit_id,
                k=sc_cfg.converter_k,
                generator_type="current_source",
            )
            built.sources.append(
                ScSource(
                    unit_id=unit_id,
                    kind="convertidor",
                    bus_id=bus_id,
                    sn_mva=sn,
                    vn_kv=bus_kv,
                    k=sc_cfg.converter_k,
                    origins={"sn_mva": "publicado"},
                )
            )
            continue
        if tech not in rules.SYNC_TECHS:
            built.excluded.append(ScExcluded(unit_id=unit_id, reason=f"tecnologia_{tech}"))
            continue

        equivalence = equivalences.step_up(unit_id, on)
        step = (
            _step_up_row(equivalence.trafo_id, tables.trafos2w, tables.trafos3w)
            if equivalence
            else None
        )
        rated_u = rules._positive(u.get("vn_gen_kv"))
        lv_kv = _lv_side(step[0], step[1], rated_u)[0] if step else None
        params = rules.source_parameters(
            {str(k): v for k, v in u.items()}, medians, step_up_lv_kv=lv_kv, bus_kv=bus_kv, rg=rg
        )
        if params is None:
            built.excluded.append(ScExcluded(unit_id=unit_id, reason="sin_parametros"))
            continue

        gen_bus = bus_idx
        trafo_idx: int | None = None
        trafo_id: str | None = None
        if step is not None and equivalence is not None:
            row, kind = step
            trafo_id = equivalence.trafo_id
            if trafo_id in gen_bus_by_trafo:
                gen_bus, trafo_idx = gen_bus_by_trafo[trafo_id]
            else:
                v_lv, sn_t, vk, vkr = _lv_side(row, kind, rated_u)
                gen_bus = int(
                    pp.create_bus(net, vn_kv=v_lv, name=f"sc:{unit_id}", type="b", in_service=True)
                )
                trafo_idx = int(
                    pp.create_transformer_from_parameters(
                        net,
                        hv_bus=bus_idx,
                        lv_bus=gen_bus,
                        sn_mva=sn_t,
                        vn_hv_kv=float(row["vn_hv_kv"]),
                        vn_lv_kv=v_lv,
                        vkr_percent=vkr,
                        vk_percent=vk,
                        pfe_kw=0.0,
                        i0_percent=0.0,
                        name=f"sc:{trafo_id}",
                    )
                )
                gen_bus_by_trafo[trafo_id] = (gen_bus, trafo_idx)
            built.by_method[equivalence.method] = built.by_method.get(equivalence.method, 0) + 1
            built.curated += int(equivalence.curated)
        else:
            built.without_step_up.append(unit_id)

        r_ohm = rdss_ohm(params.rdss_pu, params.vn_kv, params.sn_mva)
        pp.create_gen(
            net,
            bus=gen_bus,
            p_mw=0.0,
            vm_pu=1.0,
            sn_mva=params.sn_mva,
            name=unit_id,
            vn_kv=params.vn_kv,
            xdss_pu=params.xdss_pu,
            rdss_ohm=r_ohm,
            cos_phi=params.cos_phi,
            pg_percent=0.0,
            power_station_trafo=trafo_idx,
        )
        built.sources.append(
            ScSource(
                unit_id=unit_id,
                kind="sincrona",
                bus_id=bus_id,
                step_up_trafo_id=trafo_id,
                sn_mva=params.sn_mva,
                vn_kv=params.vn_kv,
                cos_phi=params.cos_phi,
                xdss_pu=params.xdss_pu,
                rdss_ohm=r_ohm,
                origins=params.origins,
            )
        )
        built.imputed.extend(params.imputed)
    # pandapower espera `power_station_trafo` como float con NaN; el entero anulable que deja
    # `create_gen` al mezclar índices y None rompe `_create_k_updated_ppci`.
    if len(net.gen):
        if "power_station_trafo" not in net.gen.columns:
            net.gen["power_station_trafo"] = math.nan
        net.gen["power_station_trafo"] = pd.to_numeric(
            net.gen["power_station_trafo"], errors="coerce"
        ).astype(float)
    return built


def calculate(
    *,
    case_id: str,
    run_id: str,
    trace: Trace,
    net_json: str,
    snapshot: LoadedSnapshot,
    cfg: LoadedConfig,
    equivalences: EquivalenceRepository,
) -> ShortCircuitAnalysis:
    """Calcula el cortocircuito trifásico máximo de un caso (FR-062, FR-063, FR-072).

    `trace` es la trazabilidad del caso (fecha, despacho, periodo, versiones); `run_id` es la
    ejecución desde la que se pidió, o un identificador nuevo si se pidió desde el CLI.

    Raises:
        DomainError: `SC_NO_SOURCES` si ninguna unidad entra al cálculo.
    """
    started = time.perf_counter()
    on = trace.dispatch_date
    built = build_sc_net(net_json, snapshot, equivalences, cfg, on=on)
    if not built.sources:
        raise DomainError("SC_NO_SOURCES", f"snapshot {snapshot.date}: sin unidades con parámetros")
    net = built.net
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # Solo las barras del caso: en las barras de generación añadidas pandapower 3.5.6
        # entra en la rama «falla dentro de la unidad» y falla con transformadores de central.
        ppsc.calc_sc(
            net,
            bus=list(range(built.n_case_buses)),
            fault="3ph",
            case="max",
            ip=False,
            ith=False,
            branch_results=False,
        )
    res = net.res_bus_sc
    buses: list[ScBusResult] = []
    for idx in range(built.n_case_buses):
        b = net.bus.loc[idx]
        base_kv = float(b["vn_kv"])
        nominal_kv = (
            float(b["nominal_kv"]) if b.get("nominal_kv") == b.get("nominal_kv") else base_kv
        )
        if cfg.config.shortcircuit.voltage_reference != "paratec_nominal":
            nominal_kv = base_kv
        ikss = float(res.at[idx, "ikss_ka"]) if idx in res.index else 0.0
        skss = float(res.at[idx, "skss_mw"]) if idx in res.index else 0.0
        rk = float(res.at[idx, "rk_ohm"]) if idx in res.index else math.inf
        xk = float(res.at[idx, "xk_ohm"]) if idx in res.index else math.inf
        no_source = not math.isfinite(ikss) or ikss <= 1e-9 or not math.isfinite(xk)
        if no_source:
            buses.append(
                ScBusResult(
                    bus_id=str(b["name"]),
                    substation=str(b["name"]).rpartition("|")[0] or None,
                    subarea=b.get("subarea") if isinstance(b.get("subarea"), str) else None,
                    nominal_kv=nominal_kv,
                    base_kv=base_kv,
                    ikss_ka=0.0,
                    skss_mva=0.0,
                    no_source=True,
                )
            )
            continue
        ikss_n, skss_n = rules.to_nominal(ikss, skss, base_kv, nominal_kv)
        buses.append(
            ScBusResult(
                bus_id=str(b["name"]),
                substation=str(b["name"]).rpartition("|")[0] or None,
                subarea=b.get("subarea") if isinstance(b.get("subarea"), str) else None,
                nominal_kv=nominal_kv,
                base_kv=base_kv,
                ikss_ka=ikss_n,
                skss_mva=skss_n,
                rk_ohm=rk,
                xk_ohm=xk,
                x_r=rules.x_over_r(rk, xk),
                no_source=False,
            )
        )
    buses.sort(key=lambda x: x.bus_id)
    quality = ScQuality(
        imputed=built.imputed,
        generators_without_step_up=sorted(built.without_step_up),
        sc_zero_sources=built.zero_sources,
        excluded=built.excluded,
        step_up_equivalences=StepUpStats(
            matched=sum(built.by_method.values()),
            by_method=dict(sorted(built.by_method.items())),
            curated=built.curated,
            uncurated=sum(built.by_method.values()) - built.curated,
        ),
    )
    duration = time.perf_counter() - started
    config = cfg.config.shortcircuit.model_dump()
    analysis = ShortCircuitAnalysis(
        case_id=case_id,
        run_id=run_id,
        case_hash=case_id,
        sc_config_hash=sc_config_hash(snapshot, cfg, equivalences),
        trace=trace,
        norm=ScNorm(c_max=cfg.config.shortcircuit.c_max),
        config=config,
        assumptions=rules.assumptions(config),
        calculated_at=datetime.now(UTC),
        summary=rules.summarize(buses, built.sources, quality, duration_s=duration),
        buses=buses,
        sources=built.sources,
        quality=quality,
        attribution=cfg.config.attribution.text,
    )
    log_event(
        log,
        "cortocircuito calculado",
        case_id=case_id,
        run_id=run_id,
        n_buses=len(buses),
        n_sources=len(built.sources),
        duration_s=round(duration, 3),
    )
    return analysis


def sc_config_hash(
    snapshot: LoadedSnapshot, cfg: LoadedConfig, equivalences: EquivalenceRepository
) -> str:
    """Hash de configuración, equivalencias y parámetros de máquina (FR-071)."""
    return rules.config_hash(
        cfg.config.shortcircuit.model_dump(),
        equivalences.sha256,
        rules.units_sha256(snapshot.tables.generators),
    )


def get_or_calculate(
    *,
    case_id: str,
    run_id: str,
    trace: Trace,
    net_json: str,
    snapshot: LoadedSnapshot,
    cfg: LoadedConfig,
    equivalences: EquivalenceRepository,
    cases: CaseRepository,
) -> ShortCircuitAnalysis:
    """Devuelve el `sc.json` vigente del caso o calcula, guarda y devuelve (FR-071)."""
    saved = cases.get_sc(case_id)
    if saved is not None and _is_current(saved, case_id, snapshot, cfg, equivalences):
        return saved
    analysis = calculate(
        case_id=case_id,
        run_id=run_id,
        trace=trace,
        net_json=net_json,
        snapshot=snapshot,
        cfg=cfg,
        equivalences=equivalences,
    )
    cases.save_sc(case_id, analysis)
    return analysis


def current(
    case_id: str,
    snapshot: LoadedSnapshot,
    cfg: LoadedConfig,
    equivalences: EquivalenceRepository,
    cases: CaseRepository,
) -> ShortCircuitAnalysis:
    """Resultado guardado vigente, o `SC_NOT_FOUND`."""
    saved = cases.get_sc(case_id)
    if saved is None or not _is_current(saved, case_id, snapshot, cfg, equivalences):
        raise DomainError("SC_NOT_FOUND", f"caso {case_id} sin cortocircuito vigente")
    return saved


def _is_current(
    saved: ShortCircuitAnalysis,
    case_id: str,
    snapshot: LoadedSnapshot,
    cfg: LoadedConfig,
    equivalences: EquivalenceRepository,
) -> bool:
    return saved.case_hash == case_id and saved.sc_config_hash == sc_config_hash(
        snapshot, cfg, equivalences
    )


def select_buses(analysis: ShortCircuitAnalysis, names: list[str]) -> ShortCircuitAnalysis:
    """Filtra las barras pedidas (`SUBESTACION|kV_base` o `SUBESTACION kV_nominal`) (FR-070).

    Raises:
        DomainError: `SC_BUS_NOT_FOUND` con el primer nombre que no exista.
    """
    if not names:
        return analysis
    chosen: list[ScBusResult] = []
    for name in names:
        hit = _find_bus(analysis.buses, name)
        if hit is None:
            raise DomainError(
                "SC_BUS_NOT_FOUND",
                f"barra {name!r}",
                user_message=(
                    f"La barra «{name}» no existe en el caso. Usa el nombre como aparece en la "
                    "tabla de barras."
                ),
            )
        if hit not in chosen:
            chosen.append(hit)
    return analysis.model_copy(update={"buses": chosen})


def _find_bus(buses: list[ScBusResult], name: str) -> ScBusResult | None:
    wanted = name.strip().upper()
    for b in buses:
        if b.bus_id.upper() == wanted:
            return b
    sub, _, kv_text = wanted.rpartition(" ")
    try:
        kv = float(kv_text.replace(",", "."))
    except ValueError:
        return None
    for b in buses:
        bus_sub = b.bus_id.rpartition("|")[0].upper()
        if bus_sub == sub and (
            abs(b.nominal_kv - kv) < 0.6
            or abs(b.base_kv - kv) < 0.6
            or class_kv(kv) == class_kv(b.base_kv)
        ):
            return b
    return None


__all__ = [
    "build_sc_net",
    "calculate",
    "current",
    "get_or_calculate",
    "sc_config_hash",
    "select_buses",
]
