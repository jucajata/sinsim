# Supuestos del modelo

Ningún parámetro eléctrico ni límite se inventa (constitución III.5, III.9, R-13). Cuando una
fuente no publica un dato, el modelo aplica un supuesto **explícito**, que aparece en el campo
`assumptions` de cada caso, en `metadatos.json` de cada exportación y en la interfaz (FR-018).
Esta página lista cada supuesto con su origen y la fecha en que se decidió.

Todos los valores configurables están en `config/defaults.toml`, cada uno con su campo
`*_source`.

## Resumen

| # | Supuesto | Valor | Origen | Fecha |
|---|---|---|---|---|
| S1 | Alcance de la red | STN + STR, barras ≥ 57,5 kV | Clarificación 1 (opción B), usuario | 2026-10-19 |
| S2 | Elementos por debajo de 57,5 kV | Se trasladan a la barra de frontera STR/SDL | Clarificación 2 (opción B), usuario | 2026-10-19 |
| S3 | Demanda por barra | `PRON_BARRA`: P = `Ener.Act.` + `Perd.PSTR`, Q = `Ener.Reac` | Clarificación 3 y 4 (opción A), usuario | 2026-10-19 |
| S4 | Referencia (slack) | Distribuida ∝ P programada; ángulo de referencia en `SAN CARLOS\|230` | Clarificación 5 (opción C) y FR-015 | 2026-10-19 / 2026-10-20 |
| S5 | Consigna de tensión de generadores | 1,0 pu | Decisión D-2, usuario | 2026-10-20 |
| S6 | Posición de taps | Paso neutro (`normalStep`) | Decisión D-2, usuario | 2026-10-20 |
| S7 | Corriente de magnetización | `i0 = 0 %` | Decisión D-2, usuario | 2026-10-20 |
| S8 | Impedancias de transformadores | Tal como las espera pandapower, sin conversión | Usuario | 2026-10-20 |
| S9 | Corriente nominal de líneas | 100 % de cargabilidad = `ratedCurrent` | Decisión D-4, usuario | 2026-10-20 |
| S10 | SVC/STATCOM | Generador con P = 0 y Q ∈ [−Q_ind, +Q_cap] a 1,0 pu | Decisión D-6, usuario | 2026-10-20 |
| S11 | Islas | Artefacto de datos; solo se energiza la componente con la referencia | Decisión D-5, usuario | 2026-10-20 |
| S12 | Parámetros faltantes | Imputación por mediana solo para pérdidas de cobre e hierro de trafos | Decisión del proyecto | 2026-10-20 |
| S13 | Versiones del despacho | Prevalece la `_V<n>` mayor; V0 = sin sufijo | Decisión D-3, usuario | 2026-10-20 |
| S14 | Base de tensión por clase | 110/112/115 → 115; 220/230 → 230; 13,2/13,8 → 13,8 | Decisión de implementación | 2026-10-20 |
| S15 | Límites de tensión y cargabilidad | CREG 025/1995 y CREG 153/2019 | Research R9 | 2026-10-20 |
| S16 | Subárea de cada barra | La que PARATEC publica para la subestación; sin ella, «sin subárea» | FR-034, usuario | 2026-10-20 |
| S17 | Ubicación de las barras | Coordenadas de PARATEC por subestación; sin ellas, franja al oeste | FR-035, usuario | 2026-10-20 |
| S18 | Lectura de flujos en la topología | Signo de pandapower: positivo sale de la barra origen | FR-036 | 2026-10-20 |
| S19 | Líneas con ambos extremos en la misma subestación | Se repara el extremo por el nombre de la línea | FR-019 | 2026-10-20 |
| S20 | Reporte de violaciones | Etiquetas por banda y límite configurados | FR-037 | 2026-10-20 |
| S21 | Coordenadas curadas | Solo completan las que PARATEC no publica, con fuente | FR-035 | 2026-10-20 |
| S22 | Modo instalado | Datos del paquete y carpeta del usuario | FR-040 a FR-046 | 2026-10-23 |
| S23 | Reparto de la potencia del generador que sale (N-1) | Referencia distribuida ∝ P programada | Agente, aceptado por el usuario | 2026-10-24 |
| S24 | Persistencia del N-1 | No se guarda en disco | Agente, aceptado por el usuario | 2026-10-24 |
| S25 | Compensadores en el N-1 | Son contingencias; un generador es la planta por barra | Usuario | 2026-10-24 |
| S26 | Tensión de referencia del cortocircuito | Nominal de PARATEC, no la base por clase | Decisión del agente | 2026-10-25 |
| S27 | Reactancia subtransitoria y `ra = 0` | No saturada; un cero publicado es faltante | Decisión del agente | 2026-10-25 |
| S28 | Resistencia de armadura faltante | Relación R_G/X''_d de IEC 60909-0 §6.6.1 | IEC 60909 | 2026-10-25 |
| S29 | Enlaces internacionales en el cortocircuito | No aportan corriente | Usuario | 2026-10-25 |
| S30 | Plantas solares y eólicas | k = 1,0 veces la corriente nominal | IEC 60909-0 §6.9 | 2026-10-25 |
| S31 | Unidades sin elevador casado | Entran en la barra de alta sin la reactancia del elevador | Usuario | 2026-10-25 |

