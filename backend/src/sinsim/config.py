"""Carga de `config/defaults.toml` y resolución de rutas (modo repositorio o instalado).

Los límites y supuestos citan su fuente en el propio TOML (constitución III.9). El hash del
archivo forma parte del identificador del caso (data-model.md §4).

Dentro del repositorio, las rutas son las de siempre. Fuera de él (paquete instalado, FR-040),
la configuración, las equivalencias, el mapa base y un snapshot de demostración salen de los
recursos de solo lectura del paquete, y lo que el usuario genera va a su carpeta de datos.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sinsim.domain.limits import LoadingLimit, VoltageBand

CONFIG_ENV = "SINSIM_CONFIG"
HOME_ENV = "SINSIM_HOME"

_PACKAGE_DIR = Path(__file__).resolve().parent
# Recursos que el build hook copia al paquete (backend/hatch_build.py). No existen en el
# árbol de código: solo en un wheel instalado.
BUNDLED_DIR = _PACKAGE_DIR / "_bundled"
WEB_DIR = _PACKAGE_DIR / "web"

REPO_MODE = "repositorio"
INSTALLED_MODE = "instalado"


def sinsim_version() -> str:
    """Versión instalada de `sinsim`."""
    try:
        return version("sinsim")
    except PackageNotFoundError:  # pragma: no cover - solo fuera de un entorno instalado
        return "0.0.0"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class VoltageLevelCfg(_Model):
    """Banda de tensión con su fuente."""

    name: str
    vn_kv_min: float
    vn_kv_max: float
    vm_min_pu: float
    vm_max_pu: float
    source: str


class VoltageCfg(_Model):
    """Lista de bandas de tensión."""

    levels: list[VoltageLevelCfg]


class LoadingCfg(_Model):
    """Límite de cargabilidad con su fuente."""

    max_percent: float
    source: str


class LimitsCfg(_Model):
    """Límites operativos (III.9)."""

    voltage: VoltageCfg
    loading: LoadingCfg


class GeneratorCfg(_Model):
    """Consigna de tensión por defecto (D-2)."""

    vm_pu_default: float
    vm_pu_source: str


class TrafoCfg(_Model):
    """Supuestos de transformadores (D-2)."""

    i0_percent: float
    i0_source: str
    tap_policy: str
    tap_source: str


class ImputationCfg(_Model):
    """Regla ante parámetros faltantes (III.5)."""

    rule: str
    params: list[str]


class NetworkCfg(_Model):
    """Alcance y barra de referencia de ángulo (FR-015, FR-017)."""

    min_vn_kv: float
    angle_ref_bus: str
    angle_ref_source: str


class SolverCfg(_Model):
    """Parámetros del solver (FR-023)."""

    algorithm: str
    tolerance_mva: float
    max_iteration: int
    init: str
    enforce_q_lims: bool
    distributed_slack: bool


class ScraperCfg(_Model):
    """Parámetros del scraper (III.10)."""

    min_interval_s: float
    timeout_s: float
    user_agent: str


class AttributionCfg(_Model):
    """Atribución obligatoria a XM (III.10)."""

    text: str


class UnifilaresCfg(_Model):
    """Enlaces a los diagramas unifilares oficiales de XM por subárea (FR-034)."""

    page_url: str
    type_report: str
    source: str
    categories: dict[str, str] = {}
    """Subárea (como `subarea` de las barras) → id de categoría en PARATEC."""

    def url_for(self, subarea: str) -> str | None:
        """URL del unifilar de la subárea, o `None` si XM no lo publica."""
        category = self.categories.get(subarea)
        if category is None:
            return None
        return f"{self.page_url}?typeReport={self.type_report}&category={category}"


class ShortCircuitCfg(_Model):
    """Cortocircuito IEC 60909 (spec 004, data-model §10); cada valor cita su fuente."""

    c_max: float = Field(ge=1.0, le=1.1)
    c_max_source: str
    converter_k: float = Field(gt=0)
    converter_k_source: str
    rg_ratio_large: float = Field(gt=0)
    rg_ratio_small: float = Field(gt=0)
    rg_ratio_lv: float = Field(gt=0)
    rg_ratio_source: str
    international_links_contribute: bool
    international_links_source: str
    voltage_reference: Literal["paratec_nominal", "model_base"]
    voltage_reference_source: str


class Config(_Model):
    """Configuración completa de `defaults.toml`."""

    limits: LimitsCfg
    generator: GeneratorCfg
    trafo: TrafoCfg
    imputation: ImputationCfg
    network: NetworkCfg
    solver: SolverCfg
    scraper: ScraperCfg
    attribution: AttributionCfg
    unifilares: UnifilaresCfg
    shortcircuit: ShortCircuitCfg

    def voltage_bands(self) -> list[VoltageBand]:
        """Bandas de tensión para `domain.limits`."""
        return [
            VoltageBand(
                name=lv.name,
                vn_kv_min=lv.vn_kv_min,
                vn_kv_max=lv.vn_kv_max,
                vm_min_pu=lv.vm_min_pu,
                vm_max_pu=lv.vm_max_pu,
                source=lv.source,
            )
            for lv in self.limits.voltage.levels
        ]

    def loading_limit(self) -> LoadingLimit:
        """Límite de cargabilidad para `domain.limits`."""
        return LoadingLimit(
            max_percent=self.limits.loading.max_percent, source=self.limits.loading.source
        )

    def user_agent(self) -> str:
        """User-Agent del scraper con la versión real."""
        return self.scraper.user_agent.replace("{version}", sinsim_version())


@dataclass(frozen=True)
class LoadedConfig:
    """Configuración cargada con su ruta y su hash."""

    config: Config
    path: Path
    sha256: str


@dataclass(frozen=True)
class RepoPaths:
    """Rutas que usan CLI y API, en modo repositorio o instalado (FR-040)."""

    root: Path
    config_file: Path
    snapshots: Path
    equivalences: Path
    cases: Path
    geo: Path
    mode: str = REPO_MODE
    # Snapshots de solo lectura que se consultan después de `snapshots` (FR-043).
    bundled_snapshots: tuple[Path, ...] = ()
    # Interfaz construida que sirve la API, si existe (FR-045).
    web: Path | None = None


def user_data_dir(
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Carpeta de datos del usuario en modo instalado (FR-041).

    `$SINSIM_HOME` si está definida; si no, la convención del sistema operativo.

    Args:
        env: Variables de entorno (por defecto, las del proceso).
        platform: Valor estilo `sys.platform` (por defecto, el actual).
        home: Carpeta personal (por defecto, `Path.home()`).
    """
    env = os.environ if env is None else env
    if env.get(HOME_ENV):
        return Path(env[HOME_ENV]).expanduser()
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    if platform == "darwin":
        return home / "Library" / "Application Support" / "sinsim"
    if platform.startswith("win"):
        local = env.get("LOCALAPPDATA")
        return (Path(local) if local else home / "AppData" / "Local") / "sinsim"
    xdg = env.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / "sinsim"


