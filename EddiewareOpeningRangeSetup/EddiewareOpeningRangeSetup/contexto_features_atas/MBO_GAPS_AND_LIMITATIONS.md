# MBO GAPS AND LIMITATIONS

## Hallazgo decisivo

Los archivos son MBO crudos, pero la ventana empieza diez segundos antes de t_decision y no cruza 00:00 UTC. En consecuencia no contiene snapshot inicial: R=0 y F_SNAPSHOT=0 en los 100 archivos.

## Gaps observados

- Intervalos con salto de `sequence > 1`: 642,899.
- Unidades saltadas: 3,549,096.
- No se interpretan como paquetes perdidos: sequence es de canal/venue y el archivo está filtrado a NQ.v.0; otros instrumentos ocupan números intermedios.
- Indicador explícito de gap irrecuperable `F_MAYBE_BAD_BOOK`: 0 filas.
- Sesiones sin MBP/tape ATAS complementario: 8.

## Censura

- Izquierda: 21.88% de IDs no comienzan con ADD.
- Derecha: toda orden viva al cutoff solo puede clasificarse como superviviente durante lo observado.
- El campo quantity remaining no existe; se deriva de A/M/C cuando el estado está disponible.

## Relojes

- Databento: ts_event/ts_recv UTC nanosegundo, sequence y raw order.
- ATAS MBP/tape: hora NY a milisegundo, sin fecha dentro de fila, sin sequence, sin receive/export timestamp.
- Liquidity Burst/prediction: UTC exportado por estrategia, típicamente precisión de milisegundos.
- Zona de empate submilisegundo en el cutoff: 595 eventos; el auditor causal los excluye.
- El BookRecorder fuerza Kind=UTC cuando el DateTime no viene marcado UTC; el Kind original no se guarda, por lo que la corrección solo puede probarse empíricamente.

## Limitaciones de interpretación

- C expresa reducción de tamaño, no una causa económica. El motivo fill se infiere por emparejamiento F/C.
- M expresa precio y/o size nuevo. Qué componente cambió requiere estado previo.
- Una nueva A al mismo precio es una orden nueva, pero no prueba que sea replacement/refill del mismo participante.
- Priority no es un campo del DBN descargado; CME/Databento preservan prioridad por orden de publicación, inútil para la cola inicial sin snapshot.
- El símbolo de vencimiento raw no quedó persistido: el descargador omitió `stype_out` aunque el manifiesto lo declaraba.

## Descarga mínima correctiva

Para cada fecha que se decida conservar: solicitar GLBX.MDP3/MBO/NQ.v.0 desde 00:00:00 UTC hasta t_decision inclusive, o una API que entregue el snapshot a t0 seguido por todos los incrementales. Verificar R, F_SNAPSHOT, F_LAST, instrument_id/contrato raw, F_MAYBE_BAD_BOOK=0 y continuidad del stream antes de estudiar cola.
