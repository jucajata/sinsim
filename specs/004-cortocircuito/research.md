# Investigación: análisis de cortocircuito trifásico (IEC 60909)

**Feature**: 004-cortocircuito | **Fecha**: 2026-10-25

Mediciones sobre `cases/demo/net.json` (snapshot 2026-10-20, periodo 19; 607 barras, 857 líneas,
209 transformadores, 195 generadores) y sobre el snapshot 2026-10-24, en el portátil del usuario,
con pandapower 3.5.6. Scripts desechables en el scratchpad de la sesión.

## R1. Tiempo de cálculo y forma de ejecución

- **Medición**: `calc_sc(net, fault="3ph", case="max")` sobre el caso completo con 192 fuentes
  tarda **0,32 s**; limitado a 3 barras (`bus=[…]`), 0,27 s (el costo es armar la matriz, no el
  número de barras pedidas).
- **Decisión**: el cálculo es **síncrono**: `POST /runs/{run_id}/sc` responde con el resultado
  completo; no hace falta el runner de trabajos del N-1 ni avance en la interfaz (FR-069 solo pide
  que se vea «en curso» mientras llega la respuesta). SC-020 (< 30 s) se cumple con margen.
- **Alternativas**: reutilizar `N1Runner` (202 + polling). Descartado: añade estado y polling para
  una operación de menos de un segundo.

## R2. Dónde viven los parámetros de cortocircuito de las unidades

- **Hallazgo**: la tabla normalizada `generators` (795 unidades) no trae `xd''`, `ratedS`,
  `ratedU`, `ra` ni `cos φ`; el `raw/` sí (`xd2`/`xdSubtrans`, `satDirectSubtransX`, `ratedS`,
  `ratedU`, `ratedPowerFactor`, `ra`, `x2`, `x0`) en todos los snapshots, incluido el empaquetado.
  Y el caso (`net.gen`) agrega las plantas por barra desde el despacho (`RECURSO@BARRA`), sin
  parámetros de máquina.
- **Decisión**:
  1. `generators.parse_units` añade las columnas `sn_mva`, `vn_gen_kv`, `cos_phi`, `xdss_pu`,
     `xdss_sat_pu`, `rdss_pu`, `x2_pu`, `x0_pu` a la tabla normalizada; los snapshots nuevos las
     traen de origen (versión del scraper sube).
  2. Para snapshots anteriores, `ParquetSnapshotRepository.load` deriva esas columnas **en
     memoria desde `raw/`**, exactamente como ya hace `_with_substation_attrs_from_raw` para
     `subarea`, `lat` y `lon` (constitución III.3/III.4: `raw/` es inmutable y verificado; no se
     escribe nada). Así el snapshot empaquetado y los versionados siguen sirviendo sin tocarlos.
  3. La red de cortocircuito **no usa `net.gen` del caso**: elimina esas plantas y los
     compensadores, y crea sus propias fuentes a partir de la tabla de unidades (R3).
- **Alternativas**: leer `raw/` en el adaptador en cada cálculo (rompe `raw → normalized → modelo`);
  exigir snapshot nuevo (deja sin cortocircuito a los snapshots versionados y al empaquetado).

## R3. Red de cortocircuito derivada del caso

- **Decisión**: `services/sc.py` parte de `net_json` del caso y construye en memoria una copia:
  - borra `net.gen` (plantas del despacho y compensadores); las cargas y los shunts se dejan como
    están porque **no afectan** el resultado (medido: diferencia máxima 0,000 kA con y sin
    cargas y shunts; IEC 60909 los desprecia y pandapower también);
  - por cada unidad síncrona en «Operación» con barra en el caso: `create_gen` con `sn_mva`,
    `vn_kv`, `xdss_pu`, `rdss_ohm`, `cos_phi`, `pg_percent = 0`, `vm_pu = 1`, `p_mw = 0`;
  - si la unidad tiene elevador casado (R4): barra nueva a su tensión, `create_transformer_from_parameters`
    con los datos del elevador y `power_station_trafo = <índice del trafo>`;
  - por cada planta solar o eólica en operación con barra: `create_sgen(..., sn_mva, k=1.0,
    generator_type="current_source")`.
  Comprobado en una red de 3 barras: el flag `power_station_trafo` cambia Ikss en la barra de alta
  (1,3131 kA con flag; 1,3108 sin él; 1,2943 sin los factores K_G y K_T a mano), es decir,
  pandapower aplica la corrección del §6.7 de la norma. Un `sgen` de 20 MVA con k = 1 en 230 kV
  suma 0,05 kA, como corresponde a I_n.
- **Determinismo**: la red derivada depende solo de `net_json`, de la tabla de unidades del
  snapshot, de `elevadores.csv` y de `[shortcircuit]`; su hash (`sc_config_hash`) entra en el
  resultado (FR-071).

## R4. Equivalencias unidad ↔ transformador elevador

