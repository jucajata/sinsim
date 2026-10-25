# Modelo de datos: análisis de cortocircuito trifásico

**Feature**: 004-cortocircuito | **Spec**: [spec.md](./spec.md)

Entidades nuevas en `backend/src/sinsim/domain/entities.py` (Pydantic, inmutables: `Frozen`). Se
reutilizan `Trace` y `ProblemInfo`.

## 1. Tipos

| Tipo | Valores |
|---|---|
| `ScSourceKind` | `sincrona`, `convertidor` |
| `ScMethod` (origen de un parámetro) | `publicado`, `mediana`, `relacion_iec`, `derivado_p_cosphi`, `tension_elevador` |
| `StepUpMethod` | `nombre+tension`, `nombre`, `tension`, `manual` |

## 2. Columnas nuevas de la tabla normalizada `generators`

| Columna | Tipo | Origen PARATEC | Regla |
|---|---|---|---|
| `sn_mva` | float \| null | `ratedS` | Potencia aparente nominal. |
| `vn_gen_kv` | float \| null | `ratedU` | Tensión nominal de la máquina. |
| `cos_phi` | float \| null | `ratedPowerFactor` | 0 < valor ≤ 1. |
| `xdss_pu` | float \| null | `xd2` (hidro) / `xdSubtrans` (térmica) | No saturada (S27). > 0. |
| `xdss_sat_pu` | float \| null | `satDirectSubtransX` | Informativa. |
| `rdss_pu` | float \| null | `ra` | Null si no publicada **o si es 0** (S27). |
| `x2_pu`, `x0_pu` | float \| null | `x2`, `x0` | Informativas (futuro 1φ). |

Para solares y eólicas solo aplica `sn_mva` (= capacidad nominal) y `cos_phi` (null). Snapshots sin
estas columnas las reciben en memoria desde `raw/` al cargarse (research R2).

## 3. `StepUpEquivalence`: fila de `data/equivalencias/elevadores.csv`

| Campo | Tipo | Regla |
|---|---|---|
| `unit_id` | str | `tech:unidad` de la tabla `generators`. Único. |
| `trafo_id` | str | `trafo_id` de `trafos2w` o `trafos3w`. Varias unidades pueden repetirlo. |
| `method` | `StepUpMethod` | Cómo se obtuvo. |
| `curated` | bool | `false` en la propuesta inicial. |
| `valid_from` | date | Como las demás equivalencias. |
| `note` | str | Libre. |

## 4. `ScSource`: fuente de cortocircuito usada

| Campo | Tipo | Regla |
|---|---|---|
| `unit_id` | str | |
| `kind` | `ScSourceKind` | |
| `bus_id` | str | Barra del caso donde aporta. |
| `step_up_trafo_id` | str \| null | Elevador casado (solo síncronas). |
| `sn_mva`, `vn_kv`, `cos_phi`, `xdss_pu`, `rdss_ohm` | float | Valores usados. `k` para convertidores. |
| `origins` | dict[str, `ScMethod`] | Origen de cada parámetro usado. |

## 5. `ScBusResult` (FR-063)

| Campo | Tipo | Regla |
|---|---|---|
| `bus_id` | str | |
| `substation`, `subarea` | str \| null | De la barra. |
| `nominal_kv` | float | Tensión nominal PARATEC (referencia, S26). |
| `base_kv` | float | `vn_kv` del modelo (S14). |
| `ikss_ka` | float | ≥ 0; 0 si «sin fuente». |
| `skss_mva` | float | ≥ 0. |
| `rk_ohm`, `xk_ohm` | float \| null | Null si sin fuente (infinito). |
| `x_r` | float \| null | `xk/rk`; null si `rk` = 0 o sin fuente. |
| `no_source` | bool | Barra sin camino a ninguna fuente. |

## 6. `ScQuality` (FR-073)

