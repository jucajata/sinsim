<!--
Sync Impact Report
- Versión: 1.3.0 → 1.4.0 (MINOR, 2026-10-25). Se añade el comando público `sinsim sc`, que
  calcula el cortocircuito trifásico IEC 60909 ya previsto en I «Capacidades en alcance»
  (specs/004-cortocircuito/; decisión del usuario del 2026-10-25), y el comando de
  mantenimiento `sinsim equivalencias elevadores`. No se elimina ni se redefine ningún principio.
  - III.4: el caso persiste además `sc.json` (resultado del cortocircuito) junto a `net.json`.
  - IV «Comandos públicos»: nuevas entradas `uv run sinsim sc …` y
    `uv run sinsim equivalencias elevadores …`.
  - Plantillas (.specify/templates/): revisadas; no requieren cambios.
- Enmienda anterior, 1.2.0 → 1.3.0 (MINOR, 2026-10-24). Se añade el comando público `sinsim n1`, que
  corre el análisis de contingencias N-1 ya previsto en I «Capacidades en alcance»
  (specs/003-contingencias-n1/; decisión del usuario del 2026-10-24). No se elimina ni se
  redefine ningún principio.
  - IV «Comandos públicos»: nueva entrada `uv run sinsim n1 …`.
  - Plantillas (.specify/templates/): revisadas; no requieren cambios.
- Enmienda anterior, 1.1.1 → 1.2.0 (MINOR, 2026-10-23). Se añade el modo instalado: sinsim se instala
  como paquete y funciona fuera del repositorio (specs/002-paquete-instalable/; decisión del
  usuario del 2026-10-23). No se elimina ni se redefine ningún principio.
  - III.4: un snapshot también puede vivir en la carpeta de datos del usuario o dentro del
    paquete (copia byte a byte del versionado). Inmutabilidad, manifiesto y verificación iguales.
  - IV: el árbol suma `backend/hatch_build.py` y `.github/workflows/release.yml`; se añade el
    comando público `sinsim serve` y una subsección «Modo instalado».
  - Plantillas (.specify/templates/): revisadas; no requieren cambios.
- Enmienda anterior, 1.1.0 → 1.1.1 (PATCH, 2026-10-20). Aclaración en IV "Comandos públicos":
  `--fecha` de `sinsim scrape` pasa de opcional a obligatoria (hallazgo I2 de
  /speckit-analyze; decisión del usuario). Sin cambios de principios.
- Enmienda anterior, 1.0.0 → 1.1.0 (MINOR). Se amplía materialmente la guía: nuevas fuentes
  de datos, nuevos directorios, un comando público y un uso adicional de HTTP 409. No se
  elimina ni se redefine ningún principio.
- Origen: decisiones del usuario del 2026-10-20 y la tabla "Complejidad y desviaciones" de
  specs/001-flujo-potencia-despacho/plan.md.
- Principios modificados (sin cambio de título):
  - I. Naturaleza del proyecto: se añaden como fuentes los archivos públicos de XM (despacho
    programado y pronóstico oficial de demanda por barra) y se aclara que usarlos como entrada
    no es despacho económico.
  - III. Reglas de dominio:
    - III.1: `adapters/paratec_to_pandapower/` pasa a llamarse `adapters/sources_to_pandapower/`
      y cubre todas las fuentes.
    - III.4: el snapshot incluye los archivos de XM.
    - III.6: se nombran las fuentes del punto de operación.
    - III.10: se cierra TODO(TERMINOS_XM) con la regla de atribución.
  - IV. Estructura y estilo: el árbol suma `data/equivalencias/` y `config/` y refleja el
    renombre; se añade el comando público `sinsim run`.
  - V. Errores: el código 409 también cubre `SNAPSHOT_CORRUPTED`, que entra al catálogo de
    ejemplo.
