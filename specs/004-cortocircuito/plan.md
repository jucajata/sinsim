# Plan: análisis de cortocircuito trifásico (IEC 60909)

**Feature**: 004-cortocircuito | **Spec**: [spec.md](./spec.md) | **Fecha**: 2026-10-25
**Rama**: `004-cortocircuito` | **Release**: 0.7.0
**Constitución**: v1.3.0 → 1.4.0 (enmienda MINOR: comando público `sinsim sc` en IV y
persistencia de `sc.json` en III.4; ver «Revisión de cumplimiento»).

## Resumen

Sobre el caso construido de una fecha y un periodo, sinsim deriva en memoria una red de
cortocircuito: quita las plantas del despacho y los compensadores, y crea una fuente por cada
unidad síncrona en operación (con su transformador elevador cuando la tabla de equivalencias lo
casa) y una fuente de corriente limitada por cada planta solar o eólica. Corre `calc_sc` trifásico
máximo de pandapower (0,3 s en el SIN, research R1), corrige los resultados a la tensión nominal de
PARATEC y entrega Ikss, Sk, Rk, Xk y X/R por barra, con calidad e imputaciones visibles. El
resultado se guarda junto al caso y se expone por API, CLI (`sinsim sc`, con `--json` para
consumidores externos) e interfaz (tabla y mapa coloreado).

## Contexto técnico

- **Lenguajes y stack**: Python 3.12, pandapower 3.5.6 (`pandapower.shortcircuit`), FastAPI,
  React + TypeScript, TanStack Query, como hoy. **Sin dependencias nuevas**.
- **Datos** (research R2): la tabla normalizada `generators` gana las columnas de máquina
  (data-model §2). El scraper las escribe en snapshots nuevos (`scraper_version` sube) y el
  repositorio las deriva en memoria desde `raw/` en los anteriores, con el patrón ya existente
  `_with_substation_attrs_from_raw`. Ningún snapshot versionado cambia.
- **Equivalencias** (research R4): `data/equivalencias/elevadores.csv` nuevo, con propuesta
  inicial generada por `sinsim equivalencias elevadores --fecha F` (comando de mantenimiento del
  repositorio, listado en la constitución IV junto a los públicos; hallazgo C2 de
  /speckit-analyze) a partir de `domain/shortcircuit.propose_step_ups`. Entra en el
  `EquivalenceRepository` (`step_up(unit_id, on)`) y en el SHA de equivalencias.
- **Dominio puro** (`domain/shortcircuit.py`, data-model §11): reglas de parámetros faltantes
  (FR-064), propuesta de elevadores, corrección a tensión nominal (S26), X/R, resumen, hash de
  configuración. Sin pandapower ni E/S.
- **Servicio** (`services/sc.py`):
  - `build_sc_net(net_json, units, trafos, equivalences, cfg) -> (net, sources, quality)`: la red
    derivada de research R3; crea una barra de generación y un transformador de central por
    elevador casado (las unidades que comparten elevador comparten barra). Las conversiones
    pu → Ω las toma de `adapters/sources_to_pandapower/generators.py` (III.1; hallazgo C1);
  - `calculate(run, snapshot, cfg, equivalences) -> ShortCircuitAnalysis`: construye, llama a
    `calc_sc(net, fault="3ph", case="max", ip=False, ith=False, branch_results=False)`, corrige
    a tensión nominal, arma `buses`, `sources`, `quality`, `summary`, `assumptions` y los hashes;
  - `select_buses(analysis, names) -> ShortCircuitAnalysis`: filtra para `--barra`/`buses`,
    resolviendo `SUBESTACION|kV_base` y `SUBESTACION kV_nominal`; `SC_BUS_NOT_FOUND` si falta.
- **Persistencia** (`adapters/storage/cases.py`): `save_sc(case_id, analysis)`, `get_sc(case_id)`
  sobre `cases/<case_id>/sc.json` (research R9). `services/sc.get_or_calculate` compara
  `case_hash` y `sc_config_hash`.
- **API** (`api/routers/sc.py`): `POST /runs/{run_id}/sc` (síncrono, 200) y
  `GET /runs/{run_id}/sc` ([contrato](./contracts/openapi-sc.yaml)).
