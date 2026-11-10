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


def test_voltage_digits_in_the_rating_are_not_unit_numbers():
    # «13.8 kV» normalizado deja un «8» suelto: no debe casar CHIVOR 8 con G1.
    u = units(*((f"CHIVOR {n}", "CHIVOR", "CHIVOR", 230.0, 13.8) for n in (1, 8)))
    t2 = trafos2w(
        *((f"CHIVOR G{n} 162 MVA 230/13.8 kV", "CHIVOR", 230.0, 13.8) for n in range(1, 9))
    )
    got = {e.unit_id: e.trafo_id for e in propose(u, t2)}
    assert got["hidráulica:CHIVOR 1"] == "trafo:CHIVOR G1 162 MVA 230/13.8 kV"
    assert got["hidráulica:CHIVOR 8"] == "trafo:CHIVOR G8 162 MVA 230/13.8 kV"


def test_series_numbered_units_use_their_last_digit():
    # GUADALUPE 31…36 (serie 3) salen por los elevadores G1…G6 de EL SALTO.
    u = units(*((f"GUADALUPE 3{n}", "GUADALUPE", "EL SALTO (EPM)", 110.0, 13.8) for n in (1, 2)))
    t2 = trafos2w(
        *(
            (
                f"EL SALTO (EPM) - GUADALUPE {n} G{n} 57 MVA 121.4/13.8 kV",
                "EL SALTO (EPM)",
                121.4,
                13.8,
            )
            for n in (1, 2)
        )
    )
    got = {e.unit_id: e.trafo_id for e in propose(u, t2)}
    assert got["hidráulica:GUADALUPE 31"].endswith("GUADALUPE 1 G1 57 MVA 121.4/13.8 kV")
    assert got["hidráulica:GUADALUPE 32"].endswith("GUADALUPE 2 G2 57 MVA 121.4/13.8 kV")


def test_three_winding_mark_g12_serves_units_one_and_two():
    u = units(*((f"GUADALUPE 4{n}", "GUADALUPE", "GUADALUPE IV", 230.0, 13.8) for n in (1, 2, 3)))
    t3 = pd.DataFrame(
        [
            {
                "trafo_id": f"trafo:GUADALUPE IV G{m} 180 MVA 230/13.2/13.2 kV",
                "name": f"GUADALUPE IV G{m} 180 MVA 230/13.2/13.2 kV",
                "substation": "GUADALUPE IV",
                "vn_hv_kv": 230.0,
                "vn_mv_kv": 13.2,
                "vn_lv_kv": 13.2,
            }
            for m in ("12", "3")
        ]
    )
    got = {e.unit_id: e.trafo_id for e in propose(u, trafos2w(), t3)}
    assert got["hidráulica:GUADALUPE 41"].endswith("G12 180 MVA 230/13.2/13.2 kV")
    assert got["hidráulica:GUADALUPE 42"].endswith("G12 180 MVA 230/13.2/13.2 kV")
    assert got["hidráulica:GUADALUPE 43"].endswith("G3 180 MVA 230/13.2/13.2 kV")


def test_a_unit_mark_of_another_plant_is_not_a_name_match():
    # La marca G1 de un parque solar no hace del transformador el elevador de CUCUANA.
    u = units(("CUCUANA 1", "CUCUANA", "MIROLINDO", 115.0, 13.8))
    t2 = trafos2w(
        ("MIROLINDO - CELSIA SOLAR ESCOBAL II 3 G1 25 MVA 115/34.5 kV", "MIROLINDO", 115.0, 34.5)
    )
    assert propose(u, t2) == []


def test_transformer_named_after_the_substation_matches_by_unit_mark_and_voltage():
    u = units(*((f"ITUANGO {n}", "ITUANGO", "ANTIOQUIA", 500.0, 18.0) for n in (1, 2)))
    t2 = trafos2w(
        ("ANTIOQUIA 1 10 MVA 500/13.2 kV", "ANTIOQUIA", 500.0, 13.2),
        *((f"ANTIOQUIA G{n} 336 MVA 500/18 kV", "ANTIOQUIA", 500.0, 18.0) for n in (1, 2)),
    )
    got = {e.unit_id: e for e in propose(u, t2)}
    assert got["hidráulica:ITUANGO 1"].trafo_id == "trafo:ANTIOQUIA G1 336 MVA 500/18 kV"
    assert got["hidráulica:ITUANGO 2"].trafo_id == "trafo:ANTIOQUIA G2 336 MVA 500/18 kV"
    assert got["hidráulica:ITUANGO 1"].method == "marca+tension"


def test_a_transformer_marked_for_another_unit_is_not_a_voltage_match():
    u = units(("ZIPAEMG 3", "ZIPAEMG", "TERMOZIPA", 115.0, 13.8))
    t2 = trafos2w(("TERMOZIPA 2 G2 41.4 MVA 125/13.8 kV", "TERMOZIPA", 125.0, 13.8))
    assert propose(u, t2) == []


