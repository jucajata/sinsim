# Tareas: análisis de cortocircuito trifásico (IEC 60909)

**Entrada**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
**Constitución**: v1.3.0 → 1.4.0. Las pruebas son condición de cierre (VI.6, SC-025).

## Formato: `[ID] [P?] [Historia] Descripción con ruta`

- **[P]**: se puede hacer en paralelo (otro archivo, sin dependencias pendientes).
- **[US9]**: HU-9, ver el nivel de cortocircuito de cada barra en la interfaz (P1).
- **[US10]**: HU-10, obtener el equivalente de Thevenin desde la terminal (P1).
- **[US11]**: HU-11, saber qué se imputó y qué no aporta (P2).

---

## Fase 1: Gobernanza y configuración

- [ ] T400 Enmendar la constitución a v1.4.0 (MINOR) en `.specify/memory/constitution.md`: en IV
  «Comandos públicos» añadir `uv run sinsim sc --fecha YYYY-MM-DD --periodo N [--fecha-despacho F]
  [--barra NOMBRE ...] [--salida CARPETA] [--json]` y, como comando de mantenimiento del
  repositorio, `uv run sinsim equivalencias elevadores --fecha YYYY-MM-DD [--salida RUTA]`
  (hallazgo C2 de /speckit-analyze); en III.4 nombrar `sc.json` junto a `net.json` como archivo
  persistido del caso (`cases/<case_id>/`); actualizar el Sync Impact Report, la versión y la fecha
  de última enmienda (2026-10-25).
- [ ] T401 [P] Sección `[shortcircuit]` en `config/defaults.toml` con los siete valores de
  data-model §10 (`c_max = 1.10`, `converter_k = 1.0`, `rg_ratio_large = 0.05`,
  `rg_ratio_small = 0.07`, `rg_ratio_lv = 0.15`, `international_links_contribute = false`,
  `voltage_reference = "paratec_nominal"`), cada uno con su comentario de fuente (IEC 60909-0 tabla 1
  y §6.6.1, §6.9; decisiones del usuario del 2026-10-25 para S29 y S26), y `ShortCircuitCfg(_Model)`
  en `backend/src/sinsim/config.py` colgada de `Config.shortcircuit` con validación de rangos
  (`c_max` en 1,0–1,1; relaciones > 0; `k` > 0).

---

## Fase 2: Fundamentos (bloquean HU-9, HU-10 y HU-11)

**Propósito**: datos de máquina en el snapshot, equivalencias de elevadores, dominio puro y el
servicio que calcula.

### Datos de máquina (research R2)

- [ ] T402 Columnas de máquina en `backend/src/sinsim/adapters/sources_to_pandapower/generators.py`
  (data-model §2): `parse_units` añade `sn_mva` (= `ratedS`), `vn_gen_kv` (= `ratedU`), `cos_phi`
  (= `ratedPowerFactor`, «0 < valor ≤ 1», si no null), `xdss_pu` (= `xd2` en hidráulicas,
  `xdSubtrans` en térmicas; «> 0», si es 0 o falta → null), `xdss_sat_pu` (= `satDirectSubtransX`),
  `rdss_pu` (= `ra`; «null si no publicada o si es 0», S27), `x2_pu`, `x0_pu`; `parse_plants`
  añade `sn_mva` (= capacidad nominal) y deja las demás en null. Añadir las columnas a `COLUMNS`
  y a `field_mapping.py`. Docstring con la regla de `ra = 0`. En el mismo módulo, la conversión
  de unidades que exige la constitución III.1: `rdss_ohm(rdss_pu, vn_kv, sn_mva) = rdss_pu ·
  vn_kv² / sn_mva` y `xdss_ohm(xdss_pu, vn_kv, sn_mva)`, con la fórmula en el docstring (hallazgo
  C1 de /speckit-analyze).
- [ ] T403 Derivación en memoria para snapshots anteriores en
  `backend/src/sinsim/adapters/storage/snapshots.py`: `_with_machine_params_from_raw(generators,
  snapshot_date)` que, cuando falte `xdss_pu` en la tabla, lee
  `raw/paratec/*HydraulicUnit*.json` y `*ThermalUnit*.json` y aplica las mismas funciones de T402
  por `unit_id`; se llama desde `load` como `_with_substation_attrs_from_raw`. No escribe nada
  (III.3/III.4). Subir `SCRAPER_VERSION` en `backend/src/sinsim/scraper/writer.py` y anotar en el
  docstring que las columnas de máquina existen desde esa versión.
