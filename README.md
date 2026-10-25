# sinsim — flujo de potencia del SIN colombiano

Herramienta open-source (MIT) para construir y simular, con [pandapower](https://www.pandapower.org/),
modelos del Sistema Interconectado Nacional (SIN) de Colombia a partir de:

- los parámetros técnicos de los equipos publicados en **PARATEC** (XM),
- el **despacho programado** diario (`dDEC`) y
- el **pronóstico oficial de demanda por barra** (`PRON_BARRA`) publicados por XM.

> **Información proporcionada por XM S.A. E.S.P. – PARATEC y archivos públicos de despacho.**
> Todo resultado es un *flujo sobre despacho programado*: describe el programa publicado por
> XM, nunca el estado real del SIN.

## Requisitos

- Python 3.12 y [uv](https://docs.astral.sh/uv/)
- Node 22.13+ y [pnpm](https://pnpm.io/) 11 (solo para la interfaz web)

## Primeros pasos (sin internet, con el snapshot incluido)

```bash
uv sync --project backend
pnpm --dir frontend install     # solo si vas a usar la interfaz
make demo                       # construye el caso del 2026-10-20, periodo 19, y corre el flujo AC
```

`make demo` escribe la exportación en `out/demo/` (cuatro CSV y `metadatos.json`).

## Instalar sin clonar el repositorio

sinsim está publicado en [PyPI](https://pypi.org/project/sinsim/). Con
[uv](https://docs.astral.sh/uv/) basta un comando; uv descarga Python 3.12 si hace falta:

```bash
uv tool install sinsim
sinsim serve          # abre la interfaz en http://127.0.0.1:8000
```

Para actualizar a la última versión: `uv tool upgrade sinsim`. Cada release de GitHub también
trae el wheel y el sdist adjuntos.

El paquete incluye la configuración, las tablas de equivalencias, el mapa base, la interfaz y
el snapshot del 2026-10-20, así que funciona sin internet desde cualquier carpeta:

```bash
sinsim snapshots list
sinsim run --fecha 2026-10-20 --periodo 19
sinsim scrape --fecha 2026-10-22     # descarga otra fecha a tu carpeta de datos
```

La primera ejecución después de instalar puede tardar hasta un minuto, mientras el sistema
carga por primera vez las librerías científicas (pandas, pandapower). Después arranca en
segundos.

Los snapshots que descargas y los casos que construyes se guardan en tu carpeta de datos:
`~/Library/Application Support/sinsim` en macOS, `~/.local/share/sinsim` en Linux y
`%LOCALAPPDATA%\sinsim` en Windows. Para usar otra, define `SINSIM_HOME`. Dentro de una copia
del repositorio, sinsim usa siempre `config/`, `data/` y `cases/` del repositorio.

Para construir el paquete tú mismo: `make package` (deja el wheel y el sdist en `backend/dist/`).

La API escucha solo en `127.0.0.1` y no tiene usuarios ni contraseñas. Para que otra página web
abierta en tu navegador no pueda usarla, rechaza las peticiones dirigidas a otro host y los
cambios que vienen de un origen que no es local.

## Comandos públicos

| Comando | Qué hace |
|---|---|
| `uv run --project backend sinsim snapshots list` | Lista las fechas disponibles y qué datos tiene cada una |
| `uv run --project backend sinsim run --fecha YYYY-MM-DD --periodo N [--tipo ac\|dc] [--exportar DIR] [--json]` | Construye el caso, imprime el reporte de calidad y corre el flujo |
| `uv run --project backend sinsim n1 --fecha YYYY-MM-DD --periodo N [--fecha-despacho F] [--salida DIR] [--json]` | Corre el flujo AC base y el análisis de contingencias N-1; escribe los cuatro listados en CSV |
| `uv run --project backend sinsim sc --fecha YYYY-MM-DD --periodo N [--fecha-despacho F] [--barra NOMBRE ...] [--salida DIR] [--json]` | Cortocircuito trifásico máximo IEC 60909 por barra (Ikss, Sk, Rk, Xk, X/R); escribe tres CSV y metadatos, o solo JSON |
| `uv run --project backend sinsim equivalencias elevadores --fecha YYYY-MM-DD [--salida RUTA]` | Mantenimiento: propone `data/equivalencias/elevadores.csv` (unidad ↔ transformador elevador) para curarlo a mano |
| `uv run --project backend sinsim scrape --fecha YYYY-MM-DD [--out data/paratec/]` | Descarga PARATEC, `dDEC` y `PRON_BARRA` de esa fecha y crea un snapshot nuevo. Se admite hasta mañana (XM publica el despacho la víspera). La interfaz hace lo mismo desde el campo de fecha |
| `make dev` | Levanta la API (`127.0.0.1:8000`) y la interfaz (`127.0.0.1:5173`) |
| `sinsim serve [--puerto N] [--no-abrir]` | Levanta la API y la interfaz construida en `127.0.0.1` y abre el navegador |
| `make package` | Construye la interfaz y el paquete instalable en `backend/dist/` |
| `make test` | Corre todas las pruebas |

Códigos de salida del CLI: `0` éxito (incluye un flujo que no convergió), `1` error general,
`2` uso incorrecto, `3` error de red, `4` validación fallida o cambio de estructura en la fuente.

## Análisis de contingencias N-1

Sobre un flujo AC convergido, sinsim saca de servicio cada línea, cada transformador y cada
generador (la planta completa en su barra, compensadores incluidos), uno a la vez, corre un flujo
AC y compara con el caso base. **Solo cuenta lo que la contingencia empeora**: una línea cuenta si
supera el 100 % y está más cargada que en el caso base; una barra, si queda fuera de su banda y más
lejos de ella que en el caso base. No hay umbral mínimo. Los resultados van en cuatro bloques:

- **Cargabilidad**: contingencias de mayor a menor cargabilidad provocada en cualquier elemento.
- **Tensiones**: de mayor a menor distancia fuera de banda, por debajo o por encima.
- **Aíslan demanda**: contingencias que dejan barras sin servicio, por MW.
- **Sin solución**: el flujo no converge ni partiendo de DC; se muestra con su diagnóstico.

En la interfaz, el botón «Analizar N-1» está debajo de las tablas de resultados y muestra el
avance. Desde la terminal:

```bash
uv run --project backend sinsim n1 --fecha 2026-10-20 --periodo 19 --salida out/n1
```

escribe `n1_cargabilidad.csv`, `n1_tensiones.csv`, `n1_aislan_demanda.csv`, `n1_sin_solucion.csv`
y `metadatos.json` con la trazabilidad: snapshot, pandapower, solver, hash del caso y límites con
su fuente. El cálculo se reparte entre los núcleos del equipo, sin dependencias nuevas: las 1.261
contingencias del caso incluido tardan alrededor de un minuto y medio en un portátil de 12 núcleos.
Si sale el generador de referencia de ángulo, la referencia pasa a la barra de reserva (supuestos
S23 a S25 en [docs/supuestos.md](docs/supuestos.md)).

## Cortocircuito (IEC 60909)

Sobre el caso construido de una fecha y un periodo, sinsim calcula la **corriente de cortocircuito
trifásica máxima** en todas las barras según IEC 60909: red completa y toda la generación en
servicio, independientemente del despacho. Para cada barra entrega Ikss (kA), la potencia de
cortocircuito Sk (MVA) y la impedancia de Thevenin Rk, Xk (Ω) con su relación X/R, referidas a la
tensión nominal de PARATEC. Es lo que piden los estudios de conexión (Circular CREG 047/2023 y
lineamientos del CNO para la CREG 174/2021) y lo que necesita un equivalente de red para modelar
lo que se conecta aguas abajo.

Cómo se arma la red de cortocircuito:

- cada unidad síncrona en operación entra con la reactancia subtransitoria, la potencia, la tensión
  y el factor de potencia que publica PARATEC; lo que falta se imputa de forma visible (mediana de
  la tecnología, relación R/X de IEC 60909) y queda en la tabla de calidad;
- las unidades con transformador elevador casado en `data/equivalencias/elevadores.csv` entran
  tras ese transformador, como unidad de central (§6.7); las demás entran en su barra de alta y
  quedan listadas para curar la tabla;
- las plantas solares y eólicas aportan su corriente nominal como fuentes de convertidor;
- los enlaces internacionales no aportan (no hay fuente pública de su potencia de cortocircuito) y
  los SVC/STATCOM quedan fuera.

En la interfaz, el botón «Cortocircuito» está debajo del N-1 y no exige que el flujo haya
convergido; muestra la tabla por barra (más corriente, más rojo), la calidad y los supuestos, y el
mapa gana la opción «Colorear por → cortocircuito». El resultado se guarda junto al caso y vuelve a
aparecer al abrir el mismo caso. Desde la terminal:

```bash
uv run --project backend sinsim sc --fecha 2026-10-20 --periodo 19 --salida out/cc
uv run --project backend sinsim sc --fecha 2026-10-20 --periodo 19 --barra "SABANALARGA|230" --json
```

La primera forma escribe `cc_barras.csv`, `cc_fuentes.csv`, `cc_calidad.csv` y `metadatos.json`;
la segunda imprime un único JSON con esa barra, su calidad y sus supuestos, pensado para que otra
herramienta lo consuma. Limitaciones de esta versión: solo falla trifásica (la monofásica necesita
impedancias de secuencia cero que PARATEC no publica), sin corriente de pico, y la propuesta de
`elevadores.csv` no está curada (supuestos S26 a S31 en [docs/supuestos.md](docs/supuestos.md)).

## Cómo se construye el caso

1. Se carga el snapshot inmutable de `data/paratec/<fecha>/` y se verifican sus checksums.
2. Se modela el STN + STR (≥ 57,5 kV). Lo que está por debajo se traslada a la barra de la
   frontera STR/SDL y queda registrado.
3. Los recursos del despacho y los nodos del pronóstico se concilian con PARATEC mediante las
   tablas versionadas de `data/equivalencias/`. Lo que no tiene equivalencia se reporta como
   **no ubicado**; nunca se descarta en silencio.
4. La demanda activa de cada barra es `Ener.Act. + Perd.PSTR`; la reactiva, `Ener.Reac`.
5. La diferencia entre generación y demanda la absorbe una **referencia distribuida** entre los
   generadores despachados, en proporción a su potencia programada.
6. Si el flujo no converge, el resultado es `no_convergio` con diagnóstico; nunca se presentan
   tensiones o flujos como válidos.

Los supuestos del modelo (consigna de tensión 1,0 pu, taps en posición neutra, `i0 = 0`,
SVC/STATCOM como fuentes de reactiva) se muestran en cada caso y en cada exportación. Los
límites de tensión y cargabilidad están en `config/defaults.toml`, cada uno con su fuente.

## Estructura

```
backend/   API FastAPI, CLI Typer y motor (src/sinsim)
frontend/  Interfaz React + TypeScript
data/      Snapshots inmutables (paratec/<fecha>/) y tablas de equivalencias
config/    Límites y supuestos con su fuente
cases/     Casos de estudio (JSON de pandapower)
specs/     Especificaciones (Spec Kit)
```

La fuente de verdad del proyecto es `.specify/memory/constitution.md`.

## Cómo colaborar

El modelo se afina con las tablas de equivalencias de `data/equivalencias/`, que relacionan los
recursos del despacho (`dDEC`) y los nodos del pronóstico de demanda (`PRON_BARRA`) con las
plantas, subestaciones y niveles de tensión de PARATEC. Lo que no tiene fila queda "sin ubicar"
en el reporte de calidad; nunca se completa en silencio. Para aportar:

1. Corre un caso y revisa en el reporte de calidad los recursos y nodos sin ubicar (el aviso
   "Cómo colaborar" de la interfaz permite copiar la lista).
2. Confirma el elemento real en [PARATEC](https://paratec.xm.com.co).
3. Edita la tabla que corresponda (`recursos_despacho.csv`, `nodos_demanda.csv`,
   `subestaciones_alias.csv` o, para una subestación sin coordenadas en PARATEC,
   `coordenadas_subestaciones.csv`): fechas `AAAA-MM-DD`, una sola fila vigente por clave y fecha,
   fuente en `note` y sin la marca "NO CURADA". Deja sin fila lo que no puedas confirmar; nunca
   se inventan parámetros eléctricos.
4. Verifica con `make test` y `make demo`: la cobertura debe subir y no debe aparecer nada nuevo
   sin ubicar.
5. Abre un pull request con el motivo y la fuente de cada fila.
