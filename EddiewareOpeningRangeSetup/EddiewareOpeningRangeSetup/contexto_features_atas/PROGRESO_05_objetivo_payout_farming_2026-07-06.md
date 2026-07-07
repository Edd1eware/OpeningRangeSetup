# Progreso 05 — Objetivo real = PAYOUT FARMING + análisis año×año setup actual (2026-07-06)

## 0. Reframe de objetivo (fijado por el usuario)

El objetivo de las cuentas fondeadas **NO es never-break** (nunca romper la cuenta). Es
**farmear payouts**: pasar el challenge → extraer la máxima cantidad de payouts → si se
quema, se repite (nuevo account/reset).

**Consecuencia:** la métrica de éxito cambia. Ya NO es "el edge sobrevive cada año con
criterio constante", sino:
- **Payouts esperados por cuenta**
- **$ EV por fee de cuenta** sobre el ciclo pasar→payouts→quema→repetir

Se mide con **Monte Carlo del path de la cuenta**, no con la tabla año×año sola. PERO un
año/tramo negativo igual destruye el farm (más quemas que payouts) → el desglose año×año
sigue siendo INSUMO del MC, no se descarta.

(Guardado también en memoria: `objective_payout_farming`. Refina `feedback_rentable_es_sobrevivir`.)

---

## 1. Análisis año×métrica — setup ACTUAL (sin cambios), datos parciales de la corrida

