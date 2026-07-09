# LVN Retest Research Engine — especificación implementada (2026-07-08)

> **Actualización 2026-07-08 (2):** la dirección ya NO se asigna por procedencia del toque.
> Se asigna por **aceptación/rechazo de valor** en la zona LVN (H7 implementada, ver sección
> "Dirección por aceptación/rechazo").

## Interpretación de la imagen

El perfil 08:30–09:30 mostrado es aproximadamente simétrico y unimodal: debe recibir probabilidad
alta de forma **D**, que representa balance y ausencia de dirección tendencial clara. Una forma
**P** (masa arriba y cola inferior) aporta contexto alcista; una forma **b** (masa abajo y cola
superior) aporta contexto bajista. Esto es una hipótesis a medir, no un filtro.

El LVN del primer minuto se estudia en todos los perfiles, incluidos D. P/b/D se conservan como
cohortes para comparar frecuencia, WR y R:R sin selección visual.

## Causalidad

| Elemento | Datos permitidos |
|---|---|
| Perfil contextual | `[08:30:00, 09:30:00)` ET |
| Perfil LVN | `[09:30:00, 09:31:00)` ET |
| Revelación de línea verde | `09:31:00` ET |
| Retests | `[09:31:00, 09:40:00)` ET |
| Outcomes | desde el retest hasta antes de `09:40:00` ET |

El indicador ATAS nunca dibuja la línea antes de 09:31. El script Python reconstruye el perfil una
sola vez con el primer minuto y no lo modifica con datos del retest.

## Definición reproducible de LVN

Para un nivel `p`, se calcula el promedio de volumen de los `N` niveles inferiores y superiores.
Califica cuando:

1. existen `N` vecinos a ambos lados;
2. `volume[p] < left_neighbor_mean` y `volume[p] < right_neighbor_mean`;
3. `volume[p] / min(left_mean, right_mean) <= lvn_max_percent_of_neighbors`;
4. `volume[p] >= min_lvn_volume`;
5. `volume[p] / POC_volume <= max_lvn_volume_percent_of_poc`.

Niveles adyacentes que califican se agrupan en un LVN; el precio representativo es el de menor
volumen. El indicador muestra solo el candidato más profundo para no ensuciar el chart. El dataset
guarda todos.

## Formas y probabilidades

Se guardan `prob_D`, `prob_P`, `prob_b`, `prob_double`, `prob_trend_up`, `prob_trend_down` y
`prob_unknown`; suman 1. Se derivan matemáticamente de balance superior/inferior, posición del POC,
centro de masa, skewness, slope, entropía, número de modos, separación y profundidad del valle.

Estas son **probabilidades de similitud con prototipos**, no probabilidades calibradas de ganar.
CatBoost podrá usar el vector continuo sin depender de una etiqueta rígida.

## Precisión de retest y outcome

- `TICK`: orden exacto; outcome desde el tick del toque.
- `BAR_UNORDERED`: el high/low prueba el toque pero no su orden intrabar. Para evitar inventarlo,
  el outcome comienza en la siguiente barra (`NEXT_BAR_CAUSAL_CONSERVATIVE`).
- Si TP y SL aparecen en la misma barra sin orden observable, el resultado es `AMBIGUOUS`, nunca se
  fuerza una victoria o derrota.

Los casos sin procedencia observable permanecen `UNKNOWN_DIRECTION` y no se borran.

## Dirección por aceptación/rechazo de valor (reemplaza dirección por procedencia)

La zona LVN es `[low_price - tolerancia, high_price + tolerancia]` del nodo completo. Tras el
toque, el primer `close` que confirma una de dos salidas define el evento:

| Interacción | Condición (close) | Lógica | Desde arriba | Desde abajo |
|---|---|---|---|---|
| `ACCEPTANCE` | atraviesa TODA la zona: cruza el borde **lejano** + `resolution_confirm_ticks` | `CONTINUATION` | SHORT | LONG |
| `REJECTION` | frena y regresa: cruza de vuelta el borde **cercano** + `resolution_confirm_ticks` | `REVERSAL` | LONG | SHORT |
| `UNRESOLVED` | la ventana 09:40 termina sin confirmar ninguna | `NONE` | UNKNOWN | UNKNOWN |
| `UNKNOWN_APPROACH` | procedencia no observable | `NONE` | — | — |

Reglas causales:

1. La dirección se asigna en el instante de confirmación, nunca en el toque.
2. El outcome (MFE/MAE/TP/SL) empieza en la confirmación y se mide desde `entry_price`
   (= close confirmante), no desde el precio del LVN. En `BAR_UNORDERED` el outcome
   empieza en la barra siguiente a la confirmación (misma política conservadora).
3. `UNRESOLVED`/`UNKNOWN_APPROACH` quedan como `UNKNOWN_DIRECTION` en los brackets.
4. La hipótesis vieja por procedencia se conserva como columna `approach_hypothetical_side`
   para comparar cohortes; ya no gobierna el outcome.

