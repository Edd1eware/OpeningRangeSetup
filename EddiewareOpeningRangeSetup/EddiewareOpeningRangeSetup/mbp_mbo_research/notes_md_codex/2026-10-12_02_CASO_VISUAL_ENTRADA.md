# Caso visual: entrada del 12 de octubre de 2026

El usuario identificó la operación de la captura como su entrada de hoy. Se conserva una copia sin editar en `C:/Users/k_99_/Documents/ChatGPT/research_edge/references/2026-10-12_entrada_ATAS_con_precios.png`.

## Lo que se puede leer

- Operación short.
- VWAP roja y descendente al señalarse la operación; después cambia a azul. No inferir de ese cambio posterior una condición nueva de gestión.
- SL marcado en30,977.50.
- TP marcado en30,947.50.
- La entrada blanca está alrededor de30,962.50. Este precio es también el punto medio matemático del SL y TP y es compatible con el RR1:1 declarado.
- Riesgo y objetivo:15puntos por lado,60ticks por lado con tickNQ0.25.
- En la vela junto a la zona de riesgo aparece la fila de venta85×70 resaltada. Su comparación diagonal toma85 contra18 de la fila superior42×18:ratio4.7222. No compararla contra70 de la misma fila.
- No hace falta que haya un stack de niveles consecutivos: el usuario confirmó que acepta imbalances separados.

## Lo que todavía no queda validado

- Hora y precio exactos del fill, cantidad de contratos y costes.
- Precio preciso de cada fila y offset del agrupamiento, porque la captura no rotula todos los niveles.
- Correspondencia exacta de la vela de señal con el primer candidato del motor.
- Reconstrucción numérica del día: la carpeta local de datos termina el2026-10-09 y no contiene el2026-10-12.

Este caso sirve para comprobar fidelidad visual y reglas. No se añade como trade independiente al backtest sin datos verificables ni se usa para ajustar parámetros por el resultado observado.
