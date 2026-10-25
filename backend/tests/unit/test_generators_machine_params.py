"""Columnas de máquina de las unidades (spec 004, data-model §2; tarea T404) y conversión pu → Ω."""

from __future__ import annotations

import pytest

from sinsim.adapters.sources_to_pandapower.generators import (
    MACHINE_COLUMNS,
    machine_params,
    parse_units,
    rdss_ohm,
    xdss_ohm,
)

DECLARED = {"GUATAPE": (230.0, 13.8)}


def record(**over: object) -> dict[str, object]:
    base = {
        "elementName": "GUATAPE 1",
        "hydraulicPlant": "GUATAPE",
        "connectionPoint": "GUATAPE 220",
        "ratedNetMaxP": 70.0,
        "minQ": 20.0,
        "maxQ": 40.0,
        "elementStateName": "Operación",
        "ratedS": 80.0,
        "ratedU": 13.8,
        "ratedPowerFactor": 0.9,
        "xd2": 0.21,
        "satDirectSubtransX": 0.19,
        "ra": 0.004,
        "x2": 0.25,
        "x0": 0.08,
    }
    base.update(over)
    return base


def test_hydraulic_unit_takes_xd2_as_unsaturated_subtransient_reactance():
    p = machine_params(record(), "hidráulica")
    assert p == {
        "sn_mva": 80.0,
        "vn_gen_kv": 13.8,
        "cos_phi": 0.9,
        "xdss_pu": 0.21,
        "xdss_sat_pu": 0.19,
        "rdss_pu": 0.004,
        "x2_pu": 0.25,
        "x0_pu": 0.08,
    }


def test_thermal_unit_takes_xd_subtrans():
    p = machine_params(record(xdSubtrans=0.136), "térmica")
    assert p["xdss_pu"] == 0.136


def test_zero_ra_and_zero_xdss_are_missing():
    p = machine_params(record(ra=0, xd2=0), "hidráulica")
    assert p["rdss_pu"] is None and p["xdss_pu"] is None


def test_cos_phi_out_of_range_is_missing():
    assert machine_params(record(ratedPowerFactor=1.4), "hidráulica")["cos_phi"] is None
    assert machine_params(record(ratedPowerFactor="-"), "hidráulica")["cos_phi"] is None


def test_parse_units_adds_the_machine_columns_without_touching_missing_params():
    [row] = parse_units([record(ra=0)], "hidráulica", "hydraulicPlant", DECLARED)
    assert set(MACHINE_COLUMNS) <= set(row)
    assert row["xdss_pu"] == 0.21 and row["rdss_pu"] is None
    assert row["missing_params"] == []


def test_rdss_ohm_known_value():
    # 0,005 pu, 13,8 kV, 150 MVA → 0,005 · 13,8² / 150 = 0,006348 Ω
    assert rdss_ohm(0.005, 13.8, 150.0) == pytest.approx(0.006348)
    assert xdss_ohm(0.2, 13.8, 150.0) == pytest.approx(0.25392)
