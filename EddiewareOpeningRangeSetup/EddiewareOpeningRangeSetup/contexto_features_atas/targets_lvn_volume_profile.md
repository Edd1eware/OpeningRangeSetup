# Targets — LVN Volume Profile Research → Strategy

Fecha de congelación inicial: **2026-07-08**  
Instrumento inicial: **NQ**  
Estado: **investigación de eventos; todavía NO es estrategia**

---

## 1. Pregunta principal del test

Cuando el primer minuto de RTH (`09:30:00–09:31:00 ET`) crea uno o más LVN, ¿qué ocurre cuando
el precio los retestea antes de `09:40:00 ET`?

El test debe determinar:

1. con qué frecuencia aparece al menos un LVN;
2. cuántos LVN aparecen por sesión y por mes;
3. qué porcentaje recibe retest antes de 09:40;
4. si el retest tiene poder predictivo medido mediante MFE, MAE y resultados TP/SL;
5. si el resultado cambia según el perfil contextual 08:30–09:30 sea D, P, b, double o trend;
6. si las probabilidades continuas de forma contienen más información que la etiqueta rígida;
7. qué bracket ofrece mejor expectativa sin destruir la frecuencia;
8. si el comportamiento se mantiene entre DST 2025 y DST 2026.

El objetivo inicial es **descubrir y medir un evento**, no producir señales ni optimizar PnL.

---

## 2. Hipótesis registradas antes de ver resultados

### H1 — Existencia de reacción

Los LVN creados durante 09:30–09:31 pueden actuar como zonas de transición/rechazo cuando el precio
los vuelve a tocar antes de 09:40.

### H2 — Forma P

Un perfil contextual P representa masa de volumen superior con cola inferior y debería aportar
contexto tendencial alcista. Se espera estudiar especialmente retests con reacción LONG.

### H3 — Forma b

Un perfil contextual b representa masa inferior con cola superior y debería aportar contexto
tendencial bajista. Se espera estudiar especialmente retests con reacción SHORT.

### H4 — Forma D como control

Un perfil D es equilibrado/simétrico y no ofrece dirección tendencial clara. Los días D no se
eliminan: forman la cohorte de control para comprobar si P/b realmente agregan información.

### H5 — Probabilidades continuas

`prob_P`, `prob_b`, `prob_D`, `prob_double`, `prob_trend_up`, `prob_trend_down` y `prob_unknown`
pueden ser más útiles que una clasificación rígida. Son similitudes matemáticas con prototipos;
no son probabilidades calibradas de ganar.

### H6 — Procedencia del retest (degradada a variable de contexto, 2026-07-08)

La dirección hipotética por procedencia (desde arriba → LONG; desde abajo → SHORT) ya NO gobierna
el outcome. Se conserva como columna `approach_hypothetical_side` para comparar cohortes.
Procedencia no observable → `UNKNOWN_DIRECTION`, conservada en el dataset.

### H7 — Aceptación/rechazo de valor en el LVN (IMPLEMENTADA 2026-07-08 — versión estructural)

Teoría de aceptación/rechazo de valor aplicada al retest del LVN. **Esta es ahora la regla
oficial de dirección del motor:**

- **Aceptación:** tras el toque, el `close` atraviesa TODA la zona LVN
  (`[low_price, high_price]` ± tolerancia) y cruza el borde lejano +
  `resolution_confirm_ticks` → el nivel no frena; **continuación** en la dirección de
  aproximación (desde arriba → SHORT, desde abajo → LONG).
- **Rechazo:** el precio frena en la zona y el `close` regresa cruzando el borde cercano +
  `resolution_confirm_ticks` → el nivel actúa como rechazo; **reversión**
  (desde arriba → LONG, desde abajo → SHORT).
- **Sin confirmación antes de 09:40** → `UNRESOLVED`, outcome `UNKNOWN_DIRECTION`, no se borra.

Causalidad: la dirección se asigna en el instante de la confirmación; el outcome empieza ahí y se
mide desde `entry_price` (= close confirmante), nunca desde el toque ni desde el precio del LVN.
En barras sin orden intrabar el outcome empieza en la barra siguiente a la confirmación.

La componente de **velocidad** de H7 sigue siendo captura continua, sin clasificar:

- velocidad de aproximación al LVN (§5);
- `zone_speed_ticks_per_second` (toque → confirmación) y `deceleration_ratio`
  (velocidad_zona / velocidad_aproximación);
- tiempo de permanencia en zona;
- `lvn_interaction` (`ACCEPTANCE`/`REJECTION`/`UNRESOLVED`) y `trade_logic`
  (`CONTINUATION`/`REVERSAL`).

