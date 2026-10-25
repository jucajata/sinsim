"""Repositorio de snapshots en `data/paratec/<fecha>/` (implementa `SnapshotRepository`).

Al cargar un snapshot se recalcula el SHA-256 de cada archivo y se compara con el manifiesto;
cualquier diferencia es `SNAPSHOT_CORRUPTED` (FR-006). Las tablas se leen con DuckDB.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from sinsim.adapters.sources_to_pandapower._common import to_float, to_text
from sinsim.adapters.sources_to_pandapower.buses import parse_subareas, parse_substation_coords
from sinsim.adapters.sources_to_pandapower.field_mapping import RESPONSE_DATA
from sinsim.adapters.sources_to_pandapower.generators import MACHINE_COLUMNS, machine_params
from sinsim.domain.entities import LoadedSnapshot, Manifest, SnapshotSummary, SnapshotTables
from sinsim.domain.errors import DomainError
from sinsim.scraper.writer import NORMALIZED, RAW_PARATEC, TABLE_NAMES, sha256_bytes, sha256_file


class ParquetSnapshotRepository:
    """Lee snapshots inmutables desde el sistema de archivos."""

    def __init__(self, root: Path, read_only_roots: tuple[Path, ...] = ()) -> None:
        """Crea el repositorio sobre un directorio raíz.

        Args:
            root: Donde se leen y se escriben snapshots (`data/paratec/` o la carpeta de datos
                del usuario).
            read_only_roots: Raíces que solo se leen, después de `root`; en modo instalado, el
                snapshot de demostración del paquete (FR-043).
        """
        self.root = root
        self.read_only_roots = read_only_roots

    def _roots(self) -> tuple[Path, ...]:
        return (self.root, *self.read_only_roots)

    def _dir(self, snapshot_date: date) -> Path:
        """Carpeta del snapshot: la primera raíz que lo tiene; si ninguna, la escribible."""
        name = snapshot_date.isoformat()
        for root in self._roots():
            if (root / name / "manifest.json").exists():
                return root / name
        return self.root / name

    def has(self, snapshot_date: date) -> bool:
        """¿Existe el snapshot en alguna raíz? Evita descargar de nuevo uno incluido."""
        return (self._dir(snapshot_date) / "manifest.json").exists()

    def read_manifest(self, snapshot_date: date) -> tuple[Manifest, str]:
        """Lee el manifiesto y devuelve también su SHA-256."""
        path = self._dir(snapshot_date) / "manifest.json"
        if not path.exists():
            raise DomainError("SNAPSHOT_NOT_FOUND", f"no existe {path.parent}")
        raw = path.read_bytes()
        return Manifest.model_validate_json(raw), sha256_bytes(raw)

    def verify(self, snapshot_date: date) -> list[str]:
        """Devuelve la lista de archivos cuyo checksum no coincide (vacía si está íntegro)."""
        manifest, _ = self.read_manifest(snapshot_date)
        base = self._dir(snapshot_date)
        bad: list[str] = []
        for entry in manifest.files:
            p = base / entry.path
            if not p.exists() or sha256_file(p) != entry.sha256:
                bad.append(entry.path)
        return bad

    def list_summaries(self) -> list[SnapshotSummary]:
        """Lista las fechas disponibles con disponibilidad e integridad (FR-002)."""
        out: list[SnapshotSummary] = []
        names = {
            d.name
            for root in self._roots()
            if root.exists()
            for d in root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        }
        for name in sorted(names):
            try:
                snapshot_date = date.fromisoformat(name)
                manifest, _ = self.read_manifest(snapshot_date)
            except (ValueError, DomainError):
                continue
            counts = manifest.record_counts
            out.append(
                SnapshotSummary(
                    date=snapshot_date,
                    has_paratec=counts.get("normalized.buses", 0) > 0,
                    has_dispatch=counts.get("xm.dispatch.resources", 0) > 0,
                    has_demand=counts.get("xm.demand.nodes", 0) > 0,
                    intact=not self.verify(snapshot_date),
                )
            )
        return out

    def load(self, snapshot_date: date) -> LoadedSnapshot:
        """Carga y verifica un snapshot (FR-006)."""
        manifest, manifest_sha = self.read_manifest(snapshot_date)
        bad = self.verify(snapshot_date)
        if bad:
            raise DomainError(
                "SNAPSHOT_CORRUPTED",
                f"checksum distinto al del manifiesto en: {', '.join(bad)}",
                user_message=(
                    "El snapshot está alterado y no se usa. Archivos afectados: "
                    + ", ".join(bad)
                    + ". Restáuralo desde git o genera uno nuevo con `sinsim scrape`."
                ),
            )
        base = self._dir(snapshot_date) / NORMALIZED
        tables = {name: self._read_table(base / f"{name}.parquet") for name in TABLE_NAMES}
        if not {"subarea", "lat", "lon"} <= set(tables["buses"].columns):
            tables["buses"] = self._with_substation_attrs_from_raw(tables["buses"], snapshot_date)
        if not set(MACHINE_COLUMNS) <= set(tables["generators"].columns):
            tables["generators"] = self._with_machine_params_from_raw(
                tables["generators"], snapshot_date
            )
        return LoadedSnapshot(
            date=snapshot_date,
            manifest=manifest,
            manifest_sha256=manifest_sha,
            tables=SnapshotTables(**tables),
        )

    def _with_substation_attrs_from_raw(
        self, buses: pd.DataFrame, snapshot_date: date
    ) -> pd.DataFrame:
        """Añade `subarea`, `lat` y `lon` a snapshots anteriores a FR-034/FR-035 desde `raw/`.

        `raw/` es inmutable y ya está verificado contra el manifiesto, así que derivar las
        columnas en memoria no altera el snapshot (constitución III.3 y III.4). No escribe nada.
        """
        out = buses.copy()
        raw = sorted(
            (self._dir(snapshot_date) / RAW_PARATEC).glob("*Substation_SubstationInfo.json")
        )
        records: list[dict[str, object]] = []
        if raw:
            payload = json.loads(raw[0].read_text(encoding="utf-8"))
            records = (
                payload.get(RESPONSE_DATA, []) if isinstance(payload, dict) else payload
            ) or []
        subareas = parse_subareas(records)
        coords = parse_substation_coords(records)
        if "subarea" not in out.columns:
            out["subarea"] = out["substation"].map(lambda s: subareas.get(str(s)))
        if "lat" not in out.columns or "lon" not in out.columns:
            out["lat"] = out["substation"].map(lambda s: coords.get(str(s), (None, None))[0])
            out["lon"] = out["substation"].map(lambda s: coords.get(str(s), (None, None))[1])
        return out

    def _with_machine_params_from_raw(
        self, generators: pd.DataFrame, snapshot_date: date
    ) -> pd.DataFrame:
        """Añade las columnas de máquina (spec 004, data-model §2) a snapshots anteriores.

        Mismo principio que `_with_substation_attrs_from_raw`: `raw/` es inmutable y está
        verificado, así que derivar las columnas en memoria no altera el snapshot (constitución
        III.3 y III.4). No escribe nada. Las plantas solares y eólicas solo reciben `sn_mva`.
        """
        out = generators.copy()
        for col in MACHINE_COLUMNS:
            if col not in out.columns:
                out[col] = None
        raw_dir = self._dir(snapshot_date) / RAW_PARATEC
        params: dict[str, dict[str, float | None]] = {}
        for tech, pattern in (
            ("hidráulica", "*HydraulicUnit*.json"),
            ("térmica", "*ThermalUnit*.json"),
        ):
            for rec in self._raw_records(raw_dir, pattern):
                unit = to_text(rec.get("elementName"))
                if unit:
                    params[f"{tech}:{unit}"] = machine_params(rec, tech)
        for tech, pattern in (("solar", "*SolarPlant*.json"), ("eólica", "*WindPlant*.json")):
            for rec in self._raw_records(raw_dir, pattern):
                plant = to_text(rec.get("elementName"))
                if plant:
                    sn = to_float(rec.get("ratedPower")) or to_float(
                        rec.get("netEffectiveCapacity")
                    )
                    params[f"{tech}:{plant}"] = {"sn_mva": sn if sn and sn > 0 else None}
        for col in MACHINE_COLUMNS:
            out[col] = out["unit_id"].map(lambda u, c=col: params.get(str(u), {}).get(c))
            out[col] = pd.to_numeric(out[col], errors="coerce")
        return out

    @staticmethod
    def _raw_records(raw_dir: Path, pattern: str) -> list[dict[str, object]]:
        files = sorted(raw_dir.glob(pattern))
        if not files:
            return []
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        records = payload.get(RESPONSE_DATA, []) if isinstance(payload, dict) else payload
        return list(records or [])

    @staticmethod
    def _read_table(path: Path) -> pd.DataFrame:
        if not path.exists():
            raise DomainError("SNAPSHOT_CORRUPTED", f"falta la tabla {path.name}")
        df = duckdb.sql(f"SELECT * FROM read_parquet('{path.as_posix()}')").df()
        if "missing_params" in df.columns:
            df["missing_params"] = df["missing_params"].map(json.loads)
        return df
