"""Reglas puras del cortocircuito (spec 004: FR-063, FR-064, S26–S28; tareas T412/T413)."""

from __future__ import annotations

import pandas as pd
import pytest

from sinsim.domain import shortcircuit as rules
from sinsim.domain.entities import ScBusResult, ScQuality, ScSource, StepUpStats

RG = rules.RgRatios(large=0.05, small=0.07, lv=0.15)
MEDIANS = {"hidráulica": {"sn_mva": 50.0, "cos_phi": 0.9, "xdss_pu": 0.25, "rdss_pu": 0.004}}


def unit(**over: object) -> dict[str, object]:
    base = {
        "unit_id": "hidráulica:PRUEBA 1",
        "tech": "hidráulica",
        "p_max_mw": 85.0,
        "sn_mva": 100.0,
        "vn_gen_kv": 13.8,
        "cos_phi": 0.85,
        "xdss_pu": 0.2,
        "rdss_pu": 0.005,
    }
    base.update(over)
    return base


def test_published_values_keep_their_origin():
    p = rules.source_parameters(unit(), MEDIANS, step_up_lv_kv=None, bus_kv=230.0, rg=RG)
    assert p is not None
    assert (p.sn_mva, p.cos_phi, p.xdss_pu, p.rdss_pu) == (100.0, 0.85, 0.2, 0.005)
    assert p.origins["sn_mva"] == p.origins["xdss_pu"] == p.origins["rdss_pu"] == "publicado"
    # Sin elevador la máquina va a la barra de alta a la tensión de esa barra (FR-065 c, S31).
    assert p.vn_kv == 230.0 and p.origins["vn_kv"] == "tension_barra"
    assert [i.parameter for i in p.imputed] == ["vn_kv"]


def test_missing_sn_is_derived_from_p_and_cos_phi_then_median():
    p = rules.source_parameters(unit(sn_mva=None), MEDIANS, step_up_lv_kv=None, bus_kv=230, rg=RG)
    assert p is not None and p.sn_mva == pytest.approx(85.0 / 0.85)
    assert p.origins["sn_mva"] == "derivado_p_cosphi"
    q = rules.source_parameters(
        unit(sn_mva=None, p_max_mw=None), MEDIANS, step_up_lv_kv=None, bus_kv=230, rg=RG
    )
    assert q is not None and q.sn_mva == 50.0 and q.origins["sn_mva"] == "mediana"


def test_missing_xdss_uses_the_median_and_zero_counts_as_missing():
    for value in (None, 0.0):
        p = rules.source_parameters(
            unit(xdss_pu=value), MEDIANS, step_up_lv_kv=None, bus_kv=230, rg=RG
        )
        assert p is not None and p.xdss_pu == 0.25 and p.origins["xdss_pu"] == "mediana"


def test_zero_or_missing_ra_falls_back_to_the_iec_ratio():
    # 100 MVA ≥ 100 MVA y U > 1 kV → 0,05 · x''_d
    p = rules.source_parameters(unit(rdss_pu=0.0), MEDIANS, step_up_lv_kv=None, bus_kv=230, rg=RG)
    assert p is not None and p.rdss_pu == pytest.approx(0.05 * 0.2)
    assert p.origins["rdss_pu"] == "relacion_iec"
    small = rules.source_parameters(
        unit(rdss_pu=None, sn_mva=40.0), MEDIANS, step_up_lv_kv=None, bus_kv=230, rg=RG
    )
    assert small is not None and small.rdss_pu == pytest.approx(0.07 * 0.2)


def test_step_up_low_voltage_prevails_over_rated_u():
    p = rules.source_parameters(
        unit(vn_gen_kv=13.2), MEDIANS, step_up_lv_kv=13.8, bus_kv=230, rg=RG
    )
    assert p is not None and p.vn_kv == 13.8 and p.origins["vn_kv"] == "tension_elevador"
    same = rules.source_parameters(
        unit(vn_gen_kv=13.8), MEDIANS, step_up_lv_kv=13.8, bus_kv=230, rg=RG
    )
    assert same is not None and same.origins["vn_kv"] == "publicado"