- **Medición** (snapshot 2026-10-24): 408 unidades síncronas en operación, 405 con barra en el
  modelo; 641 transformadores de 2 devanados y 386 de 3 con algún lado < 57,5 kV. Buscando en la
  misma subestación y con tensión de alta igual a la de la barra: 280 unidades tienen algún
  candidato; de ellas 135 tienen el nombre de la planta dentro del nombre del transformador y 116
  tienen un devanado de baja igual a `ratedU`. Muchos candidatos son transformadores de
  distribución (110/44/13,2), no elevadores. Falsos negativos por clase de tensión: «ALTO
  ANCHICAYA G1 129 MVA 230/13.8 kV» no casa con la unidad en «ALTO ANCHICAYA 220» porque 230 ≠ 220.
- **Decisión**: la propuesta inicial de `elevadores.csv` se genera con estas reglas, en orden:
  1. misma subestación (con alias) y misma **clase** de tensión de alta (220 ≡ 230, 110 ≡ 115,
     como S14);
  2. el nombre del transformador contiene el nombre de la planta o la marca `G<n>`/`U<n>` y la
     tensión de baja coincide con `ratedU` (±0,2 kV) → método `nombre+tensión`;
  3. solo el nombre → `nombre`; solo `ratedU` y un único candidato → `tension`;
  4. lo demás queda sin equivalencia (FR-065 c).
  Se espera que entre 135 y 200 unidades casen de forma automática; el archivo se marca «no
  curado» y el usuario lo revisa como `recursos_despacho.csv`. Dos unidades pueden compartir un
  elevador (caso límite de la spec).
- **Alternativas**: casar por potencia (S del trafo ≈ S de la unidad): descartado como criterio
  único porque los elevadores suelen ser mayores que la unidad y hay muchas coincidencias
  casuales; puede añadirse como desempate en la curación manual.

## R5. Tensión de referencia

- **Hallazgo**: en el caso, 223 de 591 barras tienen `nominal_kv ≠ vn_kv` (base por clase, S14).
  pandapower usa `vn_kv` para c·U_n y para pasar de Ω a kA.
- **Decisión**: `domain/shortcircuit.py` corrige a la tensión nominal de PARATEC:
  `ikss_nominal = ikss · (nominal_kv / vn_kv)`, `skss_nominal = skss · (nominal_kv / vn_kv)²`
  (`Ikss = c·U_n/(√3·Z)` es proporcional a U_n y `Sk = √3·U_n·Ikss` a U_n²); `rk` y `xk` no
  cambian. Se reportan ambas tensiones (S26). Diferencia típica: −4,3 % en Ikss y −8,5 % en Sk en
  las barras de 220 kV modeladas en base 230.

## R6. Resistencia de armadura y relación X/R

- **Medición**: con R_G = 0 en todas las máquinas, X/R mediana del SIN = 7,7; con
  R_G = 0,05·X''_d, 7,3 y la diferencia máxima en Ikss es 0,07 kA. El efecto en Ikss es pequeño;
  el efecto en X/R (lo que consume el producto externo) es visible.
- **Decisión**: `ra` publicada > 0 → `rdss_ohm = ra · vn_gen² / sn`; `ra` ausente o 0 → relación
  R/X''_d de IEC 60909-0 §6.6.1 por tamaño y tensión (S27, S28), con las tres constantes en
  `[shortcircuit]` de `defaults.toml` con su cita. Ambas rutas quedan en `imputed`.

## R7. Corriente de pico y otras salidas

- **Hallazgo**: `calc_sc` advierte que `ip` con `net.gen` solo es válido para fallas lejanas a
  generadores (métodos B/C de κ).
- **Decisión**: `ip=False`, `ith=False`, `branch_results=False`; no se publican (FR-074).

## R8. Compensadores y enlaces internacionales

- **Hallazgo**: los SVC/STATCOM del caso son `gen` con P = 0 sin parámetros de máquina; con ellos
  `calc_sc` falla por NaN en la matriz. Los enlaces con Ecuador son `sgen`/`gen` de P fija según el
  despacho; no hay `ext_grid` en el caso.
- **Decisión**: la red derivada (R3) no los crea; quedan en `quality.excluded` (compensadores) y en
  `quality.sc_zero_sources` (enlaces, FR-067). `calc_sc` funciona sin `ext_grid`.

## R9. Persistencia

- **Decisión**: `FileCaseRepository` gana `save_sc(case_id, analysis)` / `get_sc(case_id)` sobre
  `cases/<case_id>/sc.json` (y el equivalente en la carpeta de datos del usuario). El router
  devuelve el guardado si `case_hash` y `sc_config_hash` coinciden; si no, recalcula y reemplaza.
  El JSON es el `ShortCircuitAnalysis` serializado con Pydantic (mismo documento que `--json`).
- **Alternativas**: memoria como el N-1 (S24): descartado porque el resultado es una propiedad del
  snapshot y del caso, útil entre sesiones (HU-9 punto 5).

## R10. Interfaz

- **Decisión**: panel `features/shortcircuit/ScPanel.tsx` después del N-1, con botón
  «Cortocircuito», tabla ordenable y búsqueda; `sc.ts` puro con la escala de color de Ikss
  (relativa al máximo del caso, misma rampa que `loadingStyle` del N-1) y formato. `TopologyView`
  gana la opción «cortocircuito» en «Colorear por», alimentada por un mapa `bus → Ikss` que recibe
  por prop; la leyenda muestra mínimo y máximo del caso. El `GET /runs/{run_id}/sc` se consulta con
  TanStack Query y se guarda en caché por `run_id`.