Los umbrales de "normal", "rápida" y "alta" NO se definen en captura: se derivan después,
era-blind, sobre las distribuciones observadas. Cualquier filtro por velocidad se especifica
recién en Fase B, nunca antes.

Ninguna hipótesis autoriza filtrar observaciones durante la captura.

---

## 3. Ventanas causales congeladas

| Componente | Ventana ET | Regla |
|---|---:|---|
| Perfil contextual | `[08:30:00, 09:30:00)` | POC, VAH, VAL, HVN/LVN, forma y probabilidades |
| Perfil LVN | `[09:30:00, 09:31:00)` | única información permitida para crear LVN del test |
| Revelación visual | `09:31:00` | la línea verde empieza aquí, nunca retroactivamente |
| Retest | `[09:31:00, 09:40:00)` | registrar todos los episodios de toque |
| Outcome | retest → `<09:40:00` | MFE, MAE, tiempos y brackets |

No se permite usar datos posteriores a 09:31 para crear, mover o eliminar un LVN.

---

## 4. Definición inicial congelada de LVN

Para cada precio `p` del perfil 09:30–09:31:

1. deben existir `lvn_neighbor_levels` niveles a ambos lados;
2. `volume[p]` debe ser menor que el promedio de vecinos inferiores;
3. `volume[p]` debe ser menor que el promedio de vecinos superiores;
4. `volume[p] / min(left_mean, right_mean)` debe quedar bajo
   `lvn_max_percent_of_neighbors`;
5. debe cumplir `min_lvn_volume`;
6. debe quedar bajo `max_lvn_volume_percent_of_poc`;
7. el perfil debe superar `min_total_volume_at_profile`.

Los candidatos adyacentes se agrupan en un nodo. El precio representativo es el nivel con menor
volumen. El indicador muestra solo el LVN de mayor calidad para mantener un chart limpio; el motor
de investigación guarda **todos** los nodos y todos los rechazos con su razón.

Parámetros iniciales:

| Parámetro | Valor inicial |
|---|---:|
| `tick_size` | 0.25 |
| `lvn_neighbor_levels` | 2 |
| `lvn_max_percent_of_neighbors` | 0.50 |
| `min_total_volume_at_profile` | 1 |
| `min_lvn_volume` | 1 |
| `max_lvn_volume_percent_of_poc` | 0.50 |
| `retest_tolerance_ticks` | 0 |
| `retest_rearm_ticks` | 1 |
| `resolution_confirm_ticks` | 1 |

Estos valores no deben optimizarse con la misma muestra usada para evaluar el resultado.

---

## 5. Variables que debe conservar el test

### Perfil contextual y perfil del primer minuto

- POC, VAH, VAL, high, low y width;
- total volume, bid, ask y delta;
- HVN/LVN con precio, volumen, anchura, profundidad y distancias;
- upper/lower volume y ratio;
- centro de masa, skewness, kurtosis y entropía;
- distribution count y estructura multimodal;
- profile shape y vector completo de probabilidades.

### Cada retest

- fecha, símbolo, LVN ID, precio y número de retest;
- hora, segundos desde 09:31 y tiempo dentro de zona;
- desde arriba/abajo y dirección hipotética por procedencia (`approach_hypothetical_side`);
- interacción de valor: `lvn_interaction`, `trade_logic`, dirección resuelta,
  `entry_price`, `entry_time_et`, `seconds_touch_to_entry`, bordes de zona,
  `zone_speed_ticks_per_second` y `deceleration_ratio`;
- distancia recorrida desde open y velocidad de aproximación;
- volumen, bid, ask y delta en el LVN;
- imbalances, big trades, icebergs y absorciones cuando estén disponibles;
- VWAP, EMA, pendientes y distancias;
- distancias a POC/VAH/VAL contextual, POC del minuto, open y OR high/low;
- gap, ATR, volatilidad, premarket range y métricas OR.

### Outcome

- max up/down, MFE y MAE en ticks;
- tiempo a MFE/MAE;
- hits ±20, ±40, ±60 y ±80 ticks;
- resultado 20/20, 40/40, 60/60 y 80/80;
- R realizado por bracket;
- MFE/MAE ratio;
- precisión temporal y política de inicio del outcome.

---

## 6. Tratamiento de precisión y ambigüedad

| Input | Tratamiento |
|---|---|
| Tick ordenado | outcome desde el tick exacto del toque |
| Footprint/bar sin orden intrabar | outcome desde la siguiente barra, política conservadora |
| TP y SL en la misma barra | `AMBIGUOUS`; nunca se fuerza TP o SL |
| Dato opcional ausente | `NaN` + columna `*_available`; nunca se inventa cero |

