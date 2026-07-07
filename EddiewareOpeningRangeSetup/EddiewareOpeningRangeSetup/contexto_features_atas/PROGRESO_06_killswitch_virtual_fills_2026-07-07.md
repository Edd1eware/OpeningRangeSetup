# Progreso 06 — Validación integración kill-switch en ATAS Replay: ROOT CAUSE + fills virtuales (2026-07-07)

Objetivo de la sesión: validar en ATAS (replay) que el kill-switch C# reproduce el
sim/parity (`kill_switch_parity.py --base 3` → **+$15,785 / −$3,125**). Requisito 6
pendiente del PROGRESO_05 §2b-PARITY.

Resultado: **el replay de integración, como estaba armado, NO puede validar** por una
limitación de ATAS. Se implementó el fix (#3, fills virtuales). Falta re-correr.

---

## 1. Síntomas observados (3 corridas `06_run_strategy_replay.py --dates 2025-03-18`)

| Corrida | Instancias ATAS | signal | trades log | killswitch_state |
|---|---|---|---|---|
| A (con 14 inst) | 14 (6 pesadas) | CONSUMED | fallback (header corto) | `0\|0\|0\|0\|0\|0` |
| B (1 inst, pre-write) | 1 | PENDING | fallback | `0\|...` |
| C (1 inst, trace) | 1 | PENDING | fallback | `0\|...` |

En TODAS: `challenge_equity=0`, log = **fallback python** (contratos=3 hardcoded, header
corto sin `challenge_equity`), kill-switch nunca contabilizó. El "-3" que el usuario vio en
el chart (corrida A) era **dibujo**, no `CurrentPosition` real.

---

## 2. Diagnóstico con trace (definitivo)

Se agregó un trace temporal en `OnCalculate` (1 línea por barra cercana a la ventana). Reveló
la secuencia exacta (2025-03-18):

```
bar 2310 09:30:00 curPos=0 enteredToday=False sig_side=SELL   <- lee señal
bar 2310 09:30:00 curPos=0 enteredToday=True                  <- ENTRA (EnterTrade)
... 400+ filas 09:30→09:35 ... curPos=0 SIEMPRE
```

**La strategy SÍ lee la señal y SÍ entra (`enteredToday=True`), pero `CurrentPosition`
NUNCA deja de ser 0.** La orden market colocada por `OpenOrder` no llena posición → no hay
posición que cerrar → el bloque de cierre (`_tradeOpen && _prevPosition!=0 && curPos==0`) y el
de hardClose (`CurrentPosition!=0`) nunca disparan → `UpdateChallengeEquity`/`OnTradeClosed`
del kill-switch nunca corre → `killswitch_state` queda en 0 y el runner usa su fallback.

### ROOT CAUSE (evidencia dura)
| Componente | ¿coloca órdenes? | ¿anda en replay? |
|---|---|---|
| Exporter (`ATASScoreTradeResultExporter`) | **NO** (0 `OpenOrder`/`CurrentPosition`/`Order` en todo el archivo) — simula TP/SL desde precio (MFE/MAE) | ✅ sí |
| Strategy (`02_C`, ChartStrategy) | **SÍ** (`OpenOrder` market real) | ❌ no llena |

**ATAS Market Replay alimenta solo datos de precio; NO trae motor de fills/portfolio.** Una
`ChartStrategy` que hace `OpenOrder` necesita un motor que llene la orden (conexión real,
emulador/paper, o el Strategy Tester). El replay no tiene ninguno → `CurrentPosition=0`
permanente. El exporter anda porque nunca coloca orden: calcula el resultado desde el precio.
Además el proyecto no tiene handlers de orden (`OnOrderChanged`/`OrderRegisterFailed`) ni ruta
de Tester/Emulador. NO era race, ni orphans, ni state stale (todos descartados en esta sesión).

---

## 3. Fix elegido = #3 fills virtuales (DLL 2026-07-07 14:54)

Descartadas: #1 Strategy Tester (re-arquitectura del runner), #2 emulador/paper (config ATAS).
Elegido #3: **contabilidad determinista desde precio dentro de la strategy** — mismo enfoque
que el exporter. Reusa la matemática de trailing/SL existente. El pipeline `06_run` queda igual.

### Cambios en `02_C_ATASExecutionManagerStrategy.cs`
- **Flag** `UseVirtualFills` (default **ON**, GroupName Kill-switch). OFF = ruta live/emulador.
- Campos `_virtualPending/_virtualOpen/_virtualSide/_virtualEntry/_virtualStop/_virtualContracts`.
- **`EnterTrade`**: si `UseVirtualFills`, NO coloca órdenes reales; arma un *pending* virtual
  (side/entry/contratos del kill-switch vía `AllowedContracts()`), setea `_enteredToday`.
- **`ManageVirtualTrade(bar,tod,hardClose)`** (llamado cada barra tras `currentPrice`):
  1. **Pending → fill** cuando el precio TOCA el entry (`High>=entry` BUY / `Low<=entry` SELL),
     como un breakout. NO gestiona SL en la barra de fill (evita falso-SL intrabar sin ticks);
     la gestión arranca en la barra siguiente. Si llega hardClose sin tocar → sin trade.
  2. **Open**: actualiza pico favorable (extremo High/Low), activa trailing a `+TrailActivateTicks`,
     mueve stop a `pico-TrailTicks` (solo a favor). SL inicial = `entry ± SlTicks`.
  3. **Exit**: si el extremo adverso toca el stop → sale al precio del stop (motivo SL o trail);
     o `tod>=hardClose` → sale al close.
- **`CloseVirtual(exit,comment)`**: `pnl=tickMove*_virtualContracts*$5` → `UpdateChallengeEquity`
  (alimenta `_killSwitch.OnTradeClosed` + persiste) → `LogTrade` (header rico).
- El bloque viejo de `CurrentPosition` se envolvió en `if (!UseVirtualFills)` (ruta live intacta).
- Reset de campos virtuales en el cambio de fecha.
- Compila 0 errores, desplegado Indicators+Strategies **14:54**.

**Anclaje de entrada:** se usa `e.EntryPrice` canónico (del score CSV pre-escrito), NO el precio
al abrir la ventana. Como el fill espera a que el precio TOQUE ese nivel, la entrada ocurre en el
breakout real (~09:33) aunque la señal se lea a las 09:30. Resuelve de paso el "entra muy temprano".

**Caveat de fidelidad:** dentro de una barra se asume favorable-antes-que-adverso (optimista) y
no se gestiona SL en la barra de fill. Sin datos tick es lo estándar; el bracket propio de la
strategy (SL50/act20/trail10) puede diferir del bracket del exporter → el P&L virtual NO tiene
por qué igualar el score CSV, pero SÍ es la conducta real de la strategy que el kill-switch debe
procesar. La validación es contra el **parity** (secuencia de trades → tiers/net/DD), no contra
el exporter.

---

## 4. Automatización agregada al runner (esta sesión) — [[feedback_automate_tedious]]

`06_run_strategy_replay.py` + `atas_process_guard.py`:
| Automatización | Qué hace | Flag |
|---|---|---|
| Borrado state files | `challenge_equity/killswitch_state/regime_state` → cuenta limpia cada corrida | `--keep-state` para conservar |
| Pre-escritura señal | escribe `pending_strategy_signal.txt` desde el score CSV canónico ANTES del Play → mata la race Exporter/Strategy | default ON |
| Guard instancias huérfanas | `atas_process_guard.py`: mata instancias ATAS pesadas (>900MB) SIN ventana; nunca toca las de ventana ni helpers ligeros | preflight reporta; `--kill-orphans` mata |
| Fix encoding | `→`→`->` en un print (crash cp1252 en consola Windows) | — |

**Hallazgo operativo:** juntar 6+ instancias ATAS pesadas (aperturas/crashes previos sin cerrar)
crea Exporter/Strategy duplicados con statics separados peleando por el archivo de señal. Dejar
**1 sola instancia** es obligatorio. El guard lo detecta/limpia. Ojo: al reiniciar ATAS suele
quedar la instancia vieja colgada sin ventana (huérfana) → el guard la mata antes de cada corrida.

---

## 5. Estado / reanudar

- DLL **14:54** con `UseVirtualFills` desplegado. **ATAS NO recarga en caliente** → reiniciar
  para cargarlo (1 sola instancia; el guard limpia huérfanas).
- **Siguiente (sanity):** `python -u 06_run_strategy_replay.py --dates 2025-03-18`. Éxito =
  `strategy_tester_trades.csv` con **header RICO** (`...,challenge_equity,challenge_dd,...`),
  `killswitch_state.txt` ≠ `0|0|0|0|0|0`, `challenge_equity.txt` ≠ 0. Un trade SELL contabilizado.
- **Luego integración completa:** `--all` (39 fechas A+ Speed) → leer el log rico de la strategy
  (contratos/tier reales por trade) y comparar la secuencia de tiers/net/DD contra
  `kill_switch_parity.py --base 3` (meta +$15,785 / −$3,125). Si la secuencia de trades del replay
  == la secuencia real de 174 y los tiers coinciden → integración PASA.
- **Caveat:** el universo A+ Speed (39) NO es el mismo que las 174 del parity (que incluía no-A+).
  Para comparar 1:1 hay que correr el mismo universo (o re-validar el KS sobre el subset A+). Ver
  PROGRESO_05 §3b (OnlyAPlusSpeed temp OFF).
- **REVERTIR antes de vivo:** `OnlyAPlusSpeed=true`, `UseRollingWrFilter=true`, `ResetChallengeState=false`,
  y `UseVirtualFills=false` (en live/emulador se usan fills reales, no virtuales).
- Parity C# vs sim ya PASÓ byte-idéntico (PROGRESO_05 §2b-PARITY). Los fills virtuales son para
  ver el kill-switch operar la secuencia DENTRO de ATAS; la matemática ya estaba probada.

---

## 6. RESUELTO — sizing probado en ATAS + contabilidad en Python (DLL limpio 16:31)

### Trace virtual (DLL 15:57, con la strategy en Started) confirmó el ciclo hasta FILL
```
SIGNAL side=SELL entry=19830 isAPlus=True   <- lee señal
ENTER_VIRTUAL side=SELL contracts=3         <- entra; kill-switch dio 3 contratos (tier full)
FILL bar=2315 entry=19830 stop=19892.5      <- LLENÓ al tocar el entry
```
**Sizing del kill-switch PROBADO vivo en ATAS**: `AllowedContracts()` → 3 = tier del kill-switch,
cableado en la entrada. Ese era el corazón de la integración.

### Por qué NO cierra dentro de ATAS (2 causas)
1. **El runner para el replay en el terminal del exporter (~09:35)**, mismo bar del FILL, antes del
   hardClose 09:50 de la strategy → cero barras posteriores para gestionar/cerrar → no hay `CLOSE`
   → `UpdateChallengeEquity`/`OnTradeClosed` no corre. (Requisito 1 previo: primero que la strategy
   estuviera en **Started** en el panel de Strategies; un run falló porque no lo estaba → sin
   `OnCalculate`, sin archivos de estado.)
2. **BUG Tick=1.25 (debería 0.25)** — `stop=19892.5` = entry + 50·Tick → Tick=1.25 (NQ=0.25). La
   strategy lee `Tick` 5× inflado → SL/trailing 5× de distancia. Afecta también el bracket LIVE.
   PENDIENTE de arreglar (fuente de `Tick` en la ChartStrategy vs el 0.25 que usa el exporter).

### Decisión (usuario): contabilidad del kill-switch en Python
`analysis_vp/kill_switch_accounting.py` corre el motor `run_csharp` (== C# `12_KillSwitchSizer.cs`,
parity byte-idéntico) sobre los score CSV canónicos → log per-trade + tabla año×métrica. NO depende
de fills ni de cierres en ATAS.

**Resultado base=3 (secuencia 2025-03-10 → 2026-06-30, 174 trades):**
| year | trades | WR | contratos medios | PF | net |
|---|---|---|---|---|---|
| 2025 | 113 | 63.7% | 2.58 | 1.61 | +$11,730 |
| 2026 | 61 | 59.0% | 2.31 | 1.39 | +$4,055 |
| TOTAL | 174 | 62.1% | 2.49 | 1.53 | **+$15,785** |

maxDD path **−$3,125** vs cojín $4,500 → **SEGURO** (margen $1,375). Tiers full=108/half=43/min=23
(66 trades con throttle). **Idéntico al parity** (PROGRESO_05 §2b-PARITY). Log per-trade:
`...X10_R1\kill_switch_accounting_base3.csv`.

### Estado del código
- `UseVirtualFills` (default ON) queda en la strategy — sirve para forward/paper y para ver el
  sizing. Trace `VLog` **revertido**; build limpio **16:31** desplegado (Indicators+Strategies).
- **Kill-switch VALIDADO**: sizing en ATAS (contracts=tier) + contabilidad de secuencia en Python
  (== C# parity). Cierre de la validación de integración.

### PENDIENTES
1. **BUG Tick=1.25** en la ChartStrategy (afecta SL/trailing live). Investigar fuente de `Tick`.
2. Revertir flags temp antes de vivo (`OnlyAPlusSpeed=true`, `UseRollingWrFilter=true`,
   `ResetChallengeState=false`, `UseVirtualFills=false` si se usa emulador/fills reales).
3. Universo: la contabilidad usó las 174 (todas las fechas del DST run); el edge vivo es solo A+
   Speed (39). Si se opera solo A+, re-correr `kill_switch_accounting` sobre ese subset.
