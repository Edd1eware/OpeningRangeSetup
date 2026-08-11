# Progreso v22 - snapshot reset y bloqueo 2022-06-13

Fecha local: 2026-07-13 maniana.

## Reglas duras

- No look-ahead.
- No overfit.
- No maquillar resultados.
- No tratar `OPEN` como `BE`.
- No llamar prometedora una corrida inestable.
- No lanzar corrida grande hasta que Q2 termine limpio y positivo.

## LucidPro 150k confirmado

Fuente oficial consultada: Lucid Trading Help Center, `LucidPro Evaluation Account`.

Para `150,000`:

- Profit Target: `$9,000`.
- Max Loss Limit: `$4,500`.
- Daily Loss Limit: `$2,700`.
- Max Size: `10 mini` o `100 micros`.

Fuente: `https://support.lucidtrading.com/en/articles/12890029-lucidpro-evaluation-account`

## Smoke 2022-04-04

Comando:

```powershell
python -u .\04_run_replay_score_trade_results_dst_2025_2026_after_sync.py --x10-only --from-date 2022-04-04 --to-date 2022-04-04 --section-label 2022-04-04-v21-smoke-fixed-timeover --reset-state --force
```

Resultado guardado:

- Version: `score-exporter-2026-07-12-v21-1030-forced-exit`.
- Result_Label: `TIME_OVER`.
- result TP SL BE: `TIME_OVER`.
- EntryTime_NY: `09:40:00`.
- Sin entry price, exit price ni side.
- Sin `OPEN`.

Conclusion:

- El fix de `NoTradeTimeOverTimeNy = 09:40` funciono para dia sin trade.

## Smoke 2022-06-13

Comando:

```powershell
python -u .\04_run_replay_score_trade_results_dst_2025_2026_after_sync.py --x10-only --from-date 2022-06-13 --to-date 2022-06-13 --section-label 2022-06-13-v21-repro-smoke --reset-state --force
```

La corrida NO es valida.

Observaciones durante la corrida:

- El CSV global aparecio primero como `TP +20`, entrada `09:31:28`, salida `09:34:47`.
- Luego el mismo CSV volvio a `OPEN 0`.
- Luego cambio a `SL -20`.
- Mientras Replay seguia, `ExitTime_NY` y `Trade_Duration` siguieron moviendose:
  - `09:41:58`, duracion `10:30`.
  - `09:50:11`, duracion `18:42`.
  - `10:01:30`, duracion `30:01`.
- El runner no copio esos resultados porque el guardrail de estabilidad detecto que el archivo seguia cambiando.
- El timeout de 12 min entro en gracia post-timeout.
- El Stop del runner no detuvo ATAS de forma confiable; la ventana seguia `Replay - History playback...`.
- Windows se bloqueo durante la corrida, asi que se perdio control UI.
- Se mataron `python` y `OFT.Platform` para no dejar una corrida falsa viva.

Conclusion:

- `2022-06-13` sigue siendo fecha de bloqueo/reproducibilidad.
- No se puede usar esta corrida como evidencia de edge.
- No lanzar Q2 ni corrida grande con este estado.

## Causa encontrada

Existia un snapshot antiguo:

`C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\replay_sync_results\score_trade_result_snapshot_2022-06-13_NY.json`

Contenido clave:

- ExporterVersion: `score-exporter-2026-06-23-v11-canonical-sync-guards`.
- Result: `SL`.
- ExitTimeNy: `09:31:29.890`.

Problema:

- El exporter v21 no adoptaba ese snapshot porque la version no coincidia.
- Pero `TryWritePersistedTradeExit()` tampoco podia escribir un snapshot nuevo porque el archivo ya existia.
- Por eso no habia snapshot canonico nuevo y el CSV podia seguir cambiando entre recalculos/replay updates.

## Cambios hechos en v22

### Exporter C#

Archivo:

`ATASScoreTradeResultExporter.cs`

Cambios:

- Version nueva:
  - `score-exporter-2026-07-13-v22-sync-snapshot-reset`.
- `TryWritePersistedTradeExit()` ahora:
  - conserva snapshot existente si tiene la misma version del exporter;
  - permite sobrescribir snapshots viejos/de otra version.

Objetivo:

- Un snapshot stale v11 ya no bloquea el primer cierre canonico v22.

### Runner Python

Archivo:

`replay_sync_runner_common_after_sync.py`

Cambios:

- `EXPECTED_EXPORTER_VERSION = "score-exporter-2026-07-13-v22-sync-snapshot-reset"`.

Archivo:

`04_run_replay_score_trade_results_dst_2025_2026_after_sync.py`

Cambios:

- `--reset-state` ahora archiva y recrea:
  - `replay_sync_signals`
  - `replay_sync_results`
- Esto evita que snapshots viejos contaminen corridas frescas.

## Build

Comandos:

```powershell
dotnet build .\EddiewareOpeningRangeSetup.csproj -c Release
python -m py_compile .\replay_sync_runner_common_after_sync.py .\04_run_replay_score_trade_results_dst_2025_2026_after_sync.py
```

Resultado:

- Build C#: 0 errores, warnings existentes.
- Python compile: OK.

DLL v22 copiada a:

- `C:\Users\k_99_\AppData\Roaming\ATAS\Indicators\EddiewareOpeningRangeSetup.dll`
- `C:\Users\k_99_\AppData\Roaming\ATAS\Strategies\EddiewareOpeningRangeSetup.dll`

## Estado actual

- `python`: detenido.
- `OFT.Platform`: detenido.
- Windows estaba bloqueado al final de la prueba.
- ATAS debe abrirse otra vez despues de desbloquear Windows para cargar v22.

## Siguiente paso

1. Desbloquear Windows.
2. Abrir ATAS y conectar.
3. Repetir smoke `2022-06-13` con v22 y `--reset-state`.
4. Exigir:
   - version v22,
   - snapshot replay_sync_results v22 nuevo,
   - `OPEN=0`,
   - resultado estable,
   - Stop/Replay bajo control.
5. Solo si `2022-06-13` queda reproducible, repetir Q2 desde cero.
6. Solo si Q2 termina 61/61, positivo y compatible con limites LucidPro 150k, considerar corrida grande desde `2022-04-04`.
