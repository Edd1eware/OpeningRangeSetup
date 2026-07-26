# Preregistro UPBIAS-V2 — caracterización + validación forward del sesgo UP

Fecha: 2026-07-25
Autor: Claude Fable
Estado: **CONGELADO ANTES DE EJECUTAR**

## 0. El problema que este preregistro NO puede resolver

El sesgo UP se observó full-sample y ya se midió en el holdout 2024-26
(EV neto +2.38). **Cualquier test adicional sobre esos mismos 698 días NO es
confirmatorio**, por bueno que sea el protocolo: ya conozco la respuesta.

Por eso este documento separa dos cosas que suelen confundirse:

| Parte | Qué hace | Qué NO hace |
|---|---|---|
| **A — Caracterización** | Mide si el sesgo es frágil o robusto | **No valida.** No puede promover el edge |
| **B — Validación forward** | Decide de verdad, con datos que aún no existen | Requiere esperar |

Si la Parte A sale mal, se descarta sin gastar meses. Si sale bien, **no está
validado**: solo se gana el derecho a correr la Parte B.

---

## PARTE A — Caracterización sobre datos existentes (NO validatoria)

Universo: 698 sesiones `orb_features_labels_1s.csv` + `orb_trailing_pnl.csv`,
2022-04-25 → 2026-07-01. Comisión 2.0 ticks. Regla: `direction == "UP"`,
cero parámetros libres.

### A1 — ¿El sesgo sobrevive a la elección de gestión?

Se evalúan las **8** columnas de PnL existentes, todas, sin escoger:
`trail_50_20_40`, `trail_50_30_50`, `trail_50_20_30`, `trail_40_20_40`,
`trail_30_20_30`, `trail_60_30_50`, `fixed_60_60`, `fixed_60_30`.

```text
A1-C1: EV_neto(UP) > EV_neto(DOWN)  en >= 7 de 8 configuraciones
A1-C2: EV_neto(UP) > 0              en >= 6 de 8 configuraciones
```

Propósito: si el sesgo solo existe con un trailing concreto, es artefacto de esa
gestión. Si aparece en casi todas, es propiedad del mercado. **No se elige la
mejor configuración**: se cuenta cuántas cumplen.

### A2 — ¿Se sostiene a lo largo del tiempo o vive de un tramo?

Ventanas de test consecutivas de 6 meses sobre todo el periodo (≈8 ventanas).
Sin ajuste de nada (no hay parámetros).

```text
A2-C1: EV_neto(UP) > 0 en >= 60% de las ventanas
A2-C2: ninguna ventana individual concentra > 50% del PnL total
```

### A3 — Sizing dinámico sobre base POSITIVA (la pregunta que H4 nunca respondió)

Monte Carlo 10,000 cuentas, reglas Lucid 150k (target $9,000, MaxLoss $4,500,
DLL soft $2,700), base 4 contratos, pool = trades UP de FRESH 2024-26.

```text
A3-C1: payouts esperados > 0.5
A3-C2: P(quema sin payout) < 50%
A3-C3: dinámico > fijo
```

### Criterio de la Parte A

PASS = **todos** los criterios de A1, A2 y A3. Un solo fallo → el sesgo UP se
considera frágil y **no se pasa a la Parte B**. No se relaja nada.

PASS **no significa edge validado**. Significa: "no es frágil de forma obvia,
merece gastarse un forward".

---

## PARTE B — Validación forward (hasheada ahora, decidida después)

Se congela **ahora** para que no pueda ajustarse cuando lleguen los datos.

```text
regla       = OR breakout, SOLO direction == UP, trailing 50/20/40
comision    = 2.0 ticks
inicio      = primera sesión posterior a 2026-07-01 con dato disponible
n minimo    = 60 trades UP
```

Gate de validación forward (los cuatro):

| # | Criterio | Umbral |
|---|---|---|
| B1 | EV neto | > 0 |
| B2 | Profit Factor | > 1.15 |
| B3 | Trimestres con EV neto > 0 | ≥ 2 de 3 |
| B4 | Frecuencia | ≥ 4 trades/mes |

La configuración de gestión queda fijada AHORA en `trail_50_20_40` (la ya
congelada). **A1 es diagnóstico, no selección**: aunque otra configuración salga
mejor en A1, la forward usa `trail_50_20_40`. Cambiarla sería fitting.

---

## Prohibiciones

No se barren umbrales. No se elige configuración por resultado. No se excluye
ningún año, ventana ni trimestre. No se añaden condiciones al filtro (sigue
siendo solo `direction == UP`). No se repite la Parte A con otra definición de
ventana. Si A falla, se cierra y se documenta.

`INFORMATION_STATUS=UPBIAS_V2_PREREGISTERED_NO_RESULT`