- [ ] T404 [P] Pruebas en `backend/tests/unit/test_generators_machine_params.py`: `ra = 0` → null;
  `xd2 = 0` → null; `cos_phi` fuera de rango → null con `missing_params`; `rdss_ohm(0.005, 13.8,
  150) = 0.006348 Ω` (valor conocido, III.1); y en
  `backend/tests/integration/test_snapshot_machine_params.py`: cargar el snapshot empaquetado
  (sin columnas) y comprobar que `generators.xdss_pu` llega poblado desde `raw/` sin modificar
  ningún archivo del snapshot (comparar checksums antes y después).

### Equivalencias de elevadores (research R4)

- [ ] T405 Entidad `StepUpEquivalence` en `backend/src/sinsim/domain/entities.py` (data-model §3:
  `unit_id` str único, `trafo_id` str, `method: Literal["nombre+tension", "nombre", "tension",
  "manual"]`, `curated: bool`, `valid_from: date`, `note: str`) y `step_up(unit_id, on) ->
  StepUpEquivalence | None` en `EquivalenceRepository` (`backend/src/sinsim/domain/ports.py`).
- [ ] T406 Lectura de `data/equivalencias/elevadores.csv` en
  `backend/src/sinsim/adapters/storage/equivalences.py`: columnas `unit_id, trafo_id, method,
  curated, valid_from, note`; entra en `sha256()`; mismo tratamiento de `valid_from` que las demás
  tablas; archivo ausente ⇒ cero equivalencias (no error).
- [ ] T407 `propose_step_ups(units, trafos2w, trafos3w, aliases) -> list[StepUpEquivalence]` en
  `backend/src/sinsim/domain/shortcircuit.py` (puro) con las reglas de research R4 en orden: misma
  subestación (con alias) y misma clase de tensión de alta (220 ≡ 230, 110 ≡ 115; otras exactas);
  candidatos solo transformadores con algún devanado < 57,5 kV; método `nombre+tension` si el
  nombre del transformador contiene el nombre de la planta o `G<n>`/`U<n>` **y** un devanado de baja
  coincide con `vn_gen_kv` (±0,2 kV); `nombre` si solo el nombre; `tension` si solo la tensión y hay
  un único candidato; si no, sin equivalencia. `curated = false`, `valid_from` = fecha del snapshot.
- [ ] T408 Subcomando de mantenimiento `sinsim equivalencias elevadores --fecha F [--salida
  data/equivalencias/elevadores.csv]` en `backend/src/sinsim/cli.py` (grupo `equivalencias`, no
  público: no entra en la constitución) que escribe la propuesta de T407 y muestra el conteo por
  método; generar y versionar `data/equivalencias/elevadores.csv` con el snapshot 2026-10-24.
- [ ] T409 [P] Pruebas en `backend/tests/unit/test_shortcircuit_step_ups.py`: caso «ALTO ANCHICAYA
  G1 129 MVA 230/13.8 kV» casa con la unidad en «ALTO ANCHICAYA 220» por clase de tensión; un
  transformador de distribución 110/44/13,2 en la misma subestación **no** casa por nombre; dos
  unidades pueden compartir un trafo; sin candidatos ⇒ sin equivalencia.

### Dominio puro

- [ ] T410 [P] Entidades en `backend/src/sinsim/domain/entities.py` (data-model §1, §4–§9), todas
  `Frozen`: `ScSourceKind`, `ScMethod`, `ScSource`, `ScBusResult` (`ikss_ka ≥ 0`, `skss_mva ≥ 0`,
  `rk_ohm`/`xk_ohm`/`x_r` «null si sin fuente», `no_source: bool`), `ScQuality`, `ScSummary`,
  `ScAssumption`, `ShortCircuitAnalysis` (`buses` ordenadas por `bus_id`).
