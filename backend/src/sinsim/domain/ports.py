"""Interfaces que implementan los adaptadores (constitución IV).

`domain` no conoce Parquet, DuckDB ni el sistema de archivos: solo estos contratos.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Protocol

from sinsim.domain.entities import (
    LoadedSnapshot,
    Run,
    ShortCircuitAnalysis,
    SnapshotSummary,
    StepUpEquivalence,
    StudyCase,
)


class SnapshotRepository(Protocol):
    """Acceso a los snapshots inmutables de `data/paratec/`."""

    def list_summaries(self) -> list[SnapshotSummary]:
        """Lista las fechas disponibles con su disponibilidad e integridad (FR-002)."""
        ...

    def load(self, snapshot_date: date) -> LoadedSnapshot:
        """Carga y verifica un snapshot; lanza `SNAPSHOT_NOT_FOUND` o `SNAPSHOT_CORRUPTED`."""
        ...


class EquivalenceRepository(Protocol):
    """Tablas de equivalencias versionadas con vigencia (FR-011)."""

    @property
    def sha256(self) -> str:
        """Checksum conjunto de las dos tablas, para el hash del caso."""
        ...

    def resolve_resource(self, resource: str, on: date) -> ResourceEquivalence | None:
        """Equivalencia vigente de un recurso del despacho, o `None`."""
        ...

    def resolve_node(self, node: str, vn_kv: float, on: date) -> NodeEquivalence | None:
        """Equivalencia vigente de un nodo del pronóstico, o `None`."""
        ...

    def substation_aliases(self, on: date) -> dict[str, str]:
        """Alias vigentes de subestaciones: nombre de PARATEC → nombre canónico."""
        ...

    def substation_coords(self, on: date) -> Mapping[str, SubstationCoord]:
        """Coordenadas curadas vigentes de subestaciones sin coordenadas en PARATEC."""
        ...

    def step_up(self, unit_id: str, on: date) -> StepUpEquivalence | None:
        """Transformador elevador vigente de una unidad (`elevadores.csv`, FR-065), o `None`."""
        ...


class SubstationCoord(Protocol):
    """Fila vigente de `coordenadas_subestaciones.csv` (solo lectura)."""

    @property
    def lat(self) -> float: ...  # noqa: D102

    @property
    def lon(self) -> float: ...  # noqa: D102

    @property
    def note(self) -> str: ...  # noqa: D102


class ResourceEquivalence(Protocol):
    """Fila vigente de `recursos_despacho.csv` (solo lectura)."""

    @property
    def resource(self) -> str: ...  # noqa: D102

    @property
    def kind(self) -> str: ...  # noqa: D102

    @property
    def paratec_ids(self) -> list[str]: ...  # noqa: D102

    @property
    def connection_bus(self) -> str | None: ...  # noqa: D102


class NodeEquivalence(Protocol):
    """Fila vigente de `nodos_demanda.csv` (solo lectura)."""

    @property
    def node(self) -> str: ...  # noqa: D102

    @property
    def ucp(self) -> str: ...  # noqa: D102

    @property
    def vn_kv(self) -> float: ...  # noqa: D102

    @property
    def substation(self) -> str: ...  # noqa: D102

    @property
    def paratec_vn_kv(self) -> float: ...  # noqa: D102


class CaseRepository(Protocol):
    """Persistencia de casos y ejecuciones en `cases/<case_id>/`."""

    def save_case(self, case: StudyCase, net_json: str) -> Path:
        """Guarda el caso y su red; devuelve el directorio."""
        ...

    def get_case(self, case_id: str) -> StudyCase:
        """Devuelve un caso o lanza `CASE_NOT_FOUND`."""
        ...

    def get_net_json(self, case_id: str) -> str:
        """Devuelve el JSON de pandapower del caso."""
        ...

    def exists(self, case_id: str) -> bool:
        """Indica si el caso ya fue construido."""
        ...

    def save_run(self, run: Run) -> Path:
        """Guarda una ejecución; devuelve su ruta."""
        ...

    def get_run(self, run_id: str) -> Run:
        """Devuelve una ejecución o lanza `RUN_NOT_FOUND`."""
        ...

    def save_sc(self, case_id: str, analysis: ShortCircuitAnalysis) -> Path:
        """Guarda el cortocircuito del caso (`sc.json`, FR-071); devuelve su ruta."""
        ...

    def get_sc(self, case_id: str) -> ShortCircuitAnalysis | None:
        """Cortocircuito guardado del caso, o `None` si no existe."""
        ...
