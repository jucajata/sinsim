# Diseño: análisis de cortocircuito IEC 60909 en sinsim (release 0.7.0)

Fecha: 2026-10-25. Estado: borrador para revisión del usuario.

## Intención y por qué

sinsim modela el STN y el STR con datos de PARATEC y XM y ya hace flujo de carga y N-1. La
constitución (I) incluye el cortocircuito en el alcance, pero no está implementado. Se necesita
por dos razones:

1. Es el siguiente análisis que piden los estudios de conexión (Circular CREG 047/2023, anexo de
   cortocircuito; lineamientos del CNO para la CREG 174/2021, numeral 8.4): corriente de falla
   trifásica y monofásica por barra con la metodología IEC 60909 y comparación con la capacidad de
   interrupción.
2. Un producto externo (el módulo de conexiones de la webapp privada del usuario) necesita, para
   cada barra de frontera de un operador de red, la potencia de cortocircuito y la relación X/R
   del SIN aguas arriba, para construir un equivalente de Thevenin. sinsim debe entregarlos por
   API y CLI sin saber nada de ese producto.

## Objetivos

- Calcular con pandapower (`pandapower.shortcircuit.calc_sc`, IEC 60909) la corriente de
  cortocircuito trifásica máxima (`ikss_ka`, `ip_ka`, `skss_mw`) y la impedancia de Thevenin
  (`rk_ohm`, `xk_ohm`, de donde sale X/R) en todas las barras del caso construido para una fecha y
  un periodo, con la red completa y toda la generación en servicio (criterio de la Resolución UPME
  358/2026, num. 1.1).
- Exponerlo como `POST /runs/{run_id}/sc` (resultado síncrono si tarda menos de unos segundos;
  si no, el mismo patrón de job que N-1), `GET` del resultado, y `sinsim sc --fecha --periodo
  [--barra NOMBRE ...] [--salida] [--json]`.
- Mostrar en la interfaz una tabla por barra (Icc 3φ, Sk, X/R, kA de interrupción si se conoce) con
  el mismo lenguaje visual que los listados N-1, y colorear las barras del mapa por nivel de
  cortocircuito.
- Exportar CSV + `metadatos.json` como hacen el flujo y el N-1.

## No objetivos

- Falla monofásica y bifásica en este release. Requiere impedancias de secuencia cero de líneas y
  transformadores (PARATEC publica `impedanceHighLowSec0` para trafos y nada para líneas) y el
  grupo de conexión con puesta a tierra. Se deja para un release posterior con su propia spec.
- Corriente mínima de cortocircuito (`case="min"`), aportes por rama, y SCR/WSCR.
- Estabilidad dinámica.

## Anti-objetivos

- Inventar reactancias. Toda unidad sin `xd''` publicado se imputa de forma explícita y visible o
  se excluye (constitución III.5); nunca un valor por defecto escondido.
- Romper la reproducibilidad: el resultado debe depender solo del snapshot, la configuración y la
  versión de pandapower, y llevar el hash del caso.

## Restricciones

- Constitución 1.3.0: unidades de pandapower; conversiones solo en
  `adapters/sources_to_pandapower/`; dominio puro sin E/S; errores con el formato de la API;
  comando público nuevo ⇒ enmienda MINOR de la constitución (`sinsim sc`).
- Datos disponibles en PARATEC (snapshot 2026-10-24):
  - Unidades hidráulicas (284): `xd2` (subtransitoria no saturada) 189, `satDirectSubtransX` 179,
    `ratedS` 170, `ratedU` 190, `ratedPowerFactor` 204, `ra` 148, `x2`/`x0` ~185, barra de
    conexión 284.
  - Unidades térmicas (130): `xdSubtrans` 107, `satDirectSubtransX` 106, `ratedS` 95,
    `ratedU` 114, `ratedPowerFactor` 112, `ra` 58.
  - Solares (378) y eólicas (3): potencia nominal y barra; sin reactancias.
  - Transformadores: `vk` por par de devanados; `vkr` derivado de pérdidas de cobre (ya en el
    modelo). Líneas: R, X por km (ya en el modelo).

## Decisiones tomadas por el usuario

- Se calcula el cortocircuito con sinsim (no se piden valores al usuario ni a XM) y se publica
  como capacidad general de sinsim.
- Primera versión: solo trifásico máximo, IEC 60909, red completa, toda la generación en servicio.
- **Transformadores elevadores** (2026-10-25): se incorporan los elevadores que PARATEC publica
  como transformadores de central (IEC 60909-0 §6.7, `power_station_trafo`), con una tabla de
  equivalencias unidad ↔ transformador. Donde no haya transformador que case, el generador va en
  la barra de alta con `vn_kv` igual al de la barra, despreciando la reactancia del elevador, y
  queda reportado.
- **Enlaces internacionales** (2026-10-25): no hay fuente pública de su potencia de cortocircuito;
  el usuario acepta **aporte nulo** (enlace abierto) como supuesto explícito, documentado como
  S29, sabiendo que subestima la corriente en Nariño y Norte de Santander.

## Decisiones del diseñador (marcadas como mías; el usuario puede cambiarlas)