- [ ] T411 [P] Códigos en `backend/src/sinsim/domain/errors.py` con título, HTTP, código de salida y
  `user_message` en español: `SC_BUS_NOT_FOUND` (422, `ExitCode.VALIDATION`: «La barra «{nombre}» no
  existe en el caso. Usa el nombre como aparece en la tabla de barras.»), `SC_NO_SOURCES` (422,
  `ExitCode.VALIDATION`: «Ninguna unidad generadora tiene parámetros de cortocircuito en este
  snapshot. Genera uno nuevo con `sinsim scrape`.»), `SC_NOT_FOUND` (404, `ExitCode.GENERAL`: «No
  hay un cálculo de cortocircuito guardado para este caso. Lánzalo con el botón «Cortocircuito».»).
- [ ] T412 Reglas de parámetros en `backend/src/sinsim/domain/shortcircuit.py` (puro, FR-064,
  S27, S28): `source_parameters(unit, medians, step_up_lv_kv, cfg) -> (params, origins, imputed)`:
  `sn_mva` publicado → `publicado`; faltante → `p_max_mw / cos_phi` (`derivado_p_cosphi`) o mediana
  del tipo (`mediana`); `xdss_pu` faltante o 0 → mediana del tipo; `vn_kv`: si hay elevador casado
  manda la tensión de baja del elevador aunque exista `vn_gen_kv` (si difieren, se registra con
  método `tension_elevador`); sin elevador, `vn_gen_kv`, y si falta, la tensión de la barra de
  alta; `rdss` publicado > 0 → `publicado`, si no → relación
  IEC según `sn_mva ≥ 100` y `vn_kv > 1` (`relacion_iec`). `medians_by_tech(units)` calcula las
  medianas solo con valores publicados > 0. También `to_nominal(ikss, skss, base_kv, nominal_kv)`
  (S26: `ikss·base/nominal`, `skss·(base/nominal)²`), `x_over_r(rk, xk)` (null si `rk` ≤ 0 o sin
  fuente), `summarize(...)` (data-model §7) y `config_hash(cfg, equivalences_sha, units_sha)`.
- [ ] T413 [P] Pruebas unitarias en `backend/tests/unit/test_shortcircuit.py` para T412: las cuatro
  reglas de datos faltantes con valores conocidos; `ra = 0` cae en `relacion_iec`; `to_nominal` con
  base 230 y nominal 220 (Ikss ×1,0455, Sk ×1,0930); `x_over_r` con `rk = 0`; `config_hash` cambia
  al cambiar `k`.

### Servicio de cálculo (research R3)

- [ ] T414 `build_sc_net(net_json, units, trafos2w, trafos3w, equivalences, cfg) -> (net, sources,
  quality)` en `backend/src/sinsim/services/sc.py`: carga la red del caso, borra `net.gen` entero
  (plantas del despacho y compensadores → `quality.excluded` con motivo «compensador» o
  «planta_despacho_reemplazada»); por cada unidad síncrona en «Operación» con barra en el caso crea
  `gen` (`p_mw = 0`, `vm_pu = 1`, `sn_mva`, `vn_kv`, `xdss_pu`, `rdss_ohm` con la función
  `generators.rdss_ohm` de T402 —ninguna conversión de unidades aquí—, `cos_phi`,
  `pg_percent = 0`); si tiene elevador casado, **una barra de generación y un transformador por
  `trafo_id`**: la primera unidad que lo usa crea la barra a la tensión de baja del elevador y el
  transformador con `create_transformer_from_parameters` (datos del elevador; para 3 devanados, el
  par alta–baja de la unidad), y las demás unidades que comparten ese `trafo_id` se conectan a esa
  misma barra (caso límite de la spec); cada `gen` pone `power_station_trafo` al índice del
  trafo; si no hay elevador, el `gen` va a
  la barra de alta con `vn_kv` = `vn_kv` de la barra y entra en `generators_without_step_up`;
  unidades sin barra en el caso → `excluded` («sin_barra»); plantas solares y eólicas en operación
  → `sgen(sn_mva, k = cfg.converter_k, generator_type="current_source")`; enlaces internacionales
  (recursos `link:*`) → `sc_zero_sources`.
- [ ] T415 `calculate(run, snapshot, cfg, equivalences) -> ShortCircuitAnalysis` en
  `backend/src/sinsim/services/sc.py`: construye la red (T414), `calc_sc(net, fault="3ph",
  case="max", ip=False, ith=False, branch_results=False)`, toma `res_bus_sc` solo de las barras del
  caso (no las de generación añadidas), corrige con `to_nominal`, marca `no_source` cuando `ikss`
  es 0 o `xk` infinito, arma `sources`, `quality`, `summary`, `assumptions` (S26–S31 con texto y
  fuente), `norm`, `config`, `trace`, `case_hash` y `sc_config_hash`. `SC_NO_SOURCES` si no entra
  ninguna unidad. También `select_buses(analysis, names)`: acepta `SUBESTACION|kV_base` y
  `SUBESTACION kV_nominal`; `SC_BUS_NOT_FOUND` con el nombre que falte.