## Detalle

### S1. Alcance: STN + STR (≥ 57,5 kV)

Se modelan todas las barras de PARATEC con tensión nominal igual o mayor a 57,5 kV, es decir
el Sistema de Transmisión Nacional (≥ 220 kV) y los Sistemas de Transmisión Regional. El
umbral está en `[network].min_vn_kv`. Origen: pregunta 1 de `/speckit-clarify`; el usuario
corrigió su primera respuesta (solo STN) por STN + STR el 2026-10-19.

### S2. Traslado a la barra de frontera

Un generador, compensador o carga conectado por debajo de 57,5 kV se conecta en la **barra de
frontera**: la de la misma subestación con el nivel más bajo ≥ 57,5 kV al que llegue un
transformador. Cada traslado queda en `quality.transfers` con el elemento, la barra de origen,
la de destino y sus MW/Mvar. Si no hay barra de frontera, el elemento queda como no modelado y
se reporta. Origen: pregunta 2 de `/speckit-clarify`, opción B.

### S3. Demanda por barra desde `PRON_BARRA`

XM publica un pronóstico oficial por nodo. Cada nodo se concilia con una barra del modelo
mediante `data/equivalencias/nodos_demanda.csv`. La demanda activa es la suma de `Ener.Act.`
y `Perd.PSTR`, porque las pérdidas PSTR son pérdidas de la demanda al referirla a su nivel de
tensión, distintas de las pérdidas de los activos de red que calcula el flujo. La reactiva es
`Ener.Reac`. Origen: el usuario aportó la fuente (2026-10-19) y eligió la opción A de la
pregunta 4.

La demanda sin equivalencia se reporta en `quality.unlocated_demand` y en
`balance.p_demand_unlocated_mw`; no se reparte entre otras barras. Los dos componentes de la
demanda activa de cada barra se conservan por separado en `assumptions.demanda_por_barra`
(`p_act_mw`, `p_pstr_mw`, `q_mvar`) y como columnas de `net.load`.

### S4. Referencia distribuida y barra de ángulo

El desbalance entre generación programada, demanda y pérdidas lo absorben **todos los
generadores despachados**, en proporción a su P programada (`distributed_slack = True` en
pandapower). La barra de referencia de ángulo es la del STN con mayor suma de `p_max_mw`
conectada en el snapshot incluido: `SAN CARLOS|230` (1 292 MW), seguida de `GUAVIO|230` y
`ANTIOQUIA|500`. Si en un periodo esa barra no tiene generación despachada, el caso usa la
barra del generador con mayor P programada y lo declara como supuesto. Origen: pregunta 5 de
`/speckit-clarify` (opción C) y FR-015; el valor se calculó el 2026-10-20.

El ajuste total de la referencia aparece en `summary.slack_adjust_total_mw` y por generador en
`slack_adjust_mw`.

