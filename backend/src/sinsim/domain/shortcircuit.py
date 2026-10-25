"""Reglas puras del cortocircuito IEC 60909 (spec 004: FR-063, FR-064, FR-065, FR-073).

Sin pandapower ni E/S (constitución IV). Aquí viven: las reglas de parámetros faltantes de las
unidades síncronas (FR-064, S27, S28), la propuesta de equivalencias unidad ↔ transformador
elevador (research R4), la corrección a la tensión nominal de PARATEC (S26), la relación X/R, el
resumen y el hash de configuración. Las conversiones de unidades (pu → Ω) están en
`adapters/sources_to_pandapower/generators.py` (constitución III.1).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from sinsim.domain.entities import (
    ScAssumption,
    ScBusResult,
    ScExtreme,
    ScImputed,
    ScMethod,
    ScQuality,
    ScSource,
    ScSummary,
    StepUpEquivalence,
    StepUpMethod,
)

SYNC_TECHS = ("hidráulica", "térmica")
CONVERTER_TECHS = ("solar", "eólica")
MACHINE_PARAMS = ("sn_mva", "cos_phi", "xdss_pu", "rdss_pu")
SDL_MAX_KV = 57.5
"""Un devanado por debajo de este nivel identifica un transformador elevador (S1)."""
LV_TOLERANCE_KV = 0.2
"""Tolerancia para casar la tensión de baja del elevador con `ratedU` (research R4)."""
LARGE_MACHINE_MVA = 100.0
LV_MACHINE_KV = 1.0


# --- Parámetros de las unidades síncronas (FR-064) --------------------------------------------


@dataclass(frozen=True)
class RgRatios:
    """Relaciones R_G/X''_d de IEC 60909-0 §6.6.1 (S28), desde la configuración."""

    large: float
    small: float
    lv: float

    def for_machine(self, sn_mva: float, vn_kv: float) -> float:
        """Relación aplicable según tamaño y tensión de la máquina."""
        if vn_kv <= LV_MACHINE_KV:
            return self.lv
        return self.large if sn_mva >= LARGE_MACHINE_MVA else self.small


@dataclass(frozen=True)
class SourceParams:
    """Parámetros resueltos de una unidad síncrona con el origen de cada uno."""

    sn_mva: float
    vn_kv: float
    cos_phi: float
    xdss_pu: float
    rdss_pu: float
    origins: dict[str, ScMethod]
    imputed: list[ScImputed] = field(default_factory=list)


def _positive(value: object) -> float | None:
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if v == v and v > 0 else None  # excluye NaN y ceros


def medians_by_tech(units: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Medianas por tecnología de los parámetros publicados (> 0), para imputar (FR-064)."""
    out: dict[str, dict[str, float]] = {}
    if units.empty:
        return out
    for tech, group in units.groupby("tech"):
        meds: dict[str, float] = {}
        for col in MACHINE_PARAMS:
            if col not in group.columns:
                continue
            vals = pd.to_numeric(group[col], errors="coerce")
            vals = vals[vals > 0]
            if not vals.empty:
                meds[col] = float(vals.median())
        out[str(tech)] = meds
    return out


