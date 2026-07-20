# Protocolo congelado — puerta MBO para Liquidity Burst

Fecha de congelación: 2026-07-20, antes de calcular cualquier asociación A/B con los archivos MBO descargados.

## Pregunta

Determinar si la identidad de órdenes MBO disponible hasta el `prediction_timestamp` original separa absorción verdadera (`A_TRUE_ABSORPTION`) de breakout limpio (`B_CLEAN_BREAKOUT`) y aporta información incremental sobre el baseline causal MBP+tape.

## Muestra de viabilidad

- 30 fechas discovery: 15 A y 15 B.
- 10 fechas por año: 2022, 2023 y 2024.
- 15 BUY y 15 SELL.
- Ninguna fecha de validation/holdout se abre durante esta puerta.
- Unidad estadística: una señal/día, no cada mensaje MBO.

## Causalidad

- Solo se aceptan registros con `ts_event <= causal_cutoff_utc_inclusive`.
- Ventanas: 1, 3, 5 y 10 segundos antes del cutoff.
- No se usa ninguna respuesta posterior a la entrada como predictor.
- La etiqueta A/B se usa únicamente como respuesta estadística.
- La falta de snapshot de medianoche limita la reconstrucción de órdenes preexistentes. Supervivencia y vida se calculan únicamente para órdenes añadidas dentro de la ventana y se marcan como censuradas al cutoff.

## Features MBO predefinidas

Por ventana y alcance (`all`, banda de ±1 punto alrededor del burst, nivel burst y nivel de referencia):

- Conteo y tamaño de Add, Cancel, Modify, Trade y Fill.
- Órdenes únicas, órdenes nuevas, IDs con múltiples eventos y Add repetido.
- Cancel/Add, Fill/Add y tasa de modificaciones.
- Supervivencia observable de órdenes añadidas en ventana.
- Vida hasta primera cancelación/fill y fracción de vida corta <=100/250/500 ms.
- Reposición por nueva orden al mismo precio/lado después de cancelación/fill <=10/50/100/250 ms.
- Churn de mensajes y tamaño.
- Asimetrías alineadas con el lado atacado: pasivo vs opuesto.

## Modelos y evaluación

- Target positivo: absorción A.
- Comparaciones: `EXISTING_CAUSAL`, `MBO_ONLY`, `EXISTING_CAUSAL_PLUS_MBO`.
- Modelo primario: regresión logística regularizada, imputación mediana y estandarización dentro de cada fold.
- Validación: leave-one-year-out (LOYO) sobre 2022/2023/2024.
- Prueba de permutación: etiquetas permutadas dentro de cada año, semilla fija, mínimo 1,000 repeticiones.
- Estabilidad: AUC OOF global, por año y por dirección BUY/SELL; además signo del efecto univariado por año y dirección.

## Puerta de compra

La compra de las 40 fechas discovery restantes solo se autoriza automáticamente si se cumplen simultáneamente:

1. `MBO_ONLY` AUC LOYO >= 0.65.
2. `EXISTING_CAUSAL_PLUS_MBO` mejora el AUC del `EXISTING_CAUSAL` en al menos 0.08.
3. La mejora incremental tiene `p_permutación <= 0.10`.
4. En al menos dos de tres años, el AUC incremental no empeora y ningún año empeora más de 0.05.
5. AUC MBO por dirección BUY y SELL >= 0.55.
6. Al menos una feature MBO compacta tiene `|Cliff delta| >= 0.33`, el mismo signo en los tres años y en BUY/SELL, y `q_BH <= 0.20` dentro del catálogo compacto.

Si una condición falla, la compra se detiene. El resultado de 30 fechas se considera viabilidad, no validación final.

## Escalamiento si pasa

1. Descargar las 40 fechas restantes del discovery ya definido.
2. Reajustar el análisis usando las 70 discovery sin tocar validation/holdout.
3. Solo si la señal persiste bajo los mismos criterios, descargar las 54 fechas A/B reservadas.
4. Evaluarlas una sola vez, sin retocar features, umbrales ni modelos.