1. **Generadores síncronos** → `net.gen` con `sn_mva`, `vn_kv`, `xdss_pu`, `rdss_ohm`,
   `cos_phi`. `xdss_pu` = `xd2` (hidro) o `xdSubtrans` (térmica), no saturada, que es la que pide
   IEC 60909 (la saturada queda como columna informativa). `sn_mva` = `ratedS`; si falta,
   `ratedNetMaxP / ratedPowerFactor`; si falta también, se imputa por mediana del mismo tipo
   (constitución III.5) y se reporta. `rdss` = `ra` en pu si está publicada **y es mayor que
   cero**; una `ra` publicada como 0 se trata como faltante (físicamente imposible) y se reporta
   como imputada. Si falta, la relación R_G/X''_d de IEC 60909-0 §6.6.1 (0,05 para S ≥ 100 MVA y
   U > 1 kV; 0,07 para S < 100 MVA y U > 1 kV; 0,15 para U ≤ 1 kV), citada en
   `config/defaults.toml`. Unidades sin `xd''` se imputan por mediana de su tipo y quedan en
   `quality.imputed`.
1b. **Red de cortocircuito**: se deriva del caso construido (mismo hash de entrada) añadiendo,
   solo para este análisis, una barra de generación por unidad síncrona con transformador de
   central casado: barra a `ratedU` (o a la tensión de baja del transformador si `ratedU` falta,
   reportado), el generador en ella y el transformador PARATEC entre esa barra y la barra de alta
   del caso, con `power_station_trafo = True`. La equivalencia vive en
   `data/equivalencias/elevadores.csv` (unidad PARATEC, transformador PARATEC, método: nombre de
   planta / subestación / manual), generada con sugerencias por nombre y revisable; una unidad
   sin equivalencia va directo a la barra de alta con `vn_kv` de la barra y entra en
   `quality.generators_without_step_up`. Los compensadores SVC/STATCOM se excluyen del cálculo
   (no aportan corriente de falla en IEC 60909 y rompen `calc_sc` con NaN).
1c. **Tensión de referencia**: IEC 60909 define Un como la tensión nominal del sistema. Como
   pandapower usa `bus.vn_kv`, que en sinsim es la base por clase (S14: 230 para barras de 220 kV,
   115 para 110 kV), los resultados se corrigen a la tensión nominal de PARATEC de cada barra:
   `ikss` × Un/Vb y `skss` × (Un/Vb)²; `rk` y `xk` en ohm no cambian. Documentado como S26.
1d. **Corriente de pico `ip`**: pandapower solo la calcula con rigor para fallas lejanas a
   generadores; se **omite** en 0.7.0 y se deja para el release de falla monofásica.
2. **Unidades no síncronas** (solar, eólica) → `net.sgen` con `k = 1.0`×In (aporte limitado a la
   corriente nominal, cláusula de generadores de convertidor pleno de IEC 60909-0:2016 §6.9), con
   `sn_mva` = capacidad nominal. El factor `k` es configurable y citado.
3. **Todas las unidades en servicio** (`elementStateName == "Operación"`) aportan, estén o no
   despachadas en el periodo. El despacho solo fija el caso base de tensiones; IEC 60909 usa
   `c = 1,10` y no depende del punto de operación. Por eso el resultado se liga a la fecha del
   snapshot y no al periodo; el endpoint acepta el `run_id` por consistencia de trazabilidad.
4. **Enlaces internacionales** (Ecuador en Jamondino 230 y Panamericana 138; Venezuela): en el
   caso son `sgen` de P fija cuando el despacho los trae. Para el cortocircuito **no aportan**
   (decisión del usuario, S29); se listan en `quality.sc_zero_sources` para que el lector sepa
   que la Icc del suroccidente está subestimada. El día que haya fuente, el adaptador acepta
   `s_sc_max_mva` y `rx_max` por enlace en `config/defaults.toml` con su cita.
5. **Unidad de X/R**: se reporta `rk_ohm`, `xk_ohm`, `x_r = xk/rk`, `skss_mva` y `ikss_ka` por
   barra, más la tensión nominal. Es exactamente lo que necesita un equivalente de Thevenin externo.
5b. **Persistencia y consumo externo**: a diferencia del N-1 (S24), el cortocircuito depende solo
   del snapshot y la configuración, así que el resultado se guarda en `cases/<case_id>/sc.json`
   (y en la carpeta de datos del usuario en modo instalado) y `GET /runs/{run_id}/sc` lo lee de
   ahí. El consumidor externo previsto usa el CLI `sinsim sc --fecha F --periodo N --json`, que
   construye el caso si no existe y escribe el JSON completo (barras, resultados, calidad,
   supuestos, hash) a stdout; es el único contrato que se le promete.
6. **Capacidad de interrupción**: PARATEC no la publica. La tabla trae la columna vacía y la
   comparación queda a cargo de quien tenga el dato (el módulo externo la toma del anexo UPME).
7. **CLI**: `sinsim sc --fecha F --periodo N [--barra NOMBRE ...] [--salida DIR] [--json]`; código de
   salida 4 si el caso base no converge, igual que N-1.
8. **Documentación**: supuestos S26–S31 en `docs/supuestos.md` (S26 tensión nominal de
   referencia, S27 xd'' no saturada y `ra` = 0 como faltante, S28 R_G por IEC 60909, S29 enlaces
   internacionales sin aporte, S30 k de convertidores, S31 elevadores sin equivalencia), README,
   CHANGELOG 0.7.0, constitución 1.4.0 (comando `sinsim sc`, persistencia de `sc.json`).

## Lo que queda al constructor

- Estructura de módulos siguiendo N-1: `domain/shortcircuit.py` (puro: construcción de tablas,
  X/R, validaciones), `services/sc.py` (orquestación con pandapower), `api/routers/sc.py`,
  `adapters/storage/export_sc.py`, `frontend/src/features/shortcircuit/`.
- Si `calc_sc` tarda más de ~5 s en el SIN completo, usar el runner de jobs de N-1; medirlo
  primero.
- Pruebas con valor conocido: una red de 3 barras con resultado calculado a mano según IEC 60909.
- Video y post de LinkedIn del release, como en 0.6.x.