def test_step_up_high_voltage_above_the_bus_class_is_a_candidate():
    # 127 kV es clase 138 para PARATEC, pero es el elevador de una barra de 115 kV.
    u = units(("ZIPAEMG 3", "ZIPAEMG", "TERMOZIPA", 115.0, 13.8))
    t2 = trafos2w(("TERMOZIPA 3 G3 87 MVA 127/13.8 kV", "TERMOZIPA", 127.0, 13.8))
    [eq] = propose(u, t2)
    assert eq.trafo_id == "trafo:TERMOZIPA 3 G3 87 MVA 127/13.8 kV" and eq.method == "marca+tension"


def test_plant_name_inside_a_compound_transformer_name_matches():
    u = units(("FLORES 1 GAS", "FLORES I CC", "TERMOFLORES", 110.0, 13.8))
    t2 = trafos2w(("TERMOFLORES - GAS 1 G1 65 MVA 110/13.8 kV", "TERMOFLORES", 110.0, 13.8))
    [eq] = propose(u, t2)
    assert eq.method == "nombre+tension"


def test_steam_unit_does_not_take_a_gas_turbine_transformer():
    u = units(("FLORES 1 VAPOR", "FLORES I CC", "TERMOFLORES", 110.0, 13.8))
    t2 = trafos2w(
        ("TERMOFLORES - GAS 2 G1 65 MVA 110/13.8 kV", "TERMOFLORES", 110.0, 13.8),
        ("TERMOFLORES - VAPOR 4 G1 65 MVA 110/13.8 kV", "TERMOFLORES", 110.0, 13.8),
    )
    [eq] = propose(u, t2)
    assert eq.trafo_id == "trafo:TERMOFLORES - VAPOR 4 G1 65 MVA 110/13.8 kV"


def test_capacity_sends_units_to_separate_transformers():
    u = units(
        ("CENTRAL 1", "CENTRAL", "SUB", 115.0, 13.8),
        ("CENTRAL 2", "CENTRAL", "SUB", 115.0, 13.8),
    ).assign(sn_mva=40.0)
    t2 = trafos2w(
        ("CENTRAL A 45 MVA 115/13.8 kV", "SUB", 115.0, 13.8),
        ("CENTRAL B 45 MVA 115/13.8 kV", "SUB", 115.0, 13.8),
    ).assign(sn_mva=45.0)
    got = propose(u, t2)
    assert len(got) == 2 and len({e.trafo_id for e in got}) == 2


def test_aliases_reconcile_substation_names():
    u = units(("CENTRAL 1", "CENTRAL", "MONTERIA (ISA)", 115.0, 13.8))
    t2 = trafos2w(("CENTRAL G1 30 MVA 115/13.8 kV", "NUEVA MONTERIA", 115.0, 13.8))
    assert propose(u, t2, aliases={"MONTERIA (ISA)": "NUEVA MONTERIA"})
    assert propose(u, t2) == []


def test_review_flags_a_transformer_of_another_plant_and_overloaded_sharing():
    from types import SimpleNamespace

    from sinsim.domain.shortcircuit import review_step_ups

    u = units(
        ("CHIVOR 1", "CHIVOR", "CHIVOR", 230.0, 13.8),
        ("CHIVOR 8", "CHIVOR", "CHIVOR", 230.0, 13.8),
        ("CUCUANA 1", "CUCUANA", "MIROLINDO", 115.0, 13.8),
    ).assign(sn_mva=140.0)
    t2 = trafos2w(
        ("CHIVOR G1 162 MVA 230/13.8 kV", "CHIVOR", 230.0, 13.8),
        ("MIROLINDO - CELSIA SOLAR ESCOBAL II 3 G1 25 MVA 115/34.5 kV", "MIROLINDO", 115.0, 34.5),
    ).assign(sn_mva=[162.0, 25.0])
    row = lambda unit, trafo: SimpleNamespace(  # noqa: E731
        unit_id=f"hidráulica:{unit}", trafo_id=f"trafo:{trafo}", method="nombre", curated=False
    )
    rows = [
        row("CHIVOR 1", "CHIVOR G1 162 MVA 230/13.8 kV"),
        row("CHIVOR 8", "CHIVOR G1 162 MVA 230/13.8 kV"),
        row("CUCUANA 1", "MIROLINDO - CELSIA SOLAR ESCOBAL II 3 G1 25 MVA 115/34.5 kV"),
    ]
    got = {
        c.unit_id: c for c in review_step_ups(rows, u, t2, EMPTY_3W, aliases={}, class_of=class_kv)
    }
    chivor8 = " ".join(got["hidráulica:CHIVOR 8"].issues)
    assert "marca" in chivor8 and "capacidad" in chivor8
    cucuana = " ".join(got["hidráulica:CUCUANA 1"].issues)
    assert "nombre" in cucuana and "baja" in cucuana
    assert any("capacidad" in i for i in got["hidráulica:CHIVOR 1"].issues)  # comparte con CHIVOR 8