- Secciones añadidas o eliminadas: ninguna.
- Plantillas (.specify/templates/): revisadas; ninguna menciona rutas ni reglas cambiadas, así
  que no requieren cambios.
- Documentos de la feature que deben alinearse (fuera de este comando):
  - ⚠ specs/001-flujo-potencia-despacho/plan.md y research.md: renombrar
    `paratec_to_pandapower` a `sources_to_pandapower` y quitar de "Complejidad y
    desviaciones" las desviaciones que esta enmienda absorbe.
- TODO pendientes:
  - TODO(NOMBRE_PROYECTO): nombre público del proyecto (identificador técnico: `sinsim`).
-->


# Constitución del proyecto (sinsim)

> TODO(NOMBRE_PROYECTO): falta definir el nombre público. Mientras tanto se usan el
> identificador técnico `sinsim` (paquete y CLI) y el repositorio `paratec-simulation`.

Esta constitución es la fuente de verdad del repositorio. Si una spec, un plan, una tarea
o el código la contradicen, prevalece la constitución. Las palabras DEBE, NO DEBE,
DEBERÍA y PUEDE se usan en el sentido de RFC 2119.

## Principios fundamentales

### I. Naturaleza del proyecto

**Propósito**: herramienta open-source (licencia MIT) para construir, simular y analizar
modelos de red del Sistema Interconectado Nacional (SIN) de Colombia con **pandapower**,
alimentada por los parámetros técnicos publicados en **PARATEC** (XM) y por los archivos
públicos de XM que definen el punto de operación: el **despacho programado** (`dDEC`) y el
**pronóstico oficial de demanda por barra** (`PRON_BARRA`).

**Capacidades en alcance**
- Obtención de parámetros técnicos de PARATEC y de los archivos públicos de despacho y
  demanda de XM mediante un comando CLI (scraper).
- Snapshots versionados de esos datos incluidos en el repositorio, para trabajar sin
  internet.
- Conversión de los datos de las fuentes → modelo pandapower (líneas, transformadores,
  generadores, compensación, barras, cargas).
- Flujo de carga AC/DC, cortocircuito y análisis de contingencias N-1.
- Interfaz web local para seleccionar snapshot, construir/editar el caso, ejecutar
  simulaciones y visualizar resultados.

**Fuera de alcance** (requiere enmienda para incluirse)
- Estabilidad dinámica, transitorios electromagnéticos o electromecánicos.
- Despacho económico, precios de bolsa u optimización de mercado. Usar como dato de entrada
  el despacho programado que publica XM no es despacho económico.
- Operación en tiempo real o conexión a sistemas SCADA.
- Uso multiusuario en la nube con autenticación.

**Principio de reproducibilidad**: quien clone el repositorio DEBE poder ejecutar una
simulación de ejemplo con el snapshot incluido usando solo `uv sync`, `pnpm install` y
un comando documentado (`make demo`), sin acceso a internet.

**Justificación**: un alcance cerrado evita que el proyecto derive hacia dominios
(mercado, dinámica, tiempo real) con requisitos de datos y validación muy distintos.

### II. Stack tecnológico

| Capa | Tecnología | Notas |
|---|---|---|
| Lenguaje núcleo | Python 3.12 | Tipado estático obligatorio |
| Gestión de entorno | uv (`pyproject.toml` + `uv.lock`) | Versiones fijadas en el lock |
| Motor de simulación | pandapower | Versión fijada; actualizarla es un cambio con spec propia |
| Aceleración (opcional) | parallel-pandapower-solver (p3s) | Solo como extra `[gpu]`/`[fast]`; el proyecto DEBE funcionar sin él |
| Backend | FastAPI + Pydantic v2 + Uvicorn | API REST local; OpenAPI generado automáticamente |
| Frontend | React + TypeScript (strict) + Vite | Gestor: pnpm |
| Estado servidor (frontend) | TanStack Query | Sin estado global adicional salvo necesidad documentada |
| Visualización | Cytoscape.js (topología/unifilar lógico), Plotly.js (resultados) | |
| Datos de parámetros | Parquet (snapshots) + DuckDB (consultas) | Sin servidor de base de datos |
| Casos de estudio | JSON nativo de pandapower (`pp.to_json`) | Carpeta `cases/` |
| Scraper | httpx (endpoints JSON) con Playwright como respaldo | Expuesto vía Typer |
| CLI | Typer | Punto de entrada único: `sinsim` |
| Pruebas | pytest (backend), Vitest (frontend), Playwright (e2e) | |
| Calidad | ruff (lint + format), mypy/pyright, ESLint/Biome, pre-commit | |
| Contenedores (opcional) | Docker Compose | No requerido para ejecutar localmente |