def source_parameters(
    unit: Mapping[str, Any],
    medians: Mapping[str, Mapping[str, float]],
    *,
    step_up_lv_kv: float | None,
    bus_kv: float,
    rg: RgRatios,
) -> SourceParams | None:
    """Resuelve los parámetros de una unidad síncrona (FR-064, S27, S28).

    Reglas, en orden y siempre con su origen:
    - `sn_mva`: publicado; si falta, `p_max_mw / cos_phi` (`derivado_p_cosphi`); si tampoco,
      mediana de la tecnología (`mediana`).
    - `cos_phi` y `xdss_pu`: publicado o mediana de la tecnología.
    - `vn_kv`: la tensión de baja del elevador casado manda (`tension_elevador`, registrada
      como imputación si difiere de `ratedU` o este falta); sin elevador, la tensión de la
      barra de alta (`tension_barra`), porque la máquina se conecta ahí directamente (S31).
    - `rdss_pu`: publicado > 0; si falta o es 0, `R_G/X''_d` de IEC 60909 (`relacion_iec`).

    Returns:
        `None` si no hay forma de obtener `sn_mva`, `cos_phi` o `xdss_pu` (la unidad se excluye).
    """
    unit_id = str(unit["unit_id"])
    tech = str(unit.get("tech", ""))
    meds = medians.get(tech, {})
    origins: dict[str, ScMethod] = {}
    imputed: list[ScImputed] = []

    def record(param: str, value: float, method: ScMethod) -> float:
        origins[param] = method
        if method != "publicado":
            imputed.append(ScImputed(unit_id=unit_id, parameter=param, value=value, method=method))
        return value

    cos_phi = _positive(unit.get("cos_phi"))
    if cos_phi is not None and cos_phi <= 1.0:
        cos_phi = record("cos_phi", cos_phi, "publicado")
    elif "cos_phi" in meds:
        cos_phi = record("cos_phi", meds["cos_phi"], "mediana")
    else:
        return None

    sn = _positive(unit.get("sn_mva"))
    p_max = _positive(unit.get("p_max_mw"))
    if sn is not None:
        sn = record("sn_mva", sn, "publicado")
    elif p_max is not None:
        sn = record("sn_mva", p_max / cos_phi, "derivado_p_cosphi")
    elif "sn_mva" in meds:
        sn = record("sn_mva", meds["sn_mva"], "mediana")
    else:
        return None

    xdss = _positive(unit.get("xdss_pu"))
    if xdss is not None:
        xdss = record("xdss_pu", xdss, "publicado")
    elif "xdss_pu" in meds:
        xdss = record("xdss_pu", meds["xdss_pu"], "mediana")
    else:
        return None

    rated_u = _positive(unit.get("vn_gen_kv"))
    if step_up_lv_kv is not None:
        if rated_u is not None and abs(rated_u - step_up_lv_kv) <= LV_TOLERANCE_KV:
            vn = record("vn_kv", step_up_lv_kv, "publicado")
        else:
            vn = record("vn_kv", step_up_lv_kv, "tension_elevador")
    else:
        # Sin elevador la máquina se conecta directamente a la barra de alta (FR-065 c, S31):
        # pandapower refiere Z_G a `vn_kv`, así que debe ser la tensión de esa barra, nunca
        # `ratedU` (daría una impedancia de 13,8 kV en una barra de 230 kV).
        vn = record("vn_kv", bus_kv, "tension_barra")

    rdss = _positive(unit.get("rdss_pu"))
    if rdss is not None:
        rdss = record("rdss_pu", rdss, "publicado")
    else:
        rdss = record("rdss_pu", rg.for_machine(sn, vn) * xdss, "relacion_iec")

    return SourceParams(
        sn_mva=sn,
        vn_kv=vn,
        cos_phi=cos_phi,
        xdss_pu=xdss,
        rdss_pu=rdss,
        origins=origins,
        imputed=imputed,
    )


# --- Equivalencias unidad ↔ transformador elevador (FR-065, research R4) ----------------------

_GEN_MARK = re.compile(r"\b[GU]\d+\b")


def normalize_name(text: object) -> str:
    """Mayúsculas sin tildes ni signos, con espacios simples, para comparar nombres."""
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", s.upper()).split())


def _plant_token(plant: object) -> str:
    parts = [p for p in normalize_name(plant).split() if len(p) >= 3 and not p.isdigit()]
    return parts[0] if parts else ""


def _lv_windings(row: pd.Series) -> list[float]:
    out: list[float] = []
    for col in ("vn_mv_kv", "vn_lv_kv"):
        v = _positive(row.get(col))
        if v is not None and v < SDL_MAX_KV:
            out.append(v)
    return out


def _unit_number(unit: object) -> int | None:
    """Número de la unidad al final de su nombre («GUATAPE 3» → 3)."""
    m = re.search(r"(\d+)\s*$", normalize_name(unit))
    return int(m.group(1)) if m else None


def _name_matches(name: object, token: str) -> bool:
    text = normalize_name(name)
    return bool((token and token in text) or _GEN_MARK.search(text))


def _voltage_matches(lv_windings: list[float], rated_u: float | None) -> bool:
    return rated_u is not None and any(abs(lv - rated_u) <= LV_TOLERANCE_KV for lv in lv_windings)


def _prefer_unit_number(cands: pd.DataFrame, unit_no: int | None) -> pd.Series:
    """Entre varios candidatos, el que lleva la marca `G<n>`/`U<n>` o el número de la unidad."""
    if unit_no is not None:
        mark = re.compile(rf"\b(?:[GU]\s*{unit_no}|{unit_no})\b")
        for _, row in cands.iterrows():
            if mark.search(normalize_name(row.get("name"))):
                return row
    return cands.iloc[0]


