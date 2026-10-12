# NQ Opening Range Breakout — investigación L2 (Databento MBP/MBO)

Pipeline de investigación para el setup de ORB en NQ futuros, con datos de
order book de Databento (`GLBX.MDP3`).

**Los datos NO viven aquí.** Esta carpeta está dentro de un repo git; los DBN
pesan decenas de GB. Todo lo descargado se guarda en:

```
C:\Users\k_99_\Desktop\codding\MBP_MBO
```

Se cambia con la variable de entorno `ORB_DATA_ROOT`.

## Setup investigado (spec del usuario, tomado como verdad)

| Elemento | Definición |
|---|---|
| Opening range | la vela M1 de 09:30-09:31 ET |
| Ventana de entrada | velas M1 que cierran entre 09:31 y 09:39 ET |
| Ruptura | por **cuerpo**: el cierre del M1 pasa el nivel. Mecha no cuenta |
| VWAP | ancla 09:30. Long solo arriba, short solo abajo |
| Imbalances | footprint desde MBO (etapa 05), se aplica como filtro |
| R:R | 1:1 → breakeven WR = **50%** exacto |
| Tamaño del movimiento | TP = SL entre 30 y 120 ticks |
| Temporada | **solo EDT** (DST) por ahora, para que 09:30 ET = 13:30Z siempre |

### Variantes de entrada medidas

Cuando el M1 de ruptura cierra muy lejos del nivel, entrar a mercado paga casi
todo el movimiento. Se miden tres formas y se decide con la tabla:

| modo | definición |
|---|---|
| `market` | mercado al abrir el siguiente segundo. Llena siempre |
| `limit_level` | límite en el nivel OR, válido hasta 09:40. Mejor precio, no siempre llena |
| `chase_N` | mercado solo si el cierre quedó a ≤ N ticks del nivel (N = 10/15/20/30/40) |

## Etapas

| script | entrada | salida |
|---|---|---|
| `01_estimate_cost.py` | — | costo/tamaño por schema (metadata es gratis) |
| `02_download.py` | API | `<DATA>/<schema>/NQ_<schema>_<fecha>.dbn.zst` |
| `03_build_bars.py` | ohlcv-1s DBN | `<DATA>/bars/bars_1s_<año>.parquet` |
| `04_or_events.py` | bars | `<DATA>/events/or_events.parquet` + labels 1:1 |
| `05_l2_features.py` | mbp-10, mbo | `<DATA>/features/l2_features.parquet` |
| `06_train_catboost.py` | events + features | reportes año × métrica + placebo p-value |
| `99_smoke_test.py` | — | corre 04→06 con datos sintéticos, sin API |

```bash
python -u scripts/02_download.py --schema ohlcv-1s --start 2026-03-09 --end 2026-11-01        # dry run: costo
python -u scripts/02_download.py --schema ohlcv-1s --start 2026-03-09 --end 2026-11-01 --yes  # descarga
python -u scripts/03_build_bars.py
python -u scripts/04_or_events.py
python -u scripts/06_train_catboost.py --bracket 40
```

El downloader es **resumible**: salta los días que ya tiene. Cada día es un
archivo independiente y el manifiesto queda en `<DATA>/logs/download_manifest.csv`.

## Costos medidos (NQ.v.0, 2026-09)

| schema | ventana ET | MB/sesión | $/sesión | $/año (165 EDT) | GB/año |
|---|---|---|---|---|---|
| ohlcv-1s | día completo | 2.8 | 0.184 | 30.3 | 0.5 |
| trades | 09:25-10:30 | 0.7 | 0.019 | 3.1 | 0.1 |
| mbo | 09:30-10:00 | 67 | 0.113 | 18.6 | 11 |
| mbp-10 | 09:25-10:30 | 598 | 0.279 | 46.0 | 99 |

MBO es **9× más chico por minuto que MBP-10** y más rico (orden por orden).
MBP-10 repite los 10 niveles en cada evento. El costo de MBO es que hay que
reconstruir el libro, y arrancando a las 09:30 no hay snapshot del estado previo.

## Gotchas encontrados (verificados, no teoría)

| # | Problema | Evidencia | Qué se hizo |
|---|---|---|---|
| 1 | `NQ.c.0` rola por **calendario**: el viernes de vencimiento apunta al contrato que muere | 2026-09-18: `NQ.c.0` = 0 trades, `NQ.v.0` = 13,014 en 5 min | símbolo fijado a `NQ.v.0` |
| 2 | La serie continua **salta** el spread de calendario en cada roll | 09-17 cerró 29377, 09-18 abrió 29814 (+437 pts) | nunca medir gap overnight cruzando un roll |
| 3 | `DBNStore` mapea el archivo: en Windows el rename tras descargar truena con `WinError 32` | `PermissionError` en `NQ_trades_2026-09-14.dbn.part` | `del store` + `gc.collect()` + retry con espera |
| 4 | Mezclar EDT y EST mueve la apertura de 13:30Z a 14:30Z | — | `session_days()` filtra a EDT por defecto |
| 5 | La vela OR de 09:30 en NQ mide 111-156 ticks; el M1 de ruptura cierra 75-101 ticks más allá | semana 2026-09-14 | de ahí las 3 variantes de entrada |
| 6 | Un filtro ML sobre features de **puro ruido** dio PF 2.0 / EV +8.2 con n=14 | `99_smoke_test.py` | placebo test + guard de n mínimo en el reporte |

## Honestidad estadística (lo que impide el auto-engaño)

* **Timeout a mercado**: un trade que no resuelve se marca a mercado, no a 0.
  Marcarlo plano es regalarle una opción gratis a la estrategia.
* **Segundo ambiguo**: si un mismo segundo toca TP y SL, se cobra el SL. A 1s no
  se puede saber el orden y asumir el favorable es como se fabrica EV falso.
* **Placebo test**: el filtro se compara contra sacar la misma cantidad de trades
  al azar del mismo pool. Un subconjunto chico y afortunado de un pool sin edge
  luce espectacular por sí solo.
* **Walk-forward con purga**: un modelo por año de test, entrenado solo con años
  anteriores y 5 sesiones de hueco. Nunca k-fold sobre una serie de tiempo.
* **Guard de n**: cualquier año con menos de 30 trades se marca; no pesa.
* **Baseline siempre al lado**: si el filtro no le gana al "tomar todo" OOS, es ruido.

## Credenciales

`credentials/databento.env` (gitignored) o pega la key en
`credentials/NUEVA_API_KEY.txt`, sola en su línea, sin comillas y sin `#`.
La del `.txt` gana porque es la más nueva.