def test_unit_without_any_way_to_get_parameters_is_rejected():
    assert (
        rules.source_parameters(
            unit(xdss_pu=None, tech="térmica"), {}, step_up_lv_kv=None, bus_kv=230, rg=RG
        )
        is None
    )


def test_medians_ignore_missing_and_zero_values():
    df = pd.DataFrame(
        {
            "tech": ["hidráulica"] * 3,
            "sn_mva": [10.0, 30.0, None],
            "cos_phi": [0.8, 0.0, 0.9],
            "xdss_pu": [0.1, 0.3, 0.0],
            "rdss_pu": [None, None, None],
        }
    )
    meds = rules.medians_by_tech(df)["hidráulica"]
    assert set(meds) == {"sn_mva", "cos_phi", "xdss_pu"}
    assert meds["sn_mva"] == pytest.approx(20.0)
    assert meds["cos_phi"] == pytest.approx(0.85) and meds["xdss_pu"] == pytest.approx(0.2)


def test_to_nominal_corrects_current_and_power_by_the_voltage_ratio():
    ikss, skss = rules.to_nominal(10.0, 1000.0, base_kv=230.0, nominal_kv=220.0)
    assert ikss == pytest.approx(10.0 * 220 / 230)
    assert skss == pytest.approx(1000.0 * (220 / 230) ** 2)
    assert rules.to_nominal(10.0, 1000.0, 115.0, 115.0) == (10.0, 1000.0)


def test_x_over_r_handles_zero_and_missing_resistance():
    assert rules.x_over_r(2.0, 10.0) == 5.0
    assert rules.x_over_r(0.0, 10.0) is None
    assert rules.x_over_r(None, 10.0) is None


def test_config_hash_changes_with_k_and_equivalences():
    base = rules.config_hash({"converter_k": 1.0}, "eq", "units")
    assert base != rules.config_hash({"converter_k": 1.2}, "eq", "units")
    assert base != rules.config_hash({"converter_k": 1.0}, "otras", "units")
    assert base == rules.config_hash({"converter_k": 1.0}, "eq", "units")


def test_summary_counts_sources_imputations_and_no_source_buses():
    buses = [
        ScBusResult(bus_id="A|230", nominal_kv=220, base_kv=230, ikss_ka=10, skss_mva=4000),
        ScBusResult(bus_id="B|115", nominal_kv=115, base_kv=115, ikss_ka=3, skss_mva=600),
        ScBusResult(
            bus_id="C|115", nominal_kv=115, base_kv=115, ikss_ka=0, skss_mva=0, no_source=True
        ),
    ]
    sources = [
        ScSource(unit_id="u1", kind="sincrona", bus_id="A|230", sn_mva=100, vn_kv=13.8, origins={}),
        ScSource(
            unit_id="s1",
            kind="convertidor",
            bus_id="B|115",
            sn_mva=20,
            vn_kv=115,
            k=1.0,
            origins={},
        ),
    ]
    quality = ScQuality(
        imputed=[],
        generators_without_step_up=["u1"],
        sc_zero_sources=[],
        excluded=[],
        step_up_equivalences=StepUpStats(matched=0, by_method={}, curated=0, uncurated=0),
    )
    s = rules.summarize(buses, sources, quality, duration_s=1.5)
    assert (s.n_buses, s.n_sources_sync, s.n_sources_converter, s.n_no_source) == (3, 1, 1, 1)
    assert s.max_ikss is not None and s.max_ikss.bus_id == "A|230"
    assert s.min_skss is not None and s.min_skss.bus_id == "B|115"
    assert s.n_without_step_up == 1


def test_assumptions_list_s26_to_s31():
    ids = [a.id for a in rules.assumptions({"rg_ratio_source": "IEC"})]
    assert ids == ["S26", "S27", "S28", "S29", "S30", "S31"]
