"""Snapshots anteriores reciben las columnas de máquina desde `raw/` sin modificarse (T403, T404)."""

from __future__ import annotations

from pathlib import Path

from sinsim.adapters.sources_to_pandapower.generators import MACHINE_COLUMNS
from sinsim.adapters.storage.snapshots import ParquetSnapshotRepository
from sinsim.scraper.writer import sha256_file
from tests.conftest import SNAPSHOT_DATE


def _checksums(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in root.rglob("*") if p.is_file()}


def test_new_snapshots_carry_the_machine_columns(fixture_snapshot):
    g = fixture_snapshot.tables.generators
    assert set(MACHINE_COLUMNS) <= set(g.columns)
    sync = g[g.tech.isin(["hidráulica", "térmica"])]
    assert sync.xdss_pu.notna().sum() > 0.5 * len(sync)


def test_older_snapshot_gets_machine_columns_from_raw_without_writing(snapshot_root: Path):
    repo = ParquetSnapshotRepository(snapshot_root)
    before = _checksums(snapshot_root / SNAPSHOT_DATE.isoformat())
    old = repo.load(SNAPSHOT_DATE).tables.generators.drop(columns=list(MACHINE_COLUMNS))
    derived = repo._with_machine_params_from_raw(old, SNAPSHOT_DATE)
    assert set(MACHINE_COLUMNS) <= set(derived.columns)
    sync = derived[derived.tech.isin(["hidráulica", "térmica"])]
    assert sync.xdss_pu.notna().sum() > 0.5 * len(sync)
    assert (sync.rdss_pu.dropna() > 0).all()
    solar = derived[derived.tech == "solar"]
    assert solar.sn_mva.notna().any() and solar.xdss_pu.isna().all()
    assert _checksums(snapshot_root / SNAPSHOT_DATE.isoformat()) == before