- **Errores** (`domain/errors.py`): `SC_BUS_NOT_FOUND` (422, salida 4), `SC_NO_SOURCES` (422,
  salida 4), `SC_NOT_FOUND` (404, salida 1), con `user_message` en español.
- **Exportación** (`adapters/storage/export_sc.py`): `cc_barras.csv`, `cc_fuentes.csv`,
  `cc_calidad.csv`, `metadatos.json` ([contrato](./contracts/export-sc.md)).
- **CLI**: `sinsim sc` ([contrato](./contracts/cli-sc.md)); construcción de caso como `sinsim run`;
  `--json` imprime solo JSON (los avisos a stderr).
- **Configuración**: sección `[shortcircuit]` en `config/defaults.toml` y `ShortCircuitCfg` en
  `config.py` (data-model §10), cada valor con su cita.
- **Interfaz** (`frontend/src/features/shortcircuit/`, research R10):
  - `ScPanel.tsx`: botón «Cortocircuito», estado «calculando», resumen, tabla ordenable con
    búsqueda y coloreado de Ikss, tabla de calidad, bloque de supuestos;
  - `sc.ts`: escala de color relativa al máximo del caso, formato de kA/MVA/Ω, orden;
  - `TopologyView`: opción «cortocircuito» en «Colorear por» con leyenda mín–máx; recibe
    `scByBus` por prop desde `Workspace`;
  - hooks `useSc(runId)` (GET, caché por `run_id`) y `useCalculateSc()` (POST, invalida la caché);
    tipos en `api/types.ts`; métodos en `api/client.ts`.
- **Pruebas**:
  - unitarias de `domain/shortcircuit.py` (reglas FR-064, propuesta de elevadores, S26, hash);
  - integración: red de 3 barras con valor a mano (SC-021), caso de ejemplo (fuentes cuadran,
    SC-023), snapshot sin columnas de máquina (derivación desde `raw/`), persistencia por hashes;
  - contrato de API y CLI (`--json` es JSON puro; `--barra` inexistente sale con 4);
  - Vitest de `sc.ts` y `ScPanel`; un paso e2e.
  Las pruebas no llaman a XM (VI.7).

## Revisión de cumplimiento de la constitución

- **I. Naturaleza**: el cortocircuito está en «Capacidades en alcance». Fuera: estabilidad.
- **II. Stack**: sin dependencias nuevas.
- **III. Reglas de dominio**:
  - III.1 unidades: kA, MVA, Ω, pu; la conversión de `ra` (pu) a `rdss_ohm` vive en
    `adapters/sources_to_pandapower/generators.py`, con fórmula en docstring y prueba con valor
    conocido; `services/sc.py` no convierte unidades (hallazgo C1 de /speckit-analyze);
  - III.3/III.4 inmutabilidad: las columnas nuevas se escriben solo en snapshots nuevos; los
    anteriores se completan en memoria desde `raw/` (research R2). `sc.json` vive en `cases/`, no
    en el snapshot; III.4 se enmienda para nombrarlo junto a `net.json`;
  - III.5 sin parámetros inventados: FR-064 y FR-073; cada valor tiene origen (SC-024);
  - III.6 punto de operación: el cortocircuito no depende del despacho; se documenta (FR-062);
  - III.7 trazabilidad: FR-072;
  - III.9 configurables con fuente: `[shortcircuit]` cita IEC 60909 y las decisiones del usuario.
- **IV. Estructura**: `domain/`, `services/`, `adapters/`, `api/routers/`, `features/`;
  `pandapowerNet` solo en `services/` y `adapters/`; comando público nuevo ⇒ enmienda 1.4.0.
- **V. Errores**: tres códigos en el catálogo único; sin `except` desnudos.
- **VI. Agente**: spec, plan y tareas documentan comando, rutas, códigos, columnas y archivos
  (VI.2); no se tocan `data/paratec/` (VI.5); el valor de los enlaces internacionales no se inventa:
  aporte nulo aprobado por el usuario (VI.4, S29); sin llamadas a XM en pruebas (VI.7).

## Decisiones del usuario (2026-10-25)

1. Cortocircuito calculado con sinsim, público; primera versión trifásico máximo.
2. Elevadores incorporados como transformadores de central con tabla de equivalencias; sin
   equivalencia, generador en la barra de alta con reporte.