El chart usado para la captura ATAS debe ser **NQ de 1 minuto**. Un chart M5 mezclaría cinco minutos
dentro del perfil 09:30–09:31 y dejaría el experimento inválido.

---

## 7. Métricas objetivo del reporte

### Frecuencia

- sesiones procesadas;
- días con LVN / sesiones;
- LVN por día;
- retests por LVN;
- días con LVN sin retest;
- días, nodos y eventos por mes;
- frecuencia por forma D/P/b y por año.

### Edge

- `wr_X_X_all = TP / todos los eventos`;
- `wr_X_X_resolved = TP / (TP + SL)`;
- promedio y mediana de R realizado;
- profit factor en R cuando se formalice el backtest de trades;
- MFE y MAE promedio/mediana;
- distribución de MFE/MAE, no solo promedios;
- intervalo de confianza del WR y EV;
- resultados por P, b, D y buckets de probabilidades;
- resultados por interacción (`ACCEPTANCE` vs `REJECTION` vs `UNRESOLVED`) y por
  interacción × forma contextual;
- resultados por retest desde arriba/abajo y primer/subsecuente retest.

Para brackets 1:1, el WR de equilibrio bruto es 50%; el equilibrio neto debe incluir comisión y
slippage antes de aprobar una estrategia.

---

## 8. Entregables de la corrida

### Captura

`lvn_OR_strategy_replay.py` recorre Market Replay X10 08:29–09:42 y produce:

- `lvn_research_raw_YYYY-MM-DD_NY.csv`;
- `lvn_research_done_YYYY-MM-DD.txt`;
- manifest JSON con fechas exitosas, reutilizadas y fallidas.

No usa `pending_strategy_signal.txt`, A+ Speed ni resultados de la estrategia.

### Reporte

`detect_lvn_retest_events.py` produce Excel y CSV:

- `Summary`;
- `Daily_Profile`;
- `LVN_Profile`;
- `LVN_Events`;
- `No_Retest`;
- `Debug`.

Reglas del runner (2026-07-08):

- solo días hábiles de trading: excluye automáticamente feriados NYSE/CME
  (New Year, MLK, Presidents, Good Friday, Memorial, Juneteenth, July 4, Labor,
  Thanksgiving, Christmas, con observancia sáb→vie / dom→lun); `--include-holidays`
  desactiva el filtro;
- **default = preview (`prepare-only`)**: sin `--run` el script NUNCA abre Replay;
- la regla Replay X1/X10 no se toca: el script fija X10 solo, ventana 08:29–09:42.

Comando principal (captura real):

```powershell
python -u lvn_OR_strategy_replay.py --all --run `
  --from-date 2025-03-10 `
  --to-date 2026-07-06
```

Vista previa sin iniciar ATAS (default, no requiere flag):

```powershell
python -u lvn_OR_strategy_replay.py --all `
  --from-date 2025-03-10 `
  --to-date 2026-07-06
```

Generar de nuevo el reporte usando capturas existentes:

```powershell
python -u lvn_OR_strategy_replay.py --all `
  --from-date 2025-03-10 `
  --to-date 2026-07-06 `
  --report-only
