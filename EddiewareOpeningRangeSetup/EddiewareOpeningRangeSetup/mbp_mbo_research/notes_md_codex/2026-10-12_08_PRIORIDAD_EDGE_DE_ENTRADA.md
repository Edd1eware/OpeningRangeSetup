# Prioridad: edge de entrada antes de mejoras

El usuario pidió apartar temporalmente el feature que perjudicó la segunda mitad y encontrar primero una ventaja estadística del setup base. Se posponen nuevas mejoras de trailing y salidas. El feature condicional de eficiencia de tendencia no se incorpora a las nuevas políticas.

Los resultados anteriores permanecen documentados. No se descartan fechas desfavorables ni se vuelve a llamar independiente a un periodo ya inspeccionado. La referencia de salida vuelve a ser RR 1:1, con el mismo stop estructural y costes supuestos.

## Comparación registrada antes de ejecutar

Se compara la referencia con tres reglas de entrada por separado:

1. Vela que abre dentro del rango OR y cierra fuera.
2. Delta agresor de la vela alineado con la entrada, sin buscar una magnitud óptima.
3. Al menos una fila completa de imbalance alineado fuera del OR, conservando el SL detrás del más lejano de todos los alineados.

En cada política, si una vela no cumple se espera la siguiente señal válida hasta las 09:40. No se limita el estudio a filtrar las 82 operaciones anteriores, porque una entrada posterior podría cumplir la regla. No se combinan filtros ni se prueban nuevos RR o distancias de trailing.

Se consultó al usuario la interpretación exacta de «romper con cuerpo». Mientras responde, la referencia mantiene la interpretación previa de cierre fuera, aunque el open ya esté fuera. Si exige abrir dentro, se documentará como corrección de fidelidad de su setup, no como una mejora seleccionada por beneficio.

## Antecedentes y alcance

La condición de delta/agresor pertenece a una familia ya explorada en scripts anteriores; su reevaluación no es una hipótesis independiente nueva. La auditoría no encontró condiciones equivalentes explícitas de open dentro del OR ni fila completa fuera en los scripts revisados. Las búsquedas previas de cuerpo fuerte, cercanía de fila al nivel o primera ruptura son diferentes, aunque relacionadas. Todo el periodo 2026 continúa siendo exploratorio.

La comparación conservará las 150 sesiones, días sin entrada, candidatos y rechazos. Se informará rentabilidad neta en ticks y R, incertidumbre, meses, mitades y concentración, incluyendo resultados negativos. Una media positiva aislada no se llamará edge validado. No se comprarán más datos antes de tener un candidato prometedor.

Plan completo: `C:/Users/k_99_/Documents/ChatGPT/research_edge/CORE_ENTRY_RESEARCH_PLAN.md`.

Estado: comparación ejecutada y auditada. Los resultados completos están en [Comparación de entradas con RR 1:1](2026-10-12_09_COMPARACION_ENTRADAS_RR1.md). La condición de open dentro del OR produce una pista positiva en ticks, todavía sin evidencia suficiente de edge; las otras condiciones siguen negativas.
