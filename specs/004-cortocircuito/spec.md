# Spec: análisis de cortocircuito trifásico (IEC 60909)

**Feature**: 004-cortocircuito | **Fecha**: 2026-10-25 | **Estado**: borrador para revisión
**Release objetivo**: 0.7.0
**Origen**: conversación con el usuario del 2026-10-25 y diseño aprobado en
`docs/superpowers/specs/2026-10-25-cortocircuito-design.md`. El usuario necesita, para los
estudios de conexión que hace en los sistemas de distribución local, la potencia de cortocircuito y
la relación X/R del SIN en cualquier barra, calculadas con sinsim y no pedidas a terceros. De paso,
el cortocircuito es el siguiente análisis que exigen los estudios de conexión (Circular CREG
047/2023, anexo de cortocircuito; lineamientos del CNO para la CREG 174/2021, numeral 8.4) y ya
está en el alcance de la constitución (I, «Capacidades en alcance»).

## Problema

sinsim construye el modelo del STN y el STR, corre el flujo y el N-1, pero no dice cuánta corriente
circula ante una falla en una barra ni qué tan rígida es la red vista desde ahí. Sin ese dato no se
puede comparar la corriente de falla con la capacidad de interrupción de una subestación, ni
construir un equivalente de red para estudiar lo que se conecta aguas abajo. Hoy el analista lo
pide al operador de red o lo estima a mano.

## Historias de usuario

### HU-9. Ver el nivel de cortocircuito de cada barra (prioridad P1)

Como analista del SIN, después de construir el caso de una fecha y un periodo quiero lanzar el
cálculo de cortocircuito y ver, barra por barra, la corriente de falla trifásica, la potencia de
cortocircuito y la relación X/R, con el mapa coloreado por nivel de cortocircuito, para saber qué
tan rígida es la red en cada subestación y detectar barras con corrientes altas.

**Aceptación**

1. Con un caso construido en pantalla, el botón «Cortocircuito» lanza el cálculo y, al terminar,
   muestra una tabla con una fila por barra: nombre, tensión nominal, Ikss (kA), Sk (MVA), X/R,
   Rk (Ω) y Xk (Ω), ordenable por cualquier columna y con búsqueda por nombre.
2. La celda de Ikss se colorea con la misma lógica que los listados N-1: más corriente, más rojo,
   con la intensidad relativa al rango del caso.
3. Las barras del mapa se colorean con esa misma escala mientras el modo «cortocircuito» esté
   activo; al pasar el cursor por una barra se ve su Ikss y su Sk.
4. Encima de la tabla se muestra el resumen: barras calculadas, barra con mayor Ikss, barra con
   menor Sk, unidades con parámetros imputados y unidades sin transformador elevador casado.
5. El resultado se conserva al volver a abrir la interfaz con el mismo caso: no hay que recalcular.

### HU-10. Obtener el equivalente de Thevenin desde la terminal (prioridad P1)

Como analista o como otra herramienta, quiero correr el cálculo con un comando y obtener para
cada barra (o para las barras que yo indique) la potencia de cortocircuito, la relación X/R y la
impedancia de Thevenin en un archivo, para usarlas como fuente equivalente en un modelo externo.

**Aceptación**

1. `sinsim sc --fecha 2026-10-20 --periodo 19` construye el caso si hace falta, corre el cálculo y
   escribe `cc_barras.csv`, `cc_calidad.csv` y `metadatos.json` en la carpeta de salida.
2. `sinsim sc --fecha 2026-10-20 --periodo 19 --barra "SABANALARGA 220" --barra "CHINU 220" --json`
   escribe en la salida estándar un único JSON con esas dos barras, sus resultados, la calidad, los
   supuestos aplicados y el hash del caso, y nada más.
3. Los valores del CSV y del JSON coinciden con los de la tabla de la interfaz para el mismo caso.

### HU-11. Saber qué se imputó y qué no aporta (prioridad P2)

Como analista, quiero ver qué unidades generadoras entraron al cálculo con parámetros imputados,
cuáles quedaron sin transformador elevador y qué fuentes no aportan corriente, para juzgar la
confianza del resultado en cada zona.

**Aceptación**

1. La tabla de calidad lista cada unidad con al menos un parámetro imputado, el parámetro, el valor
   usado y el método; cada unidad sin transformador elevador casado; y cada enlace internacional
   declarado sin aporte.
