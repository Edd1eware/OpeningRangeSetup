# CIERRE OPERATIVO — MBO SNAPSHOT 8

Fecha de cierre: 2026-07-23.  
Estado al cerrar: los archivos pasaron integridad, pero las ocho features todavía
no habían sido extraídas ni se habían calculado métricas A/B.

Este documento completa las definiciones mecánicas del preregistro
`PREREGISTRO_PILOTO_MBO_SNAPSHOT_CAUSAL_20260723.md`. No agrega predictores ni
modifica las puertas.

## Unidad causal

- Una modificación del libro sólo se considera observable al cerrar el paquete
  marcado con `F_LAST`.
- El estado inicial es el último paquete completo cuyo cierre ocurre antes de
  `t_burst`.
- Se excluye por completo el milisegundo de `t_decision`.
- Un evento cuyo timestamp cae dentro de una ventana sólo se contabiliza si el
  cierre de su paquete también ocurre antes del fin exclusivo de esa ventana.
- Los `A` sintéticos del snapshot reconstruyen el libro, pero no se tratan como
  flujo incremental ni como refill.

## Coordenadas y agresión

- BUY: lado atacado `A` y agresor esperado `B`.
- SELL: lado atacado `B` y agresor esperado `A`.
- `L0:L2` son los tres mejores niveles del lado atacado en el último paquete
  completo anterior a `t_burst`.
- El bloque y `L0` permanecen fijos durante la ventana.
- El volumen agresor de `impact_efficiency_250ms` usa `T` del agresor esperado
  en o más allá de `L0` en la dirección del burst.

## Fills, cancelaciones y modificaciones

- `F` es fill explícito y aporta su `size` a consumo.
- `C` se considera cancelación pura únicamente cuando no existe `F` con la
  misma clave `(order_id, ts_event, price)`.
- Si la clave contiene `F` y `C`, el `C` actualiza el libro pero no vuelve a
  contarse como retirada.
- Una diferencia de cantidad en una clave `F/C` se marca ambigua y el `C`
  completo queda excluido de retirada pura.
- `M` actualiza el tamaño total visible. Una reducción no se llama cancelación
  pura; un incremento sí puede aportar refill.

## Emparejamiento de refill

- Cada `F` o `C` puro de `L0:L2` crea un lote de liquidez removida.
- Un `A` incremental o incremento neto de `M` en el mismo precio puede reponer
  ese lote si su paquete cierra como máximo 100 ms después.
- El emparejamiento es FIFO y está limitado por la cantidad removida pendiente,
  por lo que una adición no puede reponer dos veces el mismo contrato.
- El refill emparejado queda asociado a la orden que lo muestra.
- Para no sobrestimar supervivencia, cualquier reducción posterior de esa orden
  consume primero la porción atribuida a refill.
- “Durable” significa que la porción emparejada sigue visible en el instante de
  observación causal correspondiente.

## Definiciones de trayectoria

- `impact_efficiency_250ms` usa el avance direccional positivo del mejor precio
  pasivo atacado al final causal de 250 ms respecto a `L0`.
- Si no hay `T` agresor, el denominador mínimo equivale a un contrato dividido
  por la profundidad inicial.
- En cada fold LOYO, sólo `impact_efficiency_250ms` se limita a
  `[0, percentil 99 del entrenamiento]`; el límite nunca se estima con el año
  evaluado.
- `depletion_persistence_share_500ms` integra el tiempo durante el cual la
  profundidad agregada del `L0` original es cero, usando estados posteriores a
  cierres `F_LAST`.

## Motifs

- Un paquete de agresión contiene al menos un `F` del lado atacado en `L0:L2`.
- Un paquete de retirada contiene al menos un `F` o `C` puro en `L0:L2`.
- Sólo entran al denominador paquetes con 100 ms completos de observación antes
  del cutoff y antes de 500 ms.
- Motif de absorción: aparece refill emparejado que sigue vivo al final de esos
  100 ms y el mejor precio pasivo no avanza un tick en la dirección del burst.
- Motif de breakout: el `L0` original permanece vacío al menos 50 ms, el mejor
  precio pasivo avanza al menos un tick y no existe refill durable durante los
  100 ms.

## Estabilidad de mecanismo

Las seis celdas son:

```text
2022 BUY, 2022 SELL, 2023 BUY, 2023 SELL, 2024 BUY, 2024 SELL
```

Se excluye `consumption_initial_depth_ratio_250ms` de la dirección porque el
preregistro no le asignó signo inequívoco. Para las otras siete features se
compara la media A menos la media B dentro de cada celda.

Una celda es coherente cuando al menos cuatro de siete signos coinciden con la
hipótesis congelada. La puerta “5/6” exige cinco celdas coherentes.

## Evaluación congelada

- Casos de entrenamiento/evaluación: sólo A y B, `n=70`.
- C no se usa para entrenar, seleccionar, imputar, estandarizar ni fijar caps.
- Modelo: regresión logística `C=0.2`, `class_weight=balanced`.
- Validación: LOYO 2022/2023/2024.
- Imputación, escalado, selección de columnas no constantes y cap se calculan
  dentro de cada fold.
- Permutación: 1,000 repeticiones, etiquetas permutadas dentro de año.
- Bootstrap estratificado: 1,000 repeticiones.
- Bloques comparados:
  `MATRIX_TRANSITIONS`, `MBO_SNAPSHOT_8` y
  `MATRIX_TRANSITIONS_PLUS_MBO_SNAPSHOT_8`.
- Las seis transiciones MATRIX son exactamente las congeladas por soporte sin
  etiquetas en la corrida anterior; no se vuelven a minar.
- CatBoost queda fuera del veredicto primario.
