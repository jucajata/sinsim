# Cambios

Todas las versiones de sinsim, de la más reciente a la más antigua. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y la numeración sigue
[versionado semántico](https://semver.org/lang/es/). Mientras la versión empiece por 0, el
proyecto está en desarrollo y el contenido de un caso puede cambiar entre versiones menores.

Cada caso registra en su traza la versión de sinsim con que se calculó: para reproducir un
resultado, usa el código de esa versión.

## [0.7.1] - 2026-10-31

### Corregido

- `data/equivalencias/nodos_demanda.csv` curada: 528 de 543 filas confirmadas (481 propuestas
  revisadas, 45 de ellas corregidas, y 47 nodos nuevos), con la fuente en `note`. Entre las
  corregidas, nodos que estaban en una subestación homónima de otra región (UNION, SAN ANTONIO,
  CODAZZI, BARBOSA, SALAMINA…). En el periodo 20 del 2026-10-21 la demanda sin ubicar baja de
  1 443 MW (66 nodos) a 0 MW. Cambia el `case_id` de todos los casos, porque el hash de las
  equivalencias entra en él.

### Limitación conocida

- Con toda la demanda ubicada, el periodo 21 del snapshot incluido (2026-10-20) no converge: la
  tensión colapsa en Mompox–Magangué. Antes convergía solo porque faltaban 1,4 GW de demanda, y
  aun así con barras a 0,44 pu. La causa es el soporte de reactiva del modelo (taps en neutro, sin
  transformadores elevadores en el flujo, condensadores siempre conectados); la prueba de ese
  periodo queda marcada como falla esperada hasta corregirlo.

## [0.7.0] - 2026-10-25

### Añadido

- Análisis de cortocircuito trifásico máximo según IEC 60909 en todas las barras del caso: Ikss,
  Sk, Rk, Xk y X/R referidos a la tensión nominal de PARATEC, con red completa y toda la
  generación en servicio. Botón «Cortocircuito» en la interfaz (tabla coloreada, calidad,
  supuestos y mapa por Ikss), `POST`/`GET /api/runs/{run_id}/sc` y comando `sinsim sc` con
  `--barra` y `--json`.
- Transformadores elevadores de PARATEC como unidades de central, con la tabla de equivalencias
  `data/equivalencias/elevadores.csv` (207 de 408 unidades casadas de forma automática, sin curar)
  y el comando de mantenimiento `sinsim equivalencias elevadores`.
- Columnas de máquina (`sn_mva`, `vn_gen_kv`, `cos_phi`, `xdss_pu`, `xdss_sat_pu`, `rdss_pu`,
  `x2_pu`, `x0_pu`) en la tabla normalizada de unidades; los snapshots anteriores las reciben en
  memoria desde `raw/` sin modificarse.
- Sección `[shortcircuit]` en `config/defaults.toml` con el factor c, el aporte de convertidores,
  las relaciones R/X de IEC 60909 y la decisión sobre enlaces internacionales, cada uno con su
  fuente. Supuestos S26 a S31.
- El resultado del cortocircuito se guarda en `cases/<case_id>/sc.json` y se reutiliza mientras no
  cambien el caso, la configuración, las equivalencias ni los parámetros de máquina.

### Cambiado

- Constitución 1.4.0: comandos `sinsim sc` y `sinsim equivalencias elevadores`; `sc.json` entre
  los archivos del caso.

## [0.6.2] - 2026-10-24

### Corregido

- En los listados N-1, las columnas de cargabilidad y tensión quedaban fuera de la vista en
  pantallas medianas: los nombres largos no partían línea y empujaban los valores a la derecha.
  Ahora el valor va en la segunda columna, los nombres parten línea, la tabla reparte el ancho
  disponible y los dos listados se apilan por debajo de 1280 px.

### Añadido

- Color por intensidad en los listados N-1: la cargabilidad va de claro a rojo pleno entre el
  límite y el doble del límite; la tensión va en rojo (sobretensión) o azul (subtensión), más
  intenso cuanto más lejos de la banda, pleno a 0,10 pu.

## [0.6.1] - 2026-10-24

### Corregido

- pandapower ya no avisa «numba cannot be imported» en cada proceso del análisis N-1 ni en el
  flujo: numba no es dependencia del proyecto y ahora se le indica explícitamente (`numba=False`).
- Los enlaces al nombre anterior del repositorio (`paratec-simulation`) apuntan a `sinsim`: la
  ventana «Cómo colaborar», el `type` de los errores de la API y el User-Agent del scraper. Como el
  User-Agent vive en `config/defaults.toml`, el `case_id` de un mismo escenario cambia respecto a
  0.6.0.
- La página de sinsim en PyPI enlaza al repositorio y al registro de cambios.

## [0.6.0] - 2026-10-24

Análisis de contingencias N-1: qué salida de un activo deja la red en peor estado.

### Añadido

- **Análisis N-1** sobre un flujo AC convergido: saca de servicio cada línea, transformador y
  generador (planta por barra, compensadores incluidos), uno a la vez, corre un flujo AC por
  contingencia y compara con el caso base. Solo cuenta lo que empeora, sin umbral mínimo.
- **Dos listados independientes**, cargabilidad y tensiones, ordenados por el peor valor que
  provoca cada contingencia, y dos bloques: «Aíslan demanda» y «Sin solución», este con el
  diagnóstico de la no convergencia (nunca se descarta).
- **Botón «Analizar N-1»** en la interfaz, con avance y resumen. Un solo análisis a la vez.
- **Comando `sinsim n1`**, que escribe los cuatro listados en CSV y `metadatos.json` con la
  trazabilidad.
- El cálculo se reparte entre los núcleos del equipo sin dependencias nuevas: 1.261 contingencias
  en unos 76 s con 11 procesos.

### Cambiado

- Códigos nuevos en el catálogo de errores: `N1_BASE_INVALID` (422, salida 4), `N1_IN_PROGRESS`
  (409) y `N1_JOB_NOT_FOUND` (404).
- La versión de sinsim entra en el hash del caso, así que el `case_id` de un mismo escenario
  cambia respecto a 0.5.0.

### Gobernanza

- Constitución 1.3.0: se añade el comando público `sinsim n1`.

## [0.5.0] - 2026-10-23

sinsim se instala con un comando y funciona desde cualquier carpeta.

### Añadido

- **Paquete instalable** con todo lo necesario para trabajar sin internet: configuración, tablas
  de equivalencias, mapa base, la interfaz construida y el snapshot del 2026-10-20.
- **Comando `sinsim serve`**: levanta la API y la interfaz en `127.0.0.1` y abre el navegador.
- **Carpeta de datos del usuario** para los snapshots descargados y los casos, configurable con
  `SINSIM_HOME`.
- **`make package`** construye el wheel y el sdist, y una acción de GitHub los adjunta a cada
  release publicado.

### Seguridad

- La API local rechaza las peticiones de páginas web ajenas. Solo atiende peticiones dirigidas
  a `127.0.0.1` o `localhost`, lo que bloquea el DNS rebinding. En los cambios, como iniciar una
  descarga o construir un caso, exige que el origen sea local, lo que bloquea el CSRF. La
  interfaz y la CLI no notan nada.
- La acción de release fija cada acción a un commit exacto, y solo el trabajo que sube el
  paquete tiene permiso de escritura.

### Sin cambios para quien clona el repositorio

- Dentro del repositorio, sinsim sigue usando `config/`, `data/` y `cases/`. Un mismo escenario
  produce el mismo `case_id` en los dos modos.

### Gobernanza

- Constitución 1.2.0: se añade el modo instalado (III.4 y IV).

## [0.4.0] - 2026-10-23

Primera versión publicada. Reúne el modelo del SIN construido desde PARATEC, el despacho
programado y el pronóstico de demanda de XM, y la interfaz web para ejecutarlo.

### Añadido

- **Coordenadas curadas** para subestaciones que PARATEC publica sin coordenadas, en la tabla
  `data/equivalencias/coordenadas_subestaciones.csv` con su fuente. La primera fila ubica
  Pimampiro (Ecuador), extremo de los circuitos Jamondino–Pimampiro 230 kV (#3, supuesto S21).
- **Descarga desde la interfaz**: una fecha sin snapshot se descarga de PARATEC y XM desde el
  campo de fecha, hasta el día siguiente.
- **Aviso «Cómo colaborar»** en el reporte de calidad, con los recursos y nodos sin ubicar.
- **Subáreas, mapa geográfico, flujos por barra y reporte de violaciones** (#1, FR-034 a
  FR-037).

### Cambiado

- **Topología sin saturación** con muchas barras cercanas (#2): tamaños acotados en pantalla,
  flechas de flujo de tamaño fijo a mitad de rama, etiquetas sin solapes en cuatro posiciones,
  dobles circuitos separados y barras de una misma subestación repartidas según el zoom.
- **Rediseño de la interfaz** sobre el sistema de diseño sinsim: tema oscuro, foco visible,
  franja de indicadores, pestañas segmentadas, tablas con cifras alineadas y estado por fila.
  El mapa de topología va primero.
- El contenido del caso cambia respecto a 0.3.0: las coordenadas curadas entran en los
  supuestos y en el hash del caso.

### Datos

- Snapshots de PARATEC del 2026-10-09, 2026-10-19, 2026-10-20 y 2026-10-21.

[0.7.1]: https://github.com/jucajata/sinsim/releases/tag/v0.7.1
[0.7.0]: https://github.com/jucajata/sinsim/releases/tag/v0.7.0
[0.6.2]: https://github.com/jucajata/sinsim/releases/tag/v0.6.2
[0.6.1]: https://github.com/jucajata/sinsim/releases/tag/v0.6.1
[0.6.0]: https://github.com/jucajata/sinsim/releases/tag/v0.6.0
[0.5.0]: https://github.com/jucajata/sinsim/releases/tag/v0.5.0
[0.4.0]: https://github.com/jucajata/sinsim/releases/tag/v0.4.0
