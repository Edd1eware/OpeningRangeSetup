# Propuesta independiente Codex V2 — score mecánico continuo defensa–aceptación

Fecha: 2026-07-25  
Autor: Codex  
Fase: V2-1  
Estado de información al redactar: `OUTCOME_BLIND / MAPPING_CLOSED / CLAUDE_PROPOSAL_UNREAD`

## 0. Alcance y compromisos

Esta propuesta se construyó sin leer `mbo_continuous_v2/claude_sealed/`, sin abrir
mapping, outcomes ni `admin_sealed`, y sin usar etiquetas AMD como target. No usa
MFE, MAE, TP, SL, PnL, ATAS, datos descargados adicionales ni optimización contra
outcomes.

El objeto es un número continuo acotado:

- `S_defensa_aceptacion < 0`: predominio mecánico de defensa/absorción;
- `S_defensa_aceptacion > 0`: predominio mecánico de aceptación/breakout;
- valores próximos a cero: balance o sensibilidad, no una tercera clase.

La calidad de la medición se publica por separado como `Q_cobertura`.

## 1. Convenciones canónicas y componentes mecánicos

### 1.1 Definiciones comunes

- `t0 = strict_feature_cutoff`.
- `T = 5.000 s`.
- `t1 = t0 + T = t_decision`.
- `sigma = +1` para burst agresor BUY y `sigma = -1` para burst agresor SELL.
  `sigma` se obtiene de la secuencia causal del burst, nunca de AMD ni de outcomes.
- `delta_p`: tick size del instrumento, en unidades de precio.
- `L0`: precio atacado por el burst, en unidades de precio.
- `Lk = L0 + sigma*k*delta_p`, para `k=0,1,2`: escalera defensora canónica.
- `Qk0`: cantidad defensora mostrada en `Lk` en el último estado completo anterior
  a `t0`; unidades: contratos. `Q0` es `Qk0` para `k=0`.
- `p_tr(t)`: trailing touch que demuestra que el mercado quedó al otro lado de
  `L0`: best bid para BUY y best ask para SELL.
- `x(t) = sigma*(p_tr(t)-L0)/delta_p`; unidades: ticks canónicos.
- Estado de aceptación: `A(t)=1[x(t)>=1]`.
- Estado de defensa/no aceptación: `D(t)=1[x(t)<=0]`.

Como `p_tr` está en la rejilla de ticks, los dos estados son exhaustivos cuando el
libro es válido. Un intervalo inválido no se convierte en defensa: queda ausente y
reduce `Q_cobertura`.

Todos los integrales siguientes usan el camino piecewise-constant posterior a la
aplicación atómica de paquetes completos. `Omega` es el subconjunto temporal válido
de `[t0,t1)` y `T_v = |Omega|`.

### 1.2 Bloque K — cinemática de aceptación

**K1. Ocupación firmada (`K_ocupacion`)**

```text
r_K1 = (integral_Omega A(t)dt - integral_Omega D(t)dt) / T_v
```

Unidades: adimensional; rango `[-1,1]`. Positivo significa más tiempo aceptado al
otro lado de `L0`.

**K2. Desplazamiento terminal (`K_terminal`)**

```text
r_K2 = x(t1-)
```

Unidades: ticks canónicos. Se usa el último estado completo estrictamente anterior
a `t1`.

**K3. Área media firmada (`K_area`)**

```text
r_K3 = (1/T_v) * integral_Omega x(t)dt
```

Unidades: ticks canónicos. Es la integral ticks·segundo dividida por segundos.

**K4. Latencia a primera aceptación durable (`K_latencia_durable`)**

Se congela `h = 0.250 s`. `tau_A` es el inicio, medido desde `t0`, del primer
intervalo válido continuo de duración al menos `h` con `A(t)=1`.

```text
r_K4 = 1 - tau_A/(T-h), si existe
r_K4 = -1, si no existe
```

Unidades: adimensional; rango `[-1,1]`. Una aceptación durable inmediata se acerca
a `+1`; una aceptación durable tardía se acerca a cero; su ausencia vale `-1`. Un
hueco de datos rompe el intervalo durable.

**K5. Hold terminal firmado (`K_hold_terminal`)**

