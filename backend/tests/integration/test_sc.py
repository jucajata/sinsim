"""Servicio de cortocircuito (spec 004): SC-021 a SC-024, elevadores, convertidores, persistencia.

Corre sobre el caso del snapshot de fixtures (período 19). La red de tres barras valida el
cálculo contra IEC 60909 a mano (T417 a).
"""

from __future__ import annotations

import csv
import math
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandapower as pp
import pandapower.shortcircuit as ppsc
import pytest

from sinsim.adapters.sources_to_pandapower.buses import class_kv
from sinsim.adapters.storage.cases import FileCaseRepository
from sinsim.adapters.storage.equivalences import CsvEquivalenceRepository
from sinsim.config import load_config, sinsim_version
from sinsim.domain.entities import Trace
from sinsim.domain.errors import DomainError
from sinsim.domain.shortcircuit import propose_step_ups
from sinsim.services import sc
from sinsim.services.build_case import apply_aliases, build_case
from sinsim.services.run_flow import solver_settings
from tests.conftest import FIXTURES

# --- SC-021: red de tres barras contra el cálculo a mano -------------------------------------


def test_three_bus_network_matches_iec_60909_hand_calculation():
    """Unidad de 150 MVA (x''_d = 0,2; cos φ 0,85) tras su elevador 230/13,8 kV de 12 %.

    Cálculo a mano (IEC 60909-0 §6.7.2, unidad sin regulador en carga): K_SO = c/(1 + x''_d·sin φ)
    con U_nQ = U_rTHV y U_rG = U_rTLV; Z_S = K_SO·(t_r²·Z_G + Z_THV); Ikss = c·U_n/(√3·|Z_S|).
    pandapower 3.5.6 aplica además la corrección K_T del transformador de red al de central, lo
    que lo separa del valor a mano en menos del 1 % (tolerancia de SC-021).
    """
    net = pp.create_empty_network(sn_mva=100)
    hv = pp.create_bus(net, 230.0)
    lv = pp.create_bus(net, 13.8)
    far = pp.create_bus(net, 230.0)
    pp.create_line_from_parameters(net, hv, far, 50, 0.05, 0.4, 10, 1.0)
    trafo = pp.create_transformer_from_parameters(net, hv, lv, 150, 230, 13.8, 0.3, 12.0, 0, 0)
    pp.create_gen(
        net,
        lv,
        p_mw=0,
        vm_pu=1.0,
        sn_mva=150,
        vn_kv=13.8,
        xdss_pu=0.2,
        rdss_ohm=0.006348,
        cos_phi=0.85,
        pg_percent=0,
        power_station_trafo=trafo,
    )
    net.gen["power_station_trafo"] = net.gen["power_station_trafo"].astype(float)
    ppsc.calc_sc(net, bus=[hv, far], fault="3ph", case="max")

    c, x_g, sin_phi = 1.1, 0.2, math.sqrt(1 - 0.85**2)
    ratio = 230 / 13.8
    z_g = complex(0.006348 * ratio**2, x_g * 13.8**2 / 150 * ratio**2)
    r_t = 0.3 / 100 * 230**2 / 150
    x_t = math.sqrt((12 / 100 * 230**2 / 150) ** 2 - r_t**2)
    k_so = c / (1 + x_g * sin_phi)
    z_s = k_so * (z_g + complex(r_t, x_t))
    ikss_hand = c * 230 / (math.sqrt(3) * abs(z_s))
    skss_hand = math.sqrt(3) * 230 * ikss_hand

    got = net.res_bus_sc.loc[hv]
    assert got.ikss_ka == pytest.approx(ikss_hand, rel=0.01)
    assert got.skss_mw == pytest.approx(skss_hand, rel=0.01)
    assert math.hypot(got.rk_ohm, got.xk_ohm) == pytest.approx(abs(z_s), rel=0.01)
    # En la barra lejana se suma la línea: 50 km de 0,05 + j0,4 Ω/km.
    far_res = net.res_bus_sc.loc[far]
    assert far_res.xk_ohm == pytest.approx(got.xk_ohm + 20.0, rel=0.01)
    assert far_res.rk_ohm == pytest.approx(got.rk_ohm + 2.5, rel=0.02)


# --- Caso de fixtures ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_case(fixture_snapshot, equivalences_repo):
    cfg = load_config()
    built = build_case(
        snapshot=fixture_snapshot,
        dispatch_snapshot=fixture_snapshot,
        period=19,
        equivalences=equivalences_repo,
        cfg=cfg,
        sinsim_version=sinsim_version(),
    )
    trace = Trace(
        snapshot_date=fixture_snapshot.date,
        dispatch_date=fixture_snapshot.date,
        period=19,
        flow_type="ac",
        pandapower_version=pp.__version__,
        sinsim_version=sinsim_version(),
        solver=solver_settings(cfg),
        case_id=built.case.case_id,
    )
    return cfg, built, trace, pp.to_json(built.net)