**Restricciones de stack**
- NO DEBE añadirse un servidor de base de datos (Postgres, MySQL, etc.) sin enmienda.
- NO DEBE añadirse ninguna dependencia nueva sin que la spec o el plan la justifique.
- El backend y el frontend se comunican solo vía la API REST documentada en OpenAPI.

**Justificación**: fijar el stack y las versiones hace los resultados reproducibles y
evita que cada feature introduzca herramientas paralelas.

### III. Reglas de dominio (límites inmutables)

1. **Unidades**: dentro del modelo se usan las convenciones de pandapower
   (kV, MW, Mvar, MVA, km, Ω/km, nF/km, kA, %). Toda conversión desde unidades de las
   fuentes (PARATEC y archivos de XM) DEBE ocurrir únicamente en
   `adapters/sources_to_pandapower/`, con la fórmula documentada en el docstring y al menos
   una prueba con valor conocido.
2. **Base del sistema**: f = 60 Hz y S_base = 100 MVA, declarados como constantes en un
   único módulo. Ningún otro archivo los redefine.
3. **Datos crudos inmutables**: el flujo es `raw → normalized → modelo`. Los archivos en
   `raw/` NUNCA se modifican después de descargados.
4. **Snapshots inmutables**: cada snapshot vive en `data/paratec/<YYYY-MM-DD>/`, incluye los
   datos de PARATEC y los archivos de XM de esa fecha, y no se edita tras su commit. En modo
   instalado (IV) vive en `paratec/<YYYY-MM-DD>/` de la carpeta de datos del usuario, o dentro
   del paquete como copia byte a byte de uno versionado; las mismas reglas aplican. Un dato
   nuevo implica un snapshot nuevo. Cada snapshot DEBE tener
   `manifest.json` con: fecha de extracción, URL/endpoint de origen, versión del scraper,
   número de registros por entidad y checksum SHA-256 de cada archivo. Una columna derivada
   que un snapshot anterior no trae PUEDE completarse en memoria desde su `raw/` al cargarlo,
   sin escribir nada. Lo que se calcula sobre un caso vive en `cases/<case_id>/` (`case.json`,
   `net.json`, `runs/`, `sc.json` del cortocircuito), nunca dentro del snapshot.
5. **Cero parámetros inventados**: si falta un parámetro técnico, el elemento se excluye
   o se imputa de forma explícita, con la columna `imputado = true`, el método de
   imputación y un reporte visible en la UI. Nunca se completa en silencio.
6. **Punto de operación explícito**: PARATEC aporta parámetros de equipos, no demanda ni
   despacho. La generación y las cargas provienen de los archivos públicos de XM (despacho
   programado `dDEC` y pronóstico oficial de demanda por barra `PRON_BARRA`), de entrada del
   usuario o de otra fuente documentada en la spec; nunca de valores por defecto ocultos.
7. **Trazabilidad**: todo resultado de simulación DEBE registrar la fecha del snapshot, la
   versión de pandapower, el solver usado y el hash del caso.
8. **Convergencia**: un flujo de carga que no converge NUNCA se presenta como resultado
   válido. Se informa como estado `no_convergio` con diagnóstico (iteraciones, mismatch
   máximo, barras problemáticas).
