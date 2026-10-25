"""Tablas de equivalencias versionadas con vigencia (FR-011; contracts/snapshot-format.md §3).

- `recursos_despacho.csv`: recurso del despacho → unidades o planta de PARATEC, o enlace
  internacional con su barra de conexión.
- `nodos_demanda.csv`: nodo del pronóstico → (subestación, kV) de PARATEC.
- `subestaciones_alias.csv` (opcional): nombre de subestación de PARATEC que designa el mismo
  nodo físico que otra ("MONTERIA (ISA)" ≡ "NUEVA MONTERIA"). PARATEC parte algunas
  subestaciones por propietario y ninguna regla general puede deducirlo.
- `coordenadas_subestaciones.csv` (opcional): latitud y longitud WGS84 de subestaciones que
  PARATEC publica sin coordenadas (por ejemplo Pimampiro, en Ecuador). Cada fila cita su
  fuente en `note`; solo completa lo que falta y nunca reemplaza una coordenada de PARATEC.

Una vigencia solapada para la misma clave es `EQUIVALENCE_OVERLAP`. En tiempo de ejecución
solo se consulta la tabla: nunca hay coincidencia aproximada (research R7).
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sinsim.domain.entities import StepUpEquivalence
from sinsim.domain.errors import DomainError

RESOURCES_FILE = "recursos_despacho.csv"
NODES_FILE = "nodos_demanda.csv"
ALIASES_FILE = "subestaciones_alias.csv"
COORDS_FILE = "coordenadas_subestaciones.csv"
STEP_UPS_FILE = "elevadores.csv"
RESOURCE_KINDS = {"plant", "unit", "intl_link"}
STEP_UP_METHODS = {"nombre+tension", "nombre", "tension", "manual"}
STEP_UP_COLUMNS = ("unit_id", "trafo_id", "method", "curated", "valid_from", "valid_to", "note")


@dataclass(frozen=True)
class ResourceRow:
    """Fila de `recursos_despacho.csv`."""

    resource: str
    kind: str
    paratec_ids: list[str]
    connection_bus: str | None
    valid_from: date
    valid_to: date | None
    note: str


@dataclass(frozen=True)
class NodeRow:
    """Fila de `nodos_demanda.csv`."""

    node: str
    ucp: str
    vn_kv: float
    substation: str
    paratec_vn_kv: float
    valid_from: date
    valid_to: date | None
    note: str


@dataclass(frozen=True)
class AliasRow:
    """Fila de `subestaciones_alias.csv`."""

    alias: str
    substation: str
    valid_from: date
    valid_to: date | None
    note: str


@dataclass(frozen=True)
class StepUpRow:
    """Fila de `elevadores.csv` (spec 004): unidad ↔ transformador elevador."""

    unit_id: str
    trafo_id: str
    method: str
    curated: bool
    valid_from: date
    valid_to: date | None
    note: str


@dataclass(frozen=True)
class CoordRow:
    """Fila de `coordenadas_subestaciones.csv`."""

    substation: str
    lat: float
    lon: float
    valid_from: date
    valid_to: date | None
    note: str


def _date(text: str) -> date | None:
    text = text.strip()
    return date.fromisoformat(text) if text else None


def _is_valid(valid_from: date, valid_to: date | None, on: date) -> bool:
    return valid_from <= on and (valid_to is None or on <= valid_to)


def _required_date(rec: dict[str, str], where: str) -> date:
    vf = _date(rec.get("valid_from", ""))
    if vf is None:
        raise DomainError("EQUIVALENCE_OVERLAP", f"{where}: falta valid_from")
    return vf


class CsvEquivalenceRepository:
    """Lee y valida las tablas CSV (implementa `EquivalenceRepository`)."""

    def __init__(self, directory: Path) -> None:
        """Carga las tablas desde `directory` y valida sus vigencias."""
        self.directory = directory
        self._resources = self._read_resources(directory / RESOURCES_FILE)
        self._nodes = self._read_nodes(directory / NODES_FILE)
        self._aliases = self._read_aliases(directory / ALIASES_FILE)
        self._coords = self._read_coords(directory / COORDS_FILE)
        self._step_ups = self._read_step_ups(directory / STEP_UPS_FILE)
        self._check_overlaps()
        h = hashlib.sha256()
        for name in (RESOURCES_FILE, NODES_FILE, ALIASES_FILE, COORDS_FILE, STEP_UPS_FILE):
            p = directory / name
            h.update(p.read_bytes() if p.exists() else b"")
        self._sha256 = h.hexdigest()

    @property
    def sha256(self) -> str:
        """Checksum conjunto de las tablas."""
        return self._sha256

    @staticmethod
    def _read_resources(path: Path) -> list[ResourceRow]:
        if not path.exists():
            return []
        rows: list[ResourceRow] = []
        with path.open(encoding="utf-8", newline="") as fh:
            for n, rec in enumerate(csv.DictReader(fh), start=2):
                kind = rec["kind"].strip()
                where = f"{path.name} línea {n}"
                if kind not in RESOURCE_KINDS:
                    raise DomainError("EQUIVALENCE_OVERLAP", f"{where}: kind inválido {kind!r}")
                ids = [s.strip() for s in rec.get("paratec_ids", "").split(";") if s.strip()]
                rows.append(
                    ResourceRow(
                        resource=rec["resource"].strip(),
                        kind=kind,
                        paratec_ids=ids,
                        connection_bus=rec.get("connection_bus", "").strip() or None,
                        valid_from=_required_date(rec, where),
                        valid_to=_date(rec.get("valid_to", "")),
                        note=rec.get("note", "").strip(),
                    )
                )
        return rows

    @staticmethod
    def _read_nodes(path: Path) -> list[NodeRow]:
        if not path.exists():
            return []
        rows: list[NodeRow] = []
        with path.open(encoding="utf-8", newline="") as fh:
            for n, rec in enumerate(csv.DictReader(fh), start=2):
                rows.append(
                    NodeRow(
                        node=rec["node"].strip(),
                        ucp=rec.get("ucp", "").strip(),
                        vn_kv=float(rec["vn_kv"].replace(",", ".")),
                        substation=rec["substation"].strip(),
                        paratec_vn_kv=float(rec["paratec_vn_kv"].replace(",", ".")),
                        valid_from=_required_date(rec, f"{path.name} línea {n}"),
                        valid_to=_date(rec.get("valid_to", "")),
                        note=rec.get("note", "").strip(),
                    )
                )
        return rows

    @staticmethod
    def _read_aliases(path: Path) -> list[AliasRow]:
        if not path.exists():
            return []
        rows: list[AliasRow] = []
        with path.open(encoding="utf-8", newline="") as fh:
            for n, rec in enumerate(csv.DictReader(fh), start=2):
                rows.append(
                    AliasRow(
                        alias=rec["alias"].strip(),
                        substation=rec["substation"].strip(),
                        valid_from=_required_date(rec, f"{path.name} línea {n}"),
                        valid_to=_date(rec.get("valid_to", "")),
                        note=rec.get("note", "").strip(),
                    )
                )
        return rows

    @staticmethod
    def _read_coords(path: Path) -> list[CoordRow]:
        if not path.exists():
            return []
        rows: list[CoordRow] = []
        with path.open(encoding="utf-8", newline="") as fh:
            for n, rec in enumerate(csv.DictReader(fh), start=2):
                where = f"{path.name} línea {n}"
                try:
                    lat = float(rec["lat"].replace(",", "."))
                    lon = float(rec["lon"].replace(",", "."))
                except (KeyError, ValueError) as exc:
                    raise DomainError("EQUIVALENCE_OVERLAP", f"{where}: lat/lon inválidas") from exc
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    raise DomainError("EQUIVALENCE_OVERLAP", f"{where}: lat/lon fuera de rango")
                note = rec.get("note", "").strip()
                if not note:
                    raise DomainError("EQUIVALENCE_OVERLAP", f"{where}: falta la fuente en note")
                rows.append(
                    CoordRow(
                        substation=rec["substation"].strip(),
                        lat=lat,
                        lon=lon,
                        valid_from=_required_date(rec, where),
                        valid_to=_date(rec.get("valid_to", "")),
                        note=note,
                    )
                )
        return rows

    @staticmethod
    def _read_step_ups(path: Path) -> list[StepUpRow]:
        """Lee `elevadores.csv` (spec 004, data-model §3); ausente ⇒ sin equivalencias."""
        if not path.exists():
            return []
        rows: list[StepUpRow] = []
        with path.open(encoding="utf-8", newline="") as fh:
            for n, rec in enumerate(csv.DictReader(fh), start=2):
                where = f"{path.name} línea {n}"
                method = rec.get("method", "").strip()
                if method not in STEP_UP_METHODS:
                    raise DomainError("EQUIVALENCE_OVERLAP", f"{where}: method inválido {method!r}")
                curated = rec.get("curated", "").strip().lower()
                if curated not in {"true", "false"}:
                    raise DomainError(
                        "EQUIVALENCE_OVERLAP", f"{where}: curated debe ser true o false"
                    )
                rows.append(
                    StepUpRow(
                        unit_id=rec["unit_id"].strip(),
                        trafo_id=rec["trafo_id"].strip(),
                        method=method,
                        curated=curated == "true",
                        valid_from=_required_date(rec, where),
                        valid_to=_date(rec.get("valid_to", "")),
                        note=rec.get("note", "").strip(),
                    )
                )
        return rows

    def _check_overlaps(self) -> None:
        def overlap(a_from: date, a_to: date | None, b_from: date, b_to: date | None) -> bool:
            return a_from <= (b_to or date.max) and b_from <= (a_to or date.max)

        def check(rows: list[Hashable], key: Callable[..., Hashable], label: str) -> None:
            groups: dict[Hashable, list[Hashable]] = {}
            for r in rows:
                groups.setdefault(key(r), []).append(r)
            for k, grp in groups.items():
                for i, a in enumerate(grp):
                    for b in grp[i + 1 :]:
                        if overlap(a.valid_from, a.valid_to, b.valid_from, b.valid_to):  # type: ignore[attr-defined]
                            raise DomainError(
                                "EQUIVALENCE_OVERLAP", f"{label} {k!r}: vigencias solapadas"
                            )

        check(list(self._resources), lambda r: r.resource, "recurso")
        check(list(self._nodes), lambda r: (r.node, r.vn_kv), "nodo")
        check(list(self._aliases), lambda r: r.alias, "alias")
        check(list(self._coords), lambda r: r.substation, "coordenada")
        check(list(self._step_ups), lambda r: r.unit_id, "elevador")

    def resolve_resource(self, resource: str, on: date) -> ResourceRow | None:
        """Fila vigente para un recurso del despacho, o `None`."""
        for r in self._resources:
            if r.resource == resource and _is_valid(r.valid_from, r.valid_to, on):
                return r
        return None

    def resolve_node(self, node: str, vn_kv: float, on: date) -> NodeRow | None:
        """Fila vigente para un nodo del pronóstico, o `None`."""
        for r in self._nodes:
            same = r.node == node and abs(r.vn_kv - vn_kv) < 1e-6
            if same and _is_valid(r.valid_from, r.valid_to, on):
                return r
        return None

    def substation_aliases(self, on: date) -> dict[str, str]:
        """Alias vigentes: nombre de PARATEC → nombre canónico."""
        return {
            r.alias: r.substation for r in self._aliases if _is_valid(r.valid_from, r.valid_to, on)
        }

    def substation_coords(self, on: date) -> dict[str, CoordRow]:
        """Coordenadas curadas vigentes: subestación → fila (con su fuente)."""
        return {r.substation: r for r in self._coords if _is_valid(r.valid_from, r.valid_to, on)}

    def step_up(self, unit_id: str, on: date) -> StepUpEquivalence | None:
        """Transformador elevador vigente de una unidad (FR-065), o `None`."""
        for r in self._step_ups:
            if r.unit_id == unit_id and _is_valid(r.valid_from, r.valid_to, on):
                return StepUpEquivalence(
                    unit_id=r.unit_id,
                    trafo_id=r.trafo_id,
                    method=r.method,  # type: ignore[arg-type]
                    curated=r.curated,
                    valid_from=r.valid_from,
                    note=r.note,
                )
        return None

    @property
    def step_ups(self) -> list[StepUpRow]:
        """Todas las filas de elevadores (para reportes y pruebas)."""
        return list(self._step_ups)

    @property
    def coords(self) -> list[CoordRow]:
        """Todas las filas de coordenadas (para reportes y pruebas)."""
        return list(self._coords)

    @property
    def resources(self) -> list[ResourceRow]:
        """Todas las filas de recursos (para reportes y pruebas)."""
        return list(self._resources)

    @property
    def nodes(self) -> list[NodeRow]:
        """Todas las filas de nodos (para reportes y pruebas)."""
        return list(self._nodes)

    @property
    def aliases(self) -> list[AliasRow]:
        """Todas las filas de alias (para reportes y pruebas)."""
        return list(self._aliases)
