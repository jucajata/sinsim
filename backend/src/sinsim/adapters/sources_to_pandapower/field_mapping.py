"""Único mapeo nombre-de-campo-PARATEC → nombre interno (constitución IV).

Cada diccionario relaciona el campo tal como lo publica la API de PARATEC con el nombre
interno que usan las tablas normalizadas. Los adaptadores no deben usar nombres de campos de
PARATEC fuera de este módulo.
"""

from __future__ import annotations

from typing import Final

# Respuesta genérica de la API: {"header": {...}, "data": [...]}
RESPONSE_HEADER: Final = "header"
RESPONSE_DATA: Final = "data"

SUBSTATION: Final[dict[str, str]] = {
    "elementName": "substation",
    "voltageLevel": "voltage_levels_kv",
    "elementStateName": "state",
    "subAreaName": "subarea",
    "latitude": "lat",
    "longitude": "lon",
}

LINE: Final[dict[str, str]] = {
    "name": "name",
    "subStation": "substations_text",
    "ratedVoltage": "vn_kv",
    "ratedCurrent": "rated_current_a",
    "thermalLimit": "thermal_limit_a",
    "emergencyLimit": "emergency_limit_a",
    "length": "length_km",
    "typeLines": "segments",
    "state": "state",
}

LINE_SEGMENT: Final[dict[str, str]] = {
    "length": "length_km",
    "endurance": "r1_ohm_per_km",
    "reactance": "x1_ohm_per_km",
    "susceptance": "b1_us_per_km",
}

LINE_MAP: Final[dict[str, str]] = {
    "nameLine": "name",
    "sub1": "sub1",
    "sub2": "sub2",
}

TRANSFORMER: Final[dict[str, str]] = {
    "elementName": "name",
    "substationName": "substation",
    "windingType": "winding_type",
    "impedanceHighLowNom": "vk_hl_percent",
    "impedanceHighMediumNom": "vk_hm_percent",
    "impedanceMediumLowNom": "vk_ml_percent",
    "highLowCopperLosses": "pcu_hl_kw",
    "highMediumCopperLosses": "pcu_hm_kw",
    "mediumLowCopperLosses": "pcu_ml_kw",
    "ironLosses": "pfe_kw",
    "windingsList": "windings",
    "ltcFlag": "ltc",
    "highStep": "tap_max",
    "lowStep": "tap_min",
    "normalStep": "tap_neutral",
    "step": "tap_step_percent",
    "highStepU": "tap_max_u_kv",
    "lowStepU": "tap_min_u_kv",
    "elementStateName": "state",
}

WINDING: Final[dict[str, str]] = {
    "nomVoltage": "vn_kv",
    "nomCapacity": "sn_mva",
}

WINDING_TYPE_2W: Final = "Bidevanado"
WINDING_TYPE_3W: Final = "Tridevanado"

GENERATING_UNIT: Final[dict[str, str]] = {
    "elementName": "unit",
    "connectionPoint": "connection_point",
    "ratedNetMaxP": "p_max_mw",
    "minQ": "q_absorb_mvar",
    "maxQ": "q_gen_mvar",
    "elementStateName": "state",
    "operationMode": "operation_mode",
    # Parámetros de máquina para el cortocircuito (spec 004, data-model §2).
    "ratedS": "sn_mva",
    "ratedU": "vn_gen_kv",
    "ratedPowerFactor": "cos_phi",
    "satDirectSubtransX": "xdss_sat_pu",
    "ra": "rdss_pu",
    "x2": "x2_pu",
    "x0": "x0_pu",
}
# La reactancia subtransitoria no saturada tiene nombre distinto por tecnología.
HYDRAULIC_XDSS_FIELD: Final = "xd2"
THERMAL_XDSS_FIELD: Final = "xdSubtrans"
HYDRAULIC_PLANT_FIELD: Final = "hydraulicPlant"
THERMAL_PLANT_FIELD: Final = "thermalPlant"

RENEWABLE_PLANT: Final[dict[str, str]] = {
    "elementName": "plant",
    "connectionPoint": "connection_point",
    "netEffectiveCapacity": "p_max_mw",
    "elementStateName": "state",
    "operationMode": "operation_mode",
}
SOLAR_Q: Final[dict[str, str]] = {
    "absorptionCapacity": "q_absorb_mvar",
    "generationCapacity": "q_gen_mvar",
}
WIND_Q: Final[dict[str, str]] = {
    "absorptionCapacityMaxPower": "q_absorb_mvar",
    "generationCapacityMaxPower": "q_gen_mvar",
}

REACTOR: Final[dict[str, str]] = {
    "elementName": "name",
    "subStation": "substation",
    "nominalCapacity": "q_mvar",
    "nomU": "vn_kv",
    "elementState": "state",
    "compensatorType": "compensator_type",
}

CAPACITOR: Final[dict[str, str]] = {
    "elementName": "name",
    "subStation": "substation",
    "ratedCapacity": "q_mvar",
    "ratedVoltage": "vn_kv",
    "elementState": "state",
    "compensationType": "compensator_type",
}

SVC_STATCOM: Final[dict[str, str]] = {
    "elementNames": "name",
    "substationName": "substation",
    "nomVoltage": "vn_kv",
    "inductiveRating": "ind_mvar",
    "capacitiveRating": "cap_mvar",
    "elementType": "kind",
    "elementStateName": "state",
}

STATE_IN_OPERATION: Final = "Operación"
SHUNT_TYPE_PARALLEL: Final = "Derivación"
MISSING_TOKENS: Final = frozenset({"", "-", "N/A", "NA", "null", "None"})
