"""Unidades de generación de PARATEC → tabla `generators`.

- Hidráulicas y térmicas vienen por unidad (`HydraulicUnit`, `ThermalUnit`), con el nombre de
  su planta. Solares y eólicas vienen por planta; se modelan como una unidad por planta.
- `bus` sale de `connectionPoint` ("GUATAPE 220", "SAN ANTONIO (BOYACA) 115").
- `p_max_mw = ratedNetMaxP` (unidades) o `netEffectiveCapacity` (plantas renovables).
- Límites de reactiva: PARATEC publica magnitudes positivas de absorción (`minQ`) y
  generación (`maxQ`) a P máxima; en el modelo `min_q_mvar = −absorción` y
  `max_q_mvar = +generación`. Si faltan, el generador se conserva con Q libre y queda
  registrado en `missing_params` (no es un parámetro obligatorio para correr el flujo).
- Parámetros de máquina para el cortocircuito (spec 004, data-model §2): `sn_mva`
  (`ratedS`), `vn_gen_kv` (`ratedU`), `cos_phi` (`ratedPowerFactor`, en (0, 1]), `xdss_pu`
  (reactancia subtransitoria **no saturada**: `xd2` en hidráulicas, `xdSubtrans` en térmicas),
  `xdss_sat_pu`, `rdss_pu` (`ra`), `x2_pu`, `x0_pu`. Un valor publicado como 0 en `xdss_pu` o
  `rdss_pu` es físicamente imposible y se trata como no publicado (S27). Las plantas solares y
  eólicas solo traen `sn_mva`.
- Conversiones pu → Ω para pandapower (constitución III.1): `rdss_ohm` y `xdss_ohm`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from sinsim.adapters.sources_to_pandapower import field_mapping as fm
from sinsim.adapters.sources_to_pandapower._common import quality_fields, to_float, to_text
from sinsim.adapters.sources_to_pandapower.buses import (
    Declared,
    canonical_bus_id,
    parse_connection_point,
)

COLUMNS = [
    "unit_id",
    "unit",
    "plant",
    "bus",
    "substation",
    "vn_kv",
    "p_max_mw",
    "q_absorb_mvar",
    "q_gen_mvar",
    "tech",
    "state",
    "operation_mode",
    "sn_mva",
    "vn_gen_kv",
    "cos_phi",
    "xdss_pu",
    "xdss_sat_pu",
    "rdss_pu",
    "x2_pu",
    "x0_pu",
    "source_id",
    "imputed",
    "imputation_method",
    "missing_params",
]

MACHINE_COLUMNS = (
    "sn_mva",
    "vn_gen_kv",
    "cos_phi",
    "xdss_pu",
    "xdss_sat_pu",
    "rdss_pu",
    "x2_pu",
    "x0_pu",
)
"""Columnas de máquina (spec 004); los snapshots anteriores las reciben desde `raw/`."""

XDSS_FIELD_BY_TECH = {
    "hidráulica": fm.HYDRAULIC_XDSS_FIELD,
    "térmica": fm.THERMAL_XDSS_FIELD,
}


def _positive(value: Any) -> float | None:
    """Valor publicado estrictamente positivo; 0 o faltante devuelve `None` (S27)."""
    v = to_float(value)
    return v if v is not None and v > 0 else None


def machine_params(rec: Mapping[str, Any], tech: str) -> dict[str, float | None]:
    """Parámetros de máquina de una unidad síncrona desde el registro de PARATEC.

    `xdss_pu` toma la reactancia subtransitoria no saturada (`xd2` o `xdSubtrans` según la
    tecnología). `cos_phi` fuera de (0, 1] se descarta. Ceros en `xdss_pu` y `rdss_pu` son
    faltantes (S27).
    """
    cos_phi = to_float(rec.get("ratedPowerFactor"))
    if cos_phi is not None and not 0 < cos_phi <= 1:
        cos_phi = None
    xdss_field = XDSS_FIELD_BY_TECH.get(tech)
    return {
        "sn_mva": _positive(rec.get("ratedS")),
        "vn_gen_kv": _positive(rec.get("ratedU")),
        "cos_phi": cos_phi,
        "xdss_pu": _positive(rec.get(xdss_field)) if xdss_field else None,
        "xdss_sat_pu": _positive(rec.get("satDirectSubtransX")),
        "rdss_pu": _positive(rec.get("ra")),
        "x2_pu": _positive(rec.get("x2")),
        "x0_pu": _positive(rec.get("x0")),
    }


def _no_machine_params(sn_mva: float | None) -> dict[str, float | None]:
    return {col: None for col in MACHINE_COLUMNS} | {"sn_mva": sn_mva}


def rdss_ohm(rdss_pu: float, vn_kv: float, sn_mva: float) -> float:
    """Resistencia subtransitoria en Ω: `rdss_pu · vn_kv² / sn_mva` (pu en la base de la máquina).

    Ejemplo: 0,005 pu, 13,8 kV, 150 MVA → 0,006348 Ω.
    """
    return rdss_pu * vn_kv**2 / sn_mva


def xdss_ohm(xdss_pu: float, vn_kv: float, sn_mva: float) -> float:
    """Reactancia subtransitoria en Ω: `xdss_pu · vn_kv² / sn_mva` (misma base que `rdss_ohm`)."""
    return xdss_pu * vn_kv**2 / sn_mva


def _row(
    *,
    unit: str,
    plant: str,
    tech: str,
    rec: Mapping[str, Any],
    p_max: float | None,
    q_absorb: float | None,
    q_gen: float | None,
    source_id: str,
    declared: Declared,
    machine: Mapping[str, float | None],
) -> dict[str, Any]:
    missing: list[str] = []
    cp = parse_connection_point(to_text(rec.get("connectionPoint")))
    bus = sub = None
    vn_kv = None
    if cp and cp[0] in declared:
        sub, vn_kv = cp
        bus = canonical_bus_id(sub, vn_kv, declared)
    else:
        missing.append("bus")
    if p_max is None or p_max <= 0:
        missing.append("p_max_mw")
    if q_absorb is None or q_gen is None:
        missing.append("q_limits")
    # Los parámetros de máquina no entran en `missing_params`: no condicionan el flujo de carga;
    # el cortocircuito reporta sus imputaciones aparte (FR-073).
    return {
        "unit_id": f"{tech}:{unit}",
        "unit": unit,
        "plant": plant,
        "bus": bus,
        "substation": sub,
        "vn_kv": vn_kv,
        "p_max_mw": p_max,
        "q_absorb_mvar": q_absorb,
        "q_gen_mvar": q_gen,
        "tech": tech,
        "state": to_text(rec.get("elementStateName")),
        "operation_mode": to_text(rec.get("operationMode")),
        **{col: machine[col] for col in MACHINE_COLUMNS},
        **quality_fields(source_id, missing),
    }


def parse_units(
    data: Iterable[Mapping[str, Any]], tech: str, plant_field: str, declared: Declared
) -> list[dict[str, Any]]:
    """Filas para unidades hidráulicas o térmicas."""
    rows = []
    for idx, rec in enumerate(data):
        unit = to_text(rec.get("elementName")) or f"{tech}-{idx}"
        rows.append(
            _row(
                unit=unit,
                plant=to_text(rec.get(plant_field)) or unit,
                tech=tech,
                rec=rec,
                p_max=to_float(rec.get("ratedNetMaxP")),
                q_absorb=to_float(rec.get("minQ")),
                q_gen=to_float(rec.get("maxQ")),
                source_id=f"{tech}:{idx}",
                declared=declared,
                machine=machine_params(rec, tech),
            )
        )
    return rows


def parse_plants(
    data: Iterable[Mapping[str, Any]], tech: str, q_fields: Mapping[str, str], declared: Declared
) -> list[dict[str, Any]]:
    """Filas para plantas solares o eólicas (una unidad equivalente por planta)."""
    absorb_key = next(k for k, v in q_fields.items() if v == "q_absorb_mvar")
    gen_key = next(k for k, v in q_fields.items() if v == "q_gen_mvar")
    rows = []
    for idx, rec in enumerate(data):
        plant = to_text(rec.get("elementName")) or f"{tech}-{idx}"
        p_max = to_float(rec.get("netEffectiveCapacity"))
        rows.append(
            _row(
                unit=plant,
                plant=plant,
                tech=tech,
                rec=rec,
                p_max=p_max,
                q_absorb=to_float(rec.get(absorb_key)),
                q_gen=to_float(rec.get(gen_key)),
                source_id=f"{tech}:{idx}",
                declared=declared,
                # Las plantas renovables aportan su corriente nominal (FR-066): S_n ≈ capacidad.
                machine=_no_machine_params(_positive(rec.get("ratedPower")) or _positive(p_max)),
            )
        )
    return rows


def parse_generators(
    hydraulic: Iterable[Mapping[str, Any]],
    thermal: Iterable[Mapping[str, Any]],
    solar: Iterable[Mapping[str, Any]],
    wind: Iterable[Mapping[str, Any]],
    declared: Declared,
) -> pd.DataFrame:
    """Construye la tabla `generators` con las cuatro tecnologías."""
    rows = [
        *parse_units(hydraulic, "hidráulica", fm.HYDRAULIC_PLANT_FIELD, declared),
        *parse_units(thermal, "térmica", fm.THERMAL_PLANT_FIELD, declared),
        *parse_plants(solar, "solar", fm.SOLAR_Q, declared),
        *parse_plants(wind, "eólica", fm.WIND_Q, declared),
    ]
    return pd.DataFrame(rows, columns=COLUMNS)


__all__ = [
    "COLUMNS",
    "MACHINE_COLUMNS",
    "machine_params",
    "parse_generators",
    "parse_plants",
    "parse_units",
    "rdss_ohm",
    "xdss_ohm",
]