Sea `s_T=+1` si el estado terminal es aceptación y `s_T=-1` si es defensa. Sea
`ell_T` la duración del último run continuo válido del mismo estado que llega a
`t1`.

```text
r_K5 = s_T * ell_T/T
```

Unidades: adimensional; rango `[-1,1]`.

**K6. Coherencia de cruces/reclaims (`K_coherencia_cruces`)**

`N_cross` cuenta cambios `D→A` y `A→D` dentro de intervalos válidos. Un hueco no
crea un cruce. Se guardan además, como diagnósticos no ponderados, `N_DA`,
`N_AD` y el timestamp del último `A→D` (reclaim).

```text
r_K6 = s_T/(1+N_cross)
```

Unidades: adimensional; rango `[-1,1]`. Premia un estado terminal coherente y
reduce magnitud cuando hay alternancia repetida.

### 1.3 Bloque B — mecánica del libro defensor

Solo se usan mensajes MBO de la misma fuente y cantidades en contratos.

**B1. Consumo ejecutado de L0 (`B_fill_L0_Q0`)**

`E_L0` es la cantidad pasiva defensora ejecutada en `L0` por trades alineados con
`sigma`.

```text
r_B1 = E_L0/Q0
```

Unidades: contratos/contratos, adimensional. Es presión causal de consumo y por eso
su signo de aceptación es positivo; por sí sola no afirma breakout.

**B2. Refill rápido posterior al fill (`B_refill_100ms_Q0`)**

Cada fill defensor en `L0` abre un déficit FIFO `(timestamp, cantidad)`. Una orden
nueva o incremento de tamaño defensor posterior en `L0` rellena ese déficit hasta
`min(add, deficit)` si llega en `0 < latencia <= 100 ms`. El déficit no emparejado
expira a los `100 ms`. Cantidad sobreviviente, reducción y cancelación no cuentan
como refill. Para cada emparejamiento `m`, `q_m` es la cantidad y `l_m` la latencia.

```text
r_B2 = - sum_m q_m*(1-l_m/0.100s)/Q0
```

Unidades: adimensional. Refill más grande y rápido aporta más evidencia negativa
de defensa. Sin refill válido, `r_B2=0`.

**B3. Cesión neta por cancels menos adds (`B_cesion_L0_L2`)**

Para `k=0,1,2`, `C_k` y `A_k` son, respectivamente, contratos cancelados/reducidos
y añadidos/incrementados en el lado defensor y precio fijo `Lk`. Las ejecuciones no
son cancelaciones; en `L0`, `A_0` excluye la cantidad ya emparejada como refill en
B2 para no contarla dos veces. Se congelan pesos `w=(1, 0.5, 0.25)` y
`Q_L=sum_k w_k*Qk0`.

```text
r_B3 = sum_k w_k*(C_k-A_k)/Q_L
```

Unidades: adimensional. Retirar más de lo que se añade es aceptación positiva;
añadir más es defensa negativa.

**B4. Supervivencia de la cola inicial (`B_supervivencia_inicial`)**

Para cada order-id defensor presente en `L0:L2` a `t0`, `q_i0` es su cantidad
inicial y `q_i1` la cantidad del mismo id que permanece al mismo precio a `t1-`.

```text
r_B4 = - sum_i w_level(i)*min(q_i0,q_i1) / Q_L
```

Unidades: adimensional; rango `[-1,0]`. Una orden cancelada y recreada con otro id
no sobrevive. Mayor supervivencia de la cola es evidencia de defensa y aporta
signo negativo al score.

**B5. Migración del centro de profundidad (`B_migracion_depth`)**

Con `D_k(t)` igual a la profundidad defensora mostrada en el precio fijo `Lk`:

```text
mu(t) = sum_k k*D_k(t) / sum_k D_k(t)
beta_mu = integral_Omega_mu (t-t_bar)*(mu(t)-mu_bar)dt
          / integral_Omega_mu (t-t_bar)^2 dt
r_B5 = beta_mu
```

`Omega_mu` contiene únicamente instantes con profundidad total positiva y libro
válido; `t_bar` y `mu_bar` son sus medias ponderadas por duración. Unidades:
niveles/segundo. Pendiente positiva significa que la liquidez defensora migra lejos
de `L0`, en dirección de aceptación.