9. **Límites operativos configurables**: los límites de tensión y cargabilidad son
   parámetros de configuración; todo valor por defecto DEBE citar la norma o fuente de la
   que proviene.
10. **Scraping responsable**: el scraper DEBE limitar la tasa de peticiones, identificarse
    con un User-Agent descriptivo, no paralelizar de forma agresiva y respetar los términos
    de uso de XM. Los datos de XM (PARATEC, despacho programado y pronóstico de demanda) son
    información pública y PUEDEN redistribuirse en el repositorio. Toda redistribución DEBE
    llevar la atribución "Información proporcionada por XM S.A. E.S.P. – PARATEC y archivos
    públicos de despacho" en:
    - el manifiesto de cada snapshot,
    - cada exportación de resultados,
    - la interfaz,
    - el README.

**Justificación**: un resultado eléctrico solo es útil si se puede rastrear hasta datos de
origen verificables; cualquier valor silencioso o inventado invalida el análisis.

### IV. Estructura y estilo de código

#### Estructura de carpetas

```
.
├── .specify/                      # Spec Kit (memory/, templates/, scripts/)
├── specs/                         # Specs de features (spec.md, plan.md, tasks.md)
├── backend/
│   ├── pyproject.toml
│   ├── hatch_build.py             # Copia config, datos de referencia e interfaz al paquete
│   ├── src/sinsim/
│   │   ├── api/                   # Routers FastAPI y esquemas de entrada/salida
│   │   ├── domain/                # Entidades, constantes, unidades, reglas puras
│   │   ├── services/              # Casos de uso: construir red, simular, N-1
│   │   ├── adapters/
│   │   │   ├── sources_to_pandapower/  # Conversión PARATEC y archivos de XM → modelo
│   │   │   └── storage/           # Lectura/escritura Parquet, DuckDB, JSON de casos
│   │   ├── scraper/               # Clientes PARATEC y XM, validación y escritura de snapshot
│   │   └── cli.py                 # Comandos Typer
│   └── tests/{unit,integration,contract}/
├── frontend/
│   └── src/{features,components,api,lib}/
├── data/
│   ├── paratec/<YYYY-MM-DD>/{raw/,normalized/,manifest.json}
│   └── equivalencias/             # Tablas de equivalencias versionadas, con vigencia
├── config/                        # Configuración (límites con su fuente, reglas, consignas)
├── cases/                         # Casos de ejemplo en JSON pandapower
├── docs/
├── .github/workflows/release.yml  # Adjunta el paquete a cada release publicado
└── Makefile
```

#### Comandos públicos (contrato con quien clona el repo)

- `uv run sinsim scrape --fecha YYYY-MM-DD [--out data/paratec/]` — genera un snapshot
  nuevo. La fecha es obligatoria para no descargar por accidente un día incompleto.
- `uv run sinsim snapshots list` — lista snapshots disponibles.
- `uv run sinsim run --fecha YYYY-MM-DD --periodo N` — construye el caso y ejecuta el flujo
  para una fecha y un periodo.
- `make dev` — levanta backend y frontend en local.
- `make demo` — ejecuta un caso de ejemplo con el snapshot incluido.
- `make test` — corre todas las pruebas.
- `sinsim serve [--puerto N]` — levanta la API y la interfaz construida en `127.0.0.1`.
- `uv run sinsim n1 --fecha YYYY-MM-DD --periodo N [--fecha-despacho F] [--salida CARPETA] [--json]`
  — corre el flujo AC base y el análisis de contingencias N-1, y escribe los listados en CSV.
- `uv run sinsim sc --fecha YYYY-MM-DD --periodo N [--fecha-despacho F] [--barra NOMBRE ...] [--salida CARPETA] [--json]`
  — calcula el cortocircuito trifásico máximo (IEC 60909) de todas las barras del caso, o de
  las pedidas, y escribe CSV y metadatos; con `--json` imprime solo el resultado.