- [ ] T416 Persistencia en `backend/src/sinsim/adapters/storage/cases.py` y
  `backend/src/sinsim/domain/ports.py`: `save_sc(case_id, analysis)` escribe
  `cases/<case_id>/sc.json` (JSON Pydantic, `indent=2`, `ensure_ascii=False`); `get_sc(case_id)`
  devuelve el análisis o `None`. `get_or_calculate(run, ctx)` en `services/sc.py` devuelve el
  guardado si `case_hash` y `sc_config_hash` coinciden; si no, calcula, guarda y devuelve
  (FR-071).
- [ ] T417 Pruebas de integración en `backend/tests/integration/test_sc.py`: (a) red de tres
  barras (230 kV – elevador 150 MVA 12 % – generador 150 MVA 13,8 kV xd'' 0,2, línea de 50 km a una
  tercera barra) con valores a mano según IEC 60909 §6.7 (SC-021, tolerancia 1 %); (b) sobre
  `cases/demo`: cuadre de fuentes (SC-023), ningún parámetro sin origen (SC-024), todas las barras
  con `ikss > 0`, tiempo < 30 s; (c) una unidad con y otra sin elevador cambian `ikss` en su barra;
  (d) `sgen` convertidor suma `k·In`; (e) compensadores excluidos; (f) persistencia: segunda llamada
  no recalcula y cambiar `converter_k` sí.

---

## Fase 3: HU-10, equivalente de Thevenin desde la terminal (P1) 🎯 MVP

**Objetivo**: `sinsim sc` produce CSV, metadatos y JSON puro, con y sin `--barra`.
**Prueba independiente**: quickstart §2 y §4; `test_cli_sc.py` y `test_export_sc.py`.

- [ ] T418 [P] [US10] Exportación en `backend/src/sinsim/adapters/storage/export_sc.py` según
  [export-sc.md](./contracts/export-sc.md): `cc_barras.csv` (orden por `bus_id`; `rk_ohm`,
  `xk_ohm`, `x_r` vacíos si `sin_fuente`), `cc_fuentes.csv`, `cc_calidad.csv` (categorías
  `imputado`, `sin_elevador`, `sin_aporte`, `excluido`) y `metadatos.json` con todas las claves del
  contrato (incluida la atribución a XM).
- [ ] T419 [US10] Comando `sinsim sc` en `backend/src/sinsim/cli.py` según
  [cli-sc.md](./contracts/cli-sc.md): opciones `--fecha`, `--periodo`, `--fecha-despacho`,
  `--barra` (repetible), `--salida` (por defecto `./cc-<fecha>-p<NN>/`), `--json`; construye o
  reutiliza el caso como `sinsim run` sin correr el flujo; `get_or_calculate`; con `--json`
  imprime solo el JSON en stdout (avisos a stderr); sin `--json` escribe los archivos de T418 y
  muestra el resumen y las 10 barras de mayor Ikss; `--barra` filtra CSV, listado y JSON; códigos
  de salida 0/1/2/4 del contrato.
- [ ] T420 [P] [US10] Pruebas de contrato en `backend/tests/contract/test_cli_sc.py` (sobre
  `cases/demo` o el snapshot empaquetado): sin `--json` crea los cuatro archivos; con `--json` la
  salida completa es JSON válido y nada más; `--barra` inexistente sale con 4 y nombra la barra;
  `--barra` válida filtra; para una barra, los valores de `cc_barras.csv` y del JSON de `--json`
  son idénticos (SC-022, hallazgo G1); y `backend/tests/contract/test_export_sc.py`: columnas
  exactas de los CSV y claves de `metadatos.json`.

---

## Fase 4: HU-9, nivel de cortocircuito por barra en la interfaz (P1)

**Objetivo**: botón «Cortocircuito», tabla coloreada, resumen, mapa coloreado, resultado
persistente.
**Prueba independiente**: quickstart §3; `test_api_sc.py`, Vitest de `sc.ts` y `ScPanel`.

