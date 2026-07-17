# Incidente Replay X10 — control de mouse, pausa y huecos

Fecha del diagnóstico: 2026-07-17

## Contención

- Runner detenido: PID `32152`.
- Supervisor UI detenido: PID `21624`.
- Procesos de automatización restantes: `0`.
- ATAS quedó abierto y no fue manipulado después de la contención.
- No se reinició, reanudó, borró ni sobrescribió la corrida.

## Estado observado

- Fechas visitadas por el runner: 585 de 735.
- CSV terminales guardados: 327.
- Fechas fallidas: 256.
- Fecha que estaba activa al detener: `2025-08-07`.
- Última fecha terminal guardada: `2025-08-06`, resultado `TP`.
- Resultado terminal de `2025-08-07`: ausente.
- Estado ATAS a las `10:21:56.151`: `Started -> Paused`.
- `stderr` del runner y del supervisor: 0 bytes; los fallos fueron capturados en stdout.

Resultados de los 327 terminales observados: 129 TP, 100 SL y 98 TIME_OVER. Estas cifras no constituyen un backtest válido porque faltan 256 fechas intermedias.

## Primer dato que diverge

El primer fallo registrado fue `2022-05-13`. ATAS no aceptó el rango solicitado. En los bloques fallidos, los controles FROM/TO conservaron una fecha anterior mientras el runner intentaba avanzar.

Tipos de fallo:

- 251: `ATAS no aceptó el rango solicitado después de 3 intentos`.
- 5: `Permission denied` sobre un archivo marcador operacional.

Bloques consecutivos de fechas fallidas:

1. 27 fechas: 2022-05-13 a 2022-06-22.
2. 25 fechas: 2022-07-27 a 2022-08-30.
3. 28 fechas: 2022-09-08 a 2022-10-17.
4. 28 fechas: 2022-10-19 a 2023-03-31.
5. 21 fechas: 2023-04-17 a 2023-05-15.
6. 21 fechas: 2023-05-17 a 2023-06-15.
7. 27 fechas: 2023-06-21 a 2023-07-28.
8. 29 fechas: 2023-09-21 a 2023-10-31.
9. 25 fechas: 2024-04-10 a 2024-05-14.
10. 25 fechas: 2024-07-23 a 2024-08-26.

## Causa del movimiento del mouse

El movimiento no lo produjo el supervisor UIA: ese proceso usa `Invoke`, que no mueve el puntero. Lo produjo el runner existente al configurar FROM/TO:

- `replay_sync_runner_common_after_sync.py`, función `paste_text`, usa `control.click_input()`.
- `configure_replay_range` repite la operación hasta tres veces cuando ATAS no confirma el rango.
- El loop principal agrega el fallo y continúa con la fecha siguiente.
- Al alcanzar la racha de fallos sólo manda una alerta de Telegram; no aborta.

Por eso una pérdida de foco o un DateEdit congelado se convirtió en cientos de clics físicos posteriores. La cadena causal es:

`DateEdit deja de aceptar fecha -> 3 click_input por fecha -> se registra error -> el loop no aborta -> avanza a la siguiente fecha -> el puntero continúa moviéndose`.

## Decisión

La corrida queda clasificada como `PARCIAL E INVÁLIDA PARA MÉTRICAS AGREGADAS`. Los 327 terminales se preservan como evidencia, pero no deben emplearse para PF, WR, expectancy ni análisis A/B/C hasta completar exactamente los huecos.

No se reanudará ninguna automatización sin autorización. Una futura corrección tendría que ser fail-fast y detenerse ante el primer rango rechazado o ante un terminal ausente; cambiar ese comportamiento afecta el control del Replay y requiere aprobación explícita.