- `uv run sinsim equivalencias elevadores --fecha YYYY-MM-DD [--salida RUTA]` — comando de
  mantenimiento del repositorio: propone la tabla `data/equivalencias/elevadores.csv`
  (unidad ↔ transformador elevador) a partir de un snapshot, para curarla a mano.

#### Modo instalado

Fuera del repositorio, sinsim usa los recursos de solo lectura del paquete (configuración,
equivalencias, mapa base, un snapshot de demostración e interfaz) y guarda lo que genera en la
carpeta de datos del usuario: `$SINSIM_HOME` o la convención del sistema operativo. Dentro del
repositorio, todo funciona como antes. El paquete se construye con `make package`.

#### Convenciones

- **Idioma**: identificadores de código en inglés; textos de UI, mensajes al usuario y
  documentación en español. El mapeo nombre-de-campo-PARATEC → nombre-interno vive en un
  único archivo de mapeo.
- **Python**: snake_case para funciones y variables, PascalCase para clases, type hints en
  todas las firmas, docstrings estilo Google, formato y lint con ruff.
- **TypeScript**: `strict: true`, camelCase para variables, PascalCase para componentes,
  un componente por archivo, organización por feature.
- **Commits**: Conventional Commits (`feat:`, `fix:`, `data:`, `docs:`, `test:`,
  `refactor:`). Los snapshots nuevos se suben con `data: snapshot PARATEC YYYY-MM-DD`.

#### Paradigmas

- **Núcleo funcional, capa imperativa delgada**: conversiones y reglas de dominio son
  funciones puras sin E/S. La E/S (red, disco, pandapower) queda en `services/` y
  `adapters/`.
- **Dirección de dependencias**: `api → services → domain`; `adapters` implementa
  interfaces de `domain`. `domain` no importa FastAPI, pandapower ni httpx.
- El objeto `pandapowerNet` solo se crea y muta dentro de `services/` y `adapters/`.
- **Pruebas**: toda conversión de unidades y todo adaptador tiene prueba unitaria. Las
  pruebas del scraper usan fixtures grabados; nunca llaman a PARATEC real.
  Cobertura mínima de `domain/` y `adapters/`: 85 %.

**Justificación**: aislar el dominio de la E/S permite probar las conversiones eléctricas
sin red, disco ni pandapower, y hace visible dónde ocurre cada transformación.

### V. Manejo de errores y validaciones

#### Formato de error de la API

Todas las respuestas de error usan Problem Details (RFC 9457) extendido:

```json
{
  "type": "https://github.com/jucajata/paratec-simulation/errors/snapshot-not-found",
  "title": "Snapshot no encontrado",
  "status": 404,
  "detail": "No existe un snapshot de PARATEC para la fecha 2026-10-19.",
  "code": "SNAPSHOT_NOT_FOUND",
  "user_message": "No hay datos para esa fecha. Elige otra o ejecuta `sinsim scrape`.",
  "trace_id": "…"
}
```

El campo `type` es un identificador estable del tipo de error; no se exige que la URI
resuelva a una página.

#### Códigos HTTP semánticos

| Código | Uso |
|---|---|
| 200 | Operación exitosa, incluido un flujo que no convergió (`status: "no_convergio"` en el cuerpo: es un resultado de la simulación, no un error del cliente) |
| 201 | Caso de estudio creado |
| 400 | Petición mal formada o parámetros semánticamente inválidos (p. ej. fecha futura) |
| 404 | Snapshot, caso o elemento inexistente |
| 409 | Conflicto: el snapshot de esa fecha ya existe, el caso fue modificado en paralelo, o el snapshot no coincide con su manifiesto (`SNAPSHOT_CORRUPTED`) |
| 422 | Cuerpo que no cumple el esquema Pydantic |
| 502 / 503 | PARATEC no responde o devuelve una estructura inesperada durante un scrape vía API |
| 500 | Error no previsto; siempre con `trace_id`, nunca con stack trace al usuario |

