# Contrato del comando `sinsim sc` (HU-10, FR-070)

Se suma a [specs/001/contracts/cli.md](../../001-flujo-potencia-despacho/contracts/cli.md); los
códigos de salida son los de ese contrato (constitución V).

## `sinsim sc --fecha YYYY-MM-DD --periodo N [--fecha-despacho F] [--barra NOMBRE ...] [--salida CARPETA] [--json]`

| Opción | Por defecto | Descripción |
|---|---|---|
| `--fecha` | obligatoria | Fecha del snapshot de PARATEC. |
| `--periodo` | obligatoria | Periodo horario 1–24 (solo define el caso; el cálculo no depende de él). |
| `--fecha-despacho` | `--fecha` | Snapshot del despacho y la demanda, como en `sinsim run`. |
| `--barra` | todas | Barra del caso (`bus_id`, p. ej. `SABANALARGA|230`, o `SABANALARGA 220` con la tensión nominal). Repetible. |
| `--salida` | `./cc-<fecha>-p<NN>/` | Carpeta donde escribir los archivos. Se crea si no existe. |
| `--json` | no | Imprime el `ShortCircuitAnalysis` completo (o filtrado por `--barra`) en stdout y no escribe archivos. |

**Comportamiento**

1. Construye o reutiliza el caso con las mismas reglas de `sinsim run`. No corre el flujo de carga.
2. Si hay un `sc.json` vigente para el caso (mismos hashes), lo reutiliza; si no, calcula y lo
   guarda (FR-071).
3. Sin `--json`: escribe en `--salida` los archivos de [export-sc.md](./export-sc.md) y muestra el
   resumen (FR-063 y FR-073) y las 10 barras con mayor Ikss. Con `--barra`, los CSV y el listado
   solo contienen esas barras.
4. Con `--json`: stdout es un único documento JSON; los avisos van a stderr.

**Códigos de salida**

| Código | Cuándo |
|---|---|
| 0 | Cálculo terminado. |
| 1 | Error general: snapshot alterado, falta el punto de operación. |
| 2 | Uso incorrecto: fecha mal formada, periodo fuera de 1–24, `--barra` vacío. |
| 4 | Validación: `SC_BUS_NOT_FOUND` (barra inexistente, se indica cuál) o `SC_NO_SOURCES`. |