### 1.4 Bloque F — tape alineado frente a counterflow

`V_+` es el volumen agresor alineado con `sigma` y `V_-` el volumen agresor
contrario, clasificados por los mensajes MBO/trades de la misma fuente.

**F1. Imbalance de tape (`F_imbalance`)**

```text
r_F1 = (V_+ - V_-)/(V_+ + V_-)
```

Unidades: adimensional; rango `[-1,1]`. Si no hay trades, se define `r_F1=0` y no
se trata como faltante si el stream es íntegro.

**F2. Persistencia acumulada de flujo (`F_area_flujo`)**

```text
G(t) = (V_+(t0,t] - V_-(t0,t]) / Q0
r_F2 = (1/T_v) * integral_Omega G(t)dt
```

Unidades: adimensional. Flujo alineado temprano y sostenido es positivo; counterflow
temprano y sostenido es negativo.

## 2. Orientación de signo

Todas las transformaciones de precio, quote y tape pasan primero por `sigma`.
Por construcción:

- subida posterior a un BUY burst y bajada posterior a un SELL burst son positivas;
- refill, adds y supervivencia defensora son negativas;
- retirada/migración defensora y tape alineado son positivos.

No se permite invertir signos después de ver estabilidad u outcomes. Como gate
unitario previo, una secuencia sintética BUY y su espejo SELL deben producir los
mismos `r_j`, `S_defensa_aceptacion` y `Q_cobertura` dentro de `1e-12`.

## 3. Normalización outcome-blind y faltantes

### 3.1 Escalas

No se resta la mediana: el cero mecánico de cada componente debe conservarse. Para
cada componente no acotado `j`, se calcula sobre inputs válidos de discovery
2022–2023, sin outcomes:

```text
d_j = percentil_75(|r_ij|)
s_j = max(d_j, floor_j)
u_ij = tanh(r_ij/s_j)
```

Floors congelados:

| Componente | `floor_j` |
|---|---:|
| K2 | 1 tick |
| K3 | 0.25 tick |
| B1 | 0.25 |
| B2 | 0.25 |
| B3 | 0.25 |
| B5 | 0.10 niveles/s |
| F2 | 0.25 |

Para K1, K4, K5, K6, B4 y F1, ya acotados, `u_ij=r_ij`. Todo `u` se limita
aritméticamente a `[-1,1]`. Las escalas se guardan y hashean; se reutilizan sin
reestimación en perturbaciones, discovery-outcome y 2024.

No se usa ningún dato de 2024 para centrar, escalar, elegir floors o decidir
componentes. Si un componente tiene menos de 20 observaciones válidas en las 69
ventanas discovery, su escala usa solo el floor correspondiente y se registra la
incidencia; no se consulta outcome. Pseudoventanas, si la implementación necesita
pruebas/calibración de software, se limitan a los seis bloques no solapados de 5 s
en `[t0-30s,t0)` de cada sesión 2022–2023. Nunca entran como filas del endpoint ni
modifican signos, pesos o floors.

### 3.2 Faltantes

- No hay imputación por cero, mediana ni vecino.
- Un intervalo inválido se excluye del integral y reduce el `q_j` correspondiente.
- Un cero observado (cero trades, cero refill, cero cancels) es dato válido.
- Un componente no usable se omite del promedio de su bloque, pero el caso solo
  entra al endpoint si pasa la cobertura mínima de la sección 6.
- La ausencia de datos jamás genera una señal de defensa o aceptación.

Son fallos duros: snapshot inicial inválido; instrumento incorrecto; `Q0<=0` o
`Q_L<=0`; `F_MAYBE_BAD_BOOK`; retroceso en secuencia incremental; paquete incompleto
usado; uso de eventos `F_LAST>=t1`; o mezcla de proveedores. Ante cualquiera,
`S=NA`, `Q_cobertura=0`.

## 4. Ventana temporal y regla exacta `F_LAST`

La ventana de features es `[t0,t1)=[strict_feature_cutoff, t0+5.000s)`.

1. El estado inicial se forma únicamente con snapshots y paquetes completos cuyo
   `ts_recv(F_LAST) < t0`.
