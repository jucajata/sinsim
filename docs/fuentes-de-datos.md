# Fuentes de datos

> **Información proporcionada por XM S.A. E.S.P. – PARATEC y archivos públicos de despacho.**
> Los datos de XM son públicos y se redistribuyen en este repositorio con esa atribución
> (constitución III.10, research R4). Aparece en cada manifiesto, exportación, en la interfaz y
> en el README.

sinsim se alimenta de tres fuentes, todas de XM. Cada snapshot de `data/paratec/<fecha>/`
guarda la respuesta cruda de cada una (`raw/`), su versión normalizada (`normalized/*.parquet`)
y un `manifest.json` con la URL, la fecha de modificación reportada por la fuente, la versión
del estándar y el SHA-256 de cada archivo.

## 1. PARATEC (parámetros técnicos)

| Campo | Valor |
|---|---|
| Qué es | Catálogo público de parámetros técnicos de los activos del SIN (XM) |
| Acceso | HTTPS, sin credenciales, JSON (`https://paratecbackend.xm.com.co`) |
| Cliente | `backend/src/sinsim/scraper/paratec.py` (research R1) |
| Tasa | Mínimo 1 s entre peticiones, `timeout` 60 s, `User-Agent` identificado (`config/defaults.toml`, `[scraper]`) |

Entidades descargadas y endpoint de cada una:

| Entidad (`manifest.sources[].entity`) | Endpoint | Uso en el modelo |
|---|---|---|
| `paratec.substations` | `reportetransmision/api/Substation/SubstationInfo` | Barras (subestación × nivel de tensión) |
| `paratec.lines` | `reportetransmision/api/Line/getAll` | Líneas: R, X, B, longitud, corriente nominal |
| `paratec.line_map` | `mapas/api/TransmissionMap/getLines` | Extremos de línea cuando `lines` no los trae completos |
| `paratec.transformers` | `reportetransformacion/api/PowerTransformer/PowerTransformerInfo` | Transformadores de 2 y 3 devanados, taps |
| `paratec.reactors` | `reportetransmision/api/Reactor/getAll` | Reactores (shunt) |
| `paratec.capacitors` | `reportegeneracion/api/Capacitor/getAll` | Condensadores (shunt) |
| `paratec.svc_statcom` | `reportetransmision/api/StatcomSvc/getAll` | SVC/STATCOM como fuentes de reactiva |
| `paratec.hydraulic_units` | `reportegeneracion/api/HydraulicUnit/HydraulicUnitInfo` | Generadores hidráulicos |
| `paratec.thermal_units` | `reportegeneracion/api/ThermalUnit/ThermalUnitInfo` | Generadores térmicos |
| `paratec.solar_plants` | `reportegeneracion/api/SolarPlant/getAll` | Plantas solares |
| `paratec.wind_plants` | `reportegeneracion/api/WindPlant/WindPlantInfo` | Plantas eólicas |

PARATEC no publica fecha de modificación por entidad, así que `source_modified_at` queda en
`null` y la fecha del snapshot es la de la descarga (`extracted_at`). Tampoco tiene versión de
estándar; `standard_version` es `null` para estas entidades.

Si un endpoint desaparece o su respuesta no pasa el esquema (`scraper/validate.py`), el comando
termina con `PARATEC_SCHEMA_CHANGED` (código de salida 4) y no deja ningún snapshot parcial.

### Qué no publica PARATEC

- La posición operativa de los taps (sí publica rango, paso y posición neutra).
- La corriente de magnetización `i0` de los transformadores.
- Pérdidas de cobre o de hierro en cerca del 25 % de los transformadores.
- Consignas de tensión ni límites de reactiva operativos.

Cómo se trata cada vacío está en [supuestos.md](./supuestos.md).

## 2. Despacho programado (`dDEC<MMDD>.txt`)