@pytest.fixture(scope="module")
def equivalences_with_step_ups(fixture_snapshot, equivalences_repo, tmp_path_factory):
    """Copia de las equivalencias de fixtures más una propuesta de `elevadores.csv`."""
    d = tmp_path_factory.mktemp("equivalencias")
    for p in (FIXTURES / "equivalencias").iterdir():
        shutil.copy(p, d / p.name)
    tables, _ = apply_aliases(
        fixture_snapshot.tables, equivalences_repo.substation_aliases(fixture_snapshot.date)
    )
    units = tables.generators[tables.generators.state == "Operación"]
    rows = propose_step_ups(
        units,
        tables.trafos2w,
        tables.trafos3w,
        aliases={},
        class_of=class_kv,
        valid_from=fixture_snapshot.date,
    )
    assert rows, "los fixtures deben permitir casar al menos un elevador"
    with (d / "elevadores.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["unit_id", "trafo_id", "method", "curated", "valid_from", "valid_to", "note"])
        for r in rows:
            w.writerow(
                [r.unit_id, r.trafo_id, r.method, "false", r.valid_from.isoformat(), "", r.note]
            )
    return CsvEquivalenceRepository(d), len(rows)


def calculate(built_case, fixture_snapshot, equivalences):
    cfg, built, trace, net_json = built_case
    return sc.calculate(
        case_id=built.case.case_id,
        run_id=str(uuid.uuid4()),
        trace=trace,
        net_json=net_json,
        snapshot=fixture_snapshot,
        cfg=cfg,
        equivalences=equivalences,
    )


def test_every_synchronous_unit_is_accounted_for(built_case, fixture_snapshot, equivalences_repo):
    """SC-023: con elevador + sin elevador + excluidas = unidades síncronas en operación."""
    analysis = calculate(built_case, fixture_snapshot, equivalences_repo)
    g = fixture_snapshot.tables.generators
    n_sync = int((g.tech.isin(["hidráulica", "térmica"]) & (g.state == "Operación")).sum())
    sync_sources = [s for s in analysis.sources if s.kind == "sincrona"]
    excluded_units = [
        e for e in analysis.quality.excluded if e.unit_id.split(":")[0] in ("hidráulica", "térmica")
    ]
    assert len(sync_sources) + len(excluded_units) == n_sync
    assert analysis.summary.n_sources_sync == len(sync_sources)
    assert analysis.summary.n_buses == len(analysis.buses) > 500
    assert analysis.summary.duration_s < 30.0  # SC-020


def test_every_parameter_has_an_origin_and_results_are_physical(
    built_case, fixture_snapshot, equivalences_repo
):
    """SC-024 y SC-022 (coherencia interna)."""
    analysis = calculate(built_case, fixture_snapshot, equivalences_repo)
    for s in analysis.sources:
        if s.kind == "sincrona":
            assert set(s.origins) == {"sn_mva", "cos_phi", "xdss_pu", "vn_kv", "rdss_pu"}
            assert s.rdss_ohm is not None and s.rdss_ohm > 0 and s.xdss_pu and s.xdss_pu > 0
        else:
            assert s.k == 1.0 and s.origins == {"sn_mva": "publicado"}
    imputed_units = {i.unit_id for i in analysis.quality.imputed}
    assert analysis.summary.n_imputed_units == len(imputed_units)
    with_source = [b for b in analysis.buses if not b.no_source]
    assert with_source and all(0 < b.ikss_ka < 200 for b in with_source)
    assert all(b.x_r is None or b.x_r > 0 for b in with_source)
    assert [b.bus_id for b in analysis.buses] == sorted(b.bus_id for b in analysis.buses)
    corrected = [b for b in with_source if b.nominal_kv != b.base_kv]
    assert corrected, "el caso tiene barras de 220 kV en base 230 (S26)"
    for b in corrected:
        assert b.skss_mva == pytest.approx(math.sqrt(3) * b.nominal_kv * b.ikss_ka, rel=1e-6)


def test_compensators_are_excluded_and_international_links_do_not_contribute(
    built_case, fixture_snapshot, equivalences_repo
):
    analysis = calculate(built_case, fixture_snapshot, equivalences_repo)
    reasons = {e.reason for e in analysis.quality.excluded}
    assert "compensador" in reasons
    assert all(not s.unit_id.startswith(("svc:", "statcom:")) for s in analysis.sources)
    for z in analysis.quality.sc_zero_sources:
        assert "S29" in z.reason
    assert [a.id for a in analysis.assumptions] == ["S26", "S27", "S28", "S29", "S30", "S31"]


def test_step_up_transformers_change_the_result_at_their_bus(
    built_case, fixture_snapshot, equivalences_repo, equivalences_with_step_ups
):
    repo, n_rows = equivalences_with_step_ups
    without = calculate(built_case, fixture_snapshot, equivalences_repo)
    with_ = calculate(built_case, fixture_snapshot, repo)
    assert without.quality.step_up_equivalences.matched == 0
    assert 0 < with_.quality.step_up_equivalences.matched <= n_rows
    assert (
        with_.quality.step_up_equivalences.uncurated == with_.quality.step_up_equivalences.matched
    )
    assert len(with_.quality.generators_without_step_up) < len(
        without.quality.generators_without_step_up
    )
    matched = next(s for s in with_.sources if s.step_up_trafo_id)
    assert matched.vn_kv < 57.5  # la máquina queda a su tensión, tras el elevador
    before = next(b for b in without.buses if b.bus_id == matched.bus_id)
    after = next(b for b in with_.buses if b.bus_id == matched.bus_id)
    assert after.ikss_ka != pytest.approx(before.ikss_ka, rel=1e-6)
    assert after.ikss_ka < before.ikss_ka  # la reactancia del elevador reduce la corriente (S31)
    # El hash de configuración cambia con las equivalencias (FR-071).
    assert with_.sc_config_hash != without.sc_config_hash


def test_converter_sources_add_their_rated_current(built_case, fixture_snapshot, equivalences_repo):
    cfg, built, trace, net_json = built_case
    base = calculate(built_case, fixture_snapshot, equivalences_repo)
    solar = next(s for s in base.sources if s.kind == "convertidor")
    bus_before = next(b for b in base.buses if b.bus_id == solar.bus_id)
    # Sin convertidores: quitar las plantas solares y eólicas del snapshot.
    g = fixture_snapshot.tables.generators
    trimmed = fixture_snapshot.tables.__class__(
        **{**fixture_snapshot.tables.__dict__, "generators": g[~g.tech.isin(["solar", "eólica"])]}
    )
    snap2 = fixture_snapshot.__class__(
        date=fixture_snapshot.date,
        manifest=fixture_snapshot.manifest,
        manifest_sha256=fixture_snapshot.manifest_sha256,
        tables=trimmed,
    )
    no_conv = sc.calculate(
        case_id=built.case.case_id,
        run_id="x",
        trace=trace,
        net_json=net_json,
        snapshot=snap2,
        cfg=cfg,
        equivalences=equivalences_repo,
    )
    bus_after = next(b for b in no_conv.buses if b.bus_id == solar.bus_id)
    assert no_conv.summary.n_sources_converter == 0
    assert bus_after.ikss_ka < bus_before.ikss_ka


def test_persistence_reuses_the_saved_result_until_configuration_changes(
    built_case, fixture_snapshot, equivalences_repo, equivalences_with_step_ups, tmp_path: Path
):
    cfg, built, trace, net_json = built_case
    cases = FileCaseRepository(tmp_path / "cases")
    cases.save_case(built.case, net_json)
    kwargs = dict(
        case_id=built.case.case_id,
        run_id="r1",
        trace=trace,
        net_json=net_json,
        snapshot=fixture_snapshot,
        cfg=cfg,
        equivalences=equivalences_repo,
        cases=cases,
    )
    first = sc.get_or_calculate(**kwargs)
    assert (tmp_path / "cases" / built.case.case_id / "sc.json").exists()
    second = sc.get_or_calculate(**{**kwargs, "run_id": "r2"})
    assert second.calculated_at == first.calculated_at and second.run_id == "r1"
    assert (
        sc.current(built.case.case_id, fixture_snapshot, cfg, equivalences_repo, cases).run_id
        == "r1"
    )
    repo, _ = equivalences_with_step_ups
    third = sc.get_or_calculate(**{**kwargs, "run_id": "r3", "equivalences": repo})
    assert third.run_id == "r3" and third.sc_config_hash != first.sc_config_hash
    with pytest.raises(DomainError) as exc:
        sc.current(built.case.case_id, fixture_snapshot, cfg, equivalences_repo, cases)
    assert exc.value.code == "SC_NOT_FOUND"


def test_select_buses_accepts_both_spellings_and_rejects_unknown(
    built_case, fixture_snapshot, equivalences_repo
):
    analysis = calculate(built_case, fixture_snapshot, equivalences_repo)
    target = next(b for b in analysis.buses if b.base_kv == 230.0 and b.nominal_kv == 220.0)
    sub = target.bus_id.rpartition("|")[0]
    picked = sc.select_buses(analysis, [target.bus_id, f"{sub} 220"])
    assert [b.bus_id for b in picked.buses] == [target.bus_id]
    with pytest.raises(DomainError) as exc:
        sc.select_buses(analysis, ["NO EXISTE|230"])
    assert exc.value.code == "SC_BUS_NOT_FOUND" and "NO EXISTE|230" in exc.value.user_message
    assert datetime.now(UTC) > analysis.calculated_at