```

---

## 9. Targets de calidad de datos antes de analizar edge

No se interpreta WR/R:R hasta cumplir:

1. capturas completas para todas las sesiones objetivo o lista explícita de fallas;
2. ventana cubierta hasta 09:40;
3. timestamps correctamente convertidos a ET/DST;
4. precios alineados al tick 0.25;
5. footprint real disponible; fallback a close identificado por separado;
6. cero LVN creados con datos posteriores a 09:31;
7. cero filas eliminadas silenciosamente;
8. `Debug` conserva cada rechazo y razón;
9. resultados `AMBIGUOUS` reportados, no resueltos por suposición;
10. paridad del LVN visual verde contra el LVN calculado offline en fechas de muestra.

Target operativo sugerido: al menos 95% de las sesiones objetivo capturadas correctamente antes de
leer resultados. Las fechas restantes deben reintentarse y mantenerse visibles en el manifest.

---

## 10. Plan de ejecución inmediato

### Paso 0 — Preflight

1. Reiniciar ATAS para cargar la DLL nueva.
2. Usar chart **NQ 1 minuto**.
3. Aplicar `Volume_Profile_Eddieware` con `Enable LVN Research Export = true`.
4. Mantener Replay visible y accesible.
5. No es necesario iniciar Execution Manager.
6. Confirmar que `python 06_run_strategy_replay.py --help` o el runner LVN puede cargar
   `pywinauto/pywin32`; si `win32ui` falla, reparar esa dependencia antes de un recorrido largo.

### Paso 1 — Pilot de 3–5 fechas

```powershell
python -u lvn_OR_strategy_replay.py --run --dates 2025-03-10 2025-03-11 2026-07-02
```

Validar manualmente:

- CSV desde 08:30 hasta 09:39;
- línea verde revelada a 09:31;
- POC/VAH/VAL y shape razonables;
- Excel con eventos y días sin retest;
- ninguna dependencia de trades de la estrategia.

### Paso 2 — Temporada completa DST

Ejecutar el comando principal. Reintentar únicamente fechas fallidas usando `--dates ... --run --force`.

### Paso 3 — Auditoría causal

Seleccionar fechas P, b, D, con retest, sin retest y ambiguas. Comparar chart, raw CSV y workbook.

### Paso 4 — Estadística descriptiva congelada

Publicar frecuencia, MFE/MAE, WR y R por bracket sin modificar parámetros.

---

## 11. Next steps hasta llegar a una estrategia

### Fase A — Investigación sin estrategia

1. completar captura DST 2025 y 2026;
2. auditar calidad/paridad;
3. medir resultados globales y por cohortes;
4. calcular intervalos de confianza;
5. identificar si P/b agrega edge frente a D;
6. comprobar frecuencia mensual y estabilidad temporal.

**Salida:** informe de edge; todavía no hay reglas de entrada operables.

### Fase B — Congelar candidato de setup

Solo si existe evidencia, escribir una especificación inmutable:

- qué LVN se opera cuando hay varios;
- primer retest o todos;
- dirección por aceptación/rechazo (ya implementada en captura) y/o forma;
- entrada exacta: confirmación de aceptación/rechazo (implementada), touch o limit;
- filtro opcional por velocidad (deceleration_ratio / zone_speed), solo si las
  distribuciones observadas era-blind lo respaldan;
- stop, target y time exit;
- horario y número máximo de intentos;
- comisión, slippage y latencia;
- tratamiento explícito de barras ambiguas.

No escoger reglas mirando simultáneamente todo 2025–2026.

**Salida:** `LVN_setup_v1_frozen.md` con hash/configuración y cero parámetros abiertos.

### Fase C — Backtest de estrategia

1. convertir eventos en trades según el setup congelado;
2. incluir costos y slippage;
3. separar desarrollo y validación temporal;
4. usar walk-forward/era split con embargo;
5. reportar trades, trades/mes, WR, payoff, PF, EV y drawdown;
6. Monte Carlo del path y riesgo de ruina;
7. stress de ±1–2 ticks de entrada/slippage;
8. comprobar que el edge no depende de pocas fechas ni de una sola forma.

Targets provisionales de admisión —deben congelarse antes del holdout—:

- EV neto > 0;
- PF neto > 1.15;
- frecuencia suficiente para el objetivo operativo;
- estabilidad 2025/2026 y por trimestre;
- drawdown compatible con límites reales;
- resultado no explicado únicamente por casos ambiguos.

### Fase D — CatBoost, solo después del baseline

CatBoost puede usar las probabilidades de forma, contexto y order flow para descubrir edge
condicional o recortar peores eventos. Reglas:

- features disponibles en el instante del retest;
- modelo pequeño por tamaño de muestra;
- validación walk-forward;
- ninguna feature posterior al retest;
- comparar siempre contra el baseline sin ML;
- no perseguir PF alto sacrificando toda la frecuencia.

### Fase E — Replay de ejecución

Crear una estrategia ATAS separada únicamente cuando v1 esté congelada. Reproducir fills, brackets,
time exit y logs; comparar cada trade con el backtest Python.

### Fase F — Paper forward

Gate mínimo sugerido:

- aproximadamente dos meses o muestra acordada;
- EV neto positivo;
- PF > 1.15;
- desviaciones de implementación explicadas;
- cero violaciones de causalidad o duplicación de retests.

### Fase G — Producción controlada

1. tamaño mínimo;
2. límites diarios y kill switch;
3. monitor rolling de EV/frecuencia por forma;
4. downsize/pausa ante decay;
5. nunca cambiar parámetros en vivo sin nueva versión y nuevo backtest.

---

## 12. Condiciones para matar o pausar la hipótesis

La hipótesis debe pausarse si:

- el evento es demasiado raro para estimar su edge;
- el resultado neto no supera costos;
- P/b no mejora ni diferencia el comportamiento respecto a D;
- el edge vive en un solo año o pocas fechas;
- desaparece con ±1 tick de slippage;
- depende de resolver favorablemente casos ambiguos;
- falla el holdout o el forward paper.

Matar la hipótesis no invalida el motor: el dataset y el proceso quedan disponibles para probar la
siguiente definición sin contaminar la anterior.