def find_repo_root(start: Path | None = None, *, search_package: bool = True) -> Path:
    """Busca hacia arriba el directorio que contiene `config/defaults.toml`.

    Empieza en `start` (por defecto el directorio actual) y, si `search_package` y no lo
    encuentra, en la ubicación del paquete instalado en modo editable.
    """
    candidates = [start or Path.cwd()]
    if search_package:
        candidates.append(_PACKAGE_DIR)
    for base in candidates:
        for d in (base, *base.parents):
            if (d / "config" / "defaults.toml").exists():
                return d
    msg = "no se encontró config/defaults.toml; ejecuta desde el repositorio o define SINSIM_CONFIG"
    raise FileNotFoundError(msg)


def repo_paths(start: Path | None = None, *, search_package: bool = True) -> RepoPaths:
    """Resuelve las rutas del repositorio (modo repositorio)."""
    root = find_repo_root(start, search_package=search_package)
    web = root / "frontend" / "dist"
    return RepoPaths(
        root=root,
        config_file=root / "config" / "defaults.toml",
        snapshots=root / "data" / "paratec",
        equivalences=root / "data" / "equivalencias",
        cases=root / "cases",
        geo=root / "data" / "geo",
        web=web if (web / "index.html").exists() else None,
    )


def installed_paths(data_home: Path, bundled: Path, web: Path | None = None) -> RepoPaths:
    """Rutas del modo instalado (FR-041 a FR-043).

    Args:
        data_home: Carpeta de datos del usuario; ahí van snapshots descargados y casos.
        bundled: Recursos de solo lectura del paquete (`sinsim/_bundled/`).
        web: Interfaz construida incluida en el paquete, si existe.
    """
    demo = bundled / "paratec"
    return RepoPaths(
        root=data_home,
        config_file=bundled / "config" / "defaults.toml",
        snapshots=data_home / "paratec",
        equivalences=bundled / "equivalencias",
        cases=data_home / "cases",
        geo=bundled / "geo",
        mode=INSTALLED_MODE,
        bundled_snapshots=(demo,) if demo.is_dir() else (),
        web=web if web is not None and (web / "index.html").exists() else None,
    )


def resolve_paths(
    start: Path | None = None,
    *,
    search_package: bool = True,
    bundled: Path = BUNDLED_DIR,
    web: Path = WEB_DIR,
    env: Mapping[str, str] | None = None,
) -> RepoPaths:
    """Rutas del repositorio si sinsim corre dentro de él; si no, las del modo instalado (FR-040).

    Raises:
        FileNotFoundError: ni repositorio ni recursos del paquete (instalación incompleta).
    """
    try:
        return repo_paths(start, search_package=search_package)
    except FileNotFoundError:
        if not (bundled / "config" / "defaults.toml").exists():
            msg = (
                "no se encontró config/defaults.toml ni los recursos del paquete; ejecuta desde "
                "el repositorio, define SINSIM_CONFIG o reinstala sinsim desde un release"
            )
            raise FileNotFoundError(msg) from None
        return installed_paths(user_data_dir(env), bundled, web)


def load_config(path: Path | None = None) -> LoadedConfig:
    """Carga y valida la configuración.

    Args:
        path: Ruta del TOML; por defecto `$SINSIM_CONFIG` o `config/defaults.toml` del repo.
    """
    if path is None:
        env = os.environ.get(CONFIG_ENV)
        path = Path(env) if env else resolve_paths().config_file
    raw = path.read_bytes()
    config = Config.model_validate(tomllib.loads(raw.decode("utf-8")))
    return LoadedConfig(config=config, path=path, sha256=hashlib.sha256(raw).hexdigest())
