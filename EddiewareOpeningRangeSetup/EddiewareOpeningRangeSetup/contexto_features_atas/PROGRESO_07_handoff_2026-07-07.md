# Progreso 07 — HANDOFF kill-switch integración ATAS (2026-07-07, tarde)

Continúa de PROGRESO_06. Estado para reanudar en sesión nueva (tokens agotándose).

## Estado en una línea
Kill-switch **VALIDADO en Python** (+$15,785 / −$3,125 base=3, parity). La contabilidad en
**ATAS ya funciona** (Tick fix desbloqueó el cierre del trade virtual). Último cambio: la strategy
ahora usa el **SL canónico de la señal** (no SlTicks=50). **DLL 17:01 desplegado, falta re-correr.**

## Qué se hizo esta tarde (tras PROGRESO_06)
1. **Contabilidad Python** `analysis_vp/kill_switch_accounting.py` — corre el motor `run_csharp`
   (== C# `12_KillSwitchSizer.cs`) sobre los score CSV canónicos → log per-trade + tabla año×métrica.
   **base=3: net +$15,785 / maxDD −$3,125 SEGURO**, 174 trades (2025 113 / 2026 61), tiers
   full=108/half=43/min=23. IDÉNTICO al parity. Log: `...X10_R1\kill_switch_accounting_base3.csv`.
2. **BUG Tick=1.25 → 0.25 ARREGLADO** en `02_C_...Strategy.cs`: `Tick` usaba `InstrumentInfo.TickSize`
   (devuelve 1.25 en replay = 5x) → ahora `const decimal SetupTickSize = 0.25m` hardcodeado, igual que
   el exporter. Antes el SL salía a 62.5pts (nunca se tocaba, el trade no cerraba). Con 0.25 el SL a
   12.5pts sí cierra → **la contabilidad ATAS ya corre** (killswitch_state se actualiza, log rico).
3. **Divergencia de bracket detectada + decisión del usuario:** la strategy usaba `SlTicks=50` e
   IGNORABA el `SlPrice` de la señal (60t canónico) → salió SL −50t donde el canónico ganó TP.
   **Decisión: usar el SL canónico de la señal.** Implementado: campo `_virtualSlPrice = e.SlPrice`,
   el stop virtual inicial = `_virtualSlPrice` (si >0; si no, SlTicks). **DLL 17:01.**

## SIGUIENTE PASO (reanudar aquí)
1. Reiniciar ATAS para cargar **DLL 17:01** (no recarga en caliente).
2. `python -u atas_process_guard.py` (mata instancias huérfanas sin ventana; deja 1).
3. Chart 1m NQ + 3 componentes; la **strategy `EW Opening Range Execution Manager (claude_version)`
   en el panel de Strategies en Started** (crítico: si no, no corre OnCalculate → sin archivos).
4. `python -u 06_run_strategy_replay.py --dates 2025-03-18`.
5. **Verificar:** `strategy_tester_results/strategy_tester_trades.csv` — con el SL canónico (19845)
   el trade **ya NO debería SL a 19842.5**; el wick adverso llegaba a ~19842.5 pero no a 19845 →
   trailing toma el control → debería GANAR (acercarse al TP canónico). `killswitch_state.txt` ≠ ceros.
6. Si el trade gana → `--all` (39 A+ o el universo que aplique) y comparar la secuencia de la strategy
   contra `kill_switch_accounting.py`.

## CAVEATS abiertos
- **El EXIT sigue siendo TRAILING**, no el TP fijo canónico. La señal (`PendingEntry`) NO trae TP
  (solo Side/EntryPrice/SlPrice/IsAPlusSpeed/Bar). Con SL canónico + trailing la strategy APROXIMA
  el canónico pero puede NO byte-matchear el parity en el lado del exit. El número confiable del
  edge congelado sigue siendo la **contabilidad Python (+$15,785)**. Si se quiere byte-match, habría
  que meter el TP canónico en la señal, o que la strategy adopte el `result TP SL BE` del score CSV.
- **Universo:** la contabilidad usó las 174 (todas las fechas del DST run); el edge vivo es solo
  A+ Speed (39). Si se opera solo A+, re-correr accounting sobre ese subset.
- **REVERTIR antes de vivo** (todos default TEMP en `02_C`): `OnlyAPlusSpeed=true`,
  `UseRollingWrFilter=true`, `ResetChallengeState=false`, `UseVirtualFills=false` (live usa
  fills reales/emulador, no virtuales).

## Infra/automatización agregada (reusar)
| Archivo | Qué |
|---|---|
| `atas_process_guard.py` | mata instancias ATAS pesadas SIN ventana; nunca las de ventana ni helpers. `--dry-run`/`--kill-orphans` |
| `06_run_strategy_replay.py` | auto-borra state files + pre-escribe señal desde score CSV (mata race Exporter/Strategy) + preflight guard |
| `analysis_vp/kill_switch_accounting.py` | contabilidad kill-switch Python sobre score CSV canónicos |

## Verdad ATAS clave ([[atas_replay_no_fills]] en memoria)
Market Replay = solo precio, SIN motor de fills → ChartStrategy `OpenOrder` no llena,
`CurrentPosition`=0 permanente. Por eso: sizing probado con `UseVirtualFills`, contabilidad en Python.
El exporter (indicador) sí anda porque no coloca órdenes (simula desde precio, tick hardcodeado 0.25).

## Docs relacionados
`PROGRESO_05_objetivo_payout_farming_2026-07-06.md` §2b-PARITY/RESUELTO ·
`PROGRESO_06_killswitch_virtual_fills_2026-07-07.md` (root cause + fills virtuales).