Fuente: `score_trade_result_*_NY.csv` en
`...\trade_results_score\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1\`
Comisión asumida = **1 tick**. Bracket TP/SL = **20/20 → RR 1.0 → breakeven WR 50%**.
Campo P&L = `result TP SL BE` (ticks netos con BE). Solo trades reales (TP/SL/BE), se excluye
TIME_OVER/no-trade.

| year | trades | tr/mes | WR | be_WR | RR | PF | EV bruto | EV neto |
|---|---|---|---|---|---|---|---|---|
| 2025* | 63 | 14.7 | 61.9% | 50.0% | 1.0 | 1.32 | +4.6t | **+3.6t** |
| 2026* | 2 | — | 100% | 57.1% | — | inf | — | — |
| TOTAL | 65 | — | 63.1% | 50.0% | 1.0 | 1.42 | +5.8t | +4.8t |

Mezcla resultado (incluye TIME_OVER): 2025 → TP 39 / SL 24 / TIME_OVER 27. 2026 → 2 TP.

### Caveats (crítico, no ignorar)
1. **2025 es PARCIAL** (mar–jun ~4 meses). La corrida iba en 2025-06-24 al medir; falta
   jul–oct 2025 **y todo 2026**. No hay año completo ni multi-año.
2. **La config solo cubre 2025–2026** (DST_SEASONS). Los años flojos conocidos
   (**2023 PF 0.89, 2024 flojo** por memoria) **NO están en la muestra** → survivorship, no
   el test de supervivencia real.
3. **n=65 modesto**; 2 trades en 2026 no dicen nada.

**Veredicto:** setup actual va positivo en 2025-parcial (PF 1.32, EV neto +3.6t) — explica el
"hubiéramos pasado la cuenta con el último trade". Pero por criterio constante NO se declara
rentable/superviviente aún: falta cerrar la corrida (246 fechas) y la ventana excluye 2023–24.

---

## 2. Plan Monte Carlo de payout farming (pendiente de reglas de la firma)

Insumo listo (dist. empírica de trades, 2025-parcial): EV neto +3.6t/trade, WR 61.9%,
RR 1:1 (20/20), ~14.7 trades/mes, dist. TP/SL muestreable.

### Faltan 5 datos de la firma (sin ellos el MC es inventado)
| # | Dato | Ej. |
|---|---|---|
| 1 | Profit target para **pasar** | $9,000 en 150k? |
| 2 | **Payout**: mínimo para pedir + cadencia (min días / min trading days) + % split | |
| 3 | **MaxDD**: trailing (intradía/EOD) o estático $4,500 | |
| 4 | **Costo** de cuenta / reset | $/intento |
| 5 | **Tamaño real** operado (contratos) | 3 MNQ? minis? |

Ref conocida (memoria): cuenta **Lucid $150k, MaxDD=$4,500**, sizing 100k=2 / 150k=3 mini.
NQ tick=$5 / MNQ tick=$0.50 (confirmar cuál).

### Outputs del MC
| Output | Decide |
|---|---|
| P(≥1 payout antes de quemar) | ¿arranca el farm? |
| **Payouts esperados / cuenta** | rentabilidad del ciclo |
| **$ EV por fee de cuenta** | ¿farmear > costo? |
| Distribución #payouts (P5/P50/P95) | varianza del farm |

Al terminar la corrida: cruzar dist. año×año DENTRO del MC (no solo total), para que un tramo
negativo se refleje en más quemas.

---

## 1c. CIERRE 2025 completo (corrida terminó, 6c) — RESULTADO CLAVE

Año × métrica (comisión 1 tick):

| year | trades | tr/mes | WR | be_WR | RR | PF | EV bruto | EV neto |
|---|---|---|---|---|---|---|---|---|
| **2025** | 113 | 14.4 | 63.7% | 50.0% | 1.0 | **1.67** | +8.5t | **+7.5t** |
| 2026* | 9 | — | 55.6% | 50.8% | 0.97 | 1.10 | +1.7t | +0.7t |
| TOTAL | 122 | — | 63.1% | 50.0% | 1.0 | 1.62 | +8.0t | +7.0t |

Net mensual (6c): Mar −$2,100 · Abr −$960 · **May +$5,250 · Jun +$3,450 · Jul +$5,670 ·
Ago +$6,180 · Sep +$5,580 · Oct +$5,880** · 2026-03 −$2,250 · 2026-06 +$2,700.
TOTAL +$29,400. MAX DD path **−$6,810** (sin cambio).

### Veredicto
1. **2025 AGUANTÓ jul-oct**: May→Oct = **6 meses verdes seguidos** (~+5.5k c/u), PF 1.67. Edge
   consistente todo el tramo, NO lo infló un mes gordo. Resistió el año completo.
2. **2026 más débil (bandera amarilla)**: PF 1.10, EV neto +0.7t, WR 55.6% apenas sobre breakeven,
   2026-03 rojo. Señal de dependencia de régimen. Caveat: n=9, muestra sucia (mezcla probes previos,
   falta abr-may 2026 limpio). No concluyente pero es el tramo más flojo — VIGILAR.
3. **Sizing confirmado**: DD −$6,810 a 6c > cojín $4,500. A 4c=−$4,540 (revienta al filo), **3c=−$3,405
   (seguro)**. Fix determinista = bajar a 3c.

Caveat higiene: dedup por fecha dejó TIME_OVER=0 en el conteo (tr/mes sobrestimado); el net mensual
en $ es correcto. Real trading-day rate ~68% con trade (medido antes).

## 2b-RESUELTO. Kill-switch DISEÑADO + BACKTESTEADO (2026-07-07)

Simulador `analysis_vp/kill_switch_sim.py` sobre la secuencia REAL (174 trades 2025-03→2026-06).

### Diseño final (determinista, sin ML)
Throttle graduado de tamaño, anclado al cojín $4,500, con tier mínimo (nunca pausa total → evita
deadlock) y re-arme por días verdes O por tiempo (probe_days=8):
- tiers = [1.0 full, 0.5 half, 0.25 min] × base contracts
- dd desde peak: `<0.35·cojín`→full · `<0.60·cojín`→half · `≥0.60`→min
- override por racha: streak≥3→≤half, streak≥4→min
- re-arme: sube 1 tier tras 2 días verdes O 8 días atascado (anti-whipsaw/anti-deadlock)

### Hallazgo CRÍTICO — validación de robustez (barajado 2000 perms) INVIRTIÓ el optimismo
El DD del path observado era **suerte del orden**. P(QUEMA) real por config:

| config | P(QUEMA) barajado | net P50 |
|---|---|---|
| FIJO 3c | **26.1%** (¡NO era seguro!) | +$22,410 |
| FIJO 6c | 99.2% | — |
| KILL 6c | 34.5% | +$24,518 |
| FIJO 2c | 1.9% | +$14,940 |
| **KILL 4c** | **1.9%** | **+$19,780** |
| KILL 3c | 0.0% | +$16,914 |

- **FIJO 3c NO es seguro (26% quema)** — el −$3,405 observado fue orden favorable. Corrige el
  consejo previo "sizing 3c arregla el DD".
- **KILL 6c también era suerte** (parecía +18% seguro; barajado 34.5% quema).
- Stress: pérdidas ×1.3 → FIJO 3c Y KILL 6c revientan. Distribución ya al filo.

### GANADOR: KILL base-4c (f1=0.35, f2=0.60)
Vs FIJO 2c (único fijo seguro): **+32% más $ (+$19,780 vs +$14,940) al MISMO 1.9% de quema.**
El kill-switch se justifica por ROBUSTEZ (mismo retorno a 1/13 del riesgo), no por más retorno.
Caveat: barajado asume orden i.i.d; si las rachas se agrupan más que al azar (régimen), la quema
real puede ser >1.9% → razón extra para 4c, no 5-6c.

### PORT HECHO (DLL 2026-07-07 00:25) — KILL en C#
- Nueva clase `12_KillSwitchSizer.cs`: diseño validado (tiers full/half/min = base/round(base/2)/1,
  DD desde peak <0.35·cushion→full <0.60→half ≥0.60→min, override racha 3→half/4→min, re-arme 2
  verdes o 8 atascado, NUNCA pausa total). Persistencia Serialize/Deserialize.
- Cableado en `02_C_ATASExecutionManagerStrategy.cs`: flag **`UseKillSwitch`** (default ON) + prop
  **`KillSwitchBase`** (default **3**, subir a 4 tras forward). Reusa `_challengeEquity/_peak`.
  `AllowedContracts()`: si kill-switch ON → `min(CurrentSize, hardCap)` (el governor duro sigue de
  techo). `UpdateChallengeEquity` alimenta `OnTradeClosed(pnlUsd)`. Estado en `killswitch_state.txt`.
- No tocó `03_Speed_clasification` ni el exporter. Governor viejo intacto como fallback (flag OFF).
- Compila 0 errores, desplegado Indicators+Strategies 00:25.

**CAVEATS pendientes de validar:**
1. **Integer rounding — RESUELTO:** re-corrido el sim con tiers enteros del C#. base=3 (3/2/1) →
   0.7% quema, +$18,378. base=4 (4/2/1) → 1.9%, +$19,780. Los números se mantienen (base=3 entero
   hasta mejor que el fraccional). OK.
2. **Requisito 6 (replay-validación):** correr replay con `UseKillSwitch=ON, base=3` y verificar que
   los tiers/net/DD reproducen el simulador Python sobre la misma secuencia. NO usar en vivo antes.
3. `challenge_equity.txt` (equity/peak) y `killswitch_state.txt` (tier/streak/verdes/atascado/bal/peak)
   deben resetearse (`ResetChallengeState`) al arrancar cuenta nueva.

### (histórico) PENDIENTE PORT — llevar KILL-4c a C# (ATAS Execution Manager)
Sizing dinámico en la estrategia de ejecución. Requisitos:
1. Estado persistente EOD: peak equity, dd desde peak, streak perdedor, tier actual, días verdes,
   días atascado. Persistir a disco (sobrevive reinicio de ATAS / cambio de sesión).
2. Leer equity/balance real de la cuenta (o P&L acumulado del día vía el exporter).
3. Calcular contratos = base(4) × tier según las reglas de arriba, ANTES de cada entrada.
4. Anclar cojín a la regla Lucid viva ($4,500 estático tras pasar; trailing en eval).
5. Determinista, sin ML. Log de cada cambio de tier (fecha, dd, streak, tier viejo→nuevo).
6. Validar en replay que reproduce el net/DD del simulador Python (misma secuencia → mismos tiers).
NO tocar 03_Speed_clasification ni el exporter; nueva capa de sizing en el Execution Manager.

---

## 2b-viejo. (brief original, superado por 2b-RESUELTO)

Diseñar un kill-switch que se adapte al **tipo real de racha perdedora observada**, no a spikes de
un día. Debe pausar/bajar tamaño ANTES de que el DD reviente el cojín Lucid.

### Rachas reales que debe atrapar (datos 2025, 6c)
| Fenómeno observado | Valor | Riesgo |
|---|---|---|
| **MAX DRAWDOWN del path** | **−$6,810** | > cojín $4,500 → quema a 6c |
| Meses rojos de arranque | 2025-03 −$2,100, 2025-04 −$960 | sangría lenta, no un día |
| Cluster de SL seguidos | 09-18/19 (−$600/−$630) | racha corta |
| Racha perdedora máx (días con trade) | 4 | referencia |
| Peor día suelto | −81t (−$2,430 a 6c) | spike |

### Requisitos de diseño (no es un stop de un día)
1. **Multi-escala:** detectar (a) sangría lenta multi-semana (meses rojos tipo Mar-Abr) Y (b)
   cluster corto de SL, no solo el peor día. Un rolling-DD desde peak + racha de días rojos.
2. **Adaptativo al régimen:** umbral en función del baseline del backtest (EV/día, std), no fijo.
   Ej. CUSUM sobre EV/día rolling; cuando deriva bajo breakeven N trades → bandera.
3. **Acción graduada, no binaria:** 6c→3c→pausa según profundidad del DD vs cojín restante, para
   no matar frecuencia (piso 5 días rentables/ciclo, ver `feedback_frequency_over_runners`).
4. **Anclado al cojín Lucid vivo:** conocer el DD estático restante ($4,500 tras pasar) y cortar
   con margen antes de tocarlo (ej. a −$3,000 del peak ya baja a 3c).
5. **Confiable:** determinista, sin depender de ML; re-armar tamaño solo tras M días verdes.
6. **Backtest del propio kill-switch:** correrlo sobre el path 2025 y verificar que habría evitado
   el −$6,810 sin cortar de más los meses buenos (May-Sep).

Relacionado: detector de régimen de `edge_discovery_doctrine` (misma señal, distinta acción).
Construir DESPUÉS de cerrar la corrida (para calibrar umbrales con la temporada completa, no parcial).

## 2c. PENDIENTE — Near-miss logger (¿subir frecuencia a igual/mejor PF-WR?)

Pregunta del usuario: ¿CatBoost puede AUMENTAR frecuencia conservando PF/WR o superior?
Respuesta: **posible SOLO por un camino** — no filtrando los trades actuales (eso solo resta),
sino **aflojar compuerta + CatBoost selecciona el pool ampliado**. Requiere datos que HOY no existen.

### Bloqueador
`features_scan` loguea solo trades TOMADOS. Las señales **rechazadas** por los filtros A+
(structure/absorption/speed/imbalance/VWAP) + su outcome no se registran. Sin eso, CatBoost no
tiene ejemplos de "rechazado pero habría ganado" → no se puede responder.

### Qué construir: NEAR-MISS LOGGER
Registrar cada señal OR **rechazada** + por qué (cuál filtro la mató) + su **forward outcome**
(¿habría hecho TP/SL con el bracket actual?). Engancharlo en el exporter donde se evalúan los
gates A+, antes del descarte. Campos mínimos: fecha, hora, dir, entry hipotético, qué gate falló,
fwd_mfe/mae, hit TP/SL, + las features pre-entrada (mismas que features_scan).

### Test barato ANTES del pipeline pesado
1. Prender el logger una temporada.
2. Medir WR/PF del pool rechazado, **segmentado por gate que falló**.
3. **VERDE** si existe segmento rechazado con WR ≥ WR actual (63.7%) → hay frecuencia recuperable
   → CatBoost puede agregar esos trades a igual/mejor calidad.
   **ROJO** si todos los segmentos ≤ breakeven → compuerta ya óptima, no hay espacio, no insistir.

### Valor vs odds
- Valor si funciona: **alto** — más frecuencia = más días rentables = payouts más rápidos
  (alineado con `feedback_frequency_over_runners`, el objetivo prioritario).
- Odds: moderadas-bajas — depende de si los filtros A+ están sobre-apretados (desconocido).
- Costo del test: bajo (solo loguear rechazos + forward).

## 3. Estado / reanudar
- Corrida featsweep DST en curso (con Feature Scanner en el chart esta vez). Iba en 2025-06-24.
- VP (análisis/ejecución) validado y sin dibujo (DLL 19:06). Pipeline `analysis_vp/` (merge +
  univariada + CatBoost) listo, pero label +60t sobre slide 20-min está roto (base rate 1.5%,
  fwd_bars med 2). Para el ADN se decidió **opción A** = label = resultado real del trade
  (TP/SL), pero n≈110 full-run vs 293 features → CatBoost solo defendible con features MUY
  reducidas (31 VP o menos). Ver PROGRESO_04 §8.
- Reglas Lucid $150k CONFIRMADAS: pass $9,000 | DD $4,500 EOD | fee $370 | 5 días prof | payout
  min $500 | split 100%<$10k luego 90%. Sizing actual = **6 NQ mini ($5/tick)** (Telegram).
- MC payout farming corrido (`analysis_vp/mc_payout_farming.py`) — DEMASIADO optimista (i.i.d
  barajó las rachas). **Path real 2025 = MAX DD −$6,810 > cojín $4,500 → 6c se quema con su propio
  peor tramo. Fix determinista: bajar a 3c** (DD → −$3,405).
- Meses 2025 (6c): Mar −$2,100, Abr −$960 (rojos), May-Sep verdes; TOTAL +$25,770. 6 verdes/2 rojos.
- **CORRECCIÓN sizing (2026-07-07):** FIJO 3c NO es seguro (26% quema barajado). El ganador robusto
  es **KILL base-4c** (throttle dinámico, 1.9% quema, +$19,780 P50). Ver §2b-RESUELTO.
- **Siguiente (pendientes):**
  1. **PORT KILL-4c a C# (Execution Manager)** — sizing dinámico, estado EOD persistente. Ver §2b-RESUELTO.
     Validar en replay que reproduce net/DD del simulador Python. PRIORIDAD 1.
  2. Al cerrar corrida (HECHO): tabla año completo (§1c) + MC año-aware con secuencia real (pendiente
     rehacer MC — el i.i.d era optimista, usar path real como en kill_switch_sim).
  3. **Near-miss logger (§2c)** — única vía a +frecuencia. Test barato (medir pool rechazado) antes
     de pipeline pesado. PRIORIDAD 2.
  4. (Opcional, ~30%) test veto pérdida-grande vs runner con features reducidas + fresh holdout.
     CatBoost NO ayuda al setup actual (probado, sin señal, n chico) — solo tras near-miss.