3. Enlaces internacionales sin aporte (S29).
4. Consumidor externo (webapp privada) solo por el CLI con `--json`.

## Decisiones de diseño (del agente)

- **Síncrono** (research R1): sin runner de trabajos.
- **Red derivada, no el caso** (R3): `net.gen` del despacho se reemplaza por unidades con
  parámetros de máquina; `net.json` del caso no cambia ni su hash.
- **Tensión nominal de PARATEC** como referencia (R5, S26).
- **`ra` = 0 es faltante** (R6, S27); relación R/X de IEC 60909 (S28).
- **Sin `ip`** (R7, FR-074).
- **Persistencia en `cases/<id>/sc.json`** con dos hashes (R9).
- **Carpeta por defecto de `sinsim sc`**: `./cc-<fecha>-p<NN>/`, como `sinsim n1`.
- **Propuesta de `elevadores.csv` no curada** se versiona en el repo con `curated=false`; curarla
  es tarea del usuario, igual que `recursos_despacho.csv` (T064 pendiente).

## Estructura

```text
backend/src/sinsim/
├── domain/shortcircuit.py                 # reglas FR-064, elevadores, S26, X/R, resumen, hash (puro)
├── domain/entities.py                     # + ScSource, ScBusResult, ScQuality, ScSummary, ScAssumption, ShortCircuitAnalysis, StepUpEquivalence
├── domain/errors.py                       # + SC_BUS_NOT_FOUND, SC_NO_SOURCES, SC_NOT_FOUND
├── domain/ports.py                        # EquivalenceRepository.step_up; CaseRepository.save_sc/get_sc
├── adapters/sources_to_pandapower/generators.py   # + columnas de máquina (ra pu→Ω en services)
├── adapters/storage/snapshots.py          # + _with_machine_params_from_raw
├── adapters/storage/equivalences.py       # + elevadores.csv
├── adapters/storage/cases.py              # + sc.json
├── adapters/storage/export_sc.py          # CSV + metadatos.json
├── services/sc.py                         # build_sc_net, calculate, select_buses, get_or_calculate
├── api/routers/sc.py                      # POST/GET /runs/{id}/sc
├── config.py                              # + ShortCircuitCfg
└── cli.py                                 # + sinsim sc; + equivalencias elevadores (mantenimiento)
config/defaults.toml                       # + [shortcircuit]
data/equivalencias/elevadores.csv          # propuesta inicial, curated=false
backend/tests/
├── unit/test_shortcircuit.py
├── integration/test_sc.py
└── contract/test_api_sc.py, test_cli_sc.py, test_export_sc.py
frontend/src/
├── features/shortcircuit/{ScPanel.tsx, sc.ts, *.test.ts(x)}
├── features/topology/{TopologyView.tsx, colors.ts}   # modo «cortocircuito»
├── api/{types.ts, client.ts, hooks.ts}
└── features/workspace/Workspace.tsx
frontend/e2e/flujo.spec.ts                  # + paso cortocircuito
```

Documentación: README (sección «Cortocircuito»), `docs/supuestos.md` (S26 a S31), CHANGELOG
0.7.0, constitución 1.4.0, versión 0.7.0 en backend y frontend, video y post como en 0.6.x.

## Riesgos

- **Pocas equivalencias automáticas**: research R4 estima 135–200 de 408 unidades. El resto entra
  sin elevador (S31) y sobreestima la Icc cerca de esas plantas; la lista queda visible para curar.
- **Calidad de `xd''` en PARATEC**: hay valores 0 (por ejemplo dos hidráulicas con `xd2 = 0`); se
  tratan como faltantes e imputan por mediana, como `ra`.
- **Clase de tensión en el casado**: se normaliza 220↔230 y 110↔115; otras tensiones (138, 66) se
  comparan exactas.
- **Snapshots sin `raw/` completo**: si falta el JSON de unidades, `SC_NO_SOURCES` con mensaje
  que pide `sinsim scrape`.

## Seguimiento de complejidad

Ninguna violación de la constitución que justificar. La enmienda de III.4 y IV es el
procedimiento previsto para un comando público y un archivo persistido nuevos.