### Backend

- [ ] T421 [US9] Router `backend/src/sinsim/api/routers/sc.py` según
  [openapi-sc.yaml](./contracts/openapi-sc.yaml): `POST /runs/{run_id}/sc` (cuerpo opcional
  `{"buses": [...]}`, síncrono, 200, `get_or_calculate` + `select_buses`) y `GET /runs/{run_id}/sc`
  (200 con el guardado vigente; 404 `SC_NOT_FOUND`); registrar en `api/app.py`; `trace_id` y
  Problem Details como los demás routers.
- [ ] T422 [P] [US9] Pruebas de contrato en `backend/tests/contract/test_api_sc.py`: POST devuelve el
  esquema del contrato; GET antes del POST → 404 `SC_NOT_FOUND`; GET después → mismo documento;
  POST con `buses` inexistente → 422 `SC_BUS_NOT_FOUND`; `run_id` inexistente → 404.

### Frontend

- [ ] T423 [P] [US9] Tipos `ShortCircuitAnalysis`, `ScBusResult`, `ScSource`, `ScQuality`,
  `ScSummary` en `frontend/src/api/types.ts`; métodos `sc(runId)` (GET) y `calculateSc(runId)`
  (POST) en `frontend/src/api/client.ts`; hooks `useSc(runId)` (query `["sc", runId]`, sin
  reintentos en 404) y `useCalculateSc()` (mutation que escribe la caché de `["sc", runId]`) en
  `frontend/src/api/hooks.ts`.
- [ ] T424 [P] [US9] Módulo puro `frontend/src/features/shortcircuit/sc.ts`: `ikssStyle(ikss,
  maxIkss)` (misma rampa que `loadingStyle` del N-1; la intensidad va de 0 kA al máximo Ikss del
  caso, igual que la leyenda del mapa de T426; gris si `no_source`; hallazgo A1), `formatKa`, `formatMva`, `formatOhm`, `formatXr` (coma decimal, 2–3 decimales),
  `sortBuses(buses, column, dir)` y `filterBuses(buses, text)`; pruebas en
  `frontend/src/features/shortcircuit/sc.test.ts`.
- [ ] T425 [US9] `frontend/src/features/shortcircuit/ScPanel.tsx`: sección «Cortocircuito» con
  `data-testid="sc"`; botón «Cortocircuito» (`sc-start`) disponible con caso construido aunque el
  flujo no haya convergido (FR-069); estado «Calculando…» (`sc-progress`) mientras la mutación está
  en vuelo; al llegar el resultado (o al existir uno guardado al montar), resumen con
  `data-testid="sc-summary"` (barras, barra con mayor Ikss, barra con menor Sk, unidades
  imputadas, unidades sin elevador) y tabla `sc-table` con columnas barra, kV nominal, Ikss, Sk, X/R,
  Rk, Xk, ordenable por cabecera y con búsqueda (`sc-search`); celda de Ikss coloreada con
  `ikssStyle`; `table-layout: fixed` y estilos en `frontend/src/styles.css` como `.n1__*`.
  Se monta en `frontend/src/features/workspace/Workspace.tsx` después de `N1Panel` con
  `key={run.run_id}`; pruebas en `ScPanel.test.tsx` (botón, calculando, tabla, orden, búsqueda).
- [ ] T426 [US9] Modo «cortocircuito» en `frontend/src/features/topology/TopologyView.tsx` y
  `colors.ts`: `ColorBy` gana `"shortcircuit"`; `TopologyView` recibe `scByBus?: Map<string,
  number>` y `scMax?: number` desde `Workspace` (que usa `useSc(run.run_id)`); color de barra =
  `ikssColor(ikss, max)` (verde → rojo, gris sin dato); la opción solo aparece si hay resultado;
  leyenda con mínimo y máximo del caso; el tooltip de barra muestra Ikss y Sk; pruebas de `colors.ts`
  en `colors.test.ts` si no existen.
- [ ] T427 [US9] Paso e2e en `frontend/e2e/flujo.spec.ts`: tras el flujo del caso de ejemplo,
  pulsar «Cortocircuito», esperar `sc-summary`, comprobar que la tabla tiene filas y que la
  opción «cortocircuito» del selector «Colorear por» existe; recargar y comprobar que la tabla
  vuelve sin pulsar el botón (FR-071).

