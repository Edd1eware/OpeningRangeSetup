# ETA global en mensajes TIME_OVER y PnL

## Requisito

Cada mensaje diario que contenga `TIME OVER` o `PnL` debe mostrar cuánto falta
para terminar la corrida completa, no solamente la fecha o la etapa local.

## Implementación permanente

- El runner publica `telegram_run_eta.txt` con tiempo, pendientes X10 y estado.
- La DLL lee ese archivo exclusivamente al construir el mensaje Telegram.
- `TIME OVER` y los resultados con PnL agregan la misma línea global.
- La lectura es best-effort y nunca participa en señales, entradas, salidas,
  sincronización o resultados.
- Los Telegram de progreso también muestran `Tiempo restante corrida` incluso al
  comenzar o terminar (`00:00:00`).

## Corrida activa

La DLL cargada no puede adoptar código nuevo sin reiniciar ATAS. Para no detener
Replay, `telegram_terminal_eta_monitor.py` reserva las fechas pendientes y envía
el resultado terminal desde el CSV v23 con la ETA global. El balance se sigue
leyendo del ledger idempotente existente y el cálculo de PnL conserva 6 contratos
a $5 por tick.

La ETA incluye las sesiones X10 restantes más 15 minutos reservados para la etapa
de investigación Grupo D.