401 y 403 NO se usan mientras no exista una spec de autenticación (la app es local y
monousuario).

#### Reglas

- Catálogo único de códigos de error de dominio en `domain/errors.py`
  (p. ej. `PP_NOT_CONVERGED`, `PARAM_MISSING`, `SNAPSHOT_NOT_FOUND`,
  `PARATEC_SCHEMA_CHANGED`, `SNAPSHOT_CORRUPTED`).
- La UI muestra `user_message` en español, accionable y sin jerga interna; nunca stack
  traces.
- Validación en tres puntos: esquema Pydantic en la API, validación de registros PARATEC
  en el scraper y validación física (rangos plausibles) antes de simular.
- Prohibido `except:` desnudo o `except Exception: pass`. Toda excepción se registra o se
  convierte en error de dominio.
- Logs estructurados (JSON) con `trace_id`.
- **Scraper atómico**: escribe en un directorio temporal y solo renombra al destino final
  si todas las validaciones pasan. Nunca deja un snapshot parcial.
- **Códigos de salida del CLI**: 0 éxito, 1 error general, 2 uso incorrecto,
  3 error de red, 4 validación fallida o cambio de estructura en PARATEC.

**Justificación**: errores uniformes y accionables permiten que la UI, el CLI y las pruebas
reaccionen de forma predecible, y que un fallo nunca se confunda con un resultado.

### VI. Comportamiento del agente (fuente de verdad / cero código sombra)

1. **Fuente de verdad**: el agente implementa únicamente lo descrito en `spec.md`,
   `plan.md` y `tasks.md` de la feature activa, dentro de los límites de esta constitución.
2. **Cero código sombra**: NO DEBE añadir endpoints, pantallas, flags, configuraciones,
   dependencias, campos de datos ni "mejoras" que no estén documentados. Si cree que algo
   falta, lo propone por escrito y espera aprobación.
3. **Detenerse ante contradicciones**: si detecta contradicción entre spec, plan, tareas,
   constitución o código existente, el agente DEBE detenerse, describir la contradicción
   citando archivo y sección, y pedir una decisión. No elige una interpretación por su
   cuenta.
4. **Sin valores eléctricos inventados**: no inventa parámetros técnicos, límites
   normativos ni factores de conversión. Si necesita uno, lo solicita o deja un
   `TODO(fuente)` que bloquea el cierre de la tarea.
5. **Datos intocables**: no modifica, regenera ni borra archivos en `data/paratec/` salvo
   que la tarea lo indique explícitamente.
6. **Pruebas como condición de cierre**: una tarea no se marca como completada si las
   pruebas fallan, si se desactivaron pruebas o si baja la cobertura mínima.
7. **Sin llamadas reales a PARATEC** durante pruebas ni durante la implementación, salvo
   tarea explícita de scraping.
8. **Transparencia**: al cerrar cada tarea, el agente reporta archivos modificados,
   decisiones tomadas y cualquier desviación respecto al plan.

**Justificación**: todo lo que entra al repositorio debe poder rastrearse hasta una
decisión documentada; el código no especificado es deuda que nadie revisó.

## Gobernanza

- Esta constitución prevalece sobre cualquier otro documento del repositorio.
- Las enmiendas se hacen mediante PR que actualiza la versión con SemVer:
  MAJOR (se elimina o redefine un principio), MINOR (se añade un principio o sección),
  PATCH (redacción o aclaraciones).
- Cada enmienda actualiza el Sync Impact Report del encabezado y revisa las plantillas de
  `.specify/templates/`.
- El "Constitution Check" de cada `plan.md` DEBE verificar los principios III, IV y VI.

**Versión**: 1.4.0 | **Ratificada**: 2026-10-19 | **Última enmienda**: 2026-10-25
