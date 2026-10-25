"""Contrato de la API del cortocircuito (specs/004-cortocircuito/contracts/openapi-sc.yaml)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sinsim.api.app import create_app

ANALYSIS_FIELDS = {
    "case_id",
    "run_id",
    "case_hash",
    "sc_config_hash",
    "trace",
    "norm",
    "config",
    "assumptions",
    "calculated_at",
    "summary",
    "buses",
    "sources",
    "quality",
    "attribution",
}
BUS_FIELDS = {
    "bus_id",
    "substation",
    "subarea",
    "nominal_kv",
    "base_kv",
    "ikss_ka",
    "skss_mva",
    "rk_ohm",
    "xk_ohm",
    "x_r",
    "no_source",
}


@pytest.fixture
def client(app_context) -> TestClient:
    return TestClient(
        create_app(app_context), raise_server_exceptions=False, base_url="http://127.0.0.1"
    )


def run_id_of(client: TestClient) -> str:
    case = client.post("/api/cases", json={"snapshot_date": "2026-10-20", "period": 19}).json()
    run = client.post(f"/api/cases/{case['case_id']}/runs", json={"flow_type": "ac"}).json()
    return str(run["run_id"])


def test_get_before_post_is_404_sc_not_found(client: TestClient):
    run_id = run_id_of(client)
    r = client.get(f"/api/runs/{run_id}/sc")
    assert r.status_code == 404 and r.json()["code"] == "SC_NOT_FOUND"


def test_post_returns_the_full_analysis_and_get_returns_the_same_document(client: TestClient):
    run_id = run_id_of(client)
    r = client.post(f"/api/runs/{run_id}/sc")
    assert r.status_code == 200, r.text
    body = r.json()
    assert ANALYSIS_FIELDS <= set(body)
    assert body["norm"] == {
        "standard": "IEC 60909-0:2016",
        "fault": "3ph",
        "case": "max",
        "c_max": 1.1,
    }
    assert len(body["buses"]) > 500 and BUS_FIELDS <= set(body["buses"][0])
    assert [a["id"] for a in body["assumptions"]] == ["S26", "S27", "S28", "S29", "S30", "S31"]
    assert "XM S.A. E.S.P." in body["attribution"]
    again = client.get(f"/api/runs/{run_id}/sc")
    assert again.status_code == 200 and again.json() == body


def test_post_with_buses_filters_and_unknown_bus_is_422(client: TestClient):
    run_id = run_id_of(client)
    first = client.post(f"/api/runs/{run_id}/sc").json()["buses"][0]["bus_id"]
    r = client.post(f"/api/runs/{run_id}/sc", json={"buses": [first]})
    assert r.status_code == 200 and [b["bus_id"] for b in r.json()["buses"]] == [first]
    bad = client.post(f"/api/runs/{run_id}/sc", json={"buses": ["NO EXISTE|230"]})
    assert bad.status_code == 422
    problem = bad.json()
    assert problem["code"] == "SC_BUS_NOT_FOUND" and "NO EXISTE|230" in problem["user_message"]


def test_unknown_run_is_404(client: TestClient):
    r = client.post("/api/runs/00000000-0000-0000-0000-000000000000/sc")
    assert r.status_code == 404 and r.json()["code"] == "RUN_NOT_FOUND"
