# ATAS L2 vs MT5 Sync Monitor

> **RETIRADO el 13-ago-2026.** La comparación operativa ahora es **NQ ATAS vs ES ATAS**
> (`13_NQ_ES_SyncMonitor.cs` + `17_ES_FeedPublisher.cs`, documentado en
> `leader_context/2026_08_13_NQ_vs_ES_sync_monitor.md`). La clase `AtasMt5SyncMonitor`
> que describe este documento ya no existe. El EA `ATAS_MT5_SyncBridge.mq5` se conserva
> porque sigue siendo el único camino para leer un CFD, pero el motivo del cambio fue
> justamente el reloj del broker: ES nativo de CME elimina esa fuente de error.

Componentes:

- `ATAS_MT5_SyncBridge.mq5`: indicador de MT5 que publica bid/ask/last de USTEC cada 100 ms y 180 velas M1 en `FILE_COMMON`.
- `AtasMt5SyncMonitor`: indicador ATAS que reconstruye best bid/ask L2 de NQ y compara estructura M1 normalizada por ATR, cuerpo y ruptura.
- `TelegramTradeNotifier.QueuePhotoAlert`: envío persistente de la captura combinada, sin duplicados y con tres reintentos.

El monitor no compara directamente el nivel de NQ con USTEC porque futuro y CFD tienen una base diferente. Normaliza cada mercado por su propio rango/ATR y sólo declara liderazgo si el mejor encaje estructural está desplazado al menos 3 velas M1, supera los filtros de correlación y dirección, y mejora de forma suficiente el encaje a desfase cero.

- `EN SINCRONÍA`
- `L2 ATAS LIDERA`
- `MT5 LIDERA`

Telegram permanece silencioso durante la sincronía. Cuando aparece por primera vez un liderazgo estructural confirmado, manda una sola alerta con una imagen que contiene las gráficas NQ/ATAS y USTEC/MT5. El mensaje indica claramente `ATAS L2 LIDERA` o `CFD MT5 LIDERA`, el escenario LONG/SHORT, el nivel equivalente por base aditiva, la hora de la vela pivote y la hora causal de detección. Los cambios que no alcanzan tres velas permanecen clasificados como sincronía y no generan mensajes.

El monitor incorpora como indicador hijo el detector causal de `Liquidity Burst` de un segundo. Un burst reciente se reporta como `APOYA EL ESCENARIO` o `CONTRADICE EL ESCENARIO`, pero nunca bloquea ni retrasa la alerta de desfase. Si no hubo burst durante los 10 segundos anteriores, el Telegram dice expresamente que no fue detectado. El burst exacto de un segundo solo existe en datos de tape en vivo; no se reconstruye artificialmente desde velas M1 históricas.

Mientras el indicador está cargado, un hilo dedicado mantiene despiertos el sistema y la pantalla. Al retirar el indicador o cerrar ATAS se restaura la política normal de energía.

En esta instalación, `FILE_COMMON` corresponde a `C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\Common\Files`.