| Campo | Valor |
|---|---|
| Qué es | Programa de generación por recurso y periodo horario, publicado la víspera por el CND |
| Acceso | HTTPS, sin credenciales, portal de archivos de XM (`https://api-portalxm.xm.com.co/administracion-archivos/ficheros`) |
| Carpeta | `InformacionAgentes/Usuarios/Publico/DESPACHO/<AAAA-MM>/` |
| Formato | `"<RECURSO>",v1,…,v24` con separador `,` o `;`; última fila `"Total"`; valores en **MWh por periodo** |
| Estándar | Estándar de Información del Despacho Económico, **XM-CND-2014-045 ed. 2025** (se registra en el manifiesto, R-04) |
| Parser | `adapters/sources_to_pandapower/xm_dispatch.py` (research R2) |

Reglas aplicadas:

- Un periodo dura 1 h, así que MWh del periodo = MW medios. La conversión es explícita en
  `mwh_per_period_to_mw` (constitución III.1).
- Periodo 1 = 00:00–01:00 (A-01, research R11).
- La fila `Total` se verifica contra la suma de los recursos con tolerancia de 0,01 MW.
- **Versiones del mismo día** (decisión D-3 del usuario, 2026-10-20): si existen
  `dDEC<MMDD>.txt` (V0) y `dDEC<MMDD>_V<n>.txt`, prevalece la de mayor `n`. Se descargan todas,
  el manifiesto registra cuál se usó (`dispatch_version`) y el caso lleva la advertencia
  `DISPATCH_REVISED` cuando no es la V0.
- Un recurso con 0 MW en el periodo se modela fuera de servicio, no como error.

El despacho es un **programa**, no la generación real (R-10, NG-06). Por eso cada resultado se
etiqueta "Flujo sobre despacho programado".

## 3. Pronóstico oficial de demanda por barra (`PRON_BARRA<MMDD>`)

| Campo | Valor |
|---|---|
| Qué es | Pronóstico oficial definitivo de demanda por nodo (barra), publicado por XM |
| Acceso | Mismo portal de archivos; carpeta `InformacionAgentes/Usuarios/Publico/DEMANDAS/Pronostico Oficial/<AAAA-MM>/` |
| Formato | `UCP, NODO, kV, CONCEPTO, HORA01..HORA24`, tres conceptos por nodo |
| Estándar | XM-CND-2014-045 ed. 2025 (mismo estándar, registrado en el manifiesto) |
| Parser | `adapters/sources_to_pandapower/xm_demand.py` (research R3) |

Conceptos y cómo se usan (clarificación 4 del 2026-10-20, elegida por el usuario):

| Concepto | Unidad | Columna normalizada | Uso |
|---|---|---|---|
| `Ener.Act.` | MWh | `p_act_mw` | Demanda activa |
| `Perd.PSTR` | MWh | `p_pstr_mw` | Pérdidas por referir la carga al nivel de tensión; **se suman** a la activa |
| `Ener.Reac` | Mvar | `q_mvar` | Demanda reactiva |

La demanda activa de cada barra en el caso es `Ener.Act. + Perd.PSTR`. Las pérdidas PSTR son
pérdidas de la demanda (del nivel inferior al punto de conexión), distintas de las pérdidas de
las líneas y transformadores que calcula el flujo.

### Subáreas y diagramas unifilares (FR-034)

- `SubstationInfo.subAreaName` da la subárea operativa de cada subestación (18 del SIN más
  Ecuador y Venezuela). Los snapshots descargados antes de FR-034 no tienen la columna en
  `normalized/buses.parquet`; se deriva de `raw/` al cargar, sin modificar el snapshot.
- PARATEC publica los "Diagramas unifilares por subárea" en PDF (17 subáreas; Caquetá no tiene).
  El listado sale de la API pública `https://paratecbackend.xm.com.co/unifilares/api/Diagrama/getAll`.
  sinsim no los descarga: la interfaz enlaza a la página de PARATEC con los identificadores
  guardados en `config/defaults.toml` (`[unifilares]`). Los PDF son dibujos vectoriales sin
  texto extraíble, útiles para revisión manual, no como fuente de datos.