| Campo | Tipo |
|---|---|
| `imputed` | list[{unit_id, parameter, value, method}] |
| `generators_without_step_up` | list[unit_id] |
| `sc_zero_sources` | list[{resource, bus_id, reason}] |
| `excluded` | list[{unit_id, reason}] |
| `step_up_equivalences` | {matched: int, by_method: dict[StepUpMethod, int], curated: int, uncurated: int} |

## 7. `ScSummary`

`n_buses`, `max_ikss` (bus_id, ikss_ka), `min_skss` (bus_id, skss_mva), `n_sources_sync`,
`n_sources_converter`, `n_imputed_units`, `n_without_step_up`, `n_no_source`, `duration_s`.

## 8. `ScAssumption`

`id` (S26…S31), `text`, `source` (norma o decisión y fecha).

## 9. `ShortCircuitAnalysis` (FR-071, FR-072)

| Campo | Tipo |
|---|---|
| `case_id`, `run_id` | str |
| `case_hash`, `sc_config_hash` | str |
| `trace` | `Trace` (snapshot, despacho, periodo, pandapower, sinsim) |
| `norm` | `{"standard": "IEC 60909-0:2016", "fault": "3ph", "case": "max", "c_max": 1.10}` |
| `config` | copia de `[shortcircuit]` con sus citas |
| `assumptions` | list[`ScAssumption`] |
| `calculated_at` | datetime |
| `summary` | `ScSummary` |
| `buses` | list[`ScBusResult`] (orden: por `bus_id`) |
| `sources` | list[`ScSource`] |
| `quality` | `ScQuality` |
| `attribution` | str |

## 10. Configuración `[shortcircuit]` (`config/defaults.toml`)

| Clave | Valor | Fuente |
|---|---|---|
| `c_max` | 1.10 | IEC 60909-0 tabla 1 (U_n > 1 kV) |
| `converter_k` | 1.0 | IEC 60909-0:2016 §6.9 (S30) |
| `rg_ratio_large` | 0.05 | §6.6.1, S ≥ 100 MVA, U > 1 kV (S28) |
| `rg_ratio_small` | 0.07 | §6.6.1, S < 100 MVA, U > 1 kV |
| `rg_ratio_lv` | 0.15 | §6.6.1, U ≤ 1 kV |
| `international_links_contribute` | false | S29 (decisión del usuario 2026-10-25) |
| `voltage_reference` | "paratec_nominal" | S26 |

## 11. Dominio puro (`domain/shortcircuit.py`)

Funciones sin pandapower ni E/S:
- `source_parameters(unit, medians, cfg) -> (params, origins, imputed)`: aplica FR-064.
- `propose_step_ups(units, trafos2w, trafos3w, aliases) -> list[StepUpEquivalence]`: research R4.
- `to_nominal(ikss, skss, base_kv, nominal_kv)`: S26.
- `x_over_r(rk, xk)`.
- `summarize(buses, sources, quality, duration)`.
- `config_hash(cfg, equivalences_sha, units_sha)`.

## 12. Errores (`domain/errors.py`)

| Código | HTTP | Salida CLI | Cuándo |
|---|---|---|---|
| `SC_BUS_NOT_FOUND` | 422 | 4 | `--barra` con un nombre que no existe en el caso. |
| `SC_NO_SOURCES` | 422 | 4 | Ninguna unidad entra al cálculo (snapshot sin parámetros y sin `raw/`). |
| `SC_NOT_FOUND` | 404 | 1 | `GET /runs/{run_id}/sc` sin resultado guardado vigente para el caso. |

Los demás (caso o ejecución inexistentes) ya existen.

## 13. Conversiones de unidades (constitución III.1)

En `adapters/sources_to_pandapower/generators.py`, con fórmula en docstring y prueba con valor
conocido: `rdss_ohm(rdss_pu, vn_kv, sn_mva) = rdss_pu · vn_kv² / sn_mva` y
`xdss_ohm(xdss_pu, vn_kv, sn_mva) = xdss_pu · vn_kv² / sn_mva`. `services/sc.py` no convierte
unidades.
