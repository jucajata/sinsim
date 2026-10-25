"""Contrato de `sinsim sc` y de `sinsim equivalencias elevadores` (contracts/cli-sc.md, HU-10)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sinsim import cli
from sinsim.adapters.storage.export_sc import BUSES_FILE, CSV_FILES, METADATA_FILE
from sinsim.domain.entities import ShortCircuitAnalysis
from tests.conftest import make_context

runner = CliRunner()


@pytest.fixture
def ctx(snapshot_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    context = make_context(snapshot_root, tmp_path / "cases")
    monkeypatch.setattr(cli, "build_context", lambda: context)
    return context


def test_sc_writes_the_three_csv_and_metadata(ctx, tmp_path: Path):
    out = tmp_path / "salida"
    result = runner.invoke(
        cli.app, ["sc", "--fecha", "2026-10-20", "--periodo", "19", "--salida", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert {p.name for p in out.iterdir()} == {*CSV_FILES, METADATA_FILE}
    assert "Cortocircuito trifásico máximo" in result.output and "Mayor Ikss" in result.output
    meta = json.loads((out / METADATA_FILE).read_text(encoding="utf-8"))
    assert meta["tipo"] == "cortocircuito" and meta["periodo"] == 19
    assert meta["norma"]["standard"] == "IEC 60909-0:2016" and meta["pandapower"] == "3.5.6"
    assert [s["id"] for s in meta["supuestos"]] == ["S26", "S27", "S28", "S29", "S30", "S31"]
    assert "XM S.A. E.S.P." in meta["atribucion"]


def test_default_output_folder(ctx, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["sc", "--fecha", "2026-10-20", "--periodo", "7"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "cc-2026-10-20-p07" / BUSES_FILE).exists()


def test_json_is_pure_json_and_matches_the_csv(ctx, tmp_path: Path):
    out = tmp_path / "salida"
    assert (
        runner.invoke(
            cli.app, ["sc", "--fecha", "2026-10-20", "--periodo", "19", "--salida", str(out)]
        ).exit_code
        == 0
    )
    with (out / BUSES_FILE).open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    target = next(r for r in rows if r["sin_fuente"] == "false")
    result = runner.invoke(
        cli.app,
        ["sc", "--fecha", "2026-10-20", "--periodo", "19", "--barra", target["bus_id"], "--json"],
    )
    assert result.exit_code == 0, result.output
    stdout = result.stdout if hasattr(result, "stdout") else result.output
    analysis = ShortCircuitAnalysis.model_validate_json(stdout)  # un único documento JSON
    assert [b.bus_id for b in analysis.buses] == [target["bus_id"]]
    bus = analysis.buses[0]
    assert float(target["ikss_ka"]) == pytest.approx(bus.ikss_ka, rel=1e-5)  # SC-022
    assert float(target["skss_mva"]) == pytest.approx(bus.skss_mva, rel=1e-5)
    assert float(target["x_r"]) == pytest.approx(bus.x_r, rel=1e-5)
    assert not (tmp_path / "cc-2026-10-20-p19").exists()  # --json no escribe archivos


def test_unknown_bus_exits_with_4_and_names_it(ctx):
    result = runner.invoke(
        cli.app, ["sc", "--fecha", "2026-10-20", "--periodo", "19", "--barra", "NO EXISTE|230"]
    )
    assert result.exit_code == 4
    assert "SC_BUS_NOT_FOUND" in result.output and "NO EXISTE|230" in result.output


def test_bad_period_is_usage_error(ctx):
    result = runner.invoke(cli.app, ["sc", "--fecha", "2026-10-20", "--periodo", "25"])
    assert result.exit_code == 2


def test_equivalencias_elevadores_writes_a_proposal(ctx, tmp_path: Path):
    out = tmp_path / "elevadores.csv"
    result = runner.invoke(
        cli.app, ["equivalencias", "elevadores", "--fecha", "2026-10-20", "--salida", str(out)]
    )
    assert result.exit_code == 0, result.output
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and set(rows[0]) == {
        "unit_id",
        "trafo_id",
        "method",
        "curated",
        "valid_from",
        "valid_to",
        "note",
    }
    assert {r["curated"] for r in rows} == {"false"}
    assert {r["method"] for r in rows} <= {"nombre+tension", "nombre", "tension"}
    assert "unidades síncronas con elevador propuesto" in result.output