### S5. Consigna de tensión 1,0 pu

El despacho solo trae potencia activa. Los generadores se modelan como nodos PV con consigna
1,0 pu y límites de reactiva de PARATEC (`enforce_q_lims = True`). No hay norma que fije la
consigna: CREG 135/2013, num. 5.7, remite al planeamiento operativo del CND. Origen: decisión
D-2 del usuario, 2026-10-20. El caso lista en `assumptions.generadores` la consigna y los
límites de reactiva asignados a cada generador (incluidos SVC/STATCOM) con la fuente de cada
valor; cuando PARATEC no publica los límites de todas las unidades de un recurso, el generador
queda sin límite de Q y así se indica.

### S6. Taps en posición neutra

PARATEC publica el rango, el paso y la posición neutra del cambiador, pero no la posición
operativa. Se usa `normalStep` como posición. El signo del paso se deduce de la orientación
(`lowStepU > highStepU` → paso negativo). Origen: decisión D-2, 2026-10-20; el usuario confirmó
que con los datos de PARATEC es suficiente.

### S7. `i0 = 0 %`

PARATEC no publica la corriente de magnetización. Se desprecia. Origen: decisión D-2.

### S8. Impedancias de transformadores sin conversión

Los valores de PARATEC se cargan en los campos que pandapower espera, sin convertir de base:
`vk_percent` = impedancia HL en transformadores de dos devanados; en tres devanados
`vk_hv = HM`, `vk_mv = ML`, `vk_lv = HL`; `vkr` a partir de las pérdidas de cobre sobre la base
de pandapower. Origen: instrucción del usuario el 2026-10-20 ("lo que diga pandapower, no hay
que convertir nada"), que anuló una conversión de base que se había empezado a implementar.

Casos particulares decididos durante la implementación (2026-10-20):

- Un "Tridevanado" con solo dos devanados publicados se modela como transformador de dos
  devanados.
- Un tridevanado cuyo terciario está por debajo de 57,5 kV se modela como HV–MV de dos
  devanados con la impedancia HM.

### S9. Corriente nominal = 100 % de cargabilidad

`ratedCurrent` de PARATEC es el límite al 100 %. Origen: decisión D-4.

### S10. SVC/STATCOM como fuentes de reactiva

Se modelan como `gen` con P = 0, consigna 1,0 pu y Q limitada al rango inductivo/capacitivo de
PARATEC. Origen: decisión D-6 (el usuario pidió revisar qué ofrece pandapower). Los reactores y
condensadores fijos son `shunt` con el signo de pandapower (reactor +Q, condensador −Q).

### S11. Islas

El SIN es un sistema interconectado; una isla en el modelo es un artefacto de datos (línea
excluida, equivalencia faltante). Solo se energiza la componente que contiene la barra de
referencia; las demás quedan fuera de servicio y se reportan en `quality.islands` con sus
barras y los MW de generación y demanda que quedaron fuera. Origen: decisión D-5.

### S12. Imputación por mediana, solo pérdidas de transformadores

Cerca del 25 % de los transformadores no publican pérdidas de cobre o de hierro. Excluirlos
partiría la red, y la resistencia serie tiene poco efecto en el flujo. Por eso
`[imputation].rule = "median"` solo para `vkr_percent`, `pfe_kw`, `vkr_hv_percent`,
`vkr_mv_percent` y `vkr_lv_percent`: mediana de elementos del mismo tipo y nivel del mismo
snapshot. Las impedancias (`vk`) y las tensiones **nunca** se imputan. Cada imputación aparece
en `quality.imputed` con el valor usado. Origen: decisión del proyecto, 2026-10-20, documentada
en `config/defaults.toml`.

### S13. Versiones del despacho

Si XM publica `dDEC<MMDD>_V<n>.txt`, prevalece la de mayor `n`; el archivo sin sufijo es V0.
El caso lleva la advertencia `DISPATCH_REVISED` cuando se usó una revisión. Origen: decisión
D-3.

### S14. Base de tensión por clase

PARATEC mezcla 220 y 230 kV, o 110, 112 y 115 kV, dentro de una misma subestación y entre
extremos de una misma línea. pandapower exige una sola base por barra conectada, así que cada
barra toma la base de su **clase** (115, 230, 13,8 kV) y conserva su tensión declarada
(`nominal_kv`) para los límites en pu y los reportes en kV. Origen: decisión de implementación
para lograr convergencia, 2026-10-20.

### S15. Límites operativos

| Nivel | Tensión | Fuente |
|---|---|---|
| 500 kV | 0,90–1,05 pu | CREG 025/1995, Código de Operación, num. 5.1 |
| STN 220/230 kV | 0,90–1,10 pu | CREG 025/1995, Código de Operación, num. 5.1 |
| STR 57,5–<220 kV | 0,90–1,10 pu | CREG 153/2019, art. 1 (Reglamento de Distribución, num. 6.2.1.1); 57,5 y 66 kV por inferencia |
| Cargabilidad | 100 % | CREG 025/1995, Código de Planeamiento, num. 5.2 |

Origen: research R9.

### S16. Subárea de cada barra (FR-034)

La subárea es el `subAreaName` que PARATEC publica para la subestación ("SubArea Antioquia" →
"Antioquia"). Todas las barras de una subestación comparten su subárea. Si PARATEC no la
publica, la barra queda "sin subárea" y se lista en `quality.buses_without_subarea`; nunca se
asigna por cercanía ni por nombre. En el snapshot incluido, 11 de 1 344 barras quedan sin
subárea: son barras que aparecen en líneas o transformadores con un nombre de subestación que
no está en el listado de subestaciones. Origen: aprobado por el usuario el 2026-10-20.

### S17. Ubicación geográfica de las barras (FR-035)

Cada barra se dibuja en la latitud y longitud que PARATEC publica para su subestación
(`SubstationInfo.latitude`/`longitude`, WGS84). Las barras de una misma subestación comparten
punto y se reparten en un círculo de 3 px de modelo para que no se tapen. Una coordenada fuera
del rectángulo de Colombia se descarta como dato inválido. Una barra sin coordenadas se dibuja
en una franja al oeste y se lista en `quality.buses_without_coordinates`; nunca se ubica por
cercanía ni por nombre. La única excepción es una coordenada curada con fuente (S21). En el snapshot incluido faltan las coordenadas de 6 de 509
subestaciones. El mapa de fondo es solo visual: no interviene en el cálculo ni en el hash del
caso. Origen: el usuario retiró NG-12 el 2026-10-20.

### S18. Lectura de flujos en la topología (FR-036)

La generación y la carga de cada barra son las resultantes del flujo (suma de sus generadores
y de sus cargas servidas; las cargas de islas no energizadas no cuentan, igual que en el
resumen). El flujo de cada rama lleva el signo de pandapower: positivo sale del extremo
`from`/`hv`. La flecha dibujada sigue el sentido de la potencia activa. El balance de una barra
es generación − carga − Σ flujos salientes y vale cero salvo redondeo cuando el flujo
convergió. Las etiquetas aparecen a partir de un acercamiento de 2,5× para no saturar la
vista; el tamaño de barras y ramas crece como zoom^−0,6, más despacio que el acercamiento.
Con un acercamiento menor de 1,6× solo se dibuja el STN (220 kV o más); el STR aparece al
acercarse. Los datos de toda la red se cargan una sola vez, comprimidos con gzip. En la
disposición geográfica las barras están fijas, porque su posición es un dato de PARATEC; en la
lógica se pueden arrastrar.

### S19. Líneas con los dos extremos en la misma subestación

PARATEC publica `sub1 = sub2` en 17 líneas cuyo otro extremo no está en su listado de
subestaciones: plantas (El Quimbo, Guavio subterránea), clientes industriales (Propal, Refisal)
o el extranjero (Pimampiro, Ecuador). Si el nombre de la línea nombra una subestación que sí
está declarada, se usa ese extremo: así las tres líneas Jamondino–Pimampiro 230 kV llegan a
PIMAMPIRO|230. Las 14 restantes no transportan nada, se excluyen del modelo y aparecen en
`quality.not_modeled`. Antes se modelaban como lazos, lo que sumaba a la barra la carga
capacitiva completa de la línea (unos 70 Mvar en Jamondino): un apoyo de reactiva ficticio
que enmascaraba la fragilidad de tensión del suroccidente en el periodo 21. Origen: hallazgo
de la implementación, 2026-10-20.

### S20. Reporte de violaciones y etiquetas (FR-037, FR-036)

El reporte de violaciones separa barras bajo tensión, barras sobre tensión y ramas con
cargabilidad mayor al límite (100 %), ordenadas por desviación respecto al límite aplicado,
que viene de `config/defaults.toml` con su fuente. Una rama cuyos extremos están en subáreas
distintas se reporta "entre subáreas". El reporte se exporta en `violaciones.csv`. Las
etiquetas de barras y ramas de la topología se eligen por el usuario; la elección se guarda
solo en el navegador y no forma parte del caso.

### S21. Coordenadas curadas de subestaciones sin coordenadas en PARATEC (FR-035)

PARATEC declara algunas subestaciones sin latitud ni longitud. La tabla versionada
`data/equivalencias/coordenadas_subestaciones.csv` (`substation`, `lat`, `lon`, `valid_from`,
`valid_to`, `note`) completa esas coordenadas, con la fuente obligatoria en `note`. Solo llena
barras sin coordenada de PARATEC y nunca reemplaza una publicada. Las coordenadas aplicadas
aparecen en `assumptions.coordenadas_curadas` con sus barras y su fuente, y el SHA-256 de la
tabla entra en el hash del caso. Primera fila: Pimampiro (CELEC EP, Ecuador), extremo de los
cuatro circuitos Jamondino–Pimampiro 230 kV, que antes se dibujaba en la franja de barras sin
coordenadas y cruzaba el mapa con líneas falsas. Ubicación tomada de Google Maps (0,4077455;
−77,9471597). Origen: aporte del usuario, 2026-10-22.

### S22. Modo instalado: datos del paquete y carpeta del usuario (FR-040 a FR-046)

Fuera del repositorio, sinsim lee la configuración, las equivalencias, el mapa base y el snapshot
del 2026-10-20 de los recursos de solo lectura del paquete, copiados byte a byte del repositorio
al construirlo. Lo que el usuario genera va a su carpeta de datos (`$SINSIM_HOME` o la convención
del sistema). Como los archivos son idénticos, un mismo escenario produce el mismo `case_id`
instalado o en el repositorio. Una fecha que ya está en el paquete no se vuelve a descargar.
Origen: decisión del usuario, 2026-10-23 (specs/002-paquete-instalable/).

### S23. Reparto de la potencia del generador que sale en una contingencia N-1 (FR-050, FR-051)

Cuando sale una planta, su potencia la absorben los demás generadores despachados según la
referencia distribuida ya existente (FR-015): en proporción a su `slack_weight`, que es su P
programada. No se modela reserva primaria ni AGC. Si sale el generador de la barra de referencia
de ángulo, la referencia pasa a la barra STN con mayor P programada entre las que quedan (el mismo
criterio de reserva de la construcción del caso); con la referencia distribuida, esa elección no
cambia los flujos. Origen: decisión del agente aceptada por el usuario, 2026-10-24
(specs/003-contingencias-n1/).

### S24. El análisis N-1 no se guarda en disco (FR-058, FR-059)

La API guarda cada análisis en memoria mientras sigue encendida; `sinsim n1` lo escribe en CSV.
Volver a abrir la interfaz exige lanzarlo de nuevo. Origen: decisión del agente aceptada por el
usuario, 2026-10-24.

### S25. Los compensadores (SVC/STATCOM) son contingencias y un generador es la planta por barra (FR-049)

El modelo representa los compensadores como generadores con P = 0 que regulan tensión; su salida
se analiza como la de cualquier generador y se etiqueta «compensador». Un generador es la planta
completa en su barra (`RECURSO@BARRA`), no una unidad: sacar una planta grande es más severo que el
N-1 por unidad del sector. Origen: decisión del usuario, 2026-10-24.

### S26. Tensión de referencia del cortocircuito (FR-063)

pandapower calcula con la base por clase del modelo (S14: 230 kV para las barras de 220 kV, 115 para
las de 110). IEC 60909 define U_n como la tensión nominal del sistema, así que Ikss y Sk se refieren
a la tensión nominal que PARATEC publica para cada barra: `Ikss · U_n/U_base` y
`Sk · (U_n/U_base)²`; Rk y Xk en Ω no cambian. En una barra de 220 kV modelada en base 230 la
corriente baja 4,3 % y la potencia 8,5 %. La tabla muestra las dos tensiones. Origen: decisión del
agente, 2026-10-25 (specs/004-cortocircuito/).

### S27. Reactancia subtransitoria no saturada y ceros como faltantes (FR-064)

La reactancia de cada unidad es la subtransitoria **no saturada** (`xd2` en hidráulicas,
`xdSubtrans` en térmicas), que es la que pide IEC 60909; la saturada se conserva como dato
informativo. Una resistencia de armadura o una reactancia publicadas como 0 son físicamente
imposibles y se tratan como no publicadas: entran a la imputación con su método visible. Origen:
decisión del agente, 2026-10-25.

### S28. Resistencia de armadura no publicada (FR-064)

Si PARATEC no publica `ra` (o publica 0), la resistencia subtransitoria se toma de la relación
R_G/X''_d de IEC 60909-0 §6.6.1: 0,05 para máquinas de 100 MVA o más y más de 1 kV; 0,07 para
menos de 100 MVA y más de 1 kV; 0,15 hasta 1 kV. Los tres valores están en `[shortcircuit]` de
`config/defaults.toml` con su cita. Afecta poco a Ikss y bastante a X/R, que es lo que consume un
equivalente de red. Origen: decisión del agente, 2026-10-25.

### S29. Los enlaces internacionales no aportan corriente de cortocircuito (FR-067)

No hay fuente pública de la potencia de cortocircuito de las interconexiones con Ecuador
(Jamondino 230, Panamericana 138) ni con Venezuela, y la constitución prohíbe inventarla. El
usuario aceptó modelarlas sin aporte, sabiendo que la corriente queda subestimada en Nariño y Norte
de Santander. Se listan en la calidad como `sc_zero_sources`. Si aparece una fuente, la
configuración admite potencia de cortocircuito y R/X por enlace con su cita. Origen: decisión del
usuario, 2026-10-25.

### S30. Plantas solares y eólicas como fuentes de convertidor (FR-066)

Aportan k = 1,0 veces su corriente nominal, el tratamiento de generadores de convertidor pleno de
IEC 60909-0:2016 §6.9. `k` es configurable y citado. Origen: decisión del agente, 2026-10-25.

### S31. Unidades sin transformador elevador casado (FR-065)

PARATEC no vincula las unidades con su transformador elevador. La tabla
`data/equivalencias/elevadores.csv` los casa por subestación, clase de tensión, nombre de planta o
marca `G<n>`/`U<n>` y tensión de baja; la propuesta inicial (207 de 408 unidades en el snapshot del
2026-10-24) está marcada `curated = false`. Una unidad casada entra tras su elevador como unidad de
central (§6.7); una unidad sin casar entra directamente en su barra de alta, a la tensión de esa
barra, despreciando la reactancia del elevador: sobreestima la corriente cerca de esas plantas y
queda listada en `generators_without_step_up` para curar la tabla. Origen: decisión del usuario,
2026-10-25.

## Lo que NO es un supuesto sino una limitación conocida

- Las tablas `recursos_despacho.csv` y `nodos_demanda.csv` del snapshot incluido son propuestas
  heurísticas **sin curar** (tarea T064). Mientras no se curen, parte de la demanda queda sin
  ubicar y el balance lo muestra.
- El resultado describe el **despacho programado**, nunca el estado real del SIN (R-10). Cada
  caso lleva la advertencia `PROGRAM_NOT_REAL_STATE`.