2. Un paquete incremental se vuelve observable y se aplica atómicamente en
   `tau_pkg = ts_recv(F_LAST)`.
3. Entran paquetes con `t0 <= tau_pkg < t1`.
4. Si `tau_pkg >= t1`, se excluye el paquete completo aunque alguno de sus mensajes
   tenga timestamp anterior.
5. Nunca se aplica un prefijo de paquete. Para timestamps empatados se ordena por
   `ts_recv(F_LAST)`, secuencia incremental y posición original dentro del paquete;
   el estado solo cambia después del `F_LAST`.
6. Ningún evento posterior a `t1` puede reparar, completar o reclasificar un
   paquete de la ventana.

## 5. Fórmula de `S_defensa_aceptacion`

Para cada bloque, se promedian con pesos iguales los `u_j` usables:

```text
S_K = mean(u_K1,...,u_K6 usables)
S_B = mean(u_B1,...,u_B5 usables)
S_F = mean(u_F1,u_F2 usables)

S_defensa_aceptacion = (S_K + S_B + S_F)/3
```

Los tres pilares —cinemática, libro y tape— pesan exactamente `1/3`; dentro de cada
pilar los componentes pesan igual. No hay coeficientes aprendidos. Rango final:
`[-1,1]`. La fórmula solo se emite si se cumple la cobertura mínima; de lo contrario
se conserva `S=NA` y se reporta `Q_cobertura`.

## 6. `Q_cobertura` separada y cobertura mínima

Para componentes de camino, `q_j` es la fracción de los 5 s con libro válido. Para
K2/K5 es además necesario un estado terminal válido. Para B5, `q_B5` es la fracción
con libro válido y `sum_k D_k(t)>0`. Para componentes de eventos/tape, `q_j=1` si
snapshot, identidad de órdenes, secuencias y todos los paquetes hasta `t1` pasan
integridad; si no, `q_j=0`. Cada `q_j` está en `[0,1]`.

```text
Q_K = mean(q_K1,...,q_K6)
Q_B = mean(q_B1,...,q_B5)
Q_F = mean(q_F1,q_F2)
Q_cobertura = (Q_K + Q_B + Q_F)/3
```

Un caso es **evaluable**, sin crear clase alguna, solo si:

- no existe fallo duro;
- `Q_cobertura >= 0.90`;
- `Q_K>=0.80`, `Q_B>=0.80`, `Q_F>=0.80`;
- K1, K2, K3, K5 y F1 son usables;
- al menos 5/6 componentes K, 4/5 componentes B y 2/2 componentes F son usables.

La extracción discovery debe conservar al menos `56/69` casos evaluables; menos de
56 es `FAIL_COVERAGE` y prohíbe abrir outcomes.

## 7. Banda neutra numérica

Se congela:

```text
epsilon_neutro = 0.15 puntos de S
banda = [-0.15,+0.15]
```

La banda es una tolerancia de interpretación/estabilidad, no una clase C, no
produce etiqueta y no elimina filas. Todos los scores evaluables, incluidos los de
la banda, entran al endpoint continuo discovery.

## 8. Perturbaciones outcome-blind y gates congelables

Se ejecutan solo sobre inputs discovery 2022–2023, reutilizando las escalas
baseline sin recalcularlas:

- `P0`: cálculo event-time exacto, baseline.
- `P1`: cuantización de `tau_pkg` a 1 ms, round-half-to-even, preservando orden de
  secuencia y atomicidad.
- `P2`: integrales de camino mediante grid left-continuous de 10 ms, fase 0 ms;
  conteos y cantidades MBO permanecen exactos.
- `P3`: mismo grid de 10 ms con fase determinista +5 ms.
- `P4`: permutación determinista de filas por SHA-256 del identificador de mensaje,
  seguida de reagrupación por paquete, secuencia y `F_LAST`; debe reconstruir la
  misma semántica.
- `P5`: redondeo previo a normalización: precios/áreas a 0.01 tick, tiempos a 1 ms,
  ratios a `1e-4` y slopes a `1e-3 niveles/s`.
- `MIRROR`: espejo sintético BUY↔SELL de cada secuencia, sin outcomes.

