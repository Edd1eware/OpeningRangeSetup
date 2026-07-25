# Auditoría V4 — veredicto

## 1. ¿Bug conceptual en orientación/dwell?

**No.** Orientación s=+1 BUY/−1 SELL sobre burst_side: correcta (el target es el destino del burst, no el lado de la estrategia). Dwell stepwise por último T físico con dwell cero intratimestamp: implementación fiel al texto congelado de rondas 004–007. Los números son internamente coherentes: 33/98 alcanzan push14, 3 alcanzan ext33, y las exigencias compuestas (excursión P90 + permanencia continua 0.45 s; o push + retorno a −14 bajo p0 = oscilación de 28 ticks en 5 s) explican el colapso sin necesidad de bug.

## 2. La inconsistencia bilateral/unilateral ya no salva nada

Mi objeción previa (calibrar con max|d| bilateral, aplicar D_max unilateral) sigue siendo cierta como defecto de especificación, pero **el barrido ±15% ya acota su corrección**: el factor de inflación del máximo de dos orientaciones correlacionadas es ≤ ~1.3, dentro del rango escaneado. A escala 0.85 el resultado es A=3/B=1/C=94 — prevalencia un orden de magnitud bajo el gate de 15%, y Jaccard 0 contra base. La corrección de coherencia caería en esa misma región. **No hay versión defendible de estos umbrales que produzca taxonomía viable.** Recalibrar más allá sería tunear los 98: prohibido.

## 3. Conclusión protocolaria: DETENER

Regla de paro congelada #2 activada legítimamente: la taxonomía de primera secuencia a 5 s **no existe como fenómeno** con prevalencia mínima. Resultado científico negativo válido, no fracaso de proceso: las ventanas post-decisión muestran movilidad comparable o inferior al baseline pre-apertura (34% alcanza unilateral lo que 50% de ventanas aleatorias alcanza bilateral). Eso dice algo importante: **en los 5 s posteriores a `t_decision`, el precio aún no resuelve nada** — consistente con los fracasos previos de MATRIX/MBO8 sobre la misma frontera temporal.

Alto al modelado predictivo sobre esta etiqueta. Sin rescates, sin re-horizontes post hoc (mover 5 s→30 s ahora sería elección informada por el fallo).

## 4. Siguiente paso científico

Cerrar esta línea con reporte del resultado negativo y las dos lecciones para el registro: (a) el retorno completo a −T_ret bajo p0 hace A casi imposible por construcción en 5 s — defecto de especificación a no repetir; (b) la inmovilidad post-decisión sugiere que la información discriminante, si existe, está en la **mecánica del libro**, no en el precio temprano.

Continuación única posible: **preregistro nuevo de etiqueta mecánica FMD §4** (reposición de cola vs dominancia de cancelación en el nivel atacado), línea nueva que requiere decisión y autorización del usuario — la revisión única de esta línea está consumida. Los datos ya pagados (MBO predecesión 100 sesiones + 98 ventanas outcome) son reutilizables allí sin descarga nueva para ingeniería inicial.

`DETENER_TAXONOMIA_5S — RESULTADO_NEGATIVO_VALIDO`
