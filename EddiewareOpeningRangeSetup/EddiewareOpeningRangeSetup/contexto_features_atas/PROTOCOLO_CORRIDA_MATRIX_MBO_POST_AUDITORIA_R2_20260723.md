# Protocolo de corrida — MATRIX + MBO post-auditoría R2

Fecha de congelación: 2026-07-23  
Propuesto por: Codex  
Estado: preparado; lanzamiento bloqueado hasta autorización explícita del usuario.

## Pregunta científica

Después de detectar el Liquidity Burst, ¿las representaciones causales agregadas de:

1. actividad MBO anterior o igual a `t_decision`; y
2. estados/transiciones DOM+tape entre `t_burst` y `t_decision`

aportan separación temporalmente estable entre `A_TRUE_ABSORPTION` y
`B_CLEAN_BREAKOUT`?

`C_MIXED_PATH` se conserva como diagnóstico de abstención. No se usa para
redefinir A/B ni para rescatar un resultado débil.

## Puerta de capacidad MBO ya ejecutada

Veredicto: **B. SIRVEN PARCIALMENTE.**

- 100 DBN MBO crudos.
- 1,274,719 registros.
- 621,262 IDs de orden sumados por archivo.
- 78.12% de los IDs comienzan con `A` dentro de la ventana.
- 21.88% están censurados por la izquierda.
- Snapshot inicial `R/F_SNAPSHOT`: 0.
- `F_MAYBE_BAD_BOOK`: 0.
- 595 eventos posteriores al timestamp nominal, pero dentro del milisegundo
  final solicitado: excluidos conservadoramente.
- Eventos en o después de `end_utc_exclusive`: 0.
- 97.45% de los grupos de fill pudieron reconciliar su efecto visible mediante
  `C` agregado o `M` consistente con estado.

Fuentes:

- `MBO_DATA_CAPABILITY_AUDIT.md`
- `MBO_SCHEMA_INVENTORY.csv`
- `MBO_FIELD_COVERAGE.csv`
- `MBO_SESSION_QUALITY.csv`
- `MBO_EVENT_RECONCILIATION_SAMPLE.csv`
- `MBO_GAPS_AND_LIMITATIONS.md`

## Alcance congelado

- 100 sesiones discovery: 2022 = 34, 2023 = 37, 2024 = 29.
- A = 29, B = 41, C = 30.
- BUY = 47, SELL = 53.
- Validación y holdout permanecen cerrados.
- Replay X10 únicamente; X1 deshabilitado.
- Diez sesiones terminales capturadas antes de la pausa se conservan porque no
  cambia el detector, exportador, DLL ni definición temporal. Solo cambia la
  semántica offline de reconciliación MBO y el reporte de limitaciones.

## Política causal

### MBO

- Se conserva el orden físico del DBN mediante `raw_ordinal`.
- Ordenación: `ts_event`, `sequence`, `raw_ordinal`, estable.
- Predictor permitido únicamente si `ts_event <= causal_cutoff_utc_inclusive`.
- Los 595 eventos de la fracción restante del milisegundo final se excluyen.
- No se redondea `ts_event` antes de filtrar.
- No se utiliza posición inicial de cola, volumen delante ni prioridad exacta.

### MATRIX DOM+tape

- Solo eventos con `t_burst <= CausalTimestampUtc <= t_decision`.
- Estados de 100 ms, transiciones y secuencias.
- La unión con MBO se realiza por `BurstId` después de construir ambos bloques
  por separado.
- No se afirma precedencia submilisegundo MBO↔ATAS: los relojes/feed no tienen
  correspondencia evento a evento suficiente.

### Outcomes

MAE, MFE, TP, SL, PnL, WR, PF y resultado del trade no entran como predictores.
La etiqueta A/B se incorpora después de construir MATRIX y MBO.

## Semántica F/C corregida

No se emparejan filas F y C una a una. CME puede emitir varios `F` unitarios y
una sola `C` agregada.

La clave de reconciliación es:

`order_id + ts_event + price`

Clasificación:

- `EXACT_GROUP_FILL_C_MATCH`: suma F = suma C.
- `AMBIGUOUS_FILL_C_QUANTITY_MISMATCH`: existe F y C, pero las cantidades no
  coinciden; no se clasifica como cancelación pura.
- `FILL_WITHOUT_C_SAME_KEY`: fill cuyo efecto puede aparecer mediante `M`.
- `C_WITHOUT_FILL_SAME_KEY`: cancelación pura inferida.

