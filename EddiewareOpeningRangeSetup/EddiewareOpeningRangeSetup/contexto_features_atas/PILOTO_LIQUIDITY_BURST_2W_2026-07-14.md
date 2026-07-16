# Piloto Liquidity Burst Detector — 2 semanas X10 (2022-04-04 a 2022-04-15)

Fecha local: 2026-07-14 mañana.
Corrida: `LIQUIDITY-BURST-TEST-2w`, X10_R1, 9/9 sesiones, OPEN=0, exporter v22, detector `liquidity-burst-detector-2026-07-14-v1`.

## Setup verificado antes de lanzar

- DLL desplegada (Indicators + Strategies) = build Debug 2026-07-14 06:52, hash idéntico, incluye detector.
- ATAS arrancó 07:02 (después del deploy) → cargó DLL correcta.
- Exporter y runner alineados en v22.
- Detector agregado al chart por el usuario (confirmado por burst_events.csv poblado).

## Falla operativa encontrada y fix

3 lanzamientos fallaron con "Abre y deja visible la ventana Replay de ATAS" AUNQUE la ventana Replay estaba visible y en pantalla (Win32 rect OK).

**Causa raíz: la ventana PRINCIPAL de ATAS estaba minimizada.** Con el main minimizado, UIA reporta la ventana Replay flotante con rect ≈ -31000 y el runner la filtra (`rectangle().left > -10000`).

Fix aplicado: restaurar ATAS main via `ShowWindow(SW_RESTORE)` antes de lanzar. **Regla operativa: nunca minimizar ATAS durante corridas del runner.**

Nota cosmética: el runner imprime "Esperando CSV terminal v11" — texto viejo hardcodeado (línea ~696 de `replay_sync_runner_common_after_sync.py`), la versión real validada es v22.

## Captura del detector — FUNCIONA end-to-end

- `burst_events.csv`: bursts intradía con 48 columnas (deltas multi-ventana, zscore, percentil, velocity, perfil OR/VWAP/POC/VAH/VAL/HVN/LVN).
- Trade CSV: `Speed_Timing_Source=LIQUIDITY_BURST` cuando el burst promovió el speed.
- Bus detector→engine→exporter operativo en replay (edad máx 3s, mismo side).

## Tabla por día

| fecha | result | ticks | entry | side | raw_speed | timing_src | t/s | bursts (hora side z) |
|---|---|---|---|---|---|---|---|---|
| 04-04 | TIME_OVER | — | — | — | — | — | — | — |
| 04-05 | TP | +30 | 09:36:43 | SELL | invalid speed | **LIQUIDITY_BURST** | 0.12 | 09:32 BUY z=6.9; 09:36:42 SELL z=-6.0 |
| 04-06 | SL | -20 | 09:36:07 | SELL | normal | MarketTradeTime | 2.85 | 09:31 BUY z=7.4; 09:36:21 SELL z=-12.4 |
| 04-07 | TP | +20 | 09:33:42 | BUY | normal | MarketTradeTime | 2.01 | — |
| 04-08 | SL | -20 | 09:33:52 | SELL | normal | MarketTradeTime | 2.88 | 09:32:28 SELL z=-4.0; 09:33:52 SELL z=-4.6 |
| 04-11 | TP | +30 | 09:32:07 | SELL | **A+ speed** | MarketTradeTime | 6.26 | 09:31:47 SELL z=-2.7 |
| 04-12 | TP | +20 | 09:33:11 | SELL | normal | MarketTradeTime | 3.47 | — |
| 04-13 | SL | -20 | 09:31:14 | SELL | normal | MarketTradeTime | 3.85 | — |
| 04-14 | SL | -60 | 09:34:11 | SELL | invalid speed | **LIQUIDITY_BURST** | 0.43 | 09:34:10 SELL z=-6.4 |

Resumen: 8 trades, TP=4 SL=4, WR 50%, net -20 ticks, PF 0.83. (Baseline sin detector NO corrido para estas fechas exactas con v22 — comparación A/B pendiente.)

## Respuesta a la pregunta LB vs A+ speed (n=9, TENTATIVO)

| patrón | días |
|---|---|
| LB y A+ nativo el mismo día | 1 (04-11) |
| Solo LB (sin A+ nativo) | 4 |
| Solo A+ nativo (sin LB) | **0** |
| Ninguno | 4 |

1. **LB precede a A+ nativo**: el único día con A+ nativo (04-11) tuvo burst 20 segundos ANTES del entry A+. Cero días con A+ sin burst.
2. **A+ NO predice LB**: 4 de 5 días con burst no tuvieron A+ nativo.
3. **Timing**: en los 5 días con burst y trade, el primer burst llegó ANTES del entry (5/5).
4. Interpretación: LB es señal más sensible y temprana; A+ speed es un subconjunto raro que solo aparece cuando ya hubo burst. NO son indicadores de días aislados en dirección A+→sin-LB; sí existe LB-sin-A+.

## Trades promovidos por LB (raw speed no calificaba)

- 04-05: TP +30 (burst SELL 1s antes del entry).
- 04-14: SL -60 (burst SELL 1s antes; peor pérdida de la corrida — revisar por qué -60 y no -20).

Net promoción: -30 ticks en n=2 → sin evidencia de mejora ni de daño. NO tocar umbrales del detector todavía (regla del goal: solo modificar si probablemente mejora; con n=2 no hay caso).

## Pendientes

1. Investigar SL -60 de 04-14 (¿bracket distinto, slippage de replay, trail?).
2. Corrida larga (Q2 completo o más) para n estadístico: bursts como predictor de movimientos grandes (task 3) — el piloto solo valida la mecánica.
3. A/B: mismas fechas con `UseLiquidityBurstSignals=false` para aislar efecto de la promoción (2 entradas nuevas: 04-05 y 04-14 no existirían sin LB).
4. `Liquidity_Burst_*_AtEntry` columnas: en el CSV diario aparecen sin sufijo/parcial — verificar mapeo completo si se necesita para análisis fino.
