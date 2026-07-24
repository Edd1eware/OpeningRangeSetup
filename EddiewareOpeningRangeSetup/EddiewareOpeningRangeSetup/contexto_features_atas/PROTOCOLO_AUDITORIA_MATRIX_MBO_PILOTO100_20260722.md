# Protocolo previo — MATRIX + MBO CLASSIFICATION TEST, piloto 100

Fecha de congelación: 2026-07-22  
Propuesto por: Codex  
Estado inicial: protocolo registrado antes del replay y antes de observar el resultado combinado.

## Pregunta única

Después de detectar el Liquidity Burst, ¿la combinación causal de:

1. identidad y ciclo de vida MBO anterior a `t_decision`; y
2. estados, transiciones y secuencias DOM+tape entre `t_burst` y `t_decision`

permite separar `A_TRUE_ABSORPTION` de `B_CLEAN_BREAKOUT` de forma temporalmente estable, sin usar MAE, MFE, TP, SL, PnL ni eventos posteriores a `t_decision`?

`C_MIXED_PATH` se conserva como diagnóstico de ambigüedad y abstención; no se usa para redefinir A o B ni para rescatar un modelo débil.

## Muestra congelada

- Manifiesto: `DATABENTO_MBO_PILOTO_100_DISCOVERY_20260722.csv`.
- Cien sesiones únicas: 2022 = 34, 2023 = 37, 2024 = 29.
- Familias: A = 29, B = 41, C = 30.
- Dirección: BUY = 47, SELL = 53.
- Las cien fechas pertenecen únicamente a `discovery`.
- Se reutilizan 30 archivos ya comprados y se descargan 70 ventanas nuevas.
- Validación 2024–2025 y holdout 2025–2026 permanecen cerrados y no se descargan en este piloto.
- Ventana MBO comprada por sesión: 10.001 s; costo incremental estimado por Databento para las 70 ventanas nuevas: USD 4.172687928377.

## Evidencia real sobre el MBO existente

La auditoría directa de los 30 archivos iniciales encontró 360,695 registros DBN MBO crudos. El esquema real contiene:

`ts_recv`, `ts_event`, `rtype`, `publisher_id`, `instrument_id`, `action`, `side`, `price`, `size`, `channel_id`, `order_id`, `flags`, `ts_in_delta`, `sequence`, `symbol`.

Acciones observadas:

- `A` ADD: 137,402;
- `C` CANCEL: 140,194;
- `M` MODIFY: 44,733;
- `F` FILL: 22,788;
- `T` TRADE: 15,578.

El 100% de los grupos de secuencia que contienen `F` también contiene el `T` asociado. Se observó resolución real inferior al microsegundo en `ts_event`. No hubo `order_id=0`, nulos ni registros marcados con `F_MAYBE_BAD_BOOK`.

### Censura del estado inicial

No se observó ningún registro `R` de limpieza/snapshot ni la bandera `F_SNAPSHOT`. En los 30 archivos:

- órdenes únicas por archivo: 164,056;
- ciclo que comienza con `A` dentro de la ventana: 137,402, equivalentes a 83.7531%;
- ciclo ya iniciado antes de la ventana: 26,654, equivalentes a 16.2469%.

Consecuencia: sí puede reconstruirse causalmente el ciclo incremental de una orden cuya alta aparece dentro de la ventana. No puede reconstruirse de forma íntegra el estado inicial, la prioridad inicial de cola ni la cantidad original de órdenes censuradas por la izquierda. No se imputarán esos datos ni se presentarán como observados.

## Campos utilizables y límites

| Campo necesario | Disponible | Campo real | Política |
| --- | ---: | --- | --- |
| Identidad de orden | Sí | `order_id` | Identidad real, anonimizada solo al reportar ejemplos |
| ADD | Sí | `action=A` | Utilizable |
| CANCEL | Sí | `action=C` | Separar cancelación pura de la `C` emparejada con fill |
| MODIFY/REPLACE | Sí | `action=M` | Utilizable |
| FILL | Sí | `action=F`, asociado con `T` | Utilizable |
| Cantidad original | Parcial | `size` en `A` | Solo si el `A` aparece dentro de la ventana |
| Cantidad restante | Derivable parcialmente | secuencia A/M/F/C | Solo para ciclos no censurados |
| Precio | Sí | `price` | Utilizable |
| Lado BID/ASK | Sí | `side` | Utilizable según semántica de cada acción |
| Exchange timestamp | Sí | `ts_event` | Reloj causal principal |
| Resolución temporal | Sí | nanosegundos | Conservar sin redondear al unir |
| Secuencia del feed | Sí | `sequence` | No interpretar saltos como pérdida tras filtrar un instrumento |
| Posible libro inválido | Sí | bit `F_MAYBE_BAD_BOOK` de `flags` | Rechazar archivo si aparece |
| Tape asociado | Sí | `action=T` | Emparejamiento por archivo y secuencia |
| Agresora/pasiva | Sí, por semántica | `F` reposante y `T` agresora | No inferir desde snapshots |
| Profundidad/nivel | Parcial | precio de cada orden | Sin número explícito de nivel ni estado inicial completo |
| Prioridad/posición de cola | No explícita | — | No usar como predictor en este piloto |

