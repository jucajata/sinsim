"""Build hook: copia al paquete los recursos del modo instalado (FR-042).

El wheel lleva, de solo lectura:

- `sinsim/_bundled/config/defaults.toml`
- `sinsim/_bundled/equivalencias/*.csv`
- `sinsim/_bundled/geo/` (mapa base)
- `sinsim/_bundled/paratec/<DEMO_SNAPSHOT>/` (snapshot de demostración, byte a byte)
- `sinsim/web/` (interfaz construida con `pnpm --dir frontend build`, si existe)
- `sinsim/LICENSE` (texto de la GPL-3.0, que debe acompañar cada distribución)

Los toma del repositorio. El sdist los lleva en `_bundle_src/`, para que el wheel también se
pueda construir desde el sdist, fuera del repositorio.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

DEMO_SNAPSHOT = "2026-10-20"
SDIST_DIR = "_bundle_src"


def _tree(base: Path, rel: str) -> list[str]:
    """Archivos bajo `base/rel`, relativos a `base`, sin archivos ocultos."""
    root = base / rel
    if not root.is_dir():
        return []
    return sorted(
        p.relative_to(base).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )


def _glob(base: Path, rel: str, pattern: str) -> list[str]:
    return sorted(p.relative_to(base).as_posix() for p in (base / rel).glob(pattern) if p.is_file())


def resources(source: Path) -> dict[str, str]:
    """Mapa `ruta relativa en el repositorio → ruta dentro del wheel`."""
    out = {
        "config/defaults.toml": "sinsim/_bundled/config/defaults.toml",
        "LICENSE": "sinsim/LICENSE",
    }
    for rel in _glob(source, "data/equivalencias", "*.csv"):
        out[rel] = f"sinsim/_bundled/equivalencias/{Path(rel).name}"
    for rel in _glob(source, "data/geo", "*.geojson") + _glob(source, "data/geo", "README.md"):
        out[rel] = f"sinsim/_bundled/geo/{Path(rel).name}"
    for rel in _tree(source, f"data/paratec/{DEMO_SNAPSHOT}"):
        out[rel] = "sinsim/_bundled/paratec/" + rel.removeprefix("data/paratec/")
    for rel in _tree(source, "frontend/dist"):
        out[rel] = "sinsim/web/" + rel.removeprefix("frontend/dist/")
    return out


class CustomBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    """Añade los recursos al sdist o al wheel según el destino que se construye."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Registra los archivos en `force_include`."""
        backend = Path(self.root)
        repo = backend.parent
        # Desde el repositorio, o desde la copia que trae un sdist desempaquetado.
        source = repo if (repo / "config" / "defaults.toml").exists() else backend / SDIST_DIR
        mapping = resources(source)
        if not (source / "config" / "defaults.toml").exists():
            msg = f"no se encontró config/defaults.toml en {source}"
            raise FileNotFoundError(msg)
        if not any(dest.startswith("sinsim/_bundled/paratec/") for dest in mapping.values()):
            msg = f"falta el snapshot de demostración data/paratec/{DEMO_SNAPSHOT}"
            raise FileNotFoundError(msg)
        if not any(dest.startswith("sinsim/web/") for dest in mapping.values()):
            self.app.display_warning(
                "frontend/dist no existe: el paquete no tendrá interfaz. "
                "Ejecuta `pnpm --dir frontend build` antes, o usa `make package`."
            )
        for rel, dest in mapping.items():
            target = f"{SDIST_DIR}/{rel}" if self.target_name == "sdist" else dest
            build_data["force_include"][str(source / rel)] = target