2. El reporte de calidad del caso (`quality`) y `metadatos.json` contienen esas mismas listas.

## Requisitos funcionales

- **FR-062** Alcance del cálculo. Cortocircuito trifásico simétrico máximo según IEC 60909, con el
  factor de tensión c máximo de la norma, sobre la red completa del caso (todas las líneas y
  transformadores en servicio) y con **toda la generación síncrona en servicio aportando**, esté o
  no despachada en el periodo, porque el criterio regulatorio para el máximo (Resolución UPME
  358/2026, num. 1.1) es red completa y generación en línea. El despacho del periodo no interviene
  en el cálculo; el periodo se conserva solo para la trazabilidad del caso.
- **FR-063** Resultados por barra. Para cada barra del caso: corriente inicial simétrica de
  cortocircuito Ikss (kA), potencia de cortocircuito Sk (MVA), resistencia Rk (Ω), reactancia Xk (Ω)
  y relación X/R = Xk/Rk. Todos referidos a la **tensión nominal de la barra en PARATEC** (S26), no
  a la base por clase del modelo (S14); cuando difieren, Ikss y Sk se corrigen con esa tensión y
  Rk y Xk no cambian.
- **FR-064** Generadores síncronos. Cada unidad hidráulica o térmica en estado «Operación» en
  PARATEC entra con: potencia aparente nominal, tensión nominal, factor de potencia nominal,
  reactancia subtransitoria **no saturada** (S27) y resistencia de armadura. Reglas de datos
  faltantes, siempre visibles en la calidad (constitución III.5):
  - potencia aparente faltante: potencia neta máxima dividida por el factor de potencia; si
    tampoco hay, mediana de las unidades del mismo tipo;
  - reactancia subtransitoria faltante: mediana de las unidades del mismo tipo (hidráulica o
    térmica);
  - resistencia de armadura faltante **o publicada como cero**: relación R/X''d de IEC 60909-0
    §6.6.1 según tamaño y tensión de la máquina (S28), citada en la configuración;
  - tensión nominal faltante: la del lado de baja del transformador elevador casado (FR-065); si
    no hay, la unidad va a la barra de alta como en FR-065 c.
- **FR-065** Transformadores elevadores (decisión del usuario, 2026-10-25). 
  a. Existe una tabla de equivalencias unidad ↔ transformador elevador
     (`data/equivalencias/elevadores.csv`), versionada como las demás equivalencias, con el
     identificador de la unidad en PARATEC, el del transformador en PARATEC y el método de la
     equivalencia (nombre de planta, subestación, manual).
  b. El proyecto genera una propuesta inicial de esa tabla por coincidencia de nombre de planta y
     subestación con los transformadores de PARATEC cuyo lado de baja es menor a 57,5 kV; la
     propuesta queda marcada como no curada hasta que el usuario la revise, igual que
     `recursos_despacho.csv`.
  c. Una unidad con equivalencia entra al cálculo en una barra propia a su tensión nominal, unida a
     la barra de alta del caso por su transformador elevador tratado como transformador de central
     (IEC 60909-0 §6.7). Una unidad sin equivalencia entra directamente en su barra de alta a la
     tensión de esa barra, despreciando la reactancia del elevador, y queda en la lista
     `generators_without_step_up` de la calidad (S31).
  d. Esas barras y transformadores existen solo para el cálculo de cortocircuito; no cambian el
     caso de flujo ni su hash.
- **FR-066** Unidades no síncronas. Las plantas solares y eólicas entran como fuentes de corriente
  limitada: aportan k veces su corriente nominal, con k = 1,0 por defecto (S30), configurable y
  citado (IEC 60909-0:2016 §6.9, generadores de convertidor pleno).
- **FR-067** Enlaces internacionales (decisión del usuario, 2026-10-25). Las interconexiones con
  Ecuador y Venezuela **no aportan** corriente de cortocircuito (S29) porque no hay fuente pública de
  su potencia de cortocircuito. Se listan en la calidad como `sc_zero_sources`. Si en el futuro hay
  fuente, la configuración admite potencia de cortocircuito y R/X por enlace con su cita.
- **FR-068** Compensadores. Los SVC y STATCOM, que el modelo representa como generadores, quedan
  fuera del cálculo: no aportan corriente de falla en IEC 60909. Se listan en la calidad como
  excluidos.