def propose_step_ups(
    units: pd.DataFrame,
    trafos2w: pd.DataFrame,
    trafos3w: pd.DataFrame,
    *,
    aliases: Mapping[str, str],
    class_of: Callable[[float], float],
    valid_from: date,
) -> list[StepUpEquivalence]:
    """Propuesta inicial de `elevadores.csv` (research R4), marcada `curated = false`.

    Candidatos: transformadores de la misma subestación (con alias) cuya tensión de alta es de
    la misma clase que la barra de la unidad (`class_of`: 220 ≡ 230, 110 ≡ 115) y con algún
    devanado por debajo de 57,5 kV. Método, en orden: `nombre+tension` (nombre de planta o marca
    `G<n>`/`U<n>` en el transformador **y** devanado de baja igual a `ratedU` ± 0,2 kV),
    `nombre`, `tension` (solo si hay un único candidato). Sin coincidencia ⇒ sin equivalencia.
    """
    if units.empty:
        return []

    def canon(sub: object) -> str:
        s = str(sub or "")
        return aliases.get(s, s)

    frames = []
    for df, kind in ((trafos2w, "2w"), (trafos3w, "3w")):
        if not df.empty:
            part = df.copy()
            part["_kind"] = kind
            frames.append(part)
    if not frames:
        return []
    trafos = pd.concat(frames, ignore_index=True, sort=False)
    trafos["_sub"] = trafos["substation"].map(canon)
    trafos["_hv_class"] = pd.to_numeric(trafos["vn_hv_kv"], errors="coerce").map(
        lambda v: class_of(float(v)) if v == v else None
    )
    trafos["_lv"] = trafos.apply(_lv_windings, axis=1)
    trafos = trafos[trafos["_lv"].map(len) > 0]

    out: list[StepUpEquivalence] = []
    sync = units[units["tech"].isin(SYNC_TECHS)]
    for _, u in sync.iterrows():
        bus_kv = _positive(u.get("vn_kv"))
        if bus_kv is None or not isinstance(u.get("substation"), str):
            continue
        sub = canon(u["substation"])
        cand = trafos[(trafos["_sub"] == sub) & (trafos["_hv_class"] == class_of(bus_kv))]
        if cand.empty:
            continue
        token = _plant_token(u.get("plant"))
        rated_u = _positive(u.get("vn_gen_kv"))
        unit_no = _unit_number(u.get("unit"))
        names = cand[[_name_matches(n, token) for n in cand["name"]]]
        both = names[[_voltage_matches(lv, rated_u) for lv in names["_lv"]]]
        method: StepUpMethod | None = None
        chosen: pd.Series | None = None
        if not both.empty:
            method, chosen = "nombre+tension", _prefer_unit_number(both, unit_no)
        elif not names.empty:
            method, chosen = "nombre", _prefer_unit_number(names, unit_no)
        else:
            volts = cand[[_voltage_matches(lv, rated_u) for lv in cand["_lv"]]]
            if len(volts) == 1:
                method, chosen = "tension", volts.iloc[0]
        if method is None or chosen is None:
            continue
        out.append(
            StepUpEquivalence(
                unit_id=str(u["unit_id"]),
                trafo_id=str(chosen["trafo_id"]),
                method=method,
                curated=False,
                valid_from=valid_from,
                note=f"propuesta automática ({chosen['_kind']}) desde el snapshot {valid_from}",
            )
        )
    return out


# --- Resultados por barra (FR-063, S26) ----------------------------------------------------


def to_nominal(
    ikss_ka: float, skss_mva: float, base_kv: float, nominal_kv: float
) -> tuple[float, float]:
    """Refiere Ikss y Sk de la base por clase del modelo a la tensión nominal de PARATEC (S26).

    Para una misma impedancia de Thevenin, `Ikss = c·U_n/(√3·Z)` es proporcional a U_n y
    `Sk = √3·U_n·Ikss` a U_n²: una barra de 220 kV calculada en base 230 kV tiene 4,3 % menos
    corriente y 8,5 % menos potencia que lo que reporta pandapower. Rk y Xk en Ω no cambian.
    """
    if base_kv <= 0 or nominal_kv <= 0:
        return ikss_ka, skss_mva
    ratio = nominal_kv / base_kv
    return ikss_ka * ratio, skss_mva * ratio**2


def x_over_r(rk_ohm: float | None, xk_ohm: float | None) -> float | None:
    """Relación X/R; `None` si no hay impedancia o la resistencia es nula."""
    if rk_ohm is None or xk_ohm is None or rk_ohm <= 0:
        return None
    return xk_ohm / rk_ohm