### Coordenadas y mapa base (FR-035)

- `SubstationInfo.latitude`/`longitude` dan la ubicación de 503 de las 509 subestaciones del
  snapshot incluido. Snapshots anteriores a FR-035 las derivan de `raw/` al cargar.
- PARATEC también publica el trazado de 807 líneas (`TransmissionMap/getLines`, campo
  `geometry`). Hoy no se usa: las líneas se dibujan rectas entre barras.
- El mapa base es `data/geo/colombia_departamentos.geojson`, derivado de Natural Earth 1:10m
  (dominio público). Su origen y procesamiento están en `data/geo/README.md`. No se usan
  teselas raster de OpenStreetMap porque su política prohíbe la descarga masiva.

## 4. Conciliación de nombres (`data/equivalencias/`)

Las tres fuentes no comparten identificadores. La relación se mantiene en tablas CSV versionadas
con vigencia (FR-011, research R7):

| Tabla | Relaciona | Estado en el snapshot incluido |
|---|---|---|
| `recursos_despacho.csv` | Recurso del `dDEC` → planta o unidad de PARATEC | Propuesta heurística por nombre normalizado; **no curada** (T064) |
| `nodos_demanda.csv` | `NODO` del `PRON_BARRA` → subestación y nivel de PARATEC | Curada el 2026-10-31 (528 de 543 filas, fuente en `note`); 15 filas siguen "NO CURADA" |
| `subestaciones_alias.csv` | Nombres distintos de la misma subestación entre entidades de PARATEC (por ejemplo `MONTERIA (ISA)` ≡ `NUEVA MONTERIA`) | Curada a mano durante la implementación |
| `coordenadas_subestaciones.csv` | Latitud y longitud WGS84 de subestaciones que PARATEC publica sin coordenadas (por ejemplo Pimampiro, en Ecuador); solo completa, nunca reemplaza | Curada a mano, con la fuente de cada fila en `note` |

Lo que no tiene fila queda como **no ubicado** y aparece con sus MW en el reporte de calidad;
nunca se descarta en silencio (FR-012, SC-002). El SHA-256 de las tablas forma parte del hash
del caso, así que cambiar una equivalencia produce un caso distinto.

## 5. Snapshot incluido

| Campo | Valor |
|---|---|
| Fecha | 2026-10-20 |
| Descargado | 2026-10-20T14:58:12Z con `sinsim scrape --fecha 2026-10-20` |
| Despacho | `dDEC1020.txt` (V0), modificado por XM el 2026-10-19T14:37:25-05:00 |
| Demanda | `PRON_BARRA1020` |
| Ubicación | `data/paratec/2026-10-20/` (5,8 MB) |

Para generar otro snapshot: `uv run --project backend sinsim scrape --fecha YYYY-MM-DD`, o
desde la interfaz escribiendo la fecha y pulsando "Descargar datos de esta fecha" (FR-038; usa
`POST /api/snapshots/{fecha}/descarga`, la misma lógica, en el servidor local). Se admite hasta
mañana, porque XM publica el despacho programado la víspera (FR-039). Los snapshots son
inmutables; si la fecha ya existe, el comando y la API terminan con `SNAPSHOT_EXISTS` sin tocar
nada (R-02, FR-004).

PARATEC no tiene histórico: cualquier snapshot trae el despacho y la demanda de su fecha, pero
los parámetros técnicos vigentes en el momento de la descarga (`extracted_at` del manifiesto).
El comando y la interfaz lo avisan.

## 6. Reglas para las pruebas

Las pruebas automatizadas **nunca** llaman a PARATEC ni a los servidores de XM (R-03). Usan
fixtures grabados en `backend/tests/fixtures/` y `httpx.MockTransport`
(`tests/integration/test_scrape_fixtures.py`).
