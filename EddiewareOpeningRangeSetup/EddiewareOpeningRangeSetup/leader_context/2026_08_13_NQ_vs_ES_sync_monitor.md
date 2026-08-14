# NQ ATAS vs ES ATAS — monitor de liderazgo, desfase y divergencia (13-ago-2026)

Reemplaza la comparación anterior **NQ ATAS vs USTEC (CFD MT5)**. Ahora ambas patas salen de ATAS: NQ del chart donde vive el monitor, ES de un publicador que corre en un chart de ES.

---

## 1. Por qué hay dos indicadores y no uno

Se verificó por reflexión sobre `ATAS.Indicators.dll` que el SDK **no** permite leer otro instrumento desde un indicador:

| API inspeccionada | Qué expone | Sirve para ES? |
|---|---|---|
| `Indicator.Instrument` / `InstrumentInfo` | solo el símbolo del chart | No |
| `ExtendedIndicator.DataProvider` → `IIndicatorDataProvider` | `CandlesDataSeries`, `OnlineDataProvider`, `TradingManager`… | No |
| `IOnlineDataProvider` | `Subscribe`, `NewTrades`, `MarketDepthsChanged`, `SubscribeMarketByOrdersData`, `RequestCumulativeTrades` | No — todo atado al instrumento del chart |

Conclusión: la única vía causal dentro de la misma plataforma es un **puente por archivo**, misma forma que ya usaba el puente MT5. Se conserva por tanto el esquema de lectura y el ciclo de 100 ms.

---

## 2. Archivos tocados

| Archivo | Acción | Contenido |
|---|---|---|
| `17_ES_FeedPublisher.cs` | **nuevo** | Indicador `ES M1 Feed Publisher`. Se adjunta al chart **M1 de ES**. Publica L1 vivo + historial M1 |
| `13_ATAS_MT5_SyncMonitor.cs` → `13_NQ_ES_SyncMonitor.cs` | **renombrado (`git mv`, historia preservada) y reescrito** | Indicador `NQ vs ES Structural Sync`. Se adjunta al chart **M1 de NQ** |
| `14_ATAS_MT5_ComparisonScreenshot.cs` | sin cambios | Sigue generando la captura que acompaña la alerta |

Clase renombrada: `AtasMt5SyncMonitor` → `NqEsStructuralSyncMonitor`. **Hay que volver a agregar el indicador al chart**; la instancia vieja ya no existe con ese nombre.

---

## 3. Puente ES → NQ

Carpeta por defecto: `C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\atas_es_sync`

| Archivo | Cadencia | Formato |
|---|---|---|
| `es_price.csv` | 100 ms, solo si cambió algo | `ATAS_ES_SYNC_V1;symbol;bid;ask;last;utc_ms;sequence;mid` |
| `es_m1_history.csv` | 2 s | cabecera `ATAS_ES_HISTORY_V1;symbol` + filas `unix_sec;o;h;l;c;volume` (360 velas) |

Detalles:

* Escritura **atómica** (`.tmp` + `File.Move(overwrite)`): el monitor lee cada 100 ms y nunca puede parsear una fila a medias.
* Si nada se movió, el publicador **no reescribe** el archivo. Es justo lo que permite que el monitor declare `ES SIN DATOS` por antigüedad del timestamp.
* Lectura con `FileShare.ReadWrite | Delete`, tolerante a fallos de parseo.

---

## 4. Conversión ES → NQ

ES y NQ no cotizan el mismo número, así que la conversión es **multiplicativa** (el puente MT5 usaba una base aditiva porque NQ y USTEC cotizan el mismo índice).

```
ratio = mediana( close_NQ / close_ES )   sobre las últimas N velas M1 comunes (N = 60 por defecto)
ES en puntos NQ:  O,H,L,C  ×  ratio
```

* **Mediana, no media**: un solo minuto congelado en cualquiera de las dos patas arrastraría una media.
* Después de convertir, todo el motor estructural (pivotes, ATR, distancias) trabaja **en puntos NQ**, sin cambios.
* El residuo que queda tras escalar se trata como base aditiva contemporánea, igual que antes.
* El nivel equivalente del rezagado se reporta en las **dos** unidades: puntos NQ y cotización nativa (`/ ratio` si el rezagado es ES).

---

## 5. Qué mide ahora (lo nuevo)

Sobre las últimas 60 velas M1 comunes, con ES ya convertido:

| Métrica | Cómo se calcula | Para qué |
|---|---|---|
| `correlation` | Pearson de retornos log M1, lag 0 | ¿se mueven juntos? |
| `best_lag_candles` | argmax de corr(NQ[t], ES[t+L]), L ∈ [−8, +8] | **desfase**: L>0 = NQ adelanta, L<0 = ES adelanta |
| `best_lag_correlation` | correlación en ese L | fuerza del desfase |
| `spread_points_nq` | `close_NQ − close_ES×ratio` de la última vela cerrada | separación instantánea |
| `spread_z` | z-score del spread contra su propia ventana | **divergencia** normalizada |
| `spread_atr` | \|spread − media\| / ATR(14) NQ | divergencia en unidades de ruido del propio NQ |