Para cada `P1:P5`, sobre la intersección de casos evaluables con P0:

1. Spearman de rangos `rho(S_P0,S_Pk) >= 0.98`; si es indefinido, FAIL.
2. `median(|S_Pk-S_P0|) <= 0.05`.
3. `percentil_95(|S_Pk-S_P0|) <= 0.15`.
4. Flip fuerte definido solo como `S_P0>+0.15 y S_Pk<-0.15`, o viceversa:
   máximo un caso **y** tasa `<=2.0%`.
5. Retención de evaluables `>=95%` de P0.
6. `percentil_95(|Q_Pk-Q_P0|) <= 0.05`.

Además:

- P0 debe tener al menos 56/69 casos evaluables.
- `MIRROR` exige `max|delta S|<=1e-12`, `max|delta Q|<=1e-12` y cero cambios en
  usabilidad.

El gate conjunto es PASS únicamente si todas las condiciones pasan para todas las
perturbaciones y el espejo. Un solo fallo produce `V2_STABILITY_FAIL`: no se abren
outcomes y no se añaden perturbaciones retrospectivas para buscar un PASS casual.

## 9. Único endpoint discovery continuo

Se congela un solo endpoint: correlación de rangos de Spearman entre el score y un
desplazamiento terminal futuro a horizonte fijo. No se usan extremos del camino.

Con `H=60.000 s`:

```text
m1 = midpoint del último BBO completo anterior a t1
mH = midpoint del último BBO completo en o antes de t1+H,
     con antigüedad máxima de 1.000 s
OR_ticks = (OR_high-OR_low)/delta_p, con OR íntegramente anterior a t0
Y_60 = sigma * [(mH-m1)/delta_p] / max(OR_ticks,1)
endpoint = rho_Spearman(S_defensa_aceptacion, Y_60)
```

La definición del Opening Range es la ya congelada en el proyecto; no se cambia
después de ver outcomes. `Y_60` es desplazamiento terminal de midpoint, no MFE,
MAE, TP, SL ni PnL. Solo puede derivarse de datos ya existentes y sellados; falta de
midpoint/OR se marca ausente y no autoriza descargas ni sustitución de horizonte.

Reglas:

- se incluyen todos los casos con score evaluable y `Y_60` válido, sin filtrar por
  banda neutra ni por cola;
- se requieren al menos 56 casos; de lo contrario discovery es FAIL;
- ties usan rango promedio;
- se hacen 10,000 remuestreos bootstrap por sesión, con seed igual a los primeros
  64 bits del SHA-256 del preregistro convergente;
- IC95 bilateral percentil sobre `rho`.

Éxito discovery, sin grados de libertad:

```text
rho_hat >= 0.25
AND limite_inferior_IC95 > 0
```

No hay endpoint alternativo, contraste de colas, selección de horizonte, ajuste de
pesos ni segunda apertura si falla.

## 10. Condición exacta para abrir 2024

2024 solo puede abrirse si, en este orden, queda evidencia auditable de:

1. preregistro convergente y código de extracción hasheados antes de cualquier
   outcome;
2. mapping/outcomes/2024 intactos durante diseño, normalización y estabilidad;
3. escalas 2022–2023, signos, componentes, pesos, cobertura, banda, perturbaciones
   y endpoint congelados;
4. integridad causal PASS y gate conjunto de estabilidad PASS con al menos 56/69
   casos discovery evaluables;
5. una única apertura de discovery 2022–2023;
6. al menos 56 pares válidos `(S,Y_60)` y éxito exacto
   `rho_hat>=0.25 AND IC95_low>0`;
7. cero cambios posteriores a esa apertura en fórmula, código, escalas, exclusiones,
   cobertura, endpoint, horizonte o seed.

Si cualquiera de los siete puntos falla, 2024 permanece cerrado. Si todos pasan,
se autoriza una sola apertura confirmatoria de 2024 aplicando sin recalibración el
mismo extractor, escalas, score, cobertura y endpoint. 2025–2026 permanece cerrado.

`INFORMATION_STATUS=CODEX_INDEPENDENT_V2_PROPOSAL_SEALED_NO_OUTCOME`
