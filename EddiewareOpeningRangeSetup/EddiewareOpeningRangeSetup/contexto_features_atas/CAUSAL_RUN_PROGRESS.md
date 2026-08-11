# Causal No-Lookahead Progress

Fecha de trabajo: 2026-07-12

## Estado del bug

El PF 3.01 anterior queda invalidado como resultado causal. La causa fue `Cvd_Pullback_Label`: en el CSV v11 era el estado final/intratrade del CVD, no el estado disponible al entrar.

Se corrigio el exporter para separar:

- `trade_inputs.csv`: snapshot congelado al entry.
- `trade_results.csv`: resultado, MFE/MAE, CVD final, exit, alarmas y estados dinamicos.

El optimizador ahora aborta si intenta usar columnas futuras como `MFE`, `MAE`, `Exit`, `Result`, `Dynamic`, `*_Final`, `TP`, `SL` o `Cvd_Pullback_Label`.

## Comparacion sin optimizar

| Caso | Trades | WR | PF | Expectancy | DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Antes contaminado, CVD final Excelente | 342 | 73.39% | 3.01 | +15.54 ticks | 120 ticks |
| Despues causal, CVD al entry | 564 | 51.24% | 1.27 | +3.47 ticks | 435 ticks |

## Hipotesis causal actual

No hay permiso estadistico para afirmar un edge fuerte todavia.

Lo que si aparece, de forma debil, es una hipotesis de momentum:

- OR grande tiende a mejorar el resultado.
- Score alto ayuda, pero no de forma monotona limpia.
- El patron no es estable: cada fold walk-forward eligio una regla diferente.

Por eso la corrida nueva se lanza por secciones para generar archivos v12 limpios y confirmar si el patron se repite sin look-ahead.

## Walk-forward causal

Seleccion: solo datos anteriores. Prueba: siguiente año fuera de muestra.

Resultado combinado OOS:

- Trades: 302
- Frecuencia: 10.07 trades/mes
- WR: 50.66%
- PF: 1.26
- Expectancy: +3.16 ticks/trade
- DD: 414 ticks
- Gate para corrida completa: FAIL

Folds:

| Test | Regla elegida con pasado | TP | SL | OOS trades | OOS WR | OOS PF | OOS Exp |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | score>=6 AND OR<=160 | 80 | 30 | 122 | 46.72% | 1.11 | +1.27 |
| 2024 | score>=8 AND OR>=100 | 60 | 30 | 50 | 48.00% | 1.07 | +0.84 |
| 2025 | score>=7 AND OR<=160 | 60 | 30 | 70 | 52.86% | 1.44 | +5.13 |
| 2026 | OR>=140 | 100 | 60 | 60 | 58.33% | 1.45 | +6.65 |

## Criterio de escala

No se lanza historia completa 2022-2026 como "edge aprobado" hasta que una seccion fresca v12 pase una compuerta minima:

- Exporter version v12 en todos los CSV.
- `trade_inputs.csv` y `trade_results.csv` presentes.
- Sin columnas futuras en features.
- PF de seccion >= 1.40 o expectancy >= +5 ticks.
- DD compatible con Lucid antes de escalar.
- Patron explicable con variables al entry.

## Corrida a lanzar

Primera seccion: 2022-Q2.

- Rango: 2022-04-04 a 2022-06-30.
- Solo sesiones operables del calendario DST del runner.
- Fines de semana y cierres completos USA/CME excluidos.
- Modo: X10 only.
- Objetivo: validar pipeline v12 causal y medir si la hipotesis OR/score merece segunda seccion.

## Telegram

Telegram fue limpiado antes del mensaje nuevo causal. Se borro el historial registrado por el proyecto; un mensaje viejo en `atrapados` no fue borrable por limite de Bot API.

## Intento de corrida v12

Intento 1:

- Se lanzo 2022-Q2 X10 con `--reset-state --force`.
- ATAS estaba abierto pero `Platform.cnf` tenia `ActiveWorkspaceName = "The workspace hasn't been loaded"` y `LoadLastWorkspace = false`.
- El runner llego a 2022-04-04, configuro Replay X10, pero no se genero ningun CSV en 5 minutos.
- Se detuvo el proceso Python antes de que consumiera el resto de la seccion con fallos.
- Clasificacion: fallo operativo de workspace/chart/indicador no cargado, no resultado del modelo.

Correccion operativa:

- Se respaldo `Platform.cnf`.
- Se cambiara ATAS a `LoadLastWorkspace = true` y `ActiveWorkspaceName = "Eddieware_workspace"`.
- Despues de reiniciar ATAS se relanza la misma seccion.

## Estado 2026-07-12 noche

Pregunta: por que no inicio la corrida.

Respuesta corta: hubo dos bloqueos distintos, uno operativo y otro de semantica de CSV.