Columnas nuevas en `LVN_Events`: `lvn_interaction`, `trade_logic`, `lvn_zone_low`,
`lvn_zone_high`, `entry_price`, `entry_time_et`, `seconds_touch_to_entry`,
`entry_distance_from_lvn_ticks`, `zone_speed_ticks_per_second` (velocidad toque→confirmación) y
`deceleration_ratio` (velocidad en zona / velocidad de aproximación). Las velocidades se capturan
continuas; los umbrales "normal/rápida/alta" de H7 se derivan después, era-blind.

`Summary` agrega cohortes `Interaction cohort` (WR/R por `lvn_interaction`) e
`Interaction x shape`.

## Actualización 2026-07-08 (3): ADN de winners, agresión y replay corto

**Outcome extendido** (por evento, medido desde entry):
`mae_before_mfe_ticks` (adverso sobrevivido antes de la máxima extensión),
`max_pullback_before_mfe_ticks` (retroceso máximo desde el pico favorable rumbo al MFE),
`rr_max_achievable` (MFE / max(mae_before_mfe, 1 tick)), `time_to_mfe_seconds` (ya existía:
cuánto tarda en llegar a su máxima extensión).

**Agresión** (confirmación por speed + imbalances, decisión 2026-07-08 — solo features útiles
para volume profile: delta, delta change, volume, imbalances, speed, vPOC/VAH/VAL):
`tape_speed_trades_per_second` (requiere columna `bar_trades` del export nuevo),
`aggression_volume_per_second`, `aggression_delta_per_second`, `delta_touch_bar`,
`delta_prev_bar`, `delta_change_touch_bar` + los imbalances apilados ya existentes.
vPOC/VAH/VAL cubiertos por las distancias contextuales y del minuto.

**Indicador (DLL 039EFBE0)**: hasta 3 áreas LVN dibujadas (`Max LVN Areas`, default 3;
LVN1 = más profundo, línea gruesa) — fase research recolecta ADN de las 3 zonas; export CSV
agrega columna `bar_trades` (trades por barra). Requiere reiniciar ATAS para cargar.

**Replay corto (default nuevo)**: ventana `09:29–09:42` — el contexto 08:30–09:30 se lee de
las barras históricas que ATAS carga al abrir el replay; ~5x más rápido por fecha. Paridad
verificable con `compare_context_parity.py` (captura FULL 08:29 vs SHORT 09:29). Si la
historia no trae contexto, el runner avisa (`context_ok=False`) y se regresa a
`--replay-from 08:29`.

Parámetro nuevo: `--resolution-confirm-ticks` (default 1) = ticks más allá del borde de zona
para confirmar aceptación o rechazo.

## WR y R:R reportados

- `wr_X_X_all`: TP dividido entre todos los eventos de la cohorte.
- `wr_X_X_resolved`: TP / (TP + SL), excluyendo `TIME_EXIT`, `AMBIGUOUS` y dirección desconocida.
- `realized_r_X_X`: +1 para TP, -1 para SL y retorno al cierre de 09:40 escalado por el riesgo para
  `TIME_EXIT`.
- `mfe_mae_ratio`: excursión favorable / adversa; se reporta además MFE y MAE por separado.
- `Monthly occurrence`: días con LVN, nodos, nodos retesteados y eventos por mes.

## Input admitido

CSV o Parquet en formato largo:

- requerido: `timestamp` (o `ts_event`, o `date` + `time`) y `price`;
- volumen: `bid_volume` + `ask_volume`, o `volume`/`size`;
- opcional: OHLC, `side`, símbolo, big trades, iceberg y absorción;
- timestamps con offset se convierten a New York; timestamps naive usan `--input-timezone`;
- epoch numérico se interpreta como UTC.

Los archivos MBP de libro no sustituyen ejecuciones/footprint: sirven para profundidad, no para
construir volumen negociado por precio.

## Ejecución

```powershell
python detect_lvn_retest_events.py `
  --input "data\*.parquet" `
  --output "lvn_retest_results.xlsx" `
  --tick-size 0.25
```

Dependencias: `pandas`, `numpy`, `pyarrow` para Parquet y `openpyxl` para Excel.

## Outputs

| Hoja/CSV | Contenido |
|---|---|
| `Daily_Profile` | métricas completas 08:30–09:30 y 09:30–09:31 |
| `LVN_Profile` | cada LVN detectado, incluso sin retest |
| `LVN_Events` | todos los episodios de retest y outcomes |
| `Summary` | frecuencia, cohortes D/P/b, WR y R:R por mes/target |
| `No_Retest` | días con LVN pero sin toque antes de 09:40 |
| `Debug` | archivos, candidatos aceptados/rechazados y razón |

Cada hoja también se exporta a CSV en `<nombre_salida>_csv`.