## Ventanas causales congeladas

### MBO

- Solo `ts_event <= causal_cutoff_utc_inclusive`.
- Ventanas de 1, 3, 5 y 10 segundos previas al cutoff.
- El extractor vuelve a filtrar después de leer el DBN.
- Cualquier registro posterior al cutoff hace fallar la auditoría.

### Matriz DOM+tape

- Solo `t_burst <= CausalTimestampUtc <= t_decision`.
- Estados físicos de 100 ms.
- Ningún outcome se incorpora antes de construir estados, transiciones y secuencias.
- La identidad MBO no se atribuye a MBP ni a snapshots agregados.

## Representaciones congeladas

No se hará búsqueda exhaustiva de interacciones. Se compararán únicamente:

1. `MATRIX_TRANSITIONS`;
2. `MATRIX_SEQUENCES`;
3. `MATRIX_TRANSITIONS_SEQUENCES`;
4. `MBO_CORE`;
5. `MATRIX_TRANSITIONS_PLUS_MBO_CORE`;
6. `MATRIX_SEQUENCES_PLUS_MBO_CORE`;
7. `MATRIX_TRANSITIONS_SEQUENCES_PLUS_MBO_CORE`, representación primaria.

Las doce features `MBO_CORE` ya estaban congeladas antes de este piloto. Las transiciones y secuencias se seleccionan por soporte/frecuencia sin mirar la etiqueta A/B. No se crearán ratios después de observar correlaciones con el outcome.

## Validación y controles contra sobreajuste

- Modelo único principal: regresión logística, `C=0.2`, clases balanceadas.
- Imputación mediana y escalado se ajustan solo en el fold de entrenamiento.
- Predicción fuera de año mediante LOYO 2022/2023/2024.
- Permutación de etiquetas dentro de cada año, 1,000 repeticiones.
- Bootstrap de balanced accuracy, 1,000 repeticiones.
- Reportes separados por año y BUY/SELL.
- Métricas: balanced accuracy, ROC AUC, sensibilidad de A, especificidad de B y cobertura.
- A y B se unen por `BurstId` después de construir predictores.
- C queda fuera del ajuste A/B y se publica como diagnóstico de abstención.
- WR y PF no son métricas de separación y no se usarán para aprobar la hipótesis.

## Puerta científica del piloto

Una combinación será marcada `PROMETEDORA_DISCOVERY` solo si cumple simultáneamente:

- al menos 60 casos A/B;
- balanced accuracy LOYO >= 0.65;
- ROC AUC LOYO >= 0.68;
- sensibilidad A >= 0.60;
- especificidad B >= 0.60;
- límite inferior bootstrap de balanced accuracy > 0.55;
- permutación por año `p <= 0.05`;
- desempeño >= 0.55 en cada año y en BUY/SELL con muestra suficiente;
- la combinación principal mejora al mejor bloque individual en al menos 0.03 de balanced accuracy o AUC.

Estas condiciones solo autorizan considerar la compra de las fechas de validación. No autorizan declarar capacidad definitiva.

## Regla del veredicto final

En este piloto, las 100 fechas son discovery. Por diseño:

- un resultado débil produce `NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO`;
- un resultado fuerte produce `PROMETEDOR_DISCOVERY`, pero el Telegram final sigue diciendo `NO SOY CAPAZ...` y explica que falta validación temporal sellada;
- `SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO` solo puede emitirse después de superar una muestra sellada no usada para seleccionar combinaciones, con estabilidad por año y BUY/SELL.

## Telegram congelado

El primer mensaje debe indicar `MATRIX + MBO CLASSIFICATION TEST`, la pregunta científica, límites causales, censura inicial MBO y ausencia de validación sellada.

Al terminar el análisis se enviará:

`ETIQUETA MATRIX+MBO | combinaciones más efectivas`

con `n`, balanced accuracy LOYO, ROC AUC, sensibilidad A, especificidad B, intervalo bootstrap, permutación y estabilidad por año/dirección. La etiqueta no mostrará WR/PF como sustituto de esas métricas.

El último mensaje será exactamente uno de:

- `NO SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO`
- `SOY CAPAZ DE SEPARAR UNA ABSORCION DE UN BREAKOUT LIMPIO`

seguido, cuando corresponda, por la evidencia que falta.

## Condiciones que bloquean el replay

La auditoría de diseño debe fallar y no lanzar ATAS si ocurre cualquiera de estas condiciones:

- no existen 100 DBN válidos o algún archivo no corresponde a su manifiesto;
- aparece `F_MAYBE_BAD_BOOK`;
- hay duplicados de fecha o `BurstId`;
- entra una fecha de validación u holdout;
- no se encuentra el ledger MBP causal requerido para precio, lado y referencia;
- DLL instalada y DLL compilada no coinciden;
- el detector no es v7 o exporta eventos fuera de `[t_burst, t_decision]`;
- el análisis permite outcomes entre predictores;
- la carpeta de resultados no es aislada;
- Telegram no contiene la etiqueta y el veredicto congelados.