---

## Fase 5: HU-11, calidad e imputaciones visibles (P2)

**Objetivo**: la interfaz y los archivos muestran qué se imputó, qué quedó sin elevador y qué no
aporta.
**Prueba independiente**: quickstart §5; Vitest de la tabla de calidad; `cc_calidad.csv`.

- [ ] T428 [US11] Tabla de calidad en `frontend/src/features/shortcircuit/ScPanel.tsx`
  (`data-testid="sc-quality"`), plegada por defecto, con pestañas o bloques «Imputados» (unidad,
  parámetro, valor, método), «Sin elevador» (unidad, barra), «Sin aporte» (recurso, barra, motivo)
  y «Excluidos» (unidad, motivo), más el bloque «Supuestos» con S26–S31 y su fuente; textos de
  método en español en `sc.ts` (`methodLabel`); pruebas en `ScPanel.test.tsx`.
- [ ] T429 [P] [US11] Comprobar en `backend/tests/integration/test_sc.py` que `quality.imputed`,
  `generators_without_step_up`, `sc_zero_sources` y `excluded` del caso de ejemplo no están vacíos
  donde corresponde (hay unidades sin `ra`, unidades sin elevador, enlaces con Ecuador y tres
  compensadores) y que `metadatos.json` y el JSON de `--json` llevan las mismas listas (FR-073).

---

## Fase 6: Documentación, versión y cierre

- [ ] T430 [P] `docs/supuestos.md`: añadir S26 a S31 con el texto de la spec, el origen (decisión
  del agente o del usuario, 2026-10-25) y los FR que aplican; actualizar el resumen inicial.
- [ ] T431 [P] README: sección «Cortocircuito» (qué calcula, cómo se lanza en la interfaz, `sinsim
  sc` con ejemplos de `--barra` y `--json`, qué significa X/R, limitaciones: solo trifásico, sin
  `ip`, enlaces sin aporte, elevadores no curados) y tabla de comandos.
- [ ] T432 [P] CHANGELOG 0.7.0 (cortocircuito IEC 60909, columnas de máquina en snapshots nuevos,
  `elevadores.csv`, constitución 1.4.0) y versión 0.7.0 en `backend/pyproject.toml`,
  `frontend/package.json` y los textos de versión de la interfaz.
- [ ] T433 Correr el quickstart completo (§1 a §6) y `ruff`, `mypy`, `eslint`, `pnpm test`,
  `pytest`; corregir lo que falle; marcar las tareas [X]; actualizar
  `specs/004-cortocircuito/checklists/requirements.md` si cambió algo de la spec.

---

## Dependencias

- Fase 1 (T400–T401) no bloquea el código, pero T400 debe cerrarse antes del release.
- Fase 2: T402 → T403 → T404; T405 → T406 → T407 → T408 → T409; T410, T411 en paralelo; T412
  depende de T410; T413 de T412; T414 depende de T402, T406, T410, T412; T415 de T414; T416 de
  T415; T417 de T416.
- Fase 3 (HU-10) depende de la fase 2 completa; T418 y T419 en paralelo; T420 tras ambas.
- Fase 4 (HU-9) depende de la fase 2; T421 → T422; T423, T424 en paralelo; T425 depende de T423 y
  T424; T426 de T423; T427 de T425 y T426. HU-9 y HU-10 son independientes entre sí.
- Fase 5 (HU-11) depende de T425 (la tabla vive en el panel) y de T415.
- Fase 6 al final; T430–T432 en paralelo; T433 cierra.

## Ejemplos en paralelo

- Tras T401: T402, T405, T410 y T411 a la vez (archivos distintos).
- Tras T416: T418 (exportación), T421 (router), T423 y T424 (frontend) a la vez.
- Fase 6: T430, T431 y T432 a la vez.

## Estrategia

1. **MVP = Fase 2 + HU-10**: con el CLI y el JSON ya se puede alimentar el consumidor externo y
   validar los números (SC-021 a SC-024) antes de tocar la interfaz.
2. **HU-9** añade la API y la interfaz sobre el mismo servicio.
3. **HU-11** solo agrega la tabla de calidad; los datos ya existen desde la fase 2.
4. Documentación, versión 0.7.0, PR, release a PyPI, video y post, como en 0.6.x.
