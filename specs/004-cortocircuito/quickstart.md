# Quickstart: validar el cortocircuito de principio a fin

**Feature**: 004-cortocircuito. Requisitos: `uv sync` en `backend/`, `pnpm install` en
`frontend/`, snapshot `2026-10-20` (incluido) o uno nuevo con `sinsim scrape`.

## 1. Pruebas automáticas

```bash
cd backend && uv run pytest -q                      # unitarias, integración y contrato (SC-021, SC-025)
cd frontend && pnpm test                             # Vitest de sc.ts y ScPanel
```

Debe pasar `tests/unit/test_shortcircuit.py::test_red_tres_barras_iec60909` (SC-021, tolerancia
1 %) y `tests/contract/test_cli_sc.py` (con y sin `--json`).

## 2. Terminal

```bash
cd backend
uv run sinsim sc --fecha 2026-10-20 --periodo 19 --salida /tmp/cc
ls /tmp/cc            # cc_barras.csv  cc_fuentes.csv  cc_calidad.csv  metadatos.json
uv run sinsim sc --fecha 2026-10-20 --periodo 19 --barra "SABANALARGA|230" --json | python -m json.tool | head -40
uv run sinsim sc --fecha 2026-10-20 --periodo 19 --barra "NO EXISTE|230"; echo "salida: $?"   # 4
```

Esperado: el primer comando termina en segundos y muestra el resumen con las 10 barras de mayor
Ikss; el segundo imprime solo JSON; el tercero sale con 4 y nombra la barra.

## 3. Interfaz

```bash
cd backend && uv run sinsim serve
```

1. Construir el caso del 2026-10-20, periodo 19, y correr el flujo (como siempre).
2. Pulsar «Cortocircuito»: aparece la tabla por barra con Ikss coloreada, el resumen y la tabla de
   calidad (HU-9, HU-11).
3. En el mapa, «Colorear por → cortocircuito»: las barras cambian de color y la leyenda muestra el
   mínimo y el máximo del caso.
4. Recargar la página y volver al mismo caso: la tabla aparece sin recalcular (FR-071).

## 4. Coherencia (SC-022)

Comparar la fila de `SABANALARGA|230` en la tabla de la interfaz, en `/tmp/cc/cc_barras.csv` y en
el JSON del paso 2: Ikss, Sk, Rk, Xk y X/R idénticos.

## 5. Cuadre de fuentes (SC-023)

En `cc_calidad.csv` y `cc_fuentes.csv`: unidades síncronas con elevador + `sin_elevador` +
`excluido` = unidades síncronas en operación del snapshot (408 en el 2026-10-24).

## 6. Documentación

`docs/supuestos.md` tiene S26–S31; la constitución está en 1.4.0 con `sinsim sc`; el README tiene
la sección «Cortocircuito»; el CHANGELOG tiene 0.7.0.
