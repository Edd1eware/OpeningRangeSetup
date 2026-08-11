# ATAS L2 vs MT5 Sync Monitor

Componentes:

- `ATAS_MT5_SyncBridge.mq5`: indicador de MT5 que publica bid/ask/last de USTEC cada 100 ms y 180 velas M1 en `FILE_COMMON`.
- `AtasMt5SyncMonitor`: indicador ATAS que reconstruye best bid/ask L2 de NQ y compara estructura M1 normalizada por ATR, cuerpo y ruptura.
- `TelegramTradeNotifier.QueuePhotoAlert`: envío persistente de la captura combinada, sin duplicados y con tres reintentos.

El monitor no compara directamente el nivel de NQ con USTEC porque futuro y CFD tienen una base diferente. Normaliza cada mercado por su propio rango/ATR y sólo declara liderazgo si el mejor encaje estructural está desplazado al menos 3 velas M1, supera los filtros de correlación y dirección, y mejora de forma suficiente el encaje a desfase cero.

- `EN SINCRONÍA`
- `L2 ATAS LIDERA`
- `MT5 LIDERA`

Telegram permanece silencioso durante la sincronía. Cuando aparece por primera vez un liderazgo estructural confirmado, manda una alerta inmediata con una imagen que contiene las gráficas NQ/ATAS y USTEC/MT5. Los cambios que no alcanzan tres velas permanecen clasificados como sincronía y no generan mensajes.

Mientras el indicador está cargado, un hilo dedicado mantiene despiertos el sistema y la pantalla. Al retirar el indicador o cerrar ATAS se restaura la política normal de energía.

En esta instalación, `FILE_COMMON` corresponde a `C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\Common\Files`.
