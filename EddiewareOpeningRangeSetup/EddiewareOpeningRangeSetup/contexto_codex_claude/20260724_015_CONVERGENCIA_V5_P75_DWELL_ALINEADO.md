# Convergencia Codex + Claude/Fable — V5 P75 y dwell alineado

Fecha: 2026-07-24  
Estado: **CONVERGENCIA FINAL ANTES DE CALCULAR V5**

## Resultado V4

V4 queda declarado como fallo de instrumento:

- integridad MBO no-precio: 98/98;
- `A_ABSORCION_LIMPIA`: 0;
- `B_BREAKOUT_LIMPIO`: 0;
- `C_VARIABLE`: 98;
- escala 0.85: A=3, B=1, C=94;
- escala 1.15: A=0, B=0, C=98.

No se entrena ningún modelo con V4. Las 98 ventanas V4 se conservan sólo como
diagnóstico y jamás como evidencia predictiva.

## Fallos de instrumento encontrados

1. V4 calibró `T_ext` con `P90(max|d|)` bilateral y lo aplicó después a una
   excursión unilateral orientada.
2. V4 calibró el dwell adverso sin exigir previamente la secuencia `push`,
   pero en aplicación A sí exigía `push -> retorno`.
3. `burst_price`/`Entry_price` no representa necesariamente el último trade
   del tape en `p0`. Su diferencia contra `p0` mide ejecución/slippage, no
   sincronización de relojes, y no puede ser gate de causalidad.

## Fórmulas V5 congeladas

Cada pseudoventana física de cinco segundos genera exactamente dos
observaciones orientadas:

```text
s: d(t) = +(p_last(t)-p0)/0.25
-s: d(t) = -(p_last(t)-p0)/0.25
```

Para cada observación orientada:

```text
positive_excursion = max(0, max_t d(t))
adverse_excursion  = max(0, max_t -d(t))
```

Umbrales:

```text
T_push = P50 de positive_excursion orientada
T_ext  = P75 de positive_excursion orientada
T_ret  = P50 de adverse_excursion orientada
```

P75 se eligió antes del cálculo porque es el cuartil superior mecánico y hace
alcanzable, pero no garantiza, el gate de prevalencia. Con dwell mediano, la
prevalencia de referencia esperada ronda 12.5%; la población condicionada por
Liquidity Burst debe aportar elevación real para superar 15%.

## Dwell secuencia-alineado

La calibración debe medir exactamente la secuencia que se aplicará:

- B: sólo observaciones con `push -> cruce +T_ext`;
- A: sólo observaciones con `push -> cruce -T_ret`;
- el dwell es el máximo intervalo continuo calificante posterior a la
  precondición de secuencia;
- `dwB` y `dwA` son las medianas de esos máximos;
- mínimo 100 observaciones orientadas calificantes por rama;
- estados del mismo `ts_event` tienen dwell cero;
- un intento muere al salir del umbral y un cruce posterior puede reiniciarlo.

## Etiqueta V5

Se conserva sin cambios:

```text
W = [t_decision, t_decision+5 s)
p0 = último Match Event T completo en los 100 ms previos
```

- B: primera secuencia `push -> +T_ext` que completa `dwB`.
- A: primera secuencia `push -> -T_ret` que completa `dwA`.
- Gana la primera secuencia completada.
- Empate, ausencia o ambigüedad: C.

## Piloto V5 sobre las 98 ya observadas

La aplicación será única y sólo responde si el instrumento produce clases.
No constituye evidencia predictiva.

Gates:

- integridad causal 98/98;
- A >= 15% y B >= 15%;
- ninguna clase limpia >70% de A+B;
- A y B en 2022, 2023 y 2024;
- A y B en BUY y SELL;
- Jaccard A y B >=0.70 bajo umbrales simultáneos ±15%.

Si A o B queda bajo 15%, la taxonomía de precio de cinco segundos se cierra
definitivamente, sin V6.

## Confirmación posterior, sólo si el piloto pasa

- 150 sesiones 2022–2024 completamente ajenas a las 100 discovery;
- selección mecánica no condicionada por familia o resultado;
- mínimo 20 eventos por clase y prevalencia 15–70%;
- una sola evaluación predictiva congelada;
- 2025–2026 permanece cerrado hasta validación final autorizada;
- MFE, MAE, TP, SL, PnL y resultado terminal permanecen prohibidos.

## Veredicto convergente

`CONVERGENCIA_V5_P75_DWELL_ALINEADO`
