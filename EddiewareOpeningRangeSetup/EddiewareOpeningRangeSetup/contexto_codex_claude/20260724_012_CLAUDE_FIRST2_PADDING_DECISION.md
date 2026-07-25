# Veredicto: **B** — redescargar solo las 2 ventanas con padding +100 ms

## Razonamiento

**Causalidad/integridad.** V4 congeló el principio: verificar completitud, nunca asumirla. Opción A es exactamente asumirla — "riesgo material despreciable" es la misma extrapolación empírica que rechazamos en ronda 008 al elegir `mbo` sobre `trades`. Que todos los T presentes cierren `F_LAST` no prueba ausencia de un evento con `ts_event < decision+5s` y `ts_recv >= decision+5s` omitido por el filtro de transporte: es un faltante indetectable desde el propio archivo. Aceptarlo crea dos ventanas cuya etiqueta descansa en una suposición que las otras 96 no necesitan.

**Reproducibilidad.** A deja 2/98 con regla de adquisición distinta y una limitación documentada a perpetuidad; cualquier auditoría futura debe cargar la excepción. B restaura 98/98 homogéneas bajo una sola regla: solicitud por `ts_recv` con padding, etiqueta por `ts_event`. C es lo peor: mover el horizonte congelado de 5 s a 4.9 s tras conocer el problema es un cambio post hoc del endpoint — precisamente lo que el preregistro existe para impedir, y consumiría credibilidad de todo lo convergido.

**Costo.** ~USD 0.11 (2 × ~0.055). Eliminar una asimetría estructural por once centavos no admite discusión; el costo de A no es cero — es una nota al pie permanente en la validez del diseño.

**Bonus diagnóstico gratis.** Las dos ventanas viejas van a cuarentena (no se borran). Tras la redescarga, comparar evento a evento (`ts_event|sequence|record_ordinal|side|price|size`) el rango común: si las versiones con y sin padding son idénticas en `[decision, decision+5s)`, queda demostrado empíricamente que no hubo truncamiento — la limitación se cierra con evidencia, no con supuesto. Si difieren, B era imprescindible y A habría contaminado etiquetas.

## Condiciones

1. Decisión tomada a ciegas: ninguna etiqueta observada antes de autorizar y ejecutar.
2. Autorización explícita del usuario por el costo exacto de las 2 ventanas antes del `get_range`.
3. Ventanas viejas a cuarentena con hash; comparación post-descarga reportada como calidad.
4. Etiqueta causal 5 s, umbrales, gates y checks (doble decodificación, reloj ≤2 ticks en `p0`, contrato por sesión) intactos.

`CONVERGENCIA_REDESCARGA_2_VENTANAS_PADDING`
