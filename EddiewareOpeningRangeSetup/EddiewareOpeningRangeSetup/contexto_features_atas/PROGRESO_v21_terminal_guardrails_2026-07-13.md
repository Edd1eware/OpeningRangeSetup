# Progreso v21 - guardrails terminales y gate Q2

Fecha local: 2026-07-13 madrugada.

## Principio operativo

Se mantiene regla dura:

- No look-ahead.
- No overfit.
- No maquillar resultados.
- No tratar `OPEN` como `BE`.
- No lanzar corrida grande si Q2 no pasa gate causal.

## Reglas LucidPro 150k verificadas

Fuente oficial consultada: Lucid Trading Help Center, `LucidPro Evaluation Account`.

Para cuenta `150,000`:

- Profit Target: `$9,000`.
- Max Loss Limit: `$4,500`.
- Daily Loss Limit: `$2,700`.
- Max Size: `10 mini` o `100 micros`.
- La pagina tambien indica que no hay rebilling mensual y que se puede pasar en un dia, pero el objetivo local sigue siendo maximo 6 meses.

Fuente: `https://support.lucidtrading.com/en/articles/12890029-lucidpro-evaluation-account`

## Cambios hechos

### Runner Python

Archivo:

`replay_sync_runner_common_after_sync.py`

Cambios:

- `OPEN` nunca es terminal.
- Valores cero (`0`, `+0`, `-0`, `0.0`, `0.00`, etc.) no son terminales salvo `Result_Label == BE` explicito y con salida real.
- `TP`, `SL`, `EXIT`, `BE` requieren `ExitTime_NY` y `Exit_price`.
- Se agrego verificacion de estabilidad del CSV: terminal + mtime/tamano quietos antes de copiar.
- Si el CSV vuelve a `OPEN`/incompleto antes de copiar, el runner no lo guarda.
- `X10_TIMEOUT_SECONDS` quedo en `12 * 60`, pero no quedo validado como suficiente para todos los dias lentos.

Archivo:

`04_run_replay_score_trade_results_dst_2025_2026_after_sync.py`

Cambios:

- `result_is_terminal()` usa el guardrail comun del runner.

### Exporter C#

Archivo:

`ATASScoreTradeResultExporter.cs`

Cambios:

- Se separo el cierre sin trade del cierre de trades abiertos.
- Trade abierto: sigue hasta `TimeOverTimeNy = 10:30`.
- Sin trade: `NoTradeTimeOverTimeNy = 09:40`.
- Esto evita que dias sin trade queden sin CSV si ATAS no entrega un update exacto al `To=10:30`.

Build:

- `dotnet build .\EddiewareOpeningRangeSetup.csproj -c Release`
- Resultado: 0 errores, warnings existentes.

DLL copiada a:

- `C:\Users\k_99_\AppData\Roaming\ATAS\Indicators\EddiewareOpeningRangeSetup.dll`
- `C:\Users\k_99_\AppData\Roaming\ATAS\Strategies\EddiewareOpeningRangeSetup.dll`

ATAS fue reiniciado y workspace `Eddieware_workspace` cargado.

## Smokes validados

### 2022-04-07

Resultado valido:

- Version: `score-exporter-2026-07-12-v21-1030-forced-exit`
- Result_Label: `TP`
- result TP SL BE: `+20`
- EntryTime_NY: `09:33:42`
- ExitTime_NY: `09:34:00`
- Entry_price: `14511.25`
- Exit_price: `14516.25`
- OPEN: no.

### 2022-04-04

Resultado valido:

- Version: `score-exporter-2026-07-12-v21-1030-forced-exit`
- Result_Label: `TIME_OVER`
- result TP SL BE: `TIME_OVER`
- EntryTime_NY: `09:40:00`
- Sin trade y sin PnL.
- OPEN: no.

## Q2 2022 intentado

Comando lanzado:

```powershell
python -u .\04_run_replay_score_trade_results_dst_2025_2026_after_sync.py --x10-only --from-date 2022-04-04 --to-date 2022-06-30 --section-label 2022-Q2-v21-1030-no-open --reset-state --force
```

Estado parcial antes de detener:

- Guardadas: `45/61`.
- TP: `19`.
- SL: `18`.
- TIME_OVER: `8`.
- OPEN: `0`.
- Trades TP/SL: `37`.
- Net parcial: `-35 ticks`.
- PF parcial: `0.95`.
- Expectancy parcial: `-0.95 ticks/trade`.

Conclusion parcial:

- No prometedor.
- No pasa gate Lucid.
- No justifica corrida grande.

## Bloqueo actual

Fecha conflictiva: `2022-06-13`.

Observaciones:

- En una corrida secuencial Q2, el guardrail detecto CSV inestable y no copio un `OPEN/incompleto`.
- Luego el CSV global quedo terminal como `SL`.
- En smoke directo, el CSV terminal aparecio demasiado tarde para el timeout del runner.
- ATAS mostro Replay activo incluso despues del rango `To=10:30`, llegando visualmente a `10:58`.

CSV global observado despues del smoke:

- Version: `score-exporter-2026-07-12-v21-1030-forced-exit`
- Result_Label: `SL`
- result TP SL BE: `-20`
- EntryTime_NY: `09:31:28`
- ExitTime_NY: `09:57:00`
- Trade_Duration: `25:32`
- Entry_price: `11548.75`
- Exit_price: `11543.75`
- Side: `BUY`

Esto sugiere que el problema restante es de control de Replay/timeout/stop, no de convertir `OPEN` a resultado favorable.

## No lanzar todavia

No lanzar:

- Q2 completa como valida.
- DST 2025.
- Corrida grande desde `2022-04-04`.

Motivos:

- Q2 parcial no es positiva.
- Q2 no completo 61/61 sin error.
- `2022-06-13` expuso que Replay puede seguir mas alla del `To`.
- El runner necesita controlar mejor parada/timeout o confirmar que ATAS realmente respeta la ventana.

## Siguiente paso recomendado

1. Arreglar control de Replay para que el runner:
   - confirme estado Stop real,
   - no deje ATAS activo despues del timeout,
   - capture terminales que aparecen tarde sin guardar `OPEN`,
   - o aumente timeout X10 solo despues de validar velocidad real.
2. Repetir smoke `2022-06-13` hasta que se guarde en carpeta `X10_R1` como `SL` terminal.
3. Repetir Q2 2022 desde cero.
4. Solo si Q2 termina `61/61`, `OPEN=0`, errores `0`, PF/expectancy positivos y drawdown compatible con LucidPro 150k, evaluar corrida grande.

