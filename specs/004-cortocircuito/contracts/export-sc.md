# Formato de exportación del cortocircuito (FR-070, FR-072, FR-073)

CSV en UTF-8 con encabezado, separador coma y punto decimal, como la exportación de un flujo
([specs/001/contracts/export-format.md](../../001-flujo-potencia-despacho/contracts/export-format.md)).

## `cc_barras.csv` (FR-063)

`bus_id, subestacion, subarea, kv_nominal, kv_base, ikss_ka, skss_mva, rk_ohm, xk_ohm, x_r, sin_fuente`

Orden: por `bus_id`. `rk_ohm`, `xk_ohm` y `x_r` vacíos cuando `sin_fuente` es `true`.

## `cc_fuentes.csv`

`unit_id, tipo, bus_id, trafo_elevador, sn_mva, vn_kv, cos_phi, xdss_pu, rdss_ohm, k,
origen_sn, origen_vn, origen_xdss, origen_rdss`

## `cc_calidad.csv` (FR-073)

`categoria, unit_id, detalle, valor, metodo`

`categoria` ∈ {`imputado`, `sin_elevador`, `sin_aporte`, `excluido`}. Para `imputado`, `detalle` es
el parámetro; para `sin_aporte`, `unit_id` es el recurso del enlace y `detalle` la barra.

## `metadatos.json` (FR-072)

```json
{
  "tipo": "cortocircuito",
  "snapshot": "2026-10-20",
  "despacho": "2026-10-20",
  "periodo": 19,
  "case_id": "…",
  "run_id": "…",
  "case_hash": "…",
  "sc_config_hash": "…",
  "pandapower": "3.5.6",
  "sinsim": "0.7.0",
  "norma": {"standard": "IEC 60909-0:2016", "fault": "3ph", "case": "max", "c_max": 1.1},
  "config": {"converter_k": 1.0, "rg_ratio_large": 0.05, "…": "…"},
  "supuestos": [{"id": "S26", "text": "…", "source": "…"}],
  "calculado_en": "2026-10-25T20:00:00Z",
  "resumen": {"n_buses": 607, "max_ikss": {"bus_id": "SAN CARLOS|230", "ikss_ka": 44.8}, "…": "…"},
  "equivalencias_elevadores": {"matched": 150, "by_method": {"nombre+tension": 110}, "curated": 0, "uncurated": 150},
  "atribucion": "Información proporcionada por XM S.A. E.S.P. …"
}
```