La causa económica de `C` sigue siendo inferida, no explícita.

## Doce predictores MBO congelados

No se añaden features después de la auditoría.

| Predictor | Estado informativo | Interpretación permitida |
| --- | --- | --- |
| `burst_w1_passive_add_size` | Explícito | Tamaño A mostrado |
| `burst_w1_passive_pure_cancel_size` | Inferido | C sin F en la misma clave |
| `burst_w1_passive_fill_size` | Explícito | F de órdenes reposantes |
| `burst_w1_new_order_survival_share` | Inferido/censurado | Solo A nacidas en ventana |
| `burst_w1_short_lived_250ms_share` | Inferido/ciclos completos | A y salida observadas |
| `burst_w1_refill_100ms_share` | Inferido a nivel | Nueva A mismo lado/precio; no mismo participante |
| `burst_w3_cancel_to_add_size` | Mixto | C inferida frente a A explícita |
| `near_w1_add_size_side_imbalance` | Explícito derivado | Asimetría A |
| `near_w1_pure_cancel_size_side_imbalance` | Inferido | Asimetría C sin F |
| `near_w1_fill_size_side_imbalance` | Explícito derivado | Asimetría F |
| `near_w3_orderbook_message_rate` | Mixto | A/M explícitos y C inferida |
| `near_w3_reuse_order_id_share` | Explícito en ventana | Repetición de mensajes, no identidad de participante |

## Combinaciones congeladas

1. `MATRIX_TRANSITIONS`
2. `MATRIX_SEQUENCES`
3. `MATRIX_TRANSITIONS_SEQUENCES`
4. `MBO_CORE`
5. `MATRIX_TRANSITIONS_PLUS_MBO_CORE`
6. `MATRIX_SEQUENCES_PLUS_MBO_CORE`
7. `MATRIX_TRANSITIONS_SEQUENCES_PLUS_MBO_CORE`

No habrá búsqueda exhaustiva de combinaciones.

## Validación

- Regresión logística fija `C=0.2`, clases balanceadas.
- Imputación y escalado dentro del fold.
- LOYO 2022/2023/2024.
- 1,000 permutaciones dentro de año.
- 1,000 bootstraps estratificados.
- Balanced accuracy, ROC AUC, sensibilidad A, especificidad B.
- Estabilidad por año y BUY/SELL.
- C fuera del ajuste A/B.

## Interpretación

Discovery solo puede concluir:

- `NO_SUPERA_PUERTA_DISCOVERY`; o
- `PROMETEDORA_DISCOVERY`.

Aunque sea prometedora, esta corrida no puede emitir una afirmación definitiva
de capacidad porque no contiene validación sellada y el MBO tiene capacidad B
parcial.

El último Telegram comenzará con:

`NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO`

y especificará que falta validación temporal sellada, snapshot inicial para
estado/cola completos y reloj común si se pretende afirmar precedencia
submilisegundo MBO-DOM-tape.

### Ampliación condicional autorizada

Si la combinación con MBO supera la puerta discovery y mejora al mejor bloque
individual, queda autorizada la preparación/descarga de la muestra adicional
hasta 2022-04-04 bajo estas condiciones:

- excluir feriados oficiales de CME;
- excluir feriados de mercado/federales de EE. UU. que dejen NQ cerrado o con
  sesión no comparable;
- verificar actividad real del contrato NQ y descartar sesiones vacías o
  anormalmente cortas;
- mantener la nueva muestra sellada hasta congelar manifiesto, costo y hashes;
- descargar solo las ventanas causales necesarias;
- no usar las nuevas etiquetas para volver a seleccionar combinaciones.

## Entregables finales

- Auditoría causal MATRIX.
- Auditoría del join MBO/MATRIX.
- Manifiesto de features con columna explícito/inferido/censurado.
- Métricas de las siete combinaciones.
- Predicciones LOYO.
- Intervalos bootstrap y permutaciones.
- Gráfica comparativa.
- Etiqueta Telegram con las tres combinaciones más efectivas.
- Veredicto final y variables/evidencia faltantes.

## Bloqueo de lanzamiento

El runner requiere `--authorized-launch`.

Sin ese parámetro:

- no se toca Telegram;
- no se abre/reinicia ATAS;
- no se inicia Replay;
- no cambia el estado de la corrida.

El parámetro solo se utilizará después de recibir autorización explícita del
usuario en esta conversación.
