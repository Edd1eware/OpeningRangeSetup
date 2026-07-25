# Convergencia final V4 — Codex + Claude/Fable

Fecha: 2026-07-24  
Estado: **CONGELADO ANTES DE PRODUCIR UMBRALES O ETIQUETAS**

## Pregunta

¿Las features estrictamente anteriores a `t_decision` permiten anticipar y
separar una **ABSORCIÓN LIMPIA** de un **BREAKOUT LIMPIO** después de un
Liquidity Burst?

Las etiquetas antiguas derivadas de MFE/MAE/TP/SL/resultado quedan retiradas
para esta pregunta por ser circulares.

## Población

- Discovery: 98 sesiones 2022–2024 con MBO snapshot completo y contrato
  correcto.
- Excluidas por rollover incorrecto en el predictor MBO existente:
  `2022-06-13` y `2023-06-13`.
- 2025–2026 permanece completamente sellado.
- Una observación por `BurstId`.

## Semántica de tape MBO

Los registros se consumen en orden físico DBN con un `record_ordinal`
reproducible.

- Un Match Event comienza después del `F_LAST` anterior y termina en el
  siguiente `F_LAST` del instrumento.
- Puede contener múltiples `sequence`, lados y precios.
- Todo Match Event que aporte un T usado debe cerrar con `F_LAST` y tener un
  único `ts_event`.
- Todos los estados internos del mismo Match Event tienen dwell cero.
- El último T físico del Match Event fija last-sale hasta el siguiente Match
  Event con T.
- No se colapsan prints diferentes.
- `INTEGRITY_FAIL` si un evento usado no cierra, mezcla timestamps, el ordinal
  no es único, existe `F_MAYBE_BAD_BOOK`, hay retroceso incremental de
  sequence, o una doble decodificación produce distinto SHA-256 de
  `ts_event|sequence|record_ordinal|side|price|size|flags`.

La misma convención se usa en calibración y etiquetado.

## Calibración ciega y causal

Datos: trades explícitos contenidos en los MBO snapshot ya descargados.

- Ventanas físicas de 5 s, no solapadas.
- Grid determinista iniciado a `08:29:00 America/Chicago`.
- Fin exclusivo: `t_decision-60 s`.
- Mínimo: 10 ventanas físicas por sesión y 1,000 agregadas.
- Cada trayectoria se evalúa con `s=+1` y `s=-1`; el soporte se cuenta una sola
  vez por ventana física.
- `tick=0.25`.
- `p0`: último Match Event con T anterior al inicio de la ventana.
- `d(t)=s*(p_last(t)-p0)/tick`, trayectoria escalonada por Match Event.

Umbrales:

```text
T_push = P50 de max|d| por pseudo-ventana
T_ext  = P90 de max|d| por pseudo-ventana
T_ret  = T_push
T_dwB  = P50 del dwell continuo tras cruces de +T_ext
T_dwA  = P50 del dwell continuo tras cruces de -T_ret
```

Para dwell se usan sólo pseudo-ventanas que cruzan el umbral. Se exigen al
menos 100 ventanas físicas con cruce para cada estimación. Los umbrales de
precio y dwell deben ser positivos.

Diagnóstico no vinculante: publicar percentiles con y sin 08:29–08:30 CT. Sólo
los umbrales del intervalo completo son operativos.

## Etiqueta independiente de cinco segundos

Para cada burst real:

```text
W = [t_decision, t_decision+5 s)
s = +1 para BUY, -1 para SELL
p0 = último T-event con ts_event < t_decision dentro de los 100 ms previos
d(t) = s*(p_last(t)-p0)/tick
```

Secuencias:

```text
tau_push = primer cruce de d >= T_push
tau_B    = primer cruce de d >= T_ext que completa dwell continuo >= T_dwB
tau_A    = primer cruce posterior a tau_push de d <= -T_ret que completa
           dwell continuo >= T_dwA
```

- `B_BREAKOUT_LIMPIO`: `tau_B` existe y ocurre antes de `tau_A`.
- `A_ABSORCION_LIMPIA`: `tau_A` existe y ocurre antes de `tau_B`.
- `C_VARIABLE`: el resto, incluido plano, secuencia incompleta o ambigua.

Un intento de dwell muere al abandonar el umbral; un cruce posterior puede
volver a intentarlo. Si W termina antes de completar dwell, no se consume la
secuencia.

## Integridad de unión

- Se requiere p0 y al menos un T-event postdecisión.
- Contrato correcto por sesión.
- Discrepancia ATAS–Databento de p0 no mayor a 2 ticks.
- Ningún evento futuro entra como predictor.

## Gates de taxonomía

- Sensibilidad con umbrales simultáneamente a `±15%`: Jaccard A y B >= 0.70.
- Al menos 15 A y 15 B.
- Ninguna clase limpia supera 70% de A+B.
- A y B presentes en 2022, 2023 y 2024.
- A y B presentes en BUY y SELL.
- C se reporta y nunca se fuerza.

## Contraste predictivo

Predictores congelados y estrictamente predecisión:

1. `MATRIX_TRANSITIONS`;
2. `MATRIX_SEQUENCES`;
3. `MBO_SNAPSHOT_8`;
4. combinaciones preregistradas comparables.

Evaluación:

- Leave-One-Year-Out 2022/2023/2024.
- Balanced accuracy y ROC AUC fuera de muestra.
- Bootstrap diario estratificado 10,000.
- Permutación dentro de año y lado 10,000.
- Resultados separados por año y BUY/SELL.

Puerta para afirmar capacidad:

- integridad y taxonomía PASS;
- límite inferior del IC bootstrap de BA LOYO > 0.50;
- permutación `p <= 0.05`;
- BA > 0.50 en cada año y en BUY y SELL;
- ningún acceso a MFE, MAE, TP, SL, PnL o resultado terminal.

Si falla cualquiera, el mensaje será
`NO SOY CAPAZ DE SEPARAR...` y especificará la puerta fallida.

## Secuencia operativa

1. congelar V4 y SHA-256;
2. calibrar con MBO ya pagado;
3. si calibración PASS, cotizar trades
   `[t_decision-100 ms,t_decision+5 s)` para 98 sesiones;
4. no descargar si rebasa autorización o reserva de 10 GiB;
5. etiquetar y evaluar una sola vez;
6. documentar y enviar informe final a Telegram.

Después del hash no se modifican etiquetas, umbrales, horizonte ni gates.
