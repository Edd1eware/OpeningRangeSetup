# Resultado conjunto Codex + Claude/Fable — Liquidity Burst V4/V5

Fecha: 2026-07-24

## Veredicto actual

**NO SOY CAPAZ DE SEPARAR UNA ABSORCIÓN DE UN BREAKOUT LIMPIO.**

No existe todavía evidencia predictiva causal y estable. No se entrenó ningún
modelo porque las taxonomías independientes no superaron sus puertas.

## Adquisición e integridad

- Outcome MBO: 98/98 sesiones discovery 2022–2024.
- 2025–2026 permanece cerrado.
- Solicitud uniforme por `ts_recv`:
  `[t_decision-100 ms, t_decision+5 s+100 ms)`.
- Etiqueta por `ts_event`:
  `[t_decision, t_decision+5 s)`.
- Padding excluido de etiquetas y predictores.
- Match Events usados cerrados con `F_LAST`.
- `F_MAYBE_BAD_BOOK=0`.
- Retrocesos de secuencia: 0.
- Redescarga homogénea de las dos primeras sesiones:
  intervalo común idéntico por SHA-256; 0 eventos tardíos elegibles.
- Peor coste total proyectado: USD 5.922336065770.
- Tope autorizado: USD 5.93.
- Reserva de disco de 10 GiB: PASS.

## V4 — fallo de instrumento

Umbrales:

- push/retorno: 14 ticks;
- extensión: 33 ticks;
- dwell B: 0.4535600705 s;
- dwell A: 0.671530336 s.

Resultado:

| Clase | Sesiones |
|---|---:|
| A absorción limpia | 0 |
| B breakout limpio | 0 |
| C variable | 98 |

V4 mezclaba calibración bilateral `max|d|` con aplicación unilateral y no
alineaba la calibración del dwell A con la secuencia exigida.

## V5 — corrección prerregistrada y resultado

Prerregistro SHA-256:
`22b486cc7e310f5117f0a932817695d3c702a69ec975162927ca90fc8e9070a8`

Calibración ciega:

- 3,533 pseudoventanas físicas;
- 7,066 observaciones orientadas;
- `T_push=7` ticks;
- `T_ext=15` ticks;
- `T_ret=7` ticks;
- `dwB=0.648899664 s`;
- `dwA=0.568278243 s`;
- soporte secuencia B=1,824;
- soporte secuencia A=1,049;
- todas las puertas de calibración: PASS.

Aplicación única:

| Clase | n | Prevalencia |
|---|---:|---:|
| A absorción limpia | 12 | 12.24% |
| B breakout limpio | 9 | 9.18% |
| C variable | 77 | 78.57% |

Estabilidad:

| Clase | Jaccard escala 0.85 | Jaccard escala 1.15 | Gate |
|---|---:|---:|---|
| A | 0.923 | 0.417 | FAIL |
| B | 0.563 | 0.667 | FAIL |

Ambas clases aparecen en cada año y en BUY/SELL, y la mezcla limpia es
57.1%/42.9%. Sin embargo, A y B están debajo del mínimo 15% y fallan estabilidad
Jaccard 0.70. Por la regla congelada se cierra la taxonomía de precio 5 s sin
V6, sin clasificador y sin comprar 150 sesiones.

## Aclaración del precio ATAS

`matrix_mbo_joined_dataset.burst_price` corresponde al precio de
entrada/ejecución, no necesariamente al último trade Databento en `p0`.
`Entry_price-p0` se conserva como diagnóstico de ejecución/slippage y no como
prueba de desincronización. La causalidad se audita mediante timestamps,
Match Events, `F_LAST`, secuencia y precedencia física.

## Qué falta

Falta una etiqueta outcome mecánica estable que represente el estado del libro,
no una clasificación basada en la resolución temprana del precio.

## Siguiente paso conjunto propuesto

Piloto sin descarga adicional usando los datos ya pagados:

1. empalmar snapshot MBO predecisión con flujo MBO postdecisión;
2. verificar continuidad de secuencia en el solape de 100 ms;
3. definir absorción por supervivencia y reposición de la cola atacada bajo
   fills;
4. definir breakout por depleción mediante fills/cancelaciones, baja
   reposición y cesión del nivel;
5. calibrar cuantiles en pseudoventanas predecisión;
6. congelar y hashear la etiqueta antes de aplicarla;
7. aplicar una sola vez a 98 sesiones con gates de prevalencia, estabilidad,
   año y lado;
8. sólo si pasa, solicitar autorización para una muestra confirmatoria nueva.

Abrir esta línea nueva requiere autorización expresa del usuario. El piloto
inicial cuesta USD 0 en datos.