- **FR-069** Lanzamiento desde la interfaz. Con un caso construido en pantalla, el botón
  «Cortocircuito» lanza el cálculo. No requiere que el flujo haya convergido, porque el cálculo no
  depende del punto de operación. Mientras corre, la interfaz sigue respondiendo y muestra que el
  cálculo está en curso. Al terminar muestra la tabla, el resumen y el modo de mapa descritos en
  HU-9. La tabla solo muestra; no tiene acciones por fila.
- **FR-070** Comando `sinsim sc --fecha YYYY-MM-DD --periodo N [--fecha-despacho F] [--barra NOMBRE ...]
  [--salida CARPETA] [--json]`. Construye o reutiliza el caso con las mismas reglas de `sinsim run`
  (`--fecha-despacho` significa lo mismo que allí) y corre el cálculo. Sin `--json`, escribe
  `cc_barras.csv`, `cc_calidad.csv` y `metadatos.json` en la carpeta de salida y muestra el resumen
  en la terminal. Con `--json`, escribe en la salida estándar un solo documento JSON con las barras
  (todas, o las de `--barra`), sus resultados, la calidad, los supuestos aplicados y la
  trazabilidad, sin ningún otro texto. Una barra pedida con `--barra` que no exista en el caso
  produce el error de validación de la API con el nombre que no se encontró. Si el caso no se puede
  construir, sale con el código de error de validación.
- **FR-071** Persistencia. El resultado se guarda junto al caso (`sc.json` en la carpeta del caso,
  o en la carpeta de datos del usuario en modo instalado) con el hash del caso y el hash de la
  configuración de cortocircuito. Al consultar el resultado de un caso, se devuelve el guardado si
  ambos hashes coinciden; si la configuración cambió, se recalcula. Esto difiere del N-1 (S24)
  porque el cortocircuito depende solo del snapshot y la configuración, no del flujo.
- **FR-072** Trazabilidad (constitución III.7). Cada cálculo registra la fecha del snapshot, el
  periodo, la versión de pandapower, la norma y el factor c aplicados, el hash del caso, el hash de
  la configuración, los supuestos S26–S31 con su texto, la fecha y hora del cálculo y la atribución
  a XM. Van en `metadatos.json`, en el JSON de `--json` y se ven en la interfaz junto al resumen.
- **FR-073** Reporte de calidad. El cálculo produce: `imputed` (unidad, parámetro, valor, método),
  `generators_without_step_up`, `sc_zero_sources`, `excluded` (compensadores y unidades
  descartadas con la causa) y `step_up_equivalences` (cuántas unidades casaron y por qué método).
  Se guarda con el resultado, se exporta como `cc_calidad.csv` y se muestra en la interfaz.
- **FR-074** Lo que no se publica. La corriente de pico ip, las fallas monofásica y bifásica, la
  corriente mínima de cortocircuito y los aportes por rama no se calculan ni se muestran en este
  release; la tabla y los archivos no tienen esas columnas.
- **FR-075** Constitución. El comando público `sinsim sc` y la persistencia de `sc.json` se
  incorporan a la constitución (IV, «Comandos públicos» y III.4) en una enmienda MINOR a la versión
  1.4.0 antes del release.

## Casos límite

- El caso no se puede construir (sin snapshot para la fecha): no hay cálculo; la interfaz no ofrece
  el botón y el CLI sale con error de validación.
- El flujo del caso no convergió: el cálculo de cortocircuito sí se ofrece y se ejecuta (FR-069).
- Una unidad síncrona sin barra de conexión en el caso (su barra está por debajo del alcance y no
  tiene barra de frontera): queda excluida con la causa en `excluded`.
- Dos unidades que casan con el mismo transformador elevador (por ejemplo dos unidades de la misma
  planta con un solo transformador publicado): comparten el transformador, ambas en la misma barra
  de generación.
- Un transformador elevador de tres devanados: se usa el par alta–baja de la unidad; el tercer
  devanado no entra al cálculo.
- `ratedU` publicado y distinto de la tensión de baja del transformador casado: prevalece la del
  transformador y la diferencia se registra en `imputed` con método «tensión del elevador».
- Barra aislada del resto del caso (sin camino a ninguna fuente): Ikss = 0, Sk = 0 y X/R sin valor;
  se marca «sin fuente» en la tabla.
- Se cambia la configuración de cortocircuito (k, relaciones R/X) y se consulta un resultado
  guardado: se recalcula y se reemplaza (FR-071).
- `--barra` con un nombre que no existe: error de validación con el nombre (FR-070).

## Entidades clave

