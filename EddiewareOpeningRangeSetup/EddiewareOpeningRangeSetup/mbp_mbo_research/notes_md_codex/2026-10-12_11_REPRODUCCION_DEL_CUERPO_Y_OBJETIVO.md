# Reproducir la operativa para automatizarla

Fecha: 2026-10-12.

El usuario aclaró que el objetivo práctico es automatizar su operativa para reducir decisiones emocionales. El WR de al menos 60% es una estimación de su experiencia. No se ha aportado un historial de operaciones que permita comprobar ese porcentaje ni reproducir su selección discrecional exactamente.

La secuencia acordada posteriormente es: navegador para revisar las entradas y la resolución TP/SL; después portar la misma lógica a C# y contrastarla en ATAS; finalmente convertirla en un indicador con propuestas de entrada, SL y TP para confirmación manual. No se ha creado ni instalado un indicador ni activado órdenes.

## Aclaración que faltaba en el motor

Se permite que la vela abra fuera del OR, pero el cuerpo debe ir estrictamente a favor:

- Compra: cierre por encima del high del OR y cierre mayor que apertura.
- Venta: cierre por debajo del low del OR y cierre menor que apertura.
- Doji o cuerpo contrario no cumple; seguir esperando hasta las 09:40.

La referencia anterior comprobaba el cierre fuera, pero no la dirección del cuerpo. Se conserva como historial y se crea `body_direction_1r` por separado, sin optimizar filtros o parámetros para alcanzar el 60%.

## Reproducción corregida

150 sesiones disponibles, del 9 de marzo al 9 de octubre de 2026, todas observadas. RR 1:1 y los mismos costes del estudio anterior.

| Referencia | Trades | TP / SL | WR | PF neto, 1 NQ fijo | PF neto en R |
|---|---:|---:|---:|---:|---:|
| Anterior: cierre fuera, sin dirección del cuerpo | 82 | 34 / 48 | 41.46% | 0.5882 | 0.5554 |
| Actual: cierre fuera y cuerpo a favor | 81 | 34 / 47 | 41.98% | 0.5913 | 0.5680 |

Sólo cambia el 24 de junio, cierre 09:39 NY: era un largo de cuerpo bajista, apertura 29804.25 y cierre 29760.75, que acabó en SL. No hay señal posterior válida hasta las 09:40. Las otras 81 entradas coinciden en 34 campos con la referencia anterior; no se retiran pérdidas o fechas por el resultado.

Resultado neto del replay actual: −1,286.8 ticks, −24.6414R, equivalente a −USD6,434 con un NQ fijo. No hay operaciones censuradas ni timeout. Los dos casos previamente señalados cuyo primer print ya está sobre/más allá del SL permanecen visibles para revisión; no se eliminan del resultado principal.

Esto mide el modelo actual y sus supuestos, no el historial real del usuario. La aclaración del cuerpo resuelve un error concreto; la diferencia restante con su experiencia requiere localizar casos donde la selección, el footprint, la rejilla, el stop o la ejecución no coincidan con lo que él opera.

Código nuevo: `C:/Users/k_99_/Documents/ChatGPT/research_edge/scripts/body_direction_replay.py`. Nueve pruebas de dirección, doji, espera, simetría, máximo diario y causalidad pasan. El manifiesto verifica 7 referencias, 150 fuentes y 8 salidas. Código y resultados anteriores se conservan intactos.

Salidas: `C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs/body_direction_replay/`. Flujo de trabajo: `C:/Users/k_99_/Documents/ChatGPT/research_edge/REVIEW_WORKFLOW.md`.