Todo con velas **cerradas** (`UtcMinute < minuto actual`): el barrido es causal por construcción.

---

## 6. Máquina de estados (texto centrado arriba del chart)

Prioridad de arriba hacia abajo:

| Estado | Condición | Color |
|---|---|---|
| `NQ SIN DATOS` | mid NQ = 0 o L2 más viejo que `StaleAfterSeconds` (3 s) | rojo |
| `ES SIN DATOS` | mid ES = 0 o `es_price.csv` más viejo que 3 s | rojo |
| `CARGANDO ESTRUCTURA M1` | menos de 24 velas comunes, o hueco M1, o escala no estimable | oro |
| `NQ LIDERA` | NQ formó pivote grande y ES sigue sin equivalente tras 3 velas | azul |
| `ES LIDERA` | espejo del anterior | violeta |
| `DIVERGENCIA NQ/ES` | `corr < 0.55` **o** `\|z\| ≥ 2.5` | naranja |
| `DESFASE NQ/ES` | mejor lag ≠ 0 con corr ≥ 0.55 | caqui |
| `EN SINCRONÍA` | resto | verde |

El bloque de 3 líneas (estado / detalle / precios) va **centrado horizontalmente en la parte superior** (`region.Top + 12`), medido con `context.MeasureString`. Antes estaba pegado a la izquierda en `Top + 180`.

Se **quitó la compuerta DST**: existía porque el CFD de MT5 seguía calendario europeo. NQ y ES son ambos CME, misma sesión.

---

## 7. Telegram

* Dispara con `NQ LIDERA` o `ES LIDERA` (lo pedido).
* Deduplicación por firma `estado|tipo_pivote|minuto_pivote|minuto_evidencia`, cola de 256 — no repite la misma alerta.
* Opción `Telegram también en divergencia` (por defecto **apagada**) para incluir `DIVERGENCIA NQ/ES`.
* El mensaje ahora incluye: escala `xratio`, spread en puntos NQ + z, correlación M1, mejor desfase, nivel equivalente en unidades nativas y en NQ.
* La captura de pantalla y el fallback de texto siguen igual.

CSV de auditoría: `…\trade_results_score\nq_es_sync\nq_es_structural_sync_reports.csv` (esquema nuevo: 46 columnas, incluye ratio, corr, lag, spread, z, ATR).

---

## 8. Parámetros nuevos (grupo "Conversión ES→NQ")

| Propiedad | Default | Rango |
|---|---|---|
| Ventana de escala NQ/ES (velas) | 60 | 20–240 |
| Correlación mínima de sincronía | 0.55 | 0–1 |
| Divergencia: \|z\| del spread | 2.5 | 1–6 |
| Telegram también en divergencia | off | bool |

Los umbrales 0.55 / 2.5 son **puntos de partida, no calibrados**: no hay muestra todavía de corr y spread NQ-ES a M1 en este setup. Se ajustan cuando el CSV tenga sesiones.

---

## 9. Compilación y despliegue

| Paso | Resultado |
|---|---|
| `dotnet build -c Release` | **0 errores**, 60 advertencias (CA1416 preexistentes + 2 CS0618 por `Instrument`/`GetMarketDepthSnapshot` obsoletos, ya presentes en el código original) |
| DLL | 614,912 bytes, 13-ago 23:57:22 |
| `AppData\Roaming\ATAS\Indicators` | copiado y verificado |
| `AppData\Roaming\ATAS\Strategies` | copiado y verificado |
| ATAS | cerrado y relanzado (el DLL estaba bloqueado) |

---

## 10. Pasos manuales pendientes en ATAS

1. Abrir un chart **M1 de ES** y adjuntarle `ES M1 Feed Publisher`. Sin esto el monitor mostrará `ES SIN DATOS` permanentemente.
2. En el chart **M1 de NQ**, quitar el indicador viejo (`ATAS L2 vs MT5 Structural Sync`) y agregar `NQ vs ES Structural Sync`.
3. Verificar que aparecen `es_price.csv` y `es_m1_history.csv` en `atas_es_sync` y que el `ratio` mostrado ronda NQ/ES real (≈3.7–3.8 con NQ ~24k / ES ~6.4k).
4. Dejar correr y revisar el CSV antes de tocar los umbrales de divergencia.

## 11. Lo que este monitor NO es

Sigue siendo **informativo**. Que NQ lidere a ES no está validado como edge: la línea CFD/NQ ya quedó como *no concluyente* por potencia estadística (evento real ~0.25/sesión, réplica 35.9%). Aquí solo cambia la calidad de la pata comparada (ES nativo de CME en vez de un CFD con reloj de broker), lo cual elimina el bug de reloj del broker pero **no** convierte el liderazgo en señal operable. Cualquier decisión de trading exige medir esto contra su propio breakeven, año por año.
