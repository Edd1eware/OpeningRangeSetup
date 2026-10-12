# Avances de la búsqueda del edge

Objetivo: validar estadísticamente el setup de apertura del usuario y comparar LucidPro 50K y 100K sobre una estrategia reproducible y neta de costes.

## Registro del 12 de octubre de 2026

1. [Objetivo, reglas confirmadas y datos disponibles](2026-10-12_01_OBJETIVO_Y_REGLAS_CONFIRMADAS.md).
2. [Caso visual de la entrada del usuario](2026-10-12_02_CASO_VISUAL_ENTRADA.md).
3. [Auditoría de los resultados heredados](2026-10-12_03_AUDITORIA_RESULTADOS_HEREDADOS.md).
4. [Control independiente del footprint](2026-10-12_04_CONTROL_FOOTPRINT_CORREGIDO.md).
5. [Replay corregido del setup RR1:1, curva y diagnóstico del riesgo](2026-10-12_05_REPLAY_CORREGIDO_RR_1_1.md).
6. [Comparación de RR fijos sobre las mismas entradas](2026-10-12_06_COMPARACION_RR_FIJOS.md).
7. [Feature causal de tendencia y trailing](2026-10-12_07_FEATURE_TENDENCIA_Y_TRAILING.md).
8. [Prioridad al edge de entrada y nueva comparación acotada](2026-10-12_08_PRIORIDAD_EDGE_DE_ENTRADA.md).
9. [Resultados de entradas con RR 1:1: pista del cuerpo desde dentro del OR](2026-10-12_09_COMPARACION_ENTRADAS_RR1.md).
10. [Tabla WR, PF y trades del periodo DST disponible; aclaración de apertura fuera del OR](2026-10-12_10_TABLA_DST_Y_REGLA_DE_APERTURA.md).
11. [Objetivo de automatización y reproducción corregida del cuerpo a favor](2026-10-12_11_REPRODUCCION_DEL_CUERPO_Y_OBJETIVO.md).
12. [Paridad ATAS / Databento y base de datos por vela y precio](2026-10-12_12_PARIDAD_ATAS_DATABENTO_Y_BASE_DE_DATOS.md).
13. [Setup calibrado y búsqueda del edge:78 trades de referencia y35 del control](2026-10-12_13_SETUP_CALIBRADO_Y_BUSQUEDA_DEL_EDGE.md).

El control del punto 4 utiliza un stop fijo para aislar información direccional. No es el replay completo del SL detrás del imbalance.

El código nuevo y sus salidas se guardan en `C:/Users/k_99_/Documents/ChatGPT/research_edge`. Los datos originales se conservan en `C:/Users/k_99_/Desktop/codding/MBP_MBO`.

Las 150 sesiones de 2026 ya se habían usado para explorar hipótesis. Sus resultados actuales son exploratorios; cualquier candidato necesita una validación posterior independiente.

El trailing probado reduce la pérdida media respecto al 1:1, pero sigue negativo y su mejora se concentra en junio. La selección por el feature no mejoró la segunda mitad. No se compraron más datos y todavía no hay un edge robusto con estas reglas codificadas.

Por indicación del usuario, las mejoras de salida y el feature condicional quedan pospuestos. La investigación actual vuelve al edge de entrada con RR 1:1.

La comparación del punto 9 encontró una pista positiva en ticks al exigir open dentro del OR: 39 trades, +295.8 ticks con un NQ fijo. El resultado en R sigue ligeramente negativo y los intervalos incluyen cero. Todavía no es un edge validado ni un candidato que cumpla los criterios fijados para pagar más datos.

Actualización más reciente: tras el cotejo del punto12, el usuario pidió retomar señales y el edge. El punto13 documenta la referencia calibrada:78trades,WR42.31%,PF neto1NQ0.602. El único control de apertura dentro obtiene35trades,WR54.29%,PF1NQ1.382 yPF_R0.959. Es una pista exploratoria; no hay edge confirmado. Ambas corridas y todos sus cruces están auditados. La comparación C#/ATAS actual sigue pendiente. Se mantiene navegador → C# y ATAS → indicador de confirmación manual; no se fuerza60% ajustando el histórico ni se compran datos aún.