1. Primer intento v19:

- Se copio DLL v19 a `AppData/Roaming/ATAS/Indicators` y `Strategies`.
- ATAS abrio en `Authorization`; se hizo click en `Connect`.
- El workspace cargo, pero el runner fallo al inicio porque detecto Replay como desconectado por un texto viejo de UI.
- Se corrigio `replay_is_connected()` para confiar primero en el boton `The replay is on/off`.
- Tambien se corrigio el Excel para no romper cuando un intento no genera CSV y faltan headers como `EntryTime_NY`.

2. Segundo intento v19:

- Replay si arranco en X10 para 2022-04-04.
- Telegram se limpio y se reinicio estado.
- El exporter v19 si recibio eventos intrabar (`Source=MarketTradeTime`, `IsTradeEvent=TRUE`).
- No produjo trade terminal; escribio una fila `NO_PROFILE` de un candidato rechazado por `SPEED`.
- El runner espero 5 minutos porque `NO_PROFILE` no es resultado terminal.

Correccion aplicada:

- `WriteRejectedScoreFile()` ya no escribe en `score_trade_result_YYYY-MM-DD_NY.csv`.
- Los candidatos rechazados ahora van a `score_best_rejected_YYYY-MM-DD_NY.csv`.
- El archivo principal queda reservado para resultados terminales: TP/SL/EXIT/BE/TIME_OVER/NO_TRADE.
- Version nueva del exporter: `score-exporter-2026-07-12-v20-causal-terminal-results`.
- El runner ahora exige esa version v20.

Bloqueo actual:

- ATAS fue reiniciado con DLL v20 copiada.
- ATAS volvio a pantalla `Authorization`.
- El email aparece cargado (`mtw.eduardo.me@gmail.com`), pero el campo de password aparece vacio para UI Automation.
- Dos clicks en `Connect` no pasaron de Authorization.
- No se puede lanzar validacion v20 hasta que ATAS quede conectado.

Estado tecnico honesto:

- El problema inicial de Replay desconectado ya esta corregido.
- El problema de `NO_PROFILE` bloqueando el runner ya esta corregido en codigo y compilado.
- Falta validar v20 en ATAS despues de login real.
- No hay WR/PF nuevo valido de v20 todavia.

## Resultado seccion 2022-Q2 v20 causal

Carpeta:

`C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1`

Archivos esperados/encontrados: 61/61.

Conteo por `Result_Label`:

- TP: 15
- SL: 9
- OPEN: 28
- TIME_OVER: 9

Metricas sobre trades cerrados TP/SL solamente:

- Trades cerrados: 24
- WR: 62.50%
- PF: 2.03
- Net: +311 ticks
- Expectancy: +12.96 ticks/trade cerrado
- DD maximo secuencial, tratando OPEN/TIME_OVER como 0: 100 ticks
- Racha max ganadora: 5
- Racha max perdedora: 3

Metricas si se usa el denominador crudo de entradas:

- Entradas con precio: 52
- Wins: 15
- Losses: 9
- OPEN/0: 28
- WR crudo: 28.85%

Advertencia critica:

Los 28 `OPEN` no son BE confirmados. En los CSV aparecen con:

- `Result_Label=OPEN`
- `result TP SL BE=0`
- sin `ExitTime_NY`
- sin `Exit_price`
- sin MAE/MFE util

Por eso el resumen de Telegram `BE: 28` debe leerse como "OPEN/0", no como breakeven ejecutable. Hasta cerrar esos OPEN de forma causal en el exporter, el PF 2.03 es prometedor pero no aprobado para full run.

Meses:

| Mes | Sesiones | Entradas | TP/SL | WR TP/SL | PF TP/SL | OPEN | TIME_OVER | Net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-04 | 19 | 15 | 7 | 28.57% | 0.57 | 8 | 4 | -60 |
| 2022-05 | 21 | 19 | 8 | 75.00% | 3.50 | 11 | 2 | +200 |
| 2022-06 | 21 | 18 | 9 | 77.78% | 3.11 | 9 | 3 | +171 |

Lectura:

- Mayo y junio son fuertes.
- Abril falla: PF 0.57 y net -60.
- La muestra cerrada es pequena: 24 TP/SL en 3 meses.
- El resultado depende de como se resuelvan los 28 OPEN.

Siguiente correccion necesaria antes de escalar:

- Forzar cierre causal de cualquier trade abierto al final de ventana (`TimeOverTimeNy` o `replay_to_time`) con precio disponible de ese momento.
- Etiquetar explicitamente `TIME_EXIT`, `BE`, o `OPEN_FORCED_EXIT`; no dejar `OPEN` como resultado final.
- Guardar MAE/MFE real para esos trades.
- Recalcular Q2. Solo despues decidir si correr la siguiente seccion.