- **Resultado de barra**: barra (nombre, subestación, tensión nominal PARATEC, tensión base del
  modelo), Ikss, Sk, Rk, Xk, X/R, marca «sin fuente».
- **Fuente de cortocircuito**: unidad síncrona (tipo, parámetros usados y su origen: publicado,
  imputado por mediana, relación IEC), fuente de corriente limitada (solar, eólica, k), enlace sin
  aporte.
- **Equivalencia de elevador**: unidad PARATEC, transformador PARATEC, método, curada o no.
- **Análisis de cortocircuito**: el conjunto de resultados de barra de un caso, con su calidad, su
  resumen, su trazabilidad y los dos hashes (caso y configuración).

## Fuera de alcance

- Fallas monofásica y bifásica (requieren impedancias de secuencia cero de líneas, que PARATEC no
  publica, y grupos de conexión con puesta a tierra).
- Corriente de pico, corriente mínima, aportes por rama, SCR y variantes.
- Comparación con la capacidad de interrupción: PARATEC no la publica; la tabla no tiene esa
  columna y la comparación la hace quien tenga el dato.
- Cortocircuito con contingencias (N-1 de cortocircuito).
- Estabilidad dinámica.

## Criterios de éxito

- **SC-020** Sobre el caso del 2026-10-20, periodo 19, el cálculo completo de todas las barras
  termina en menos de 30 segundos en el portátil del usuario y el resultado guardado se vuelve a
  mostrar en menos de 2 segundos.
- **SC-021** En una red de prueba de tres barras con una fuente síncrona, un transformador de
  central y una línea, Ikss, Sk, Rk y Xk coinciden con el cálculo a mano según IEC 60909 con una
  tolerancia del 1 %.
- **SC-022** Para una barra elegida, el valor de la tabla de la interfaz, el de `cc_barras.csv` y el
  del JSON de `--json` son idénticos.
- **SC-023** Toda unidad síncrona en operación del snapshot está en exactamente uno de estos
  conjuntos: entra con transformador elevador casado, entra sin elevador
  (`generators_without_step_up`) o está excluida con causa. El resumen cuadra con el total.
- **SC-024** Ningún parámetro de cortocircuito del cálculo carece de origen: cada uno es publicado
  por PARATEC, imputado y listado en `imputed`, o un valor de configuración con cita.
- **SC-025** Todas las pruebas existentes pasan. Las nuevas cubren SC-021, la corrección a tensión
  nominal (FR-063), las cuatro reglas de datos faltantes (FR-064), una unidad con y otra sin
  elevador (FR-065), una fuente de corriente limitada (FR-066), la exclusión de compensadores
  (FR-068), la persistencia por hashes (FR-071) y el comando `sinsim sc` con y sin `--json`.

## Supuestos

- **S26 (propuesto)** Los resultados se refieren a la tensión nominal que PARATEC publica para la
  barra, que es la tensión nominal del sistema que define IEC 60909, y no a la base por clase del
  modelo (S14). Decisión del agente, 2026-10-25.
- **S27 (propuesto)** La reactancia subtransitoria usada es la no saturada (`xd2` en hidráulicas,
  `xdSubtrans` en térmicas); la saturada se conserva como dato informativo. Una resistencia de
  armadura publicada como cero se trata como no publicada. Decisión del agente, 2026-10-25.
- **S28 (propuesto)** Resistencia de armadura no publicada: relación R/X''d de IEC 60909-0 §6.6.1
  (0,05 para S ≥ 100 MVA y U > 1 kV; 0,07 para S < 100 MVA y U > 1 kV; 0,15 para U ≤ 1 kV).
  Decisión del agente, 2026-10-25.
- **S29 (aprobado por el usuario, 2026-10-25)** Los enlaces internacionales no aportan corriente de
  cortocircuito porque no hay fuente pública de su potencia de cortocircuito; la corriente en
  Nariño y Norte de Santander queda subestimada y así se informa.
- **S30 (propuesto)** Las plantas solares y eólicas aportan k = 1,0 veces su corriente nominal
  (IEC 60909-0:2016 §6.9). Decisión del agente, 2026-10-25.
- **S31 (aprobado por el usuario, 2026-10-25)** Las unidades sin transformador elevador casado entran
  en su barra de alta despreciando la reactancia del elevador, lo que sobreestima la corriente
  cerca de esas plantas; quedan listadas para que el usuario cure la tabla de equivalencias.
