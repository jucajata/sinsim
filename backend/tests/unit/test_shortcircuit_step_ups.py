"""Propuesta de equivalencias unidad ↔ transformador elevador (spec 004, FR-065; tarea T409)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from sinsim.adapters.sources_to_pandapower.buses import class_kv
from sinsim.domain.shortcircuit import propose_step_ups

ON = date(2026, 10, 24)


def units(*rows: tuple[str, str, str, float, float | None]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "unit_id": f"hidráulica:{u}",
                "unit": u,
                "plant": plant,
                "tech": "hidráulica",
                "substation": sub,
                "vn_kv": kv,
                "vn_gen_kv": rated_u,
                "bus": f"{sub}|{class_kv(kv):g}",
            }
            for u, plant, sub, kv, rated_u in rows
        ]
    )


def trafos2w(*rows: tuple[str, str, float, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trafo_id": f"trafo:{name}",
                "name": name,
                "substation": sub,
                "vn_hv_kv": hv,
                "vn_lv_kv": lv,
            }
            for name, sub, hv, lv in rows
        ]
    )


EMPTY_3W = pd.DataFrame(
    columns=["trafo_id", "name", "substation", "vn_hv_kv", "vn_mv_kv", "vn_lv_kv"]
)


def propose(u: pd.DataFrame, t2: pd.DataFrame, t3: pd.DataFrame = EMPTY_3W, aliases=None):
    return propose_step_ups(u, t2, t3, aliases=aliases or {}, class_of=class_kv, valid_from=ON)


def test_voltage_class_matches_230_kv_transformer_with_220_kv_unit_bus():
    u = units(("ALTO ANCHICAYA 1", "ALTO ANCHICAYA", "ALTO ANCHICAYA", 220.0, 13.8))
    t2 = trafos2w(("ALTO ANCHICAYA G1 129 MVA 230/13.8 kV", "ALTO ANCHICAYA", 230.0, 13.8))
    [eq] = propose(u, t2)
    assert eq.trafo_id == "trafo:ALTO ANCHICAYA G1 129 MVA 230/13.8 kV"
    assert eq.method == "nombre+tension" and eq.curated is False and eq.valid_from == ON


def test_each_unit_prefers_the_transformer_with_its_own_number():
    u = units(
        ("GUATAPE 1", "GUATAPE", "GUATAPE", 230.0, 13.8),
        ("GUATAPE 2", "GUATAPE", "GUATAPE", 230.0, 13.8),
    )
    t2 = trafos2w(
        ("GUATAPE G1 100 MVA 230/13.8 kV", "GUATAPE", 230.0, 13.8),
        ("GUATAPE G2 100 MVA 230/13.8 kV", "GUATAPE", 230.0, 13.8),
    )
    got = {e.unit_id: e.trafo_id for e in propose(u, t2)}
    assert got["hidráulica:GUATAPE 1"].endswith("G1 100 MVA 230/13.8 kV")
    assert got["hidráulica:GUATAPE 2"].endswith("G2 100 MVA 230/13.8 kV")


def test_distribution_transformer_in_the_same_substation_does_not_match_by_name():
    u = units(("AGUA FRESCA 1", "AGUA FRESCA", "AMAGA", 110.0, 6.6))
    t2 = trafos2w(("AMAGA 40 MVA 110/44 kV", "AMAGA", 110.0, 44.0))
    assert propose(u, t2) == []


def test_single_candidate_with_matching_low_voltage_matches_by_voltage_only():
    u = units(("PLANTA X 1", "PLANTA X", "SUB", 115.0, 6.6))
    t2 = trafos2w(("SUB 2 20 MVA 115/6.6 kV", "SUB", 115.0, 6.6))
    [eq] = propose(u, t2)
    assert eq.method == "tension"


def test_two_voltage_only_candidates_are_ambiguous_and_produce_nothing():
    u = units(("PLANTA X 1", "PLANTA X", "SUB", 115.0, 6.6))
    t2 = trafos2w(
        ("SUB 2 20 MVA 115/6.6 kV", "SUB", 115.0, 6.6),
        ("SUB 3 20 MVA 115/6.6 kV", "SUB", 115.0, 6.6),
    )
    assert propose(u, t2) == []


def test_two_units_may_share_one_transformer():
    u = units(
        ("CENTRAL 1", "CENTRAL", "SUB", 115.0, 13.8),
        ("CENTRAL 2", "CENTRAL", "SUB", 115.0, 13.8),
    )
    t2 = trafos2w(("CENTRAL G1 30 MVA 115/13.8 kV", "SUB", 115.0, 13.8))
    got = propose(u, t2)
    assert len(got) == 2 and {e.trafo_id for e in got} == {"trafo:CENTRAL G1 30 MVA 115/13.8 kV"}


def test_three_winding_transformer_with_a_low_voltage_winding_is_a_candidate():
    u = units(("CENTRAL 1", "CENTRAL", "SUB", 115.0, 13.8))
    t3 = pd.DataFrame(
        [
            {
                "trafo_id": "trafo:CENTRAL 1 60 MVA 115/34.5/13.8 kV",
                "name": "CENTRAL 1 60 MVA 115/34.5/13.8 kV",
                "substation": "SUB",
                "vn_hv_kv": 115.0,
                "vn_mv_kv": 34.5,
                "vn_lv_kv": 13.8,
            }
        ]
    )
    [eq] = propose(u, trafos2w(), t3)
    assert eq.method == "nombre+tension" and "(3w)" in eq.note


def test_aliases_reconcile_substation_names():
    u = units(("CENTRAL 1", "CENTRAL", "MONTERIA (ISA)", 115.0, 13.8))
    t2 = trafos2w(("CENTRAL G1 30 MVA 115/13.8 kV", "NUEVA MONTERIA", 115.0, 13.8))
    assert propose(u, t2, aliases={"MONTERIA (ISA)": "NUEVA MONTERIA"})
    assert propose(u, t2) == []
