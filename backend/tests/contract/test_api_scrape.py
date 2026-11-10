"""FR-038: descarga de una fecha desde la API con respuestas grabadas (sin red, R-03)."""

from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from sinsim.api.app import create_app
from sinsim.scraper import http as scraper_http
from tests.conftest import make_context
from tests.integration.test_scrape_fixtures import FakeXm

PROBLEM_FIELDS = {"type", "title", "status", "detail", "code", "user_message", "trace_id"}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeXm:
    fake = FakeXm()
    monkeypatch.setattr(scraper_http, "DEFAULT_TRANSPORT", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(scraper_http.RateLimitedClient, "_wait", lambda self: None)
    return fake


@pytest.fixture
def client(tmp_path: Path) -> tuple[TestClient, Path]:
    data_dir = tmp_path / "paratec"
    data_dir.mkdir()
    ctx = make_context(data_dir, tmp_path / "cases")
    return TestClient(
        create_app(ctx), raise_server_exceptions=False, base_url="http://127.0.0.1"
    ), data_dir


def wait_done(client: TestClient, job_id: str, timeout_s: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = client.get(f"/api/snapshots/descargas/{job_id}")
        assert r.status_code == 200, r.text
        job = r.json()
        if job["status"] in ("listo", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("la descarga no terminó a tiempo")


def test_scrape_from_api_creates_snapshot_and_reports_steps(fake: FakeXm, client):
    api, data_dir = client
    r = api.post("/api/snapshots/2026-10-20/descarga")
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] in ("en_cola", "descargando") and job["date"] == "2026-10-20"
    assert "PARATEC no tiene histórico" in job["notice"]
    done = wait_done(api, job["job_id"])
    assert done["status"] == "listo" and done["step"] == "listo", done
    assert done["error"] is None and done["finished_at"] is not None
    assert done["snapshot"] == {
        "date": "2026-10-20",
        "has_paratec": True,
        "has_dispatch": True,
        "has_demand": True,
        "intact": True,
    }
    assert (data_dir / "2026-10-20" / "manifest.json").exists()
    assert not any(p.name.startswith(".tmp-") for p in data_dir.iterdir())
    listed = api.get("/api/snapshots").json()
    assert [s["date"] for s in listed] == ["2026-10-20"]
    # FR-004: la segunda petición no toca nada.
    r = api.post("/api/snapshots/2026-10-20/descarga")
    assert r.status_code == 409 and r.json()["code"] == "SNAPSHOT_EXISTS"
    assert set(r.json()) == PROBLEM_FIELDS


def test_missing_day_ends_in_error_with_cli_code_and_no_partial_snapshot(fake: FakeXm, client):
    api, data_dir = client
    r = api.post("/api/snapshots/2026-10-19/descarga")
    assert r.status_code == 202
    done = wait_done(api, r.json()["job_id"])
    assert done["status"] == "error" and done["step"] == "error"
    assert done["snapshot"] is None
    assert done["error"]["code"] == "XM_FILE_NOT_FOUND"
    assert set(done["error"]) == PROBLEM_FIELDS
    assert (
        "no ha publicado" in done["error"]["user_message"]
        or "XM no tiene" in done["error"]["user_message"]
    )
    assert list(data_dir.iterdir()) == []


def test_only_one_scrape_at_a_time(fake: FakeXm, client, monkeypatch: pytest.MonkeyPatch):
    api, _ = client
    gate = threading.Event()
    original = fake.handler

    def slow_handler(request: httpx.Request) -> httpx.Response:
        gate.wait(timeout=30)
        return original(request)

    monkeypatch.setattr(scraper_http, "DEFAULT_TRANSPORT", httpx.MockTransport(slow_handler))
    first = api.post("/api/snapshots/2026-10-20/descarga")
    assert first.status_code == 202
    second = api.post("/api/snapshots/2026-10-19/descarga")
    assert second.status_code == 409 and second.json()["code"] == "SCRAPE_IN_PROGRESS"
    assert "2026-10-20" in second.json()["user_message"]
    gate.set()
    assert wait_done(api, first.json()["job_id"])["status"] == "listo"
    # Con el cupo libre, se acepta otra.
    assert api.post("/api/snapshots/2026-10-19/descarga").status_code == 202


def test_date_rules_and_unknown_job(fake: FakeXm, client):
    api, _ = client
    later = (date.today() + timedelta(days=2)).isoformat()
    r = api.post(f"/api/snapshots/{later}/descarga")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_DATE"
    r = api.post("/api/snapshots/2026-13-01/descarga")
    assert r.status_code == 422 and r.json()["code"] == "REQUEST_INVALID"
    r = api.get("/api/snapshots/descargas/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and r.json()["code"] == "SCRAPE_JOB_NOT_FOUND"
    # D+1 se admite (FR-039): el fake no tiene ese día, así que termina en XM_FILE_NOT_FOUND.
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    r = api.post(f"/api/snapshots/{tomorrow}/descarga")
    assert r.status_code == 202
    assert wait_done(api, r.json()["job_id"])["error"]["code"] == "XM_FILE_NOT_FOUND"


def test_suggested_date_follows_the_dispatch_publication_hour(client):
    api, _ = client
    r = api.get("/api/snapshots/fecha-sugerida")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"date", "published_at", "timezone"}
    assert body["published_at"] == "15:00" and body["timezone"] == "America/Bogota"
    today = date.today()
    assert body["date"] in (today.isoformat(), (today + timedelta(days=1)).isoformat())