def summarize(
    buses: Iterable[ScBusResult],
    sources: Iterable[ScSource],
    quality: ScQuality,
    *,
    duration_s: float,
) -> ScSummary:
    """Resumen del cálculo (data-model §7)."""
    bus_list = list(buses)
    src_list = list(sources)
    with_source = [b for b in bus_list if not b.no_source]
    max_ikss = max(with_source, key=lambda b: b.ikss_ka, default=None)
    min_skss = min(with_source, key=lambda b: b.skss_mva, default=None)
    return ScSummary(
        n_buses=len(bus_list),
        max_ikss=ScExtreme(bus_id=max_ikss.bus_id, value=max_ikss.ikss_ka) if max_ikss else None,
        min_skss=ScExtreme(bus_id=min_skss.bus_id, value=min_skss.skss_mva) if min_skss else None,
        n_sources_sync=sum(1 for s in src_list if s.kind == "sincrona"),
        n_sources_converter=sum(1 for s in src_list if s.kind == "convertidor"),
        n_imputed_units=len({i.unit_id for i in quality.imputed}),
        n_without_step_up=len(quality.generators_without_step_up),
        n_no_source=sum(1 for b in bus_list if b.no_source),
        duration_s=duration_s,
    )


def config_hash(config: Mapping[str, Any], equivalences_sha256: str, units_sha256: str) -> str:
    """Hash de todo lo que, además del caso, determina el resultado (FR-071)."""
    payload = json.dumps(
        {"config": dict(config), "equivalences": equivalences_sha256, "units": units_sha256},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def units_sha256(units: pd.DataFrame) -> str:
    """Hash de los parámetros de máquina de las unidades, en orden de `unit_id`."""
    cols = [
        c
        for c in (
            "unit_id",
            "tech",
            "state",
            "bus",
            "p_max_mw",
            "sn_mva",
            "vn_gen_kv",
            "cos_phi",
            "xdss_pu",
            "rdss_pu",
        )
        if c in units.columns
    ]
    if units.empty:
        return hashlib.sha256(b"").hexdigest()
    text = units[cols].sort_values("unit_id").to_csv(index=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assumptions(config: Mapping[str, Any]) -> list[ScAssumption]:
    """Supuestos S26 a S31 con su texto y su fuente (FR-072)."""
    return [
        ScAssumption(
            id="S26",
            text="Los resultados se refieren a la tensión nominal de PARATEC de cada barra, "
            "no a la base por clase del modelo (S14).",
            source=str(config.get("voltage_reference_source", "")),
        ),
        ScAssumption(
            id="S27",
            text="La reactancia subtransitoria usada es la no saturada; una resistencia de "
            "armadura o una reactancia publicadas como 0 se tratan como no publicadas.",
            source="Decisión del agente, 2026-10-25 (specs/004-cortocircuito/).",
        ),
        ScAssumption(
            id="S28",
            text="Resistencia de armadura no publicada: relación R_G/X''_d de IEC 60909-0 "
            "§6.6.1 por tamaño y tensión de la máquina.",
            source=str(config.get("rg_ratio_source", "")),
        ),
        ScAssumption(
            id="S29",
            text="Los enlaces internacionales no aportan corriente de cortocircuito; la "
            "corriente en Nariño y Norte de Santander queda subestimada.",
            source=str(config.get("international_links_source", "")),
        ),
        ScAssumption(
            id="S30",
            text="Las plantas solares y eólicas aportan k veces su corriente nominal como "
            "fuentes de convertidor pleno.",
            source=str(config.get("converter_k_source", "")),
        ),
        ScAssumption(
            id="S31",
            text="Las unidades sin transformador elevador casado entran en su barra de alta "
            "despreciando la reactancia del elevador, lo que sobreestima la corriente cerca de "
            "ellas; quedan listadas para curar `elevadores.csv`.",
            source="Decisión del usuario, 2026-10-25 (specs/004-cortocircuito/).",
        ),
    ]


__all__ = [
    "CONVERTER_TECHS",
    "MACHINE_PARAMS",
    "SDL_MAX_KV",
    "SYNC_TECHS",
    "RgRatios",
    "SourceParams",
    "assumptions",
    "config_hash",
    "medians_by_tech",
    "normalize_name",
    "propose_step_ups",
    "source_parameters",
    "summarize",
    "to_nominal",
    "units_sha256",
    "x_over_r",
]
